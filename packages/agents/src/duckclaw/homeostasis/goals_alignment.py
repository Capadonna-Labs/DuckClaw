"""Evaluación transversal de alineación entre objetivos y contexto observable."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from typing import Any

from duckclaw.homeostasis.surprise import compute_surprise

GOALS_ALIGNMENT_REVIEW_PHRASE = "Revisión de alineación con /goals"

_NUDGE_OPENERS: tuple[str, ...] = (
    "Estoy revisando cómo va el contexto frente a tus objetivos de /crons.",
    "Detecté posibles desvíos respecto a lo que definiste en /crons; voy a analizarlo.",
    "Hice un chequeo rápido de alineación con tus metas — te comento en un momento.",
    "El estado actual no encaja del todo con uno o más objetivos; estoy cruzando datos.",
    "Revisión proactiva: comparo señales observables con tus /crons antes de proponerte pasos.",
    "Veo señales de desalineación con tus objetivos; preparo un análisis breve.",
    "Estoy contrastando lo observable ahora con las metas que guardaste en /crons.",
    "Pausa proactiva: analizo si el contexto actual cumple tus objetivos programados.",
)

_DEFAULT_MODE = (os.getenv("DUCKCLAW_GOALS_ALIGNMENT_DEFAULT_MODE") or "on_misalignment").strip().lower()
_DEFAULT_NOTIFY = (os.getenv("DUCKCLAW_GOALS_ALIGNMENT_DEFAULT_NOTIFY") or "both").strip().lower()
_DEFAULT_JITTER = float(os.getenv("DUCKCLAW_GOALS_ALIGNMENT_JITTER") or "0.15")


@dataclass
class AlignmentItem:
    belief_key: str
    title: str
    target: float | None
    observed: float | None
    threshold: float | None
    delta: float
    is_anomaly: bool
    has_data: bool
    comparison: str = "symmetric"
    goal_kind: str = "task"
    priority: int = 100


@dataclass
class AlignmentReport:
    aligned: bool
    misaligned_count: int
    items: list[AlignmentItem] = field(default_factory=list)
    goals_count: int = 0
    opener_hint: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["items"] = [asdict(i) for i in self.items]
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


def normalize_notify_channel(raw: str | None) -> str:
    v = (raw or _DEFAULT_NOTIFY or "both").strip().lower()
    if v in ("admin", "telegram", "both"):
        return v
    return "both"


def normalize_proactive_mode(raw: str | None) -> str:
    v = (raw or _DEFAULT_MODE or "on_misalignment").strip().lower()
    if v in ("always", "on_misalignment"):
        return v
    return "on_misalignment"


def normalize_jitter_ratio(raw: Any) -> float:
    if raw is None:
        return max(0.0, min(0.5, _DEFAULT_JITTER))
    if isinstance(raw, (int, float)):
        return max(0.0, min(0.5, float(raw)))
    s = str(raw).strip().lower().rstrip("%")
    try:
        v = float(s)
        if "%" in str(raw) or v > 1.0:
            v = v / 100.0
        return max(0.0, min(0.5, v))
    except ValueError:
        return max(0.0, min(0.5, _DEFAULT_JITTER))


def pick_nudge_opener(chat_id: str, epoch: float) -> str:
    seed = f"{chat_id}:{int(epoch)}"
    idx = int(hashlib.sha256(seed.encode()).hexdigest()[:8], 16) % len(_NUDGE_OPENERS)
    return _NUDGE_OPENERS[idx]


def _goal_title(goal: dict, fallback_key: str) -> str:
    t = (goal.get("title") or "").strip()
    if t:
        return t[:80] + ("…" if len(t) > 80 else "")
    return (goal.get("belief_key") or fallback_key or "").strip()


def _parse_float(raw: Any) -> float | None:
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def manifest_monitor_goal_keys(goals: list[dict[str, Any]] | list[Any]) -> list[str]:
    """belief_keys de metas monitor (nunca declarables como cumplidas vía HITL)."""
    out: list[str] = []
    for g in goals or []:
        if isinstance(g, dict):
            kind = str(g.get("goal_kind") or "task").strip() or "task"
            key = (g.get("belief_key") or "").strip()
        else:
            kind = str(getattr(g, "goal_kind", None) or "task").strip() or "task"
            key = (getattr(g, "belief_key", None) or "").strip()
        if kind == "monitor" and key:
            out.append(key)
    return out


def hitl_declarable_for_goals(goals: list[dict[str, Any]]) -> tuple[bool, str]:
    """
    False si el manifiesto incluye metas monitor: no se declaran «cumplidas» con /loop-approve.
    """
    keys = manifest_monitor_goal_keys(goals)
    if not keys:
        return True, ""
    preview = ", ".join(keys[:4])
    if len(keys) > 4:
        preview += f" (+{len(keys) - 4})"
    return (
        False,
        f"Metas monitor ({preview}) son revisión continua; no declares cumplimiento ni "
        "uses request_homeostasis_validation para cerrarlas.",
    )


def refresh_goal_observations(db: Any, chat_id: Any, worker_id: str) -> list[dict]:
    """
    Normaliza observed_value ya persistido en goals sin LLM.
    Devuelve la lista de goals (mutada en memoria y persistida si hubo cambios).
    """
    from duckclaw.commands.goals import get_manager_goals, set_manager_goals

    goals = get_manager_goals(db, chat_id)
    if not goals:
        return goals

    _ = worker_id

    changed = False
    for g in goals:
        if not isinstance(g, dict):
            continue
        new_obs: float | None = None

        if g.get("observed_value") is not None:
            new_obs = _parse_float(g.get("observed_value"))

        if new_obs is not None and new_obs != _parse_float(g.get("observed_value")):
            g["observed_value"] = new_obs
            changed = True

    if changed:
        set_manager_goals(db, chat_id, goals)
    return goals


def refresh_goals_list_observations(
    db: Any,
    chat_id: Any,
    worker_id: str,
    goals: list[dict],
) -> list[dict]:
    """Refresh observed_value on an in-memory goals list (no agent_config persist)."""
    if not goals:
        return goals
    _ = (db, chat_id, worker_id)
    out: list[dict] = []
    for g in goals:
        if not isinstance(g, dict):
            continue
        row = dict(g)
        new_obs: float | None = None
        if row.get("observed_value") is not None:
            new_obs = _parse_float(row.get("observed_value"))
        if new_obs is not None:
            row["observed_value"] = new_obs
        out.append(row)
    return out


def assess_goals_list_alignment(
    db: Any,
    chat_id: Any,
    goals: list[dict],
    *,
    worker_id: str = "",
) -> AlignmentReport:
    from duckclaw.commands.goals import _get_goals_registry_for_chat
    from harness_core.goal_priority import parse_goal_priority, sort_goals_by_priority

    goals = sort_goals_by_priority(
        refresh_goals_list_observations(db, chat_id, worker_id, goals)
    )
    registry = _get_goals_registry_for_chat(db, chat_id)
    key_to_belief = {b.key.strip(): b for b in (registry.beliefs if registry else [])}

    items: list[AlignmentItem] = []
    misaligned = 0

    for g in goals:
        if not isinstance(g, dict):
            continue
        key = (g.get("belief_key") or "").strip()
        b = key_to_belief.get(key)
        target = _parse_float(g.get("target_value"))
        thresh = _parse_float(g.get("threshold"))
        if b is not None:
            target = target if target is not None else float(b.target)
            thresh = thresh if thresh is not None else float(b.threshold)
        observed = _parse_float(g.get("observed_value"))
        comp = "symmetric"
        if b is not None:
            comp = getattr(b, "comparison", "symmetric") or "symmetric"

        title = _goal_title(g, key)
        goal_kind = str(g.get("goal_kind") or "task").strip() or "task"
        priority = parse_goal_priority(g.get("priority"))
        has_data = observed is not None and target is not None and thresh is not None
        if not has_data or (target == 0 and thresh == 0):
            items.append(
                AlignmentItem(
                    belief_key=key,
                    title=title,
                    target=target,
                    observed=observed,
                    threshold=thresh,
                    delta=0.0,
                    is_anomaly=False,
                    has_data=False,
                    comparison=comp,
                    goal_kind=goal_kind,
                    priority=priority,
                )
            )
            continue

        res = compute_surprise(observed, target, thresh, comparison=comp)
        if res.is_anomaly:
            misaligned += 1
        items.append(
            AlignmentItem(
                belief_key=key,
                title=title,
                target=target,
                observed=observed,
                threshold=thresh,
                delta=res.delta,
                is_anomaly=res.is_anomaly,
                has_data=True,
                comparison=comp,
                goal_kind=goal_kind,
                priority=priority,
            )
        )

    aligned = misaligned == 0
    opener = ""
    if not aligned:
        first = next((i for i in items if i.is_anomaly), None)
        if first:
            opener = (
                f"Detecté desalineación en P{first.priority} «{first.title}» "
                f"(obs={first.observed}, meta={first.target})."
            )
        else:
            opener = pick_nudge_opener(str(chat_id), 0.0)

    return AlignmentReport(
        aligned=aligned,
        misaligned_count=misaligned,
        items=items,
        goals_count=len(goals),
        opener_hint=opener,
    )


def assess_goals_alignment(
    db: Any,
    chat_id: Any,
    *,
    worker_id: str = "",
    tenant_id: str | None = None,
) -> AlignmentReport:
    from duckclaw.graphs.on_the_fly_commands import get_chat_state

    try:
        from harness_core.targets import load_homeostasis_manifest, manifest_goals_as_dicts

        tid = (tenant_id or get_chat_state(db, chat_id, "tenant_id") or "default").strip() or "default"
        manifest = load_homeostasis_manifest(db, tid, chat_id=chat_id)
        goals = manifest_goals_as_dicts(manifest)
        if goals:
            return assess_goals_list_alignment(db, chat_id, goals, worker_id=worker_id)
    except Exception:
        pass
    goals = refresh_goal_observations(db, chat_id, worker_id)
    return assess_goals_list_alignment(db, chat_id, goals, worker_id=worker_id)


def format_alignment_report_markdown(report: AlignmentReport) -> str:
    """Bloque legible para /loop --status y reportes fly."""
    lines = ["## Alineación con /goals", ""]
    if report.goals_count <= 0:
        lines.append("Sin metas en manifiesto — define objetivos con `/goals`.")
        return "\n".join(lines)
    if report.aligned:
        lines.append(f"**Estado:** alineado ({report.goals_count} meta(s)).")
    else:
        lines.append(
            f"**Estado:** {report.misaligned_count} desvío(s) "
            f"de {report.goals_count} meta(s)."
        )
    if report.opener_hint:
        lines.append(report.opener_hint)
    if report.goals_count > 1:
        lines.append(
            "Orden de atención: menor P primero (P1 antes que P2)."
        )
    lines.append("")
    for item in report.items:
        kind = (item.goal_kind or "task").strip() or "task"
        title = (item.title or item.belief_key or "?").strip()
        pl = f"P{item.priority} · " if item.priority >= 1 else ""
        if not item.has_data:
            lines.append(f"- {pl}**{title}** (`{kind}`): sin datos observables aún")
            continue
        flag = "⚠️" if item.is_anomaly else "✓"
        obs = item.observed if item.observed is not None else "?"
        target = item.target if item.target is not None else "?"
        thresh = item.threshold if item.threshold is not None else "?"
        lines.append(
            f"- {flag} {pl}**{title}** (`{kind}`): obs={obs}, meta={target}, "
            f"umbral={thresh}, delta={item.delta:.4g}"
        )
    return "\n".join(lines)


def build_alignment_nudge_system_event(
    report: AlignmentReport,
    *,
    chat_id: str = "",
    epoch: float = 0.0,
) -> str:
    """SYSTEM_EVENT para tick proactivo por desalineación."""
    opener = pick_nudge_opener(chat_id or "default", epoch or 0.0)
    misaligned = [i for i in report.items if i.is_anomaly]
    titles = "; ".join((m.title or m.belief_key) for m in misaligned[:8]) or "(sin títulos)"
    compact = [
        {
            "belief_key": m.belief_key,
            "title": m.title,
            "observed": m.observed,
            "target": m.target,
            "delta": m.delta,
        }
        for m in misaligned[:12]
    ]
    payload_json = json.dumps(
        {"misaligned": compact, "aligned": report.aligned, "misaligned_count": report.misaligned_count},
        ensure_ascii=False,
    )
    directive = (
        f"{opener} {GOALS_ALIGNMENT_REVIEW_PHRASE}. "
        f"Objetivos con desvío: {titles}. "
        f"Informe embebido: {payload_json}. "
        "Escribe al usuario en **primera persona** que estás analizando la situación; "
        "resume la desalineación detectada y propón **2–3 acciones concretas** para volver a la meta. "
        "Si falta observed en el informe, usa las capabilities de datos disponibles para obtener evidencia. "
        "No inventes cifras; mensaje útil y breve."
    )
    return f"[SYSTEM_EVENT: {directive}]"


def alignment_review_phrase_in_text(text: str) -> bool:
    t = text or ""
    return GOALS_ALIGNMENT_REVIEW_PHRASE in t
