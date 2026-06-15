"""Assess homeostasis manifest alignment (infra + domain goals) for meditate messaging."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from harness_core.skills.strix_compute_delta import compute_distance_vector
from harness_core.states.meditate_state import CurrentMetrics, HomeostasisManifest


@dataclass
class ManifestAlignmentResult:
    infra_aligned: bool
    goals_aligned: bool
    aligned: bool
    distance_vector: dict[str, float] = field(default_factory=dict)
    goal_lines: list[str] = field(default_factory=list)
    infra_lines: list[str] = field(default_factory=list)
    misaligned_count: int = 0

    def format_message(self) -> str:
        if not self.aligned:
            parts = ["Desalineación detectada en homeostasis."]
            if self.goal_lines:
                parts.append("Metas: " + "; ".join(self.goal_lines))
            if self.infra_lines:
                parts.append("Infra: " + "; ".join(self.infra_lines))
            return " ".join(parts)
        goal_txt = "; ".join(self.goal_lines) if self.goal_lines else "(sin metas de dominio definidas)"
        infra_txt = "; ".join(self.infra_lines) if self.infra_lines else "dentro de umbrales"
        return (
            "Contexto alineado con las metas homeostasis. "
            f"Metas: {goal_txt}. Infra: {infra_txt}."
        )


def _format_infra_lines(distance: dict[str, float], metrics: dict[str, Any]) -> list[str]:
    labels = {
        "error_rate_pct": "error_rate",
        "stale_tasks_count": "tareas stale",
        "memory_fragmentation_index": "fragmentación memoria",
        "avg_latency_ms": "latencia media",
        "db_lock_events": "locks DuckDB",
    }
    lines: list[str] = []
    for key, label in labels.items():
        try:
            dist = float(distance.get(key) or 0)
            obs = metrics.get(key)
        except (TypeError, ValueError):
            continue
        if dist > 0:
            lines.append(f"{label} fuera de umbral (Δ={dist:g}, obs={obs})")
    if not lines:
        lines.append("sin desvíos infra (stale, locks, error_rate, fragmentación OK)")
    return lines


def assess_manifest_alignment(
    manifest: HomeostasisManifest,
    metrics: CurrentMetrics | dict[str, Any],
    *,
    db: Any = None,
    chat_id: Any = None,
    worker_id: str = "",
) -> ManifestAlignmentResult:
    """Contrast manifest infra + domain goals against current metrics/context."""
    m = metrics if isinstance(metrics, CurrentMetrics) else CurrentMetrics.model_validate(metrics)
    distance = compute_distance_vector(m, manifest.infra)
    infra_aligned = all(float(v or 0) <= 0 for v in distance.values())

    goal_lines: list[str] = []
    misaligned = 0
    goals_aligned = True

    goals_dicts = [g.model_dump() for g in manifest.goals]
    if goals_dicts and db is not None and chat_id is not None:
        try:
            from duckclaw.homeostasis.goals_alignment import assess_goals_list_alignment

            report = assess_goals_list_alignment(
                db, chat_id, goals_dicts, worker_id=worker_id
            )
            goals_aligned = report.aligned
            misaligned = report.misaligned_count
            for item in report.items:
                st = "✓" if not item.is_anomaly else "⚠️"
                if item.has_data and item.target is not None:
                    goal_lines.append(
                        f"{item.title} target={item.target} (obs: {item.observed}) {st}"
                    )
                else:
                    goal_lines.append(f"{item.title} target={item.target} (sin dato)")
        except Exception:
            for g in manifest.goals:
                title = (g.title or g.belief_key).strip()
                goal_lines.append(f"{title} target={g.target_value} (sin evaluar)")
    elif goals_dicts:
        for g in manifest.goals:
            title = (g.title or g.belief_key).strip()
            goal_lines.append(f"{title} target={g.target_value} (sin dato)")
    else:
        goals_aligned = True

    infra_lines = _format_infra_lines(distance, m.model_dump())
    aligned = infra_aligned and goals_aligned
    return ManifestAlignmentResult(
        infra_aligned=infra_aligned,
        goals_aligned=goals_aligned,
        aligned=aligned,
        distance_vector=distance,
        goal_lines=goal_lines,
        infra_lines=infra_lines,
        misaligned_count=misaligned,
    )
