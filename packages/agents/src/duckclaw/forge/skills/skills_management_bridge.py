"""Skill bridge: create/edit/list/deactivate catalog skills (admin_skills).

Gives a worker a structured way to persist reusable knowledge — "watch SNX
for FCF stabilization", a repeatable checklist, a house rule — as a named,
independently invoked skill, instead of the only alternative being
``update_system_prompt`` (which unconditionally injects into every turn and
only grows, never gets structured or invoked selectively).

Only ``skill_type="directive"`` (plain text, injected via ``/name`` in chat —
see ``playground/directive_skills.py``) is a live, immediately usable skill.
``skill_type="python"`` only writes catalog metadata (visible in the admin
UI); it does not register a new callable tool — that still requires a
hand-written module under ``forge/skills/`` wired into
``skill_tool_registry.DEFAULT_SKILL_TOOL_REGISTRY``. The tool description
below says this explicitly so an agent doesn't believe it created a live
tool when it only catalogued an intent.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Literal, Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

_log = logging.getLogger(__name__)

_PYTHON_METADATA_NOTE = (
    "skill_type='python' solo registra metadata en el catálogo (visible en la UI admin); "
    "no crea una tool ejecutable nueva. Para eso hace falta un módulo Python nuevo en "
    "forge/skills/ registrado a mano en skill_tool_registry.py."
)


def _actor_and_db_path(db: Any) -> tuple[str, str]:
    from duckclaw.forge.skills.goals_tool_context import get_goals_tool_db_path
    from duckclaw.forge.skills.knowledge_tool_context import get_session_actor_email

    actor = (get_session_actor_email() or "").strip() or "system"
    db_path = (get_goals_tool_db_path() or "").strip() or str(getattr(db, "_path", "") or "").strip()
    return actor, db_path


def _dispatch_skill_command(db: Any, command: Any, *, actor: str, db_path: str) -> tuple[bool, str]:
    """Write via the singleton DB-Writer — direct dispatch for an in-process
    writable handle (tests, scripts), or the fire-and-forget queue for the
    normal read-only agent db (mirrors ``model_setup._set_system_prompt_policy``)."""
    if db is not None and not bool(getattr(db, "_read_only", True)):
        try:
            from duckclaw.write_command_handlers import dispatch_command

            target = getattr(db, "_con", None) or getattr(db, "_native", None) or db
            dispatch_command(target, command.model_dump())
            return True, ""
        except Exception as exc:
            return False, str(exc)[:500]

    if not db_path:
        return False, "No se pudo resolver la ruta de la bóveda."
    try:
        from duckclaw.db_write_fire_and_forget import enqueue_write_and_resolve
    except Exception as exc:
        return False, f"cola DuckDB no disponible: {exc}"
    return enqueue_write_and_resolve(command, db_path=db_path, user_id=actor)


def _upsert_skill_impl(
    db: Any,
    name: str,
    description: str,
    skill_type: str = "directive",
) -> str:
    from duckclaw.write_commands import UpsertCatalogSkillCommand

    clean_name = (name or "").strip()
    if not clean_name:
        return json.dumps({"ok": False, "error": "name vacío"}, ensure_ascii=False)
    text = (description or "").strip()
    if not text:
        return json.dumps({"ok": False, "error": "description vacío"}, ensure_ascii=False)
    st = (skill_type or "directive").strip().lower()
    if st not in ("directive", "python"):
        st = "directive"
    implementation_ref = f"directive://{clean_name}" if st == "directive" else f"catalog://{clean_name}"

    actor, db_path = _actor_and_db_path(db)
    command = UpsertCatalogSkillCommand(
        actor_email=actor,
        name=clean_name,
        description=text,
        skill_type=st,
        implementation_ref=implementation_ref,
        visibility="private",
    )
    ok, err = _dispatch_skill_command(db, command, actor=actor, db_path=db_path)
    if not ok:
        return json.dumps({"ok": False, "error": err or "No se pudo guardar el skill"}, ensure_ascii=False)

    note = (
        f"Invócalo escribiendo /{clean_name} al inicio de un mensaje en el chat."
        if st == "directive"
        else _PYTHON_METADATA_NOTE
    )
    return json.dumps(
        {"ok": True, "name": clean_name, "skill_type": st, "message": f"Skill '{clean_name}' guardado. {note}"},
        ensure_ascii=False,
    )


def _list_skills_impl(db: Any, tenant_id: str = "default") -> str:
    actor, _ = _actor_and_db_path(db)
    if db is None:
        return json.dumps({"ok": False, "error": "DB no disponible"}, ensure_ascii=False)
    tid = (tenant_id or "default").replace("'", "''")
    esc_actor = actor.replace("'", "''")
    try:
        raw = db.query(
            "SELECT name, skill_type, description, visibility, owner_email "
            "FROM main.admin_skills "
            f"WHERE tenant_id = '{tid}' AND active "
            f"AND (visibility = 'public' OR owner_email = '{esc_actor}') "
            "ORDER BY name"
        )
        rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)[:500]}, ensure_ascii=False)
    return json.dumps({"ok": True, "skills": rows}, ensure_ascii=False)


def _deactivate_skill_impl(db: Any, name: str) -> str:
    from duckclaw.write_commands import DeactivateCatalogSkillCommand

    clean_name = (name or "").strip()
    if not clean_name:
        return json.dumps({"ok": False, "error": "name vacío"}, ensure_ascii=False)
    actor, db_path = _actor_and_db_path(db)
    command = DeactivateCatalogSkillCommand(actor_email=actor, name=clean_name)
    ok, err = _dispatch_skill_command(db, command, actor=actor, db_path=db_path)
    if not ok:
        return json.dumps({"ok": False, "error": err or "No se pudo desactivar el skill"}, ensure_ascii=False)
    return json.dumps({"ok": True, "name": clean_name, "message": "Skill desactivado."}, ensure_ascii=False)


class CreateSkillInput(BaseModel):
    name: str = Field(
        ...,
        min_length=2,
        max_length=128,
        description="Nombre único del skill, ej. 'radar_watchlist'. Sin espacios; se invoca como /nombre.",
    )
    description: str = Field(
        ...,
        min_length=1,
        max_length=1024,
        description="Para skill_type='directive': el texto exacto que se inyecta al invocar /nombre.",
    )
    skill_type: Literal["directive", "python"] = Field(
        default="directive",
        description="'directive' (texto invocable, recomendado) o 'python' (solo metadata de catálogo).",
    )


class EditSkillInput(CreateSkillInput):
    pass


class ListSkillsInput(BaseModel):
    pass


class DeactivateSkillInput(BaseModel):
    name: str = Field(..., min_length=2, max_length=128)


def register_skills_management_skill(
    tools_list: list[Any],
    skills_management_config: Optional[dict] = None,
    *,
    db: Any = None,
    tenant_id: str = "default",
) -> None:
    cfg = skills_management_config if isinstance(skills_management_config, dict) else {}
    if cfg.get("enabled") is False:
        return

    existing = {str(getattr(t, "name", "") or "") for t in tools_list}

    def _create_skill(name: str, description: str, skill_type: str = "directive") -> str:
        return _upsert_skill_impl(db, name, description, skill_type)

    def _edit_skill(name: str, description: str, skill_type: str = "directive") -> str:
        return _upsert_skill_impl(db, name, description, skill_type)

    def _list_skills() -> str:
        return _list_skills_impl(db, tenant_id)

    def _deactivate_skill(name: str) -> str:
        return _deactivate_skill_impl(db, name)

    if "create_skill" not in existing:
        tools_list.append(
            StructuredTool.from_function(
                _create_skill,
                name="create_skill",
                description=(
                    "Crea un skill nuevo (conocimiento reutilizable persistido), en vez de "
                    "hacer crecer tu system prompt con update_system_prompt. "
                    "skill_type='directive' (default): texto que se inyecta solo cuando alguien "
                    "escribe /nombre en el chat — úsalo para checklists, recordatorios, reglas "
                    "de watchlist, etc. skill_type='python': solo registra metadata en el "
                    "catálogo, no crea una tool ejecutable. Falla si el nombre ya existe con otro "
                    "dueño — usa edit_skill para modificar uno tuyo."
                ),
                args_schema=CreateSkillInput,
            )
        )
    if "edit_skill" not in existing:
        tools_list.append(
            StructuredTool.from_function(
                _edit_skill,
                name="edit_skill",
                description=(
                    "Edita (upsert) un skill que ya creaste — mismos parámetros que create_skill. "
                    "Reemplaza description/skill_type del skill existente con ese name."
                ),
                args_schema=EditSkillInput,
            )
        )
    if "list_skills" not in existing:
        tools_list.append(
            StructuredTool.from_function(
                _list_skills,
                name="list_skills",
                description=(
                    "Lista los skills activos visibles para ti (públicos del tenant + privados "
                    "tuyos): name, skill_type, description, visibility, owner_email."
                ),
                args_schema=ListSkillsInput,
            )
        )
    if "deactivate_skill" not in existing:
        tools_list.append(
            StructuredTool.from_function(
                _deactivate_skill,
                name="deactivate_skill",
                description="Desactiva (soft-delete) un skill tuyo por name. No lo borra físicamente.",
                args_schema=DeactivateSkillInput,
            )
        )
    _log.info(
        "Skills management skill registrado — "
        "create_skill/edit_skill/list_skills/deactivate_skill disponibles"
    )
