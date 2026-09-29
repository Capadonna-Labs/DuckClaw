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

# This deployment runs write-confirmation as fire-and-forget by default
# (DUCKCLAW_WRITE_POLL_SEC unset/0) — enqueue_write_and_resolve() would then
# report ok=True the instant the command is *enqueued*, blind to the
# DB-Writer rejecting it moments later (e.g. a tenant mismatch). A skill
# create/edit/deactivate needs a real yes/no, so this always polls with its
# own fixed timeout regardless of that env var.
_WRITE_CONFIRM_TIMEOUT_SEC = 10.0

_PYTHON_METADATA_NOTE = (
    "skill_type='python' solo registra metadata en el catálogo (visible en la UI admin); "
    "no crea una tool ejecutable nueva. Para eso hace falta un módulo Python nuevo en "
    "forge/skills/ registrado a mano en skill_tool_registry.py."
)


def _actor_and_db_path(db: Any) -> tuple[str, str]:
    """Actor + the gateway HUB path — never the worker's bound vault.

    admin_skills lives in the hub: the "/" menu (GET /catalog/skills) and
    /name invocation (playground/directive_skills.py) both read it there. The
    worker's bound ``db`` is its vault, so writing/reading through it put
    skills somewhere nothing else ever looks.
    """
    del db
    from duckclaw.forge.skills.knowledge_tool_context import get_session_actor_email
    from duckclaw.gateway_db import get_gateway_db_path

    actor = (get_session_actor_email() or "").strip() or "system"
    return actor, (get_gateway_db_path() or "").strip()


def _open_hub_read_only(hub_path: str) -> Any:
    from duckclaw import DuckClaw

    return DuckClaw(hub_path, read_only=True)


def _dispatch_skill_command(db: Any, command: Any, *, actor: str, db_path: str) -> tuple[bool, str]:
    """Enqueue to the singleton DB-Writer against the hub and wait for its real status."""
    del db
    if not db_path:
        return False, "No se pudo resolver la ruta del hub (DUCKCLAW_GATEWAY_DB_PATH)."
    try:
        from duckclaw.db_write_fire_and_forget import enqueue_write_command, wait_write_task
    except Exception as exc:
        return False, f"cola DuckDB no disponible: {exc}"
    task_id = enqueue_write_command(command, db_path=db_path, user_id=actor)
    status = wait_write_task(task_id, timeout_sec=_WRITE_CONFIRM_TIMEOUT_SEC)
    if status is None:
        # No confirmation either way within our own timeout — never claim
        # success blindly here (unlike resolve_write_enqueue_result, which
        # would if DUCKCLAW_WRITE_POLL_SEC is unset, as it is on this deploy).
        return False, f"Sin confirmación del db-writer tras {_WRITE_CONFIRM_TIMEOUT_SEC:.0f}s (task_id={task_id})"
    if status.status != "success":
        return False, (status.detail or "db-writer failed")[:500]
    return True, ""


def _upsert_skill_impl(
    db: Any,
    name: str,
    description: str,
    skill_type: str = "directive",
    tenant_id: str = "default",
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
        tenant_id=(tenant_id or "default").strip() or "default",
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
    actor, hub_path = _actor_and_db_path(db)
    if not hub_path:
        return json.dumps({"ok": False, "error": "No se pudo resolver la ruta del hub."}, ensure_ascii=False)
    tid = (tenant_id or "default").replace("'", "''")
    esc_actor = actor.replace("'", "''")
    try:
        hub = _open_hub_read_only(hub_path)
        try:
            raw = hub.query(
                "SELECT name, skill_type, description, visibility, owner_email "
                "FROM main.admin_skills "
                f"WHERE tenant_id = '{tid}' AND active "
                f"AND (visibility = 'public' OR owner_email = '{esc_actor}') "
                "ORDER BY name"
            )
        finally:
            close = getattr(hub, "close", None)
            if callable(close):
                close()
        rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)[:500]}, ensure_ascii=False)
    return json.dumps({"ok": True, "skills": rows}, ensure_ascii=False)


def _deactivate_skill_impl(db: Any, name: str, tenant_id: str = "default") -> str:
    from duckclaw.write_commands import DeactivateCatalogSkillCommand

    clean_name = (name or "").strip()
    if not clean_name:
        return json.dumps({"ok": False, "error": "name vacío"}, ensure_ascii=False)
    actor, db_path = _actor_and_db_path(db)
    command = DeactivateCatalogSkillCommand(
        actor_email=actor,
        tenant_id=(tenant_id or "default").strip() or "default",
        name=clean_name,
    )
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
        return _upsert_skill_impl(db, name, description, skill_type, tenant_id)

    def _edit_skill(name: str, description: str, skill_type: str = "directive") -> str:
        return _upsert_skill_impl(db, name, description, skill_type, tenant_id)

    def _list_skills() -> str:
        return _list_skills_impl(db, tenant_id)

    def _deactivate_skill(name: str) -> str:
        return _deactivate_skill_impl(db, name, tenant_id)

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
