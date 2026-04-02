"""Escribir .env, wizard_config, MCP, compose, Strix y PM2 tras confirmar Review."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

from duckclaw.dotenv_immutable import (
    is_repo_dotenv_immutable,
    merge_proposed_env_file,
    merged_root_and_proposed_flat_env,
)
from duckops.sovereign.atomic import atomic_write
from duckops.sovereign.docker_compose import write_compose_override
from duckops.sovereign.draft import SovereignDraft
from duckops.sovereign.redis_local import try_start_redis_local
from duckops.sovereign.strix_policy import patch_security_policy
from duckops.sovereign.telegram_set_webhook import register_telegram_webhook_after_deploy

DEFAULT_SOVEREIGN_VAULT = "db/sovereign_memory.duckdb"


def effective_primary_duckdb_relpath(draft: SovereignDraft) -> str:
    """
    Ruta .duckdb principal del gateway.

    Si la bóveda sigue en el valor por defecto soberano y el usuario solo rellenó
    «DuckDB shared», esa ruta pasa a ser la principal (BI-Analyst no usa ATTACH
    compartido; necesita DUCKCLAW_DB_PATH).
    """
    vault = (draft.duckdb_vault_path or "").strip() or DEFAULT_SOVEREIGN_VAULT
    shared = (draft.duckdb_shared_path or "").strip()
    if shared and vault == DEFAULT_SOVEREIGN_VAULT:
        return shared
    return vault


def shared_attach_relpath(draft: SovereignDraft) -> str | None:
    """Segunda base (Leila / grants). None si no hay o si ya es la principal."""
    shared = (draft.duckdb_shared_path or "").strip()
    if not shared:
        return None
    primary = effective_primary_duckdb_relpath(draft)
    if shared == primary:
        return None
    return shared


def _resolve_repo_db_path(repo_root: Path, rel_or_abs: str) -> Path:
    p = Path((rel_or_abs or "").strip())
    if not p.parts:
        return (repo_root / DEFAULT_SOVEREIGN_VAULT).resolve()
    if p.is_absolute():
        return p.resolve()
    return (repo_root / p).resolve()


def _parse_repo_dotenv(repo_root: Path) -> dict[str, str]:
    """Claves del ``.env`` del repo (tras merge del wizard) para reutilizar en un bloque PM2 nuevo."""
    out: dict[str, str] = {}
    path = repo_root / ".env"
    if not path.is_file():
        return out
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, _, v = s.partition("=")
            ks = k.strip()
            if not ks:
                continue
            out[ks] = v.strip().strip("'\"").strip()
    except Exception:
        pass
    return out


_PM2_SKIP_ENV_UPDATES_KEYS = frozenset(
    {
        "DUCKCLAW_DB_PATH",
        "DUCKDB_PATH",
        "DUCKCLAW_SHARED_DB_PATH",
    }
)


def _apply_materialize_env_updates_to_pm2_env(
    env: dict[str, str],
    env_updates: dict[str, str] | None,
) -> None:
    """Fusiona claves del materialize (Telegram, Redis, LLM, …) sin pisar rutas DuckDB resueltas."""
    if not env_updates:
        return
    for key, val in env_updates.items():
        if key in _PM2_SKIP_ENV_UPDATES_KEYS:
            continue
        env[key] = val if val is not None else ""


def patch_api_gateways_pm2_for_draft(
    repo_root: Path,
    draft: SovereignDraft,
    console_print,
    *,
    env_updates: dict[str, str] | None = None,
) -> None:
    """
    Alinea o crea el bloque ``apps[]`` para ``draft.gateway_pm2_name``.

    - Si ya existe: actualiza ``DUCKCLAW_DB_PATH`` / ``DUCKCLAW_SHARED_DB_PATH``.
    - Si no existe: **añade** automáticamente un bloque (host, puerto, env copiado de
      ``.env`` + ``config/dotenv_wizard_proposed.env`` + identidad del borrador +
      ``env_updates`` del materialize) para que ``main.py`` resuelva bien la DuckDB y
      los tokens Telegram con ``.env`` inmutable.

    El gateway cargado con PM2 **sobrescribe** ``DUCKCLAW_DB_PATH`` desde este JSON
    (ver ``api-gateway/main.py``); actualizar solo ``.env`` no bastaba.
    """
    from duckclaw.pm2_gateway_db import clear_pm2_gateway_db_cache  # noqa: PLC0415

    app_name = (draft.gateway_pm2_name or "").strip()
    if not app_name:
        return

    primary_rel = effective_primary_duckdb_relpath(draft)
    primary_abs = _resolve_repo_db_path(repo_root, primary_rel)
    attach_rel = shared_attach_relpath(draft)

    cfg_path = repo_root / "config" / "api_gateways_pm2.json"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)

    if cfg_path.is_file():
        try:
            raw = json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception as exc:
            console_print(f"No se pudo leer api_gateways_pm2.json: {exc}")
            return
    else:
        raw = {"apps": []}

    apps = raw.get("apps") if isinstance(raw, dict) else None
    if not isinstance(apps, list):
        apps = []
        raw["apps"] = apps

    idx: int | None = None
    for i, a in enumerate(apps):
        if isinstance(a, dict) and (a.get("name") or "").strip() == app_name:
            idx = i
            break

    port = int(draft.gateway_port)

    if idx is None:
        dot = merged_root_and_proposed_flat_env(repo_root)
        env: dict[str, str] = dict(dot)
        env["PYTHONPATH"] = str(repo_root.resolve())
        env["DUCKCLAW_PM2_PROCESS_NAME"] = app_name
        ru = (draft.redis_url or "").strip() or dot.get("REDIS_URL") or dot.get("DUCKCLAW_REDIS_URL") or ""
        if ru:
            env["REDIS_URL"] = ru
            env["DUCKCLAW_REDIS_URL"] = ru
        env["DUCKCLAW_DB_PATH"] = str(primary_abs)
        env["DUCKCLAW_GATEWAY_TENANT_ID"] = (draft.tenant_id or "default").strip() or "default"
        env["DUCKCLAW_DEFAULT_WORKER_ID"] = (draft.default_worker_id or "finanz").strip()
        for k, val in (
            ("DUCKCLAW_LLM_PROVIDER", draft.llm_provider),
            ("DUCKCLAW_LLM_MODEL", draft.llm_model),
            ("DUCKCLAW_LLM_BASE_URL", draft.llm_base_url),
        ):
            vs = (val or "").strip()
            if vs:
                env[k] = vs
        if attach_rel is not None:
            env["DUCKCLAW_SHARED_DB_PATH"] = str(_resolve_repo_db_path(repo_root, attach_rel))
        elif (draft.duckdb_shared_path or "").strip():
            env.pop("DUCKCLAW_SHARED_DB_PATH", None)

        for a in apps:
            if isinstance(a, dict) and int(a.get("port") or 0) == port:
                console_print(
                    f"[yellow]Aviso:[/] ya hay un gateway en puerto {port} en api_gateways_pm2.json; "
                    "si el arranque por --port resuelve el bloque equivocado, cambia uno de los puertos."
                )
                break

        apps.append({"name": app_name, "host": "0.0.0.0", "port": port, "env": env})
        console_print(
            f"[green]Nuevo gateway[/] '{app_name}' añadido a config/api_gateways_pm2.json (puerto {port})."
        )
        idx = len(apps) - 1

    app = apps[idx]
    if not isinstance(app, dict):
        return
    app.setdefault("host", "0.0.0.0")
    env = app.get("env")
    if not isinstance(env, dict):
        env = {}
        app["env"] = env

    env["DUCKCLAW_DB_PATH"] = str(primary_abs)
    if attach_rel is not None:
        env["DUCKCLAW_SHARED_DB_PATH"] = str(_resolve_repo_db_path(repo_root, attach_rel))
    elif (draft.duckdb_shared_path or "").strip():
        env.pop("DUCKCLAW_SHARED_DB_PATH", None)

    _apply_materialize_env_updates_to_pm2_env(env, env_updates)

    atomic_write(cfg_path, json.dumps(raw, indent=2) + "\n", encoding="utf-8")
    clear_pm2_gateway_db_cache()
    console_print(f"PM2 config: DUCKCLAW_DB_PATH → {primary_abs}")
    if attach_rel is not None:
        console_print(f"PM2 config: DUCKCLAW_SHARED_DB_PATH → {env['DUCKCLAW_SHARED_DB_PATH']}")


def _wizard_config_path() -> Path:
    return Path.home() / ".config" / "duckclaw" / "wizard_config.json"


def load_last_duckdb_vault_path_from_wizard_config() -> str:
    """Ruta de bóveda guardada en la última materialización (wizard_config.json)."""
    path = _wizard_config_path()
    if not path.is_file():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return (data.get("db_path") or "").strip()
    except Exception:
        pass
    return ""


def load_last_wizard_creator_telegram_user_id_from_wizard_config() -> str:
    """Último user_id del creador guardado en wizard_config.json (materialización previa)."""
    path = _wizard_config_path()
    if not path.is_file():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return (data.get("wizard_creator_telegram_user_id") or "").strip()
    except Exception:
        pass
    return ""


def load_last_wizard_creator_admin_display_name_from_wizard_config() -> str:
    """Último nombre de admin del creador (username en BD) guardado en wizard_config.json."""
    path = _wizard_config_path()
    if not path.is_file():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return (data.get("wizard_creator_admin_display_name") or "").strip()
    except Exception:
        pass
    return ""


def load_last_wizard_extra_admin_telegram_ids_from_wizard_config() -> str:
    """Últimos admins extra (CSV) guardados en wizard_config.json."""
    path = _wizard_config_path()
    if not path.is_file():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return (data.get("wizard_extra_admin_telegram_ids") or "").strip()
    except Exception:
        pass
    return ""


def load_last_gateway_tenant_id_from_wizard_config() -> str:
    """Último ``DUCKCLAW_GATEWAY_TENANT_ID`` guardado en wizard_config.json."""
    path = _wizard_config_path()
    if not path.is_file():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return (data.get("gateway_tenant_id") or "").strip()
    except Exception:
        pass
    return ""


def load_gateway_tenant_hint_from_repo_env(repo_root: Path) -> str:
    """Lee ``DUCKCLAW_GATEWAY_TENANT_ID`` del ``.env`` del repo si está definido."""
    envp = repo_root / ".env"
    if not envp.is_file():
        return ""
    try:
        text = envp.read_text(encoding="utf-8")
    except OSError:
        return ""
    for raw in text.splitlines():
        s = raw.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, _, v = s.partition("=")
        if k.strip() != "DUCKCLAW_GATEWAY_TENANT_ID":
            continue
        val = v.strip().strip("'\"")
        return val if val else ""
    return ""


def load_last_gateway_pm2_name_from_wizard_config() -> str:
    """Último nombre PM2 del gateway guardado en wizard_config.json (clave ``gateway_pm2_name``)."""
    path = _wizard_config_path()
    if not path.is_file():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return (data.get("gateway_pm2_name") or "").strip()
    except Exception:
        pass
    return ""


def load_last_default_worker_id_from_wizard_config() -> str:
    """Último worker por defecto guardado en wizard_config.json (clave ``default_worker_id``)."""
    path = _wizard_config_path()
    if not path.is_file():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return (data.get("default_worker_id") or "").strip()
    except Exception:
        pass
    return ""


def load_last_gateway_port_from_wizard_config() -> int | None:
    """Último puerto del gateway guardado en wizard_config.json (clave ``gateway_port``)."""
    path = _wizard_config_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        raw = data.get("gateway_port")
        if raw is None:
            return None
        p = int(raw)
        if 1 <= p <= 65535:
            return p
    except (TypeError, ValueError, json.JSONDecodeError, OSError):
        pass
    return None


def load_gateway_port_hint_from_api_gateways_json(repo_root: Path, gateway_pm2_name: str) -> int | None:
    """Puerto en ``config/api_gateways_pm2.json`` para la app cuyo ``name`` coincide con ``gateway_pm2_name``."""
    name = (gateway_pm2_name or "").strip()
    if not name:
        return None
    cfg_path = repo_root / "config" / "api_gateways_pm2.json"
    if not cfg_path.is_file():
        return None
    try:
        raw = json.loads(cfg_path.read_text(encoding="utf-8"))
        apps = raw.get("apps") if isinstance(raw, dict) else None
        if not isinstance(apps, list):
            return None
        for a in apps:
            if not isinstance(a, dict):
                continue
            if (a.get("name") or "").strip() != name:
                continue
            port = a.get("port")
            if port is None:
                return None
            p = int(port)
            if 1 <= p <= 65535:
                return p
            return None
    except (TypeError, ValueError, json.JSONDecodeError, OSError):
        pass
    return None


def load_default_worker_id_hint_from_repo_env(repo_root: Path) -> str:
    """Lee ``DUCKCLAW_DEFAULT_WORKER_ID`` del ``.env`` del repo si está definido."""
    envp = repo_root / ".env"
    if not envp.is_file():
        return ""
    try:
        text = envp.read_text(encoding="utf-8")
    except OSError:
        return ""
    for raw in text.splitlines():
        s = raw.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, _, v = s.partition("=")
        if k.strip() != "DUCKCLAW_DEFAULT_WORKER_ID":
            continue
        val = v.strip().strip("'\"")
        return val if val else ""
    return ""


def load_pm2_gateway_name_hint_from_repo_env(repo_root: Path) -> str:
    """Lee ``DUCKCLAW_PM2_PROCESS_NAME`` del ``.env`` del repo si está definido."""
    envp = repo_root / ".env"
    if not envp.is_file():
        return ""
    try:
        text = envp.read_text(encoding="utf-8")
    except OSError:
        return ""
    for raw in text.splitlines():
        s = raw.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, _, v = s.partition("=")
        if k.strip() != "DUCKCLAW_PM2_PROCESS_NAME":
            continue
        val = v.strip().strip("'\"")
        return val if val else ""
    return ""


def load_telegram_creator_hint_from_repo_env(repo_root: Path) -> str:
    """
    Si en ``.env`` hay ``DUCKCLAW_ADMIN_CHAT_ID`` o ``DUCKCLAW_OWNER_ID`` numérico,
    úsalo como sugerencia de admin (mismo criterio que el gateway).
    """
    envp = repo_root / ".env"
    if not envp.is_file():
        return ""
    try:
        text = envp.read_text(encoding="utf-8")
    except OSError:
        return ""
    vals: dict[str, str] = {}
    for raw in text.splitlines():
        s = raw.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, _, v = s.partition("=")
        ks = k.strip()
        if ks:
            vals[ks] = v.strip().strip("'\"")
    for key in ("DUCKCLAW_ADMIN_CHAT_ID", "DUCKCLAW_OWNER_ID"):
        val = (vals.get(key) or "").strip()
        if val.isdigit():
            return val
    return ""


def load_duckdb_vault_hint_from_repo_env(repo_root: Path) -> str:
    """Si existe .env en el repo con DUCKCLAW_DB_PATH / DUCKDB_PATH, úsalo como sugerencia."""
    envp = repo_root / ".env"
    if not envp.is_file():
        return ""
    try:
        text = envp.read_text(encoding="utf-8")
    except OSError:
        return ""
    for raw in text.splitlines():
        s = raw.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, _, v = s.partition("=")
        k = k.strip()
        if k not in ("DUCKCLAW_DB_PATH", "DUCKDB_PATH"):
            continue
        v = v.strip().strip("'\"")
        if not v:
            continue
        p = Path(v)
        if p.is_absolute():
            try:
                return str(p.resolve().relative_to(repo_root.resolve()))
            except ValueError:
                return v
        return v
    return ""


def merge_env_file(repo_root: Path, updates: dict[str, str]) -> bool:
    """
    Fusiona claves en ``.env`` (vía atomic_write).

    Si el repo está marcado como inmutable (``.env.immutable`` o
    ``DUCKCLAW_DOTENV_IMMUTABLE``), **no** escribe ``.env``; vuelca la fusión en
    ``config/dotenv_wizard_proposed.env``.

    Returns:
        True si se escribió ``.env``; False si solo se escribió la propuesta.
    """
    if is_repo_dotenv_immutable(repo_root):
        merge_proposed_env_file(repo_root, updates)
        return False
    env_path = repo_root / ".env"
    keys_done: set[str] = set()
    new_lines: list[str] = []
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in line:
                new_lines.append(line)
                continue
            k, _, _ = line.partition("=")
            k = k.strip()
            if k in updates:
                new_lines.append(f"{k}={updates[k]}")
                keys_done.add(k)
            else:
                new_lines.append(line)
    for key, val in updates.items():
        if key not in keys_done:
            new_lines.append(f"{key}={val}")
    atomic_write(env_path, "\n".join(new_lines) + "\n")
    return True


def _ensure_mcp_yaml_telegram_enabled(repo_root: Path) -> None:
    path = repo_root / "config" / "mcp_servers.yaml"
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    pattern_replace = re.compile(
        r"(^  telegram:\s*\n)(\s*)enabled:\s*\S+",
        re.MULTILINE,
    )
    new_text, n = pattern_replace.subn(r"\1\2enabled: true", text, count=1)
    if n == 0:
        new_text, n2 = re.subn(
            r"(^  telegram:\s*\n)",
            r"\1    enabled: true\n",
            text,
            count=1,
            flags=re.MULTILINE,
        )
        if n2:
            text = new_text
        else:
            return
    else:
        text = new_text
    atomic_write(path, text)


def seed_telegram_guard_admins(
    repo_root: Path,
    db_path: Path,
    draft: SovereignDraft,
    console_print,
) -> None:
    """
    Inserta en ``main.authorized_users`` al creador del wizard y admins extra (role=admin).
    Requiere ``wizard_creator_telegram_user_id`` numérico.
    """
    creator = (draft.wizard_creator_telegram_user_id or "").strip()
    if not creator or not creator.isdigit():
        console_print(
            "[yellow]Telegram Guard:[/] sin ``wizard_creator_telegram_user_id`` válido; "
            "no se sembraron admins (añade tu ID con ``duckops init`` de nuevo o inserta en DuckDB)."
        )
        return
    tenant = (draft.tenant_id or "default").strip() or "default"
    ids: list[str] = [creator]
    raw_extra = (draft.wizard_extra_admin_telegram_ids or "").replace(";", ",")
    for part in raw_extra.split(","):
        p = part.strip()
        if p.isdigit() and p not in ids:
            ids.append(p)
    orig = sys.path[:]
    try:
        sys.path.insert(0, str(repo_root))
        from duckclaw import DuckClaw  # noqa: PLC0415

        db = DuckClaw(str(db_path.resolve()))
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS main.authorized_users (
                tenant_id VARCHAR,
                user_id VARCHAR,
                username VARCHAR,
                role VARCHAR DEFAULT 'user',
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (tenant_id, user_id)
            );
            """
        )
        creator_uname = (draft.wizard_creator_admin_display_name or "").strip()
        for uid in ids:
            db.execute(
                "DELETE FROM main.authorized_users WHERE tenant_id = ? AND user_id = ?",
                [tenant, uid],
            )
            uname = creator_uname if uid == creator else ""
            db.execute(
                "INSERT INTO main.authorized_users (tenant_id, user_id, username, role) VALUES (?, ?, ?, ?)",
                [tenant, uid, uname, "admin"],
            )
        console_print(
            f"[green]Telegram Guard:[/] {len(ids)} usuario(s) con rol admin "
            f"(tenant_id={tenant!r}) en {db_path}"
        )
    except Exception as exc:
        console_print(f"[red]Telegram Guard:[/] no se pudo sembrar authorized_users: {exc}")
    finally:
        sys.path[:] = orig


