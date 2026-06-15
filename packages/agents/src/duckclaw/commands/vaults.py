"""DB-first multi-vault chat commands.

This module owns the /vault command so the graph command dispatcher can stay
thin and focused on routing command names.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable

from duckclaw.vaults import (
    create_vault as _vault_create,
    list_vaults as _vault_list,
    remove_vault as _vault_remove,
    resolve_active_vault as _vault_resolve_active,
    switch_vault as _vault_switch,
    vault_scope_id_for_tenant,
)


WorkerIdResolver = Callable[[Any, Any], str]


def _dedicated_gateway_db_path_for_vault() -> str | None:
    """
    Same rule as the API Gateway: PM2 config + multiplex / DUCKDB_PATH keys.

    This prevents /vault from showing the registry hub when a dedicated gateway
    opened a tenant vault for the current session.
    """
    from duckclaw.pm2_gateway_db import dedicated_gateway_db_path_resolved

    return dedicated_gateway_db_path_resolved()


def _session_duckdb_path_for_fly(db: Any) -> str | None:
    """Path for the DuckClaw session opened by the gateway for this turn."""
    p = getattr(db, "_path", None)
    if p is None:
        return None
    s = str(p).strip()
    if not s or s == ":memory:":
        return None
    try:
        return str(Path(s).expanduser().resolve())
    except Exception:
        return None


def _fly_vault_label_for_tenant(tenant_id: Any) -> str:
    tid = str(tenant_id or "").strip()
    if not tid or tid.lower() == "default":
        return _dedicated_gateway_vault_label()
    return tid


def _dedicated_gateway_vault_label() -> str:
    proc = (os.environ.get("DUCKCLAW_PM2_PROCESS_NAME") or "").strip()
    matched = (os.environ.get("DUCKCLAW_PM2_MATCHED_APP_NAME") or "").strip()
    fallback = proc or matched
    if fallback:
        return fallback.replace("-Gateway", "").replace("-", " ").strip() or "este gateway"
    return "este gateway"


def _format_vault_size_mb(size_bytes: int | float) -> str:
    """Size for /vault messages (1 MB = 1024² bytes, two decimals)."""
    try:
        b = max(0, int(size_bytes))
    except (TypeError, ValueError):
        b = 0
    mb = b / (1024 * 1024)
    return f"{mb:.2f} MB"


def _effective_vault_tenant_label(tenant_id: Any) -> str:
    tid_req = str(tenant_id or "").strip()
    if tid_req and tid_req.lower() != "default":
        return tid_req
    try:
        from duckclaw.forge.team_env import default_tenant_id_from_runtime

        resolved = (default_tenant_id_from_runtime() or "").strip()
    except Exception:
        resolved = ""
    return resolved if resolved and resolved.lower() != "default" else ""


def _template_bound_vault_path(worker_id: str | None, vault_user_id: Any) -> str | None:
    """Absolute path if the worker template declares forge_context.vault_binding."""
    wid = (worker_id or "").strip()
    if not wid or wid.lower() in ("manager", "default", "entry_router", "manager_router"):
        return None
    try:
        from duckclaw.vaults import resolve_template_vault_path
        from duckclaw.workers.manifest import load_manifest

        spec = load_manifest(wid)
        return resolve_template_vault_path(spec.forge_vault_binding, vault_user_id)
    except Exception:
        return None


def execute_vault(
    args: str,
    *,
    vault_user_id: Any,
    tenant_id: Any = None,
    db: Any | None = None,
    entry_worker_id: str | None = None,
    chat_id: Any | None = None,
    worker_id_resolver: WorkerIdResolver | None = None,
) -> str:
    user_id = str(vault_user_id or "").strip() or "default"
    vault_scope = vault_scope_id_for_tenant(tenant_id)
    raw = (args or "").strip()
    session_db_path = _session_duckdb_path_for_fly(db) if db is not None else None
    template_db: str | None = None
    template_worker = ""
    if not session_db_path:
        wid = (entry_worker_id or "").strip()
        if not wid and db is not None and chat_id is not None and worker_id_resolver is not None:
            wid = (worker_id_resolver(db, chat_id) or "").strip()
        template_db = _template_bound_vault_path(wid, user_id)
        if template_db:
            template_worker = wid
    fixed_db = session_db_path or template_db or _dedicated_gateway_db_path_for_vault()
    if fixed_db:
        fp = Path(fixed_db).expanduser().resolve()
        if session_db_path:
            label = _fly_vault_label_for_tenant(tenant_id)
        elif template_db:
            label = f"plantilla {template_worker}" if template_worker else "plantilla"
        else:
            label = _dedicated_gateway_vault_label()
        if not raw:
            size = 0
            try:
                size = fp.stat().st_size if fp.exists() else 0
            except Exception:
                pass
            gtid = _effective_vault_tenant_label(tenant_id)
            extra = f"\nTenant: {gtid}" if gtid else ""
            return (
                f"🗄 BD de este gateway ({label}): {fp.name}\n"
                f"Ruta: {fp}\nTamaño: {_format_vault_size_mb(size)}{extra}"
            )
        tokens = raw.split()
        cmd = (tokens[0] or "").strip().lower()
        if cmd.startswith("--"):
            cmd = cmd[2:]
        if cmd in ("list", "new", "use", "rm"):
            hint = (
                "Los comandos /vault list|new|use|rm son del registry multi-bóveda; "
                "aquí no aplican. Usa /vault sin argumentos para ver la ruta."
            )
            if template_db:
                hint = (
                    "La bóveda está fijada en manifest.yaml (forge_context.vault_binding). "
                    "Cámbiala en Plantillas → Bóveda DuckDB. " + hint
                )
            return f"En este contexto ({label}) solo aplica la BD anterior. {hint}"
        return (
            f"Usa /vault sin argumentos para ver la BD de {label}. "
            "Comandos adicionales del registry no aplican en este gateway."
        )
    if not raw:
        active_id, active_path = _vault_resolve_active(user_id, vault_scope)
        size = 0
        try:
            p = Path(active_path)
            size = p.stat().st_size if p.exists() else 0
        except Exception:
            pass
        tenant_extra = _effective_vault_tenant_label(tenant_id)
        tenant_line = f"\nTenant: {tenant_extra}" if tenant_extra else ""
        return (
            f"🗄 Bóveda activa: {active_id}\nRuta: {active_path}\n"
            f"Tamaño: {_format_vault_size_mb(size)}{tenant_line}\n\n"
            "Comandos: /vault list | /vault --list | /vault new <name> | /vault --new <name> | "
            "/vault use <id> | /vault --use <id> | /vault rm <id> | /vault --rm <id>"
        )
    tokens = raw.split()
    cmd = (tokens[0] or "").strip().lower()
    if cmd.startswith("--"):
        cmd = cmd[2:]
    if cmd == "list":
        rows = _vault_list(user_id, vault_scope)
        if not rows:
            return "No hay bóvedas."
        lines = []
        for r in rows:
            mark = "✅" if r.get("is_active") else "•"
            sz = int(r.get("size_bytes", 0) or 0)
            lines.append(
                f"{mark} {r.get('vault_id')} ({r.get('vault_name')}) - {_format_vault_size_mb(sz)}"
            )
        return "🗄 Bóvedas:\n" + "\n".join(lines)
    if cmd == "new":
        name = " ".join(tokens[1:]).strip()
        if not name:
            return "Uso: /vault new <name> | /vault --new <name>"
        created = _vault_create(user_id, name, vault_scope)
        return f"✅ Bóveda creada: {created.get('vault_id')} ({created.get('vault_name')})"
    if cmd == "use":
        vid = " ".join(tokens[1:]).strip()
        if not vid:
            return "Uso: /vault use <vault_id> | /vault --use <vault_id>"
        ok = _vault_switch(user_id, vid, vault_scope)
        if not ok:
            return f"No existe la bóveda '{vid}'. Usa /vault list."
        active_id, _ = _vault_resolve_active(user_id, vault_scope)
        return f"✅ Bóveda activa actual: {active_id}"
    if cmd == "rm":
        vid = " ".join(tokens[1:]).strip()
        if not vid:
            return "Uso: /vault rm <vault_id> | /vault --rm <vault_id>"
        ok = _vault_remove(user_id, vid, vault_scope)
        if not ok:
            return f"No existe la bóveda '{vid}'."
        active_id, _ = _vault_resolve_active(user_id, vault_scope)
        return f"🗑 Bóveda eliminada: {vid}. Activa actual: {active_id}"
    return (
        "Uso: /vault | /vault list | /vault --list | /vault new <name> | /vault --new <name> | "
        "/vault use <vault_id> | /vault --use <vault_id> | /vault rm <vault_id> | /vault --rm <vault_id>"
    )
