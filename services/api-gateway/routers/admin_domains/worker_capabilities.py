"""Admin introspection: effective skills and runtime tools for a worker."""

from __future__ import annotations

import re
from typing import Any

import yaml
from fastapi import APIRouter, Depends

from core.admin_identity import effective_actor_email, open_gateway_db
from duckclaw.admin_worker_catalog import get_visible_worker_for_actor
from duckclaw.framework_tool_pack import (
    ensure_baseline_skills,
    load_framework_tool_pack,
    should_apply_framework_baseline,
)
from routers.admin_domains.admin_common import actor_from_header, problem, require_admin_key

router = APIRouter(prefix="/workers", tags=["admin-worker-capabilities"])


def _sanitize_worker_id(worker_id: str) -> str:
    wid = re.sub(r"[^a-zA-Z0-9_-]", "", (worker_id or "").strip())
    if not wid:
        raise problem(400, "worker_id inválido", worker_id or "")
    return wid


def _read_raw_manifest_dict(spec: Any) -> dict[str, Any]:
    worker_dir = getattr(spec, "worker_dir", None)
    if worker_dir is not None:
        for name in ("manifest.yaml", "manifest.yml"):
            path = worker_dir / name
            if path.is_file():
                data = yaml.safe_load(path.read_text(encoding="utf-8"))
                return data if isinstance(data, dict) else {}
    return {}


def _declared_skills(manifest_data: dict[str, Any]) -> list[str]:
    from duckclaw.workers.manifest import _parse_skill_bindings

    skills_list = manifest_data.get("skills") or []
    if isinstance(skills_list, str):
        skills_list = [s.strip() for s in skills_list.split(",") if s.strip()]
    names, _ = _parse_skill_bindings(skills_list)
    return [str(s).strip().lower().replace("-", "_") for s in names if str(s).strip()]


def _load_worker_spec(
    worker_id: str,
    *,
    actor: str,
) -> tuple[str, Any, dict[str, Any], str]:
    from duckclaw.workers.manifest import load_manifest

    wid = _sanitize_worker_id(worker_id)
    actor_email = effective_actor_email(actor)
    tenant_id = "default"
    spec: Any | None = None

    with open_gateway_db(read_only=True) as db:
        if "@" in actor_email:
            visible = get_visible_worker_for_actor(db, actor_email=actor_email, worker_id=wid)
            if visible:
                tenant_id = str(visible.get("tenant_id") or "default")
            elif wid != "default":
                raise problem(404, "Worker no visible en catálogo", wid)
        try:
            spec = load_manifest(wid, db=db, tenant_id=tenant_id)
        except Exception:
            spec = None

    if spec is None:
        if wid != "default":
            raise problem(404, "Worker no encontrado", wid)
        try:
            spec = load_manifest(wid)
        except Exception as exc:
            raise problem(404, "Worker no encontrado", str(exc)) from exc

    manifest_data = _read_raw_manifest_dict(spec)
    return wid, spec, manifest_data, tenant_id


