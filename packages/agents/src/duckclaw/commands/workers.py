"""DB-first fly commands for worker catalog discovery (/roles, /skills)."""

from __future__ import annotations

from typing import Any

from duckclaw.commands.team_templates import _resolve_template_id
from duckclaw.guardrails.loader import format_guardrail

_DEFAULT_WORKER = "manager"


def execute_roles(db: Any, chat_id: Any) -> str:
    """/roles: lista todos los trabajadores virtuales (templates) disponibles."""
    _ = db, chat_id
    from duckclaw.workers.factory import list_workers

    all_templates = list_workers()
    if not all_templates:
        return "No hay templates en forge/templates. Añade al menos uno."
    lines = "\n".join(f"- {w}" for w in all_templates)
    return format_guardrail("fly_commands", "roles_list_intro", lines=lines)


def execute_skills_list(db: Any, chat_id: Any, args: str) -> str:
    """/skills <worker_id>: lista herramientas del template. worker_id debe ser uno de /roles."""
    _ = db, chat_id
    from duckclaw.workers.factory import list_workers

    available = list_workers()
    wid_raw = (args or "").strip()
    if not wid_raw:
        return "Uso: /skills <worker_id>. Ver templates: /roles"
    if wid_raw.startswith("--"):
        return "Indica un worker_id (ej. research_worker). Ver templates: /roles"
    canonical = _resolve_template_id(available, wid_raw)
    if not canonical:
        return f"Template '{wid_raw}' no encontrado. Disponibles (usa /roles): {', '.join(available)}"
    try:
        from duckclaw.workers.manifest import load_manifest

        spec = load_manifest(canonical)
        skill_lines = [f"- {s}" for s in (spec.skills_list or [])]
        skill_lines.append("- read_sql (solo lectura)")
        skill_lines.append("- admin_sql (lectura + escrituras)")
        return f"🔧 {spec.name} ({canonical})\n" + "\n".join(skill_lines)
    except Exception as e:
        return f"Error: {e}."
