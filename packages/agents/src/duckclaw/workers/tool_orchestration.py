"""Manifest-driven tool forcing, chains, affirm follow-up, and replan rules."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langchain_core.messages import ToolMessage

from duckclaw.guardrails.loader import load_worker_guardrail


@dataclass(frozen=True)
class IntentDef:
    intent_id: str
    patterns: tuple[re.Pattern[str], ...]
    force_first_tool: str


@dataclass(frozen=True)
class ToolChainDef:
    after_tools: frozenset[str]
    when_intents: frozenset[str]
    force_next: str


@dataclass(frozen=True)
class AffirmFollowupDef:
    short_affirm_patterns: tuple[re.Pattern[str], ...]
    pending_action_patterns: tuple[str, ...]
    planned_task_guardrail: str


@dataclass(frozen=True)
class ReplanRuleDef:
    when_intent: str
    require_tool: str
    unless_tools: frozenset[str]


@dataclass(frozen=True)
class ToolOrchestration:
    clock_anchor_tool: str | None
    clock_before_intents: frozenset[str]
    intents: dict[str, IntentDef]
    tool_chains: tuple[ToolChainDef, ...]
    affirm_followup: AffirmFollowupDef | None
    replan_rules: tuple[ReplanRuleDef, ...]


def _compile_patterns(raw: Any) -> tuple[re.Pattern[str], ...]:
    out: list[re.Pattern[str]] = []
    if not isinstance(raw, list):
        return tuple()
    for item in raw:
        s = str(item or "").strip()
        if not s:
            continue
        try:
            out.append(re.compile(s))
        except re.error:
            continue
    return tuple(out)


def parse_tool_orchestration(spec: Any) -> ToolOrchestration | None:
    """Build orchestration from WorkerSpec.tool_orchestration_config."""
    raw = getattr(spec, "tool_orchestration_config", None)
    if not isinstance(raw, dict) or not raw:
        return None

    clock_tool: str | None = None
    clock_before: frozenset[str] = frozenset()
    ca = raw.get("clock_anchor")
    if isinstance(ca, dict):
        clock_tool = (str(ca.get("tool") or "").strip() or None)
        bi = ca.get("before_intents")
        if isinstance(bi, list):
            clock_before = frozenset(str(x).strip() for x in bi if str(x).strip())

    intents: dict[str, IntentDef] = {}
    raw_intents = raw.get("intents")
    if isinstance(raw_intents, dict):
        for iid, idef in raw_intents.items():
            if not isinstance(idef, dict):
                continue
            patterns = _compile_patterns(idef.get("patterns"))
            ft = (str(idef.get("force_first_tool") or "").strip() or "")
            if patterns and ft:
                intents[str(iid).strip()] = IntentDef(
                    intent_id=str(iid).strip(),
                    patterns=patterns,
                    force_first_tool=ft,
                )

    chains: list[ToolChainDef] = []
    raw_chains = raw.get("tool_chains")
    if isinstance(raw_chains, list):
        for c in raw_chains:
            if not isinstance(c, dict):
                continue
            after = c.get("after_tools")
            after_set = frozenset(
                str(x).strip() for x in (after if isinstance(after, list) else []) if str(x).strip()
            )
            wi = c.get("when_intent")
            if isinstance(wi, str):
                intent_set = frozenset({wi.strip()}) if wi.strip() else frozenset()
            elif isinstance(wi, list):
                intent_set = frozenset(str(x).strip() for x in wi if str(x).strip())
            else:
                intent_set = frozenset()
            fn = (str(c.get("force_next") or "").strip() or "")
            if after_set and intent_set and fn:
                chains.append(
                    ToolChainDef(after_tools=after_set, when_intents=intent_set, force_next=fn)
                )

    affirm: AffirmFollowupDef | None = None
    af = raw.get("affirm_followup")
    if isinstance(af, dict):
        sap = _compile_patterns(af.get("short_affirm_patterns"))
        pap_raw = af.get("pending_action_patterns")
        pap = tuple(
            str(x).strip().lower()
            for x in (pap_raw if isinstance(pap_raw, list) else [])
            if str(x).strip()
        )
        guard = (str(af.get("planned_task_guardrail") or "").strip() or "")
        if sap and pap and guard:
            affirm = AffirmFollowupDef(
                short_affirm_patterns=sap,
                pending_action_patterns=pap,
                planned_task_guardrail=guard,
            )

    replan_rules: list[ReplanRuleDef] = []
    repl = raw.get("replan")
    if isinstance(repl, dict):
        rules = repl.get("rules")
        if isinstance(rules, list):
            for r in rules:
                if not isinstance(r, dict):
                    continue
                wi = (str(r.get("when_intent") or "").strip() or "")
                rt = (str(r.get("require_tool") or "").strip() or "")
                ut = r.get("unless_tools")
                ut_set = frozenset(
                    str(x).strip() for x in (ut if isinstance(ut, list) else []) if str(x).strip()
                )
                if wi and rt:
                    replan_rules.append(
                        ReplanRuleDef(when_intent=wi, require_tool=rt, unless_tools=ut_set)
                    )

    if not intents and not chains and not affirm and not replan_rules and not clock_tool:
        return None

    return ToolOrchestration(
        clock_anchor_tool=clock_tool,
        clock_before_intents=clock_before,
        intents=intents,
        tool_chains=tuple(chains),
        affirm_followup=affirm,
        replan_rules=tuple(replan_rules),
    )


def parse_tool_orchestration_from_spec(spec: Any) -> ToolOrchestration | None:
    """Alias for callers that pass WorkerSpec."""
    return parse_tool_orchestration(spec)


def match_intent(incoming: str, orch: ToolOrchestration) -> str | None:
    text = (incoming or "").strip()
    if not text or "[system_directive:" in text.lower():
        return None
    for iid, idef in orch.intents.items():
        for pat in idef.patterns:
            if pat.search(text):
                return iid
    return None


def _last_human_index(messages: list[Any]) -> int:
    from langchain_core.messages import HumanMessage

    for i in range(len(messages) - 1, -1, -1):
        if isinstance(messages[i], HumanMessage):
            return i
    return max(0, len(messages) - 1)


def _tools_since(messages: list[Any], from_idx: int) -> list[str]:
    names: list[str] = []
    for m in messages[max(0, from_idx + 1) :]:
        if isinstance(m, ToolMessage):
            n = str(getattr(m, "name", "") or "").strip()
            if n:
                names.append(n)
    return names


def _tool_called_since(messages: list[Any], from_idx: int, tool_name: str) -> bool:
    return tool_name in _tools_since(messages, from_idx)


def chain_after_tool(
    orch: ToolOrchestration,
    incoming: str,
    messages: list[Any],
    tools_by_name: dict[str, Any],
) -> str | None:
    """If turn ran only chain prerequisites, return force_next tool."""
    intent = match_intent(incoming, orch)
    if not intent:
        return None
    lh = _last_human_index(messages)
    ran = _tools_since(messages, lh)
    if not ran:
        return None
    for chain in orch.tool_chains:
        if intent not in chain.when_intents:
            continue
        if ran != list(chain.after_tools):
            continue
        nxt = chain.force_next
        if nxt in tools_by_name and nxt not in ran:
            return nxt
    return None


def resolve_forced_tool(
    orch: ToolOrchestration,
    incoming: str,
    messages: list[Any],
    tools_by_name: dict[str, Any],
) -> str | None:
    """
    Priority: tool_chains (post gct) > clock_anchor > intent force_first_tool (may run after prior tools).
    Returns tool name to force, or None.
    """
    chained = chain_after_tool(orch, incoming, messages, tools_by_name)
    if chained:
        return chained

    intent = match_intent(incoming, orch)
    if not intent:
        return None

    lh = _last_human_index(messages)
    ran = _tools_since(messages, lh)
    last_msg = messages[-1] if messages else None
    already_tool = isinstance(last_msg, ToolMessage)

    if orch.clock_anchor_tool:
        anchor = orch.clock_anchor_tool
        if anchor in tools_by_name and anchor not in ran:
            if intent in orch.clock_before_intents or not orch.clock_before_intents:
                if not already_tool:
                    return anchor

    idef = orch.intents.get(intent)
    if not idef:
        return None
    ft = idef.force_first_tool
    if ft not in tools_by_name or ft in ran:
        return None

    if orch.clock_anchor_tool and orch.clock_anchor_tool not in ran:
        if intent in orch.clock_before_intents:
            return None

    if not already_tool:
        return ft

    # Encadenar intent tool tras tools previas del mismo turno (p. ej. read_sql → admin_sql).
    if already_tool and ft not in ran:
        return ft

    return None


def _iter_assistant_bodies_newest_first(history: Any) -> list[str]:
    out: list[str] = []
    if not history:
        return out
    for turn in reversed(list(history)):
        if not isinstance(turn, dict):
            continue
        r = str(turn.get("role") or turn.get("type") or "").lower()
        if r not in ("assistant", "ai", "model"):
            continue
        content = turn.get("content")
        if isinstance(content, str):
            body = content.strip()
        elif isinstance(content, list):
            parts = [
                str(p.get("text") or "")
                for p in content
                if isinstance(p, dict) and str(p.get("type") or "").lower() == "text"
            ]
            body = " ".join(x for x in parts if x).strip()
        else:
            body = str(content or "").strip()
        if body:
            out.append(body)
    return out


def _assistant_has_pending_actions(body: str, markers: tuple[str, ...]) -> bool:
    low = (body or "").strip().lower()
    if not low:
        return False
    return any(m in low for m in markers)


def _is_short_affirm(incoming: str, patterns: tuple[re.Pattern[str], ...]) -> bool:
    text = (incoming or "").strip()
    if not text:
        return False
    return any(p.search(text) for p in patterns)


def affirm_followup_planned_task(
    orch: ToolOrchestration,
    incoming: str,
    history: Any,
    worker_dir: Path,
) -> str | None:
    af = orch.affirm_followup
    if not af or not _is_short_affirm(incoming, af.short_affirm_patterns):
        return None
    for body in _iter_assistant_bodies_newest_first(history):
        if _assistant_has_pending_actions(body, af.pending_action_patterns):
            template = load_worker_guardrail(worker_dir, af.planned_task_guardrail)
            ctx = body[:4000]
            if "{context}" in template:
                return template.format(context=ctx)
            return f"{template}\n\nContexto del mensaje anterior del asistente:\n{ctx}"
    return None


def try_manifest_affirm_followup(
    incoming: str,
    history: Any,
    assigned_worker: str,
    spec: Any,
) -> tuple[str, list[str], str, str] | None:
    """
    Returns (plan_title, tasks, planned_task, worker_override) or None.
    """
    orch = parse_tool_orchestration(spec)
    if not orch:
        return None
    worker_dir = getattr(spec, "worker_dir", None)
    if not worker_dir:
        return None
    planned = affirm_followup_planned_task(orch, incoming, history, Path(worker_dir))
    if not planned:
        return None
    wid = (assigned_worker or getattr(spec, "logical_worker_id", "") or "").strip()
    return ("Confirmar acciones ledger", [planned], planned, wid)


def replan_rule_triggered(
    orch: ToolOrchestration,
    incoming: str,
    tools_used: list[str] | None,
) -> tuple[bool, str]:
    intent = match_intent(incoming, orch)
    if not intent:
        return False, ""
    used = {str(t).strip() for t in (tools_used or []) if str(t).strip()}
    for rule in orch.replan_rules:
        if rule.when_intent != intent:
            continue
        if rule.require_tool in used:
            continue
        if rule.unless_tools and used.intersection(rule.unless_tools):
            continue
        return True, f"orchestration: intent={intent} missing tool={rule.require_tool}"
    return False, ""