def _runtime_tools_for_worker(
    worker_id: str,
    *,
    tenant_id: str,
) -> tuple[list[str], bool]:
    from langchain_core.language_models.fake_chat_models import FakeListChatModel

    from duckclaw.workers.factory_graph_setup import initialize_worker_graph_context

    class _BindableFakeLLM(FakeListChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

    fake_llm = _BindableFakeLLM(responses=["ok"])
    try:
        with open_gateway_db(read_only=True) as db:
            ctx = initialize_worker_graph_context(
                worker_id,
                ":memory:",
                fake_llm,
                db=db,
                tenant_id=tenant_id,
                llm_provider="none_llm",
            )
    except Exception:
        try:
            ctx = initialize_worker_graph_context(
                worker_id,
                ":memory:",
                fake_llm,
                llm_provider="none_llm",
            )
        except Exception:
            return [], False

    tools_by_name = getattr(ctx, "tools_by_name", None) or {}
    tool_names = sorted(str(name) for name in tools_by_name.keys() if str(name).strip())
    return tool_names, "run_sandbox" in tools_by_name


def _optional_flags(
    manifest_data: dict[str, Any],
    skills_effective: list[str],
    *,
    db: Any | None = None,
    tenant_id: str = "default",
    actor_email: str = "",
) -> dict[str, Any]:
    from duckclaw.integration_gaps import build_optional_integration_flags

    integrations = build_optional_integration_flags(
        skills_effective,
        db=db,
        tenant_id=tenant_id,
        actor_email=actor_email,
    )
    return {
        "integrations": integrations,
        "tavily": bool(integrations.get("tavily")) and "research" in skills_effective,
        "browser_sandbox": bool(manifest_data.get("browser_sandbox")),
    }


def _compute_gaps(
    *,
    skills_effective: list[str],
    tools_runtime: list[str],
    sandbox_registered: bool,
    docker_ok: bool,
    manifest_data: dict[str, Any],
    optional: dict[str, bool],
    db: Any | None = None,
    tenant_id: str = "default",
    actor_email: str = "",
) -> tuple[list[str], list[dict[str, Any]]]:
    from duckclaw.integration_gaps import build_integration_secret_gaps, integration_gap_messages

    gaps: list[str] = []
    integration_gaps: list[dict[str, Any]] = []
    runtime_set = set(tools_runtime)

    if sandbox_registered and not docker_ok:
        gaps.append("run_sandbox registrado pero Docker no está disponible en el host")

    integration_gaps = build_integration_secret_gaps(
        skills_effective,
        db=db,
        tenant_id=tenant_id,
        actor_email=actor_email,
    )
    gaps.extend(integration_gap_messages(integration_gaps))

    if manifest_data.get("browser_sandbox") and "run_browser_sandbox" not in runtime_set:
        gaps.append("browser_sandbox en manifest pero run_browser_sandbox no está registrado")

    pack = load_framework_tool_pack()
    framework_tools = pack.get("framework_tools") or {}
    expected_framework = set(framework_tools.get("always_registered") or [])
    if should_apply_framework_baseline(manifest_data):
        missing_framework = sorted(expected_framework - runtime_set)
        if missing_framework:
            gaps.append(
                "tools framework baseline ausentes en runtime: " + ", ".join(missing_framework)
            )

    for skill in skills_effective:
        normalized = skill.strip().lower().replace("-", "_")
        if normalized in runtime_set:
            continue
        if normalized in {"time_context"}:
            continue
        if normalized == "get_current_time" and "get_current_time" not in runtime_set:
            gaps.append("skill get_current_time efectiva pero tool get_current_time no registrada")
            continue
        if normalized in (framework_tools.get("always_registered") or []):
            continue
        if normalized in (framework_tools.get("sandbox") or []):
            continue
        if normalized in (framework_tools.get("sandbox_opt_in") or []):
            continue
        if normalized in (pack.get("optional_skills") or {}):
            if normalized == "research" and not optional.get("tavily"):
                continue
            if any(
                row.get("skill") == normalized for row in integration_gaps if not row.get("configured", True)
            ):
                continue
            continue
        gaps.append(f"skill '{normalized}' sin tool homónima en runtime")

    return gaps, integration_gaps


def build_worker_capabilities_payload(
    worker_id: str,
    *,
    actor: str = "admin-ui",
) -> dict[str, Any]:
    wid, _spec, manifest_data, tenant_id = _load_worker_spec(worker_id, actor=actor)
    skills_declared = _declared_skills(manifest_data)
    skills_effective = ensure_baseline_skills(skills_declared, manifest=manifest_data)
    framework_baseline = should_apply_framework_baseline(manifest_data)

    tools_runtime, sandbox_registered = _runtime_tools_for_worker(wid, tenant_id=tenant_id)

    try:
        from duckclaw.graphs.sandbox import _docker_available

        docker_ok = bool(_docker_available())
    except Exception:
        docker_ok = False

    actor_email = effective_actor_email(actor)
    with open_gateway_db(read_only=True) as db:
        optional = _optional_flags(
            manifest_data,
            skills_effective,
            db=db,
            tenant_id=tenant_id,
            actor_email=actor_email,
        )
        gaps, integration_gaps = _compute_gaps(
            skills_effective=skills_effective,
            tools_runtime=tools_runtime,
            sandbox_registered=sandbox_registered,
            docker_ok=docker_ok,
            manifest_data=manifest_data,
            optional=optional,
            db=db,
            tenant_id=tenant_id,
            actor_email=actor_email,
        )

    return {
        "worker_id": wid,
        "skills_declared": skills_declared,
        "skills_effective": skills_effective,
        "tools_runtime": tools_runtime,
        "framework_baseline": framework_baseline,
        "sandbox": {
            "registered": sandbox_registered,
            "docker_ok": docker_ok,
            "session_enabled": None,
        },
        "optional": optional,
        "gaps": gaps,
        "integration_gaps": integration_gaps,
    }


def build_worker_mcp_grants_payload(
    worker_id: str,
    *,
    actor: str = "admin-ui",
) -> dict[str, Any]:
    from duckclaw.admin_mcp_connectors import (
        _connector_has_auth,
        list_mcp_connectors,
        list_worker_mcp_connectors,
        resolve_worker_uid,
    )

    wid, _, _, tenant_id = _load_worker_spec(worker_id, actor=actor)
    with open_gateway_db(read_only=True) as db:
        worker_uid = resolve_worker_uid(db, worker_id=wid, tenant_id=tenant_id)
        granted_ids: set[str] = set()
        if worker_uid:
            granted = list_worker_mcp_connectors(db, worker_uid=worker_uid, tenant_id=tenant_id)
            granted_ids = {str(c.get("connector_id") or "") for c in granted if c.get("connector_id")}
        connectors: list[dict[str, Any]] = []
        for connector in list_mcp_connectors(db, tenant_id=tenant_id):
            cid = str(connector.get("connector_id") or "")
            if not cid:
                continue
            connectors.append(
                {
                    "connector_id": cid,
                    "display_name": str(connector.get("display_name") or cid),
                    "preset_id": str(connector.get("preset_id") or ""),
                    "enabled": bool(connector.get("enabled", True)),
                    "has_auth": bool(_connector_has_auth(db, connector)),
                    "granted": cid in granted_ids,
                }
            )
    return {"worker_id": wid, "connectors": connectors}


@router.get("/{worker_id}/capabilities", dependencies=[Depends(require_admin_key)])
async def get_worker_capabilities(
    worker_id: str,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    """Skills declaradas vs efectivas y tools registradas en runtime para un worker."""
    return build_worker_capabilities_payload(worker_id, actor=actor)


@router.get("/{worker_id}/mcp-grants", dependencies=[Depends(require_admin_key)])
async def get_worker_mcp_grants(
    worker_id: str,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    """Conectores MCP del tenant con estado de grant para el worker."""
    return build_worker_mcp_grants_payload(worker_id, actor=actor)