def ensure_duckdb_file(repo_root: Path, relative_or_abs: str) -> bool:
    p = Path(relative_or_abs)
    if not p.is_absolute():
        p = (repo_root / p).resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.is_file():
        return True
    orig = sys.path[:]
    try:
        sys.path.insert(0, str(repo_root))
        from duckclaw import DuckClaw  # noqa: PLC0415

        DuckClaw(str(p)).execute("SELECT 1")
        return True
    except Exception:
        return False
    finally:
        sys.path[:] = orig


def telegram_webhook_post_deploy_message(draft: SovereignDraft) -> str:
    """
    Texto post-despliegue: instrucciones manuales y curl de respaldo.
    Tras reiniciar PM2, ``materialize`` llama a la Bot API (setWebhook) cuando hay token y URL.
    """
    port = int(draft.gateway_port)
    base = (draft.telegram_webhook_public_base_url or "").strip().rstrip("/")
    path = "/api/v1/telegram/webhook"
    full_url = f"{base}{path}" if base else f"https://TU_TUNEL_A_PUERTO_{port}{path}"
    pm2n = (draft.gateway_pm2_name or "").strip() or "este gateway"
    payload = {
        "url": full_url,
        "secret_token": "<TELEGRAM_WEBHOOK_SECRET>",
        "allowed_updates": ["message", "edited_message"],
    }
    curl_body = json.dumps(payload)
    curl_block = (
        'curl -sS -X POST "https://api.telegram.org/bot<BOT_TOKEN>/setWebhook" \\\n'
        '  -H "Content-Type: application/json" \\\n'
        f"  -d '{curl_body}'"
    )
    lines = [
        "[bold cyan]Telegram — webhook entrante[/]",
        "",
        "[green]El wizard intentará registrar setWebhook[/] contra la Bot API cuando hay token y URL HTTPS; "
        "si falla la red o la API, usa el curl de abajo.",
        "",
        f"Cada [bold]bot[/] (token) necesita su propio [bold]setWebhook[/] apuntando al proceso que escucha su puerto.",
        f"Este wizard configuró [bold]{pm2n}[/] en el puerto [bold]{port}[/] (revisa config/api_gateways_pm2.json si tienes varios).",
        f"URL completa del webhook: [bold]{full_url}[/]",
        "",
        "Si usas [bold]TELEGRAM_WEBHOOK_SECRET[/] en .env, reemplaza el marcador en [bold]secret_token[/] por el mismo valor.",
        "",
        "[dim]# Sustituye BOT_TOKEN y el marcador del secret_token[/]",
        curl_block,
        "",
        "[dim]Comprobar:[/] curl -sS \"https://api.telegram.org/bot<BOT_TOKEN>/getWebhookInfo\"",
        "",
        "Revisa [bold]last_error_message[/]: si Telegram no puede conectar al HTTPS del webhook, ahí suele aparecer el motivo.",
        "Si tienes [bold]TELEGRAM_WEBHOOK_SECRET[/] en .env, [bold]secret_token[/] en setWebhook debe ser idéntico; si no, el gateway responde 403 y en logs verás el aviso correspondiente.",
        "",
        "Si [bold]url[/] sale vacía o [bold]pending_update_count[/] crece, Telegram no está llegando al gateway correcto.",
        "",
    ]
    ts_funnel_hint = draft.tailscale_funnel_bg_via_wizard or (
        base.lower().endswith(".ts.net") if base else False
    )
    if ts_funnel_hint:
        lines.append(
            "[dim]Funnel/Tailscale: revisa [bold]tailscale funnel status[/]. "
            "Con [bold]--bg[/] suele sobrevivir reinicios del servicio. "
            "https://tailscale.com/kb/1223/funnel/[/]"
        )
    cfpm = (draft.cloudflared_pm2_process_name or "").strip()
    if cfpm:
        lines.append(
            f"[dim]Cloudflare Quick Tunnel (PM2): [bold]{cfpm}[/]. [bold]pm2 list[/] · [bold]pm2 save[/].[/]"
        )
    return "\n".join(lines)


