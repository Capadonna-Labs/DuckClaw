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
    force_next_alternates: frozenset[str] = frozenset()


@dataclass(frozen=True)
class AffirmFollowupDef:
    short_affirm_patterns: tuple[re.Pattern[str], ...]
    pending_action_patterns: tuple[str, ...]
    planned_task_guardrail: str
    force_tool_when_pending: str | None = None
    force_tool_alternates: frozenset[str] = frozenset()


@dataclass(frozen=True)
class ReplanRuleDef:
    when_intent: str
    require_tool: str
    unless_tools: frozenset[str]
    after_tools: frozenset[str] = frozenset()
    require_tool_alternates: frozenset[str] = frozenset()


@dataclass(frozen=True)
class ToolOrchestration:
    clock_anchor_tool: str | None
    clock_before_intents: frozenset[str]
    intents: dict[str, IntentDef]
    tool_chains: tuple[ToolChainDef, ...]
    affirm_followup: AffirmFollowupDef | None
    replan_rules: tuple[ReplanRuleDef, ...]
    sandbox_force_fallback_snippet: str | None = None


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
            if wi is None:
                wi = c.get("when_intents")
            if isinstance(wi, str):
                intent_set = frozenset({wi.strip()}) if wi.strip() else frozenset()
            elif isinstance(wi, list):
                intent_set = frozenset(str(x).strip() for x in wi if str(x).strip())
            else:
                intent_set = frozenset()
            fn = (str(c.get("force_next") or "").strip() or "")
            alt_raw = c.get("force_next_alternates")
            alt_set = frozenset(
                str(x).strip()
                for x in (alt_raw if isinstance(alt_raw, list) else [])
                if str(x).strip()
            )
            if after_set and intent_set and fn:
                chains.append(
                    ToolChainDef(
                        after_tools=after_set,
                        when_intents=intent_set,
                        force_next=fn,
                        force_next_alternates=alt_set,
                    )
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
        force_pending = (str(af.get("force_tool_when_pending") or "").strip() or None)
        alt_raw = af.get("force_tool_alternates")
        alt_set = frozenset(
            str(x).strip()
            for x in (alt_raw if isinstance(alt_raw, list) else [])
            if str(x).strip()
        )
        if sap and pap and guard:
            affirm = AffirmFollowupDef(
                short_affirm_patterns=sap,
                pending_action_patterns=pap,
                planned_task_guardrail=guard,
                force_tool_when_pending=force_pending,
                force_tool_alternates=alt_set,
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
                at = r.get("after_tools")
                at_set = frozenset(
                    str(x).strip() for x in (at if isinstance(at, list) else []) if str(x).strip()
                )
                alt_raw = r.get("require_tool_alternates")
                alt_set = frozenset(
                    str(x).strip()
                    for x in (alt_raw if isinstance(alt_raw, list) else [])
                    if str(x).strip()
                )
                if wi and rt:
                    replan_rules.append(
                        ReplanRuleDef(
                            when_intent=wi,
                            require_tool=rt,
                            unless_tools=ut_set,
                            after_tools=at_set,
                            require_tool_alternates=alt_set,
                        )
                    )

    fallback_snippet = (
        str(raw.get("sandbox_force_fallback_snippet") or "").strip() or None
    )

    if (
        not intents
        and not chains
        and not affirm
        and not replan_rules
        and not clock_tool
        and not fallback_snippet
    ):
        return None

    return ToolOrchestration(
        clock_anchor_tool=clock_tool,
        clock_before_intents=clock_before,
        intents=intents,
        tool_chains=tuple(chains),
        affirm_followup=affirm,
        replan_rules=tuple(replan_rules),
        sandbox_force_fallback_snippet=fallback_snippet,
    )


def parse_tool_orchestration_from_spec(spec: Any) -> ToolOrchestration | None:
    """Alias for callers that pass WorkerSpec."""
    return parse_tool_orchestration(spec)


def orchestration_intent_text(user_incoming: str | None, incoming: str | None) -> str:
    """
    Manifest intent matching text for worker turns.

    ``tool_surface_intent_text`` prefers the short user utterance; orchestration
    also needs the manager planned task (same signal as replan ``combined``).
    """
    user = (user_incoming or "").strip()
    inc = (incoming or "").strip()
    if user and inc and user != inc:
        return f"{user}\n{inc}"
    return user or inc


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


def _first_bindable_tool(
    candidates: list[str],
    tools_by_name: dict[str, Any],
    ran: set[str] | frozenset[str],
) -> str | None:
    """Return first candidate present in ``tools_by_name`` and not yet run."""
    for name in candidates:
        n = (name or "").strip()
        if n and n in tools_by_name and n not in ran:
            return n
    return None


def _tools_since(messages: list[Any], from_idx: int) -> list[str]:
    names: list[str] = []
    for m in messages[max(0, from_idx + 1) :]:
        if isinstance(m, ToolMessage):
            n = str(getattr(m, "name", "") or "").strip()
            if n:
                names.append(n)
    return names


def _chain_prereqs_met(
    prereqs: list[str],
    ran: set[str],
    tools_by_name: dict[str, Any],
) -> bool:
    """True when chain ``after_tools`` gate is satisfied for this bind surface."""
    if not prereqs:
        return False
    bindable = [p for p in prereqs if p in tools_by_name]
    if not bindable:
        # ponytail: prereq tool not registered → do not block force_next once turn started
        return bool(ran)
    return all(p in ran for p in bindable)


def _tool_called_since(messages: list[Any], from_idx: int, tool_name: str) -> bool:
    return tool_name in _tools_since(messages, from_idx)


def _messages_have_pending_actions(messages: list[Any], markers: tuple[str, ...]) -> bool:
    """True if any assistant message in history matches pending-action markers."""
    from langchain_core.messages import AIMessage

    for msg in reversed(messages or []):
        if not isinstance(msg, AIMessage):
            continue
        body = str(getattr(msg, "content", "") or "").strip()
        if body and _assistant_has_pending_actions(body, markers):
            return True
    return False


def _force_tool_on_affirm_pending(
    orch: ToolOrchestration,
    incoming: str,
    messages: list[Any],
    tools_by_name: dict[str, Any],
) -> str | None:
    """
    Manifest ``affirm_followup.force_tool_when_pending``: short affirm + pending assistant
    action → force named tool (worker declares tool id; framework stays domain-agnostic).
    """
    af = orch.affirm_followup
    pending_tool = (af.force_tool_when_pending or "").strip() if af else ""
    if not af or not pending_tool or not _is_short_affirm(incoming, af.short_affirm_patterns):
        return None
    lh = _last_human_index(messages)
    ran = set(_tools_since(messages, lh))
    candidates = [pending_tool, *list(af.force_tool_alternates or ())]
    forced = _first_bindable_tool(candidates, tools_by_name, ran)
    if not forced:
        return None
    if not _messages_have_pending_actions(messages, af.pending_action_patterns):
        return None
    return forced


def _force_replan_require_tool_after_prereqs(
    orch: ToolOrchestration,
    incoming: str,
    messages: list[Any],
    tools_by_name: dict[str, Any],
) -> str | None:
    """
    Manifest ``replan.rules[].after_tools``: once prereqs ran for ``when_intent``, force
    ``require_tool`` before the turn ends (same contract as ``tool_chains``, replan-shaped).
    """
    intent = match_intent(incoming, orch)
    if not intent:
        return None
    lh = _last_human_index(messages)
    ran = set(_tools_since(messages, lh))
    for rule in orch.replan_rules:
        if rule.when_intent != intent:
            continue
        required = (rule.require_tool or "").strip()
        if not required or required in ran:
            continue
        if rule.unless_tools and ran.intersection(rule.unless_tools):
            continue
        prereqs = list(rule.after_tools)
        if not prereqs or not all(tool in ran for tool in prereqs):
            continue
        candidates = [required, *list(rule.require_tool_alternates or ())]
        forced = _first_bindable_tool(candidates, tools_by_name, ran)
        if forced:
            return forced
    return None


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
    ran = set(_tools_since(messages, lh))
    if not ran:
        return None
    for chain in orch.tool_chains:
        if intent not in chain.when_intents:
            continue
        prereqs = list(chain.after_tools)
        if not _chain_prereqs_met(prereqs, ran, tools_by_name):
            continue
        candidates = [chain.force_next, *list(chain.force_next_alternates or ())]
        forced = _first_bindable_tool(candidates, tools_by_name, ran)
        if forced:
            return forced
    return None


def _force_replan_require_tool_when_unmet(
    orch: ToolOrchestration,
    incoming: str,
    messages: list[Any],
    tools_by_name: dict[str, Any],
) -> str | None:
    """
    Manifest ``replan.rules[]`` with no ``after_tools``: force ``require_tool``
    in-worker once the turn already invoked at least one tool.
    """
    intent = match_intent(incoming, orch)
    if not intent:
        return None
    lh = _last_human_index(messages)
    ran = set(_tools_since(messages, lh))
    if not ran:
        return None
    for rule in orch.replan_rules:
        if rule.when_intent != intent:
            continue
        if rule.after_tools:
            continue
        required = (rule.require_tool or "").strip()
        if not required or required in ran:
            continue
        if rule.unless_tools and ran.intersection(rule.unless_tools):
            continue
        candidates = [required, *list(rule.require_tool_alternates or ())]
        forced = _first_bindable_tool(candidates, tools_by_name, ran)
        if forced:
            return forced
    return None


def _sandbox_affirm_prereqs_met(
    orch: ToolOrchestration,
    incoming: str,
    pending_tool: str,
    messages: list[Any],
) -> bool:
    """
    Manifest ``tool_chains``: do not affirm-force sandbox until ``after_tools`` ran
    (e.g. ``read_sql`` before ``execute_sandbox_script``).
    """
    if pending_tool not in ("execute_sandbox_script", "run_sandbox"):
        return True
    intent = match_intent(incoming, orch)
    if not intent:
        return True
    lh = _last_human_index(messages)
    ran = set(_tools_since(messages, lh))
    for chain in orch.tool_chains:
        if intent not in chain.when_intents:
            continue
        candidates = {chain.force_next, *chain.force_next_alternates}
        if pending_tool not in candidates:
            continue
        prereqs = list(chain.after_tools)
        if prereqs and not all(tool in ran for tool in prereqs):
            return False
    return True


def _resolve_intent_force_first_tool(
    orch: ToolOrchestration,
    incoming: str,
    messages: list[Any],
    tools_by_name: dict[str, Any],
) -> str | None:
    """Clock anchor + manifest intent ``force_first_tool`` for the current turn."""
    lh = _last_human_index(messages)
    ran = _tools_since(messages, lh)
    last_msg = messages[-1] if messages else None
    already_tool = isinstance(last_msg, ToolMessage)

    intent = match_intent(incoming, orch)
    if not intent:
        anchor = orch.clock_anchor_tool
        text = (incoming or "").strip()
        if (
            anchor
            and anchor in tools_by_name
            and anchor not in ran
            and not already_tool
            and text
            and "[system_directive:" not in text.lower()
            and not orch.clock_before_intents
        ):
            return anchor
        return None

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

    if already_tool and ft not in ran:
        return ft

    return None


def resolve_forced_tool(
    orch: ToolOrchestration,
    incoming: str,
    messages: list[Any],
    tools_by_name: dict[str, Any],
) -> str | None:
    """
    Priority: tool_chains > replan prereqs > clock/intent first tools > affirm follow-up.
    Returns tool name to force, or None.
    """
    chained = chain_after_tool(orch, incoming, messages, tools_by_name)
    if chained:
        return chained

    replan_after_prereqs = _force_replan_require_tool_after_prereqs(
        orch, incoming, messages, tools_by_name
    )
    if replan_after_prereqs:
        return replan_after_prereqs

    intent_first = _resolve_intent_force_first_tool(orch, incoming, messages, tools_by_name)
    if intent_first:
        return intent_first

    replan_immediate = _force_replan_require_tool_when_unmet(
        orch, incoming, messages, tools_by_name
    )
    if replan_immediate:
        return replan_immediate

    affirm_pending = _force_tool_on_affirm_pending(orch, incoming, messages, tools_by_name)
    if affirm_pending and _sandbox_affirm_prereqs_met(
        orch, incoming, affirm_pending, messages
    ):
        return affirm_pending

    return None


_EMAIL_INTENT_RE = re.compile(
    r"(?is)\b("
    r"correo|correos|e-mail|email|gmail|"
    r"bandeja\s+de\s+entrada|inbox|mail"
    r")\b|busca(r)?\s+(el\s+)?correo|"
    r"saca(r)?\s+insights\s+(del\s+)?correo"
)


def incoming_has_email_intent(text: str) -> bool:
    """True when the user asks to find/read/analyze email (Spanish/English cues)."""
    t = (text or "").strip()
    if not t or "[system_directive:" in t.lower():
        return False
    return bool(_EMAIL_INTENT_RE.search(t))


def incoming_has_email_screenshot(text: str) -> bool:
    """Email intent plus an attached screenshot (VLM ok or failed)."""
    t = text or ""
    if not incoming_has_email_intent(t):
        return False
    markers = (
        "[VLM_CONTEXT",
        "Contexto visual adjunto:",
        "[IMAGENES_ADJUNTAS]",
        "visión (VLM) no disponible",
        "visión (VLM) falló",
    )
    return any(m in t for m in markers)


def _vlm_unavailable(text: str) -> bool:
    t = text or ""
    return "visión (VLM) no disponible" in t or "visión (VLM) falló" in t


def _strip_vlm_markdown_noise(value: str) -> str:
    return re.sub(r"\*+", "", (value or "")).strip()


def _extract_vlm_visual_context(text: str) -> str:
    m = re.search(
        r"Contexto visual adjunto:\s*(.+?)(?:\n\[VLM_CONTEXT|\n\[IMAGENES|\n\[DIRECTIVA|\Z)",
        text or "",
        re.S | re.I,
    )
    return m.group(1).strip() if m else ""


def _gmail_from_clause(sender: str) -> str:
    val = _strip_vlm_markdown_noise(sender.strip().strip("\"'"))
    if not val:
        return ""
    m = re.search(r"[\w.+-]+@[\w.-]+\.\w+", val)
    if m:
        return f"from:{m.group(0)}"
    return f'from:"{val}"'


def build_gmail_targeted_query(text: str) -> str | None:
    """Build Gmail query from VLM/caption text; generic labels only."""
    combined = text or ""
    ctx = _extract_vlm_visual_context(combined)
    scan = ctx or combined
    if not ctx and not incoming_has_email_intent(combined):
        return None
    parts: list[str] = []

    for pat in (
        r'(?:remitente|de|from)[:\s]+["\']([^"\']+)["\']',
        r"(?:remitente|de|from)[:\s]+([^\n.]{2,120}?)(?:\n|$|\.)",
    ):
        m = re.search(pat, scan, re.I)
        if m:
            clause = _gmail_from_clause(m.group(1))
            if clause:
                parts.append(clause)
            break

    if not parts:
        m = re.search(r"[\w.+-]+@[\w.-]+\.\w+", scan)
        if m:
            parts.append(f"from:{m.group(0)}")

    for pat in (
        r'(?:asunto|subject)[:\s]+["\']([^"\']+)["\']',
        r"(?:asunto|subject)[:\s]+([^\n.]{2,200}?)(?:\n|$|\.)",
        r'asunto\s+["\']([^"\']+)["\']',
        r'(?:asunto|subject|t[ií]tulo)\s+(?:es|:)\s+["\']?([^"\'\n.]{5,200})',
    ):
        m = re.search(pat, scan, re.I)
        if m:
            subj = _strip_vlm_markdown_noise(m.group(1).strip().strip("\"'"))
            if subj:
                parts.append(f'subject:"{subj}"')
            break

    if parts:
        return " ".join(parts)
    return None


def format_email_directive(enriched_text: str) -> str:
    """Directive for single-email fetch via Gmail MCP."""
    q = build_gmail_targeted_query(enriched_text)
    has_vlm = "Contexto visual adjunto:" in (enriched_text or "")
    has_screenshot = incoming_has_email_screenshot(enriched_text)
    vlm_down = _vlm_unavailable(enriched_text)
    base = (
        "[DIRECTIVA_CORREO] Pide correo/email concreto. "
        "Usa Gmail MCP search_threads → get_message/get_thread. "
        "NO uses search_corpus (Workspace) ni extract_document_text en .png/.jpg. "
        "NO escanees toda la bandeja (prohibido is:inbox newer_than salvo que el usuario pida inbox)."
    )
    if has_vlm:
        if q:
            directive = (
                f"{base} Contexto visual identifica un correo: "
                f"search_threads con query `{q}` → get_message/get_thread del primer hit."
            )
        else:
            directive = (
                f"{base} Extrae remitente/asunto del Contexto visual adjunto y "
                "usa search_threads con from:/subject: acotados → get_message/get_thread."
            )
    elif has_screenshot and vlm_down:
        directive = (
            f"{base} Usuario adjuntó captura de UN correo pero VLM no está disponible. "
            "NO hagas resumen de bandeja. Pregunta remitente/asunto visible en la captura "
            "o espera a que visión funcione; luego search_threads acotado → get_message/get_thread."
        )
    elif has_screenshot:
        directive = (
            f"{base} Usuario adjuntó captura de UN correo. "
            "Usa remitente/asunto visibles → search_threads acotado → get_message/get_thread."
        )
    else:
        directive = (
            f"{base} Si no tienes remitente/asunto, pregunta al usuario o "
            "busca is:inbox newer_than:1d."
        )
    return directive


def try_targeted_email_fast_plan(
    incoming: str,
) -> tuple[str, list[str], str, str] | None:
    """Manager fast path: screenshot + email intent → one email, not inbox scan."""
    text = (incoming or "").strip()
    if not incoming_has_email_screenshot(text):
        return None
    q = build_gmail_targeted_query(text)
    vlm_down = _vlm_unavailable(text)
    title = "Buscar correo específico e insights"
    if vlm_down:
        tasks = [
            "NO escanees bandeja ni resumas inbox",
            "VLM no disponible: pide remitente/asunto del correo en la captura al usuario",
            "Con from:/subject: confirmados → search_threads acotado → get_message/get_thread → insights",
        ]
    elif q:
        tasks = [
            f"Gmail search_threads con query acotada `{q}`",
            "get_message o get_thread del primer resultado",
            "Extraer insights del contenido de ese correo",
        ]
    else:
        tasks = [
            "Gmail search_threads con from:/subject: del Contexto visual",
            "get_message o get_thread del primer resultado",
            "Extraer insights del contenido de ese correo",
        ]
    guard = (
        "[EMAIL_SCREENSHOT] Usuario adjuntó captura de UN correo. "
        "Prohibido resumen de bandeja/inbox. Solo ese correo.\n\n"
    )
    return title, tasks, guard + text, ""


def find_gmail_mcp_search_tool(tools_by_name: dict[str, Any]) -> str | None:
    """Resolve bound Gmail MCP ``search_threads`` tool name (connector id varies)."""
    candidates = [n for n in tools_by_name if n.endswith("__search_threads")]
    gmail_named = [n for n in candidates if "gmail" in n.lower()]
    if gmail_named:
        return gmail_named[0]
    if len(candidates) == 1:
        return candidates[0]
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
    *,
    user_incoming: str | None = None,
) -> tuple[bool, str]:
    intent = match_intent(incoming, orch)
    if not intent and user_incoming:
        intent = match_intent(user_incoming, orch)
    if not intent:
        return False, ""
    used = {str(t).strip() for t in (tools_used or []) if str(t).strip()}
    for rule in orch.replan_rules:
        if rule.when_intent != intent:
            continue
        satisfied_tools = {rule.require_tool, *rule.require_tool_alternates}
        if used.intersection(satisfied_tools):
            continue
        if rule.unless_tools and used.intersection(rule.unless_tools):
            continue
        return True, f"orchestration: intent={intent} missing tool={rule.require_tool}"
    return False, ""
