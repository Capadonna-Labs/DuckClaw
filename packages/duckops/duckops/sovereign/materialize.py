"""Escribir .env, wizard_config, MCP, compose, Strix y PM2 tras confirmar Review."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

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


def patch_api_gateways_pm2_for_draft(
    repo_root: Path,
    draft: SovereignDraft,
    console_print,
) -> None:
    """
    Alinea ``env.DUCKCLAW_DB_PATH`` (y opcionalmente ``DUCKCLAW_SHARED_DB_PATH``)
    del bloque PM2 con nombre ``draft.gateway_pm2_name``.

    El gateway cargado con PM2 **sobrescribe** ``DUCKCLAW_DB_PATH`` desde este JSON
    (ver ``api-gateway/main.py``); actualizar solo ``.env`` no bastaba.
    """
    cfg_path = repo_root / "config" / "api_gateways_pm2.json"
    if not cfg_path.is_file():
        return
    app_name = (draft.gateway_pm2_name or "").strip()
    if not app_name:
        return
    try:
        raw = json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception as exc:
        console_print(f"No se pudo leer api_gateways_pm2.json: {exc}")
        return
    apps = raw.get("apps") if isinstance(raw, dict) else None
    if not isinstance(apps, list):
        return
    idx: int | None = None
    for i, a in enumerate(apps):
        if isinstance(a, dict) and (a.get("name") or "").strip() == app_name:
            idx = i
            break
    if idx is None:
        console_print(
            f"Aviso: no hay app '{app_name}' en config/api_gateways_pm2.json — "
            "el proceso PM2 seguirá usando la DUCKCLAW_DB_PATH del JSON actual. "
            "Crea el bloque o edita el archivo a mano."
        )
        return

    primary_rel = effective_primary_duckdb_relpath(draft)
    primary_abs = _resolve_repo_db_path(repo_root, primary_rel)
    attach_rel = shared_attach_relpath(draft)

    app = apps[idx]
    env = app.get("env")
    if not isinstance(env, dict):
        env = {}
        app["env"] = env

    env["DUCKCLAW_DB_PATH"] = str(primary_abs)
    if attach_rel is not None:
        env["DUCKCLAW_SHARED_DB_PATH"] = str(_resolve_repo_db_path(repo_root, attach_rel))
    elif (draft.duckdb_shared_path or "").strip():
        # «Shared» era solo la principal: quitar clave secundaria del bloque PM2.
        env.pop("DUCKCLAW_SHARED_DB_PATH", None)

    atomic_write(cfg_path, json.dumps(raw, indent=2) + "\n", encoding="utf-8")
    console_print(f"PM2 config: DUCKCLAW_DB_PATH → {primary_abs}")
    if attach_rel is not None:
        console_print(f"PM2 config: DUCKCLAW_SHARED_DB_PATH → {env['DUCKCLAW_SHARED_DB_PATH']}")


def _wizard_config_path() -> Path:
    return Path.home() / ".config" / "duckclaw" / "wizard_config.json"


def merge_env_file(repo_root: Path, updates: dict[str, str]) -> None:
    """Fusiona claves en ``.env`` con backup .bak (vía atomic_write por archivo completo)."""
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
    if attach_rel is not None:
        updates["DUCKCLAW_SHARED_DB_PATH"] = attach_rel
    elif (draft.duckdb_shared_path or "").strip():
        # Misma ruta que la principal (p. ej. solo rellenaron «shared»): no debe quedar
        # un segundo path en .env ni grants apuntando al mismo archivo.
        updates["DUCKCLAW_SHARED_DB_PATH"] = ""
    tok = draft.telegram_bot_token.strip()
    if tok:
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
        merge_env_file(repo_root, updates)
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

    patch_security_policy(repo_root, draft.default_worker_id)

    patch_api_gateways_pm2_for_draft(repo_root, draft, console_print)

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
            from duckops.manager import serve  # noqa: PLC0415

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