def save_wizard_config_json(draft: SovereignDraft) -> None:
    path = _wizard_config_path()
    prev: dict = {}
    if path.exists():
        try:
            prev = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(prev, dict):
                prev = {}
        except Exception:
            prev = {}
    prev.update(
        {
            "mode": draft.mode,
            "channel": draft.channel,
            "bot_mode": draft.bot_mode,
            "llm_provider": draft.llm_provider,
            "llm_model": draft.llm_model,
            "llm_base_url": draft.llm_base_url,
            "db_path": draft.duckdb_vault_path,
            "gateway_pm2_name": draft.gateway_pm2_name,
            "gateway_tenant_id": (draft.tenant_id or "default").strip() or "default",
            "default_worker_id": (draft.default_worker_id or "").strip(),
            "gateway_port": int(draft.gateway_port),
            "wizard_creator_telegram_user_id": (draft.wizard_creator_telegram_user_id or "").strip(),
            "wizard_creator_admin_display_name": (draft.wizard_creator_admin_display_name or "").strip(),
            "wizard_extra_admin_telegram_ids": (draft.wizard_extra_admin_telegram_ids or "").strip(),
            "telegram_webhook_public_base_url": (draft.telegram_webhook_public_base_url or "").strip(),
            "cloudflared_pm2_process_name": (draft.cloudflared_pm2_process_name or "").strip(),
            "tailscale_funnel_bg_via_wizard": draft.tailscale_funnel_bg_via_wizard,
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, json.dumps(prev, indent=2) + "\n",
                 encoding="utf-8")


def materialize(
    repo_root: Path,
    draft: SovereignDraft,
    *,
    console_print,
    deploy_pm2: bool = True,
) -> int:
    """
    Aplica el borrador al disco. Devuelve 0 si OK, 1 si error crítico.
    """
    primary_rel = effective_primary_duckdb_relpath(draft)
    attach_rel = shared_attach_relpath(draft)

    _dw = (draft.default_worker_id or "").strip().lower()
    updates: dict[str, str] = {
        "REDIS_URL": draft.redis_url.strip(),
        "DUCKCLAW_REDIS_URL": draft.redis_url.strip(),
        "DUCKCLAW_DB_PATH": primary_rel,
        "DUCKDB_PATH": primary_rel,
        "DUCKCLAW_GATEWAY_TENANT_ID": draft.tenant_id.strip(),
        "DUCKCLAW_DEFAULT_WORKER_ID": draft.default_worker_id.strip(),
        "DUCKCLAW_LLM_PROVIDER": draft.llm_provider.strip(),
        "DUCKCLAW_LLM_MODEL": draft.llm_model.strip(),
        "DUCKCLAW_LLM_BASE_URL": draft.llm_base_url.strip(),
        "DUCKCLAW_PM2_PROCESS_NAME": draft.gateway_pm2_name.strip(),
    }
    # Gateways no-Finanz con tenant propio: bóveda inicial por slug de worker (p. ej. job_hunter).
    if _dw and _dw != "finanz":
        updates["DUCKCLAW_MULTI_VAULT_INITIAL_VAULT_ID"] = (draft.default_worker_id or "").strip()
    else:
        updates["DUCKCLAW_MULTI_VAULT_INITIAL_VAULT_ID"] = ""
    if attach_rel is not None:
        updates["DUCKCLAW_SHARED_DB_PATH"] = attach_rel
    elif (draft.duckdb_shared_path or "").strip():
        # Misma ruta que la principal (p. ej. solo rellenaron «shared»): no debe quedar
        # un segundo path en .env ni grants apuntando al mismo archivo.
        updates["DUCKCLAW_SHARED_DB_PATH"] = ""
    tok = draft.telegram_bot_token.strip()
    if tok:
        from duckclaw.integrations.telegram.telegram_agent_token import telegram_agent_token_env_name

        _wid = (draft.default_worker_id or "finanz").strip()
        _std_key = telegram_agent_token_env_name(_wid)
        if _std_key:
            updates[_std_key] = tok
        updates["TELEGRAM_BOT_TOKEN"] = tok
    sec = draft.telegram_webhook_secret.strip()
    if sec:
        updates["TELEGRAM_WEBHOOK_SECRET"] = sec
    ts = draft.duckclaw_tailscale_auth_key.strip()
    if ts:
        updates["DUCKCLAW_TAILSCALE_AUTH_KEY"] = ts

    updates["DUCKCLAW_TELEGRAM_MCP_ENABLED"] = "1" if draft.enable_telegram_mcp else "0"

    if draft.redis_local_managed:
        ok, msg = try_start_redis_local(repo_root)
        console_print(f"[Redis local] {msg}")
        if not ok:
            console_print("(Continuando; puedes arrancar Redis manualmente.)")

    try:
        wrote_env = merge_env_file(repo_root, updates)
        if not wrote_env:
            console_print(
                "[yellow].env inmutable[/]: no se modificó la raíz del repo (sentinel "
                "`.env.immutable` o `DUCKCLAW_DOTENV_IMMUTABLE`). Valores fusionados en "
                "[bold]config/dotenv_wizard_proposed.env[/]."
            )
    except Exception as e:
        console_print(f"Error escribiendo .env: {e}")
        return 1

    save_wizard_config_json(draft)

    if draft.enable_telegram_mcp:
        _ensure_mcp_yaml_telegram_enabled(repo_root)

    if not ensure_duckdb_file(repo_root, primary_rel):
        console_print(
            f"Advertencia: no se pudo crear la DuckDB en {primary_rel} "
            "(¿falta duckclaw en PYTHONPATH?)."
        )
    else:
        _db_abs = _resolve_repo_db_path(repo_root, primary_rel)
        seed_telegram_guard_admins(repo_root, _db_abs, draft, console_print)

    patch_security_policy(repo_root, draft.default_worker_id)

    patch_api_gateways_pm2_for_draft(repo_root, draft, console_print, env_updates=updates)

    console_print(telegram_webhook_post_deploy_message(draft))

    if draft.orchestration == "docker" and draft.generate_docker_compose:
        try:
            p = write_compose_override(repo_root)
            console_print(f"Escrito {p.relative_to(repo_root)}")
        except Exception as e:
            console_print(f"docker-compose: {e}")

    exit_code = 0
    if draft.orchestration == "pm2" and deploy_pm2:
        try:
            from duckclaw.ops.manager import serve  # noqa: PLC0415

            _env_file = repo_root / ".env"
            if _env_file.is_file():
                for _line in _env_file.read_text(encoding="utf-8").splitlines():
                    _line = _line.strip()
                    if _line and not _line.startswith("#") and "=" in _line:
                        _k, _, _v = _line.partition("=")
                        if _k.strip():
                            os.environ.setdefault(
                                _k.strip(),
                                _v.strip().strip("'\"").strip(),
                            )
            exit_code = serve(
                host="0.0.0.0",
                port=int(draft.gateway_port),
                pm2=True,
                gateway=True,
                name=draft.gateway_pm2_name.strip() or None,
                cwd=str(repo_root),
            )
        except Exception as e:
            console_print(
                f"PM2: {e}. Ejecuta: duckops serve --pm2 --gateway --port {draft.gateway_port}"
            )

    register_telegram_webhook_after_deploy(repo_root, draft, console_print)
    return exit_code


def save_draft_json(draft: SovereignDraft) -> Path:
    """Quick Save (Ctrl+S) — solo borrador, sin tocar .env del repo."""
    path = Path.home() / ".config" / "duckclaw" / "wizard_draft.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, draft.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


def load_draft_json() -> SovereignDraft | None:
    path = Path.home() / ".config" / "duckclaw" / "wizard_draft.json"
    if not path.is_file():
        return None
    try:
        return SovereignDraft.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception:
        return None
