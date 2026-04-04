"""Registrar webhook en Telegram Bot API tras el deploy del Sovereign Wizard."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from duckclaw.dotenv_immutable import merged_root_and_proposed_flat_env

from duckops.sovereign.draft import SovereignDraft

_WEBHOOK_PATH = "/api/v1/telegram/webhook"
_SET_WEBHOOK_TIMEOUT_SEC = 45


def _effective_telegram_bot_token(repo_root: Path, draft: SovereignDraft) -> str:
    t = (draft.telegram_bot_token or "").strip()
    if t:
        return t
    kv = merged_root_and_proposed_flat_env(repo_root)
    from duckclaw.integrations.telegram.telegram_agent_token import resolve_telegram_token_from_flat_env

    wid = (getattr(draft, "default_worker_id", None) or "finanz").strip()
    return resolve_telegram_token_from_flat_env(kv, wid)


def _effective_telegram_webhook_secret(repo_root: Path, draft: SovereignDraft) -> str:
    """Mismo valor que verá el gateway: borrador, o fusión .env + proposed (inmutable)."""
    s = (draft.telegram_webhook_secret or "").strip()
    if s:
        return s
    kv = merged_root_and_proposed_flat_env(repo_root)
    return (kv.get("TELEGRAM_WEBHOOK_SECRET") or "").strip()


def webhook_full_url_for_draft(draft: SovereignDraft) -> str | None:
    base = (draft.telegram_webhook_public_base_url or "").strip().rstrip("/")
    if not base:
        return None
    if "TU_TUNEL" in base.upper():
        return None
    return f"{base}{_WEBHOOK_PATH}"


def build_set_webhook_body(
    repo_root: Path,
    draft: SovereignDraft,
) -> dict[str, Any] | None:
    url = webhook_full_url_for_draft(draft)
    if not url:
        return None
    body: dict[str, Any] = {
        "url": url,
        "allowed_updates": ["message", "edited_message"],
    }
    sec = _effective_telegram_webhook_secret(repo_root, draft)
    if sec:
        body["secret_token"] = sec
    return body


def call_set_webhook_sync(bot_token: str, body: dict[str, Any]) -> dict[str, Any]:
    raw = json.dumps(body).encode("utf-8")
    req = Request(
        f"https://api.telegram.org/bot{bot_token}/setWebhook",
        data=raw,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=_SET_WEBHOOK_TIMEOUT_SEC) as resp:
        text = resp.read().decode("utf-8")
    data = json.loads(text)
    if not isinstance(data, dict):
        return {"ok": False, "description": "respuesta no JSON objeto"}
    return data


def register_compact_telegram_webhooks_if_configured(
    repo_root: Path,
    console_print: Callable[[str], None],
    *,
    flat_env: dict[str, str] | None = None,
) -> bool:
    """
    Si ``DUCKCLAW_PUBLIC_URL`` y ``DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES`` (formato compacto) están
    definidos, registra un ``setWebhook`` por bot (mismo comportamiento que ``scripts/register_webhooks.py``).

    Returns:
        True si aplica multiplex compacto (se intentó ``setWebhook`` por ruta y **no** debe
        ejecutarse el flujo single-URL ``…/telegram/webhook``), aunque algún bot falle.
    """
    if flat_env is not None:
        kv = flat_env
    else:
        kv = merged_root_and_proposed_flat_env(repo_root)
    public = (kv.get("DUCKCLAW_PUBLIC_URL") or "").strip().rstrip("/")
    raw = (kv.get("DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES") or "").strip()
    if not public or not raw or raw.startswith("[") or ":/api/" not in raw:
        return False

    secret = (kv.get("TELEGRAM_WEBHOOK_SECRET") or "").strip()
    api_gw = repo_root / "services" / "api-gateway"
    if str(api_gw) not in sys.path:
        sys.path.insert(0, str(api_gw))
    from core.telegram_compact_webhook_routes import parse_compact_telegram_webhook_routes  # noqa: PLC0415

    try:
        routes = parse_compact_telegram_webhook_routes(raw)
    except ValueError as exc:
        console_print(f"[yellow]Telegram setWebhook (compacto): no se pudo parsear ROUTES: {exc}[/]")
        return False
    if not routes:
        return False

    console_print(
        "[bold cyan]Telegram — setWebhook modo path-multiplex[/] (``DUCKCLAW_PUBLIC_URL`` + ROUTES compacto)"
    )
    ok_any = False
    for r in routes:
        hook_url = f"{public}{r.webhook_path}"
        body: dict[str, Any] = {
            "url": hook_url,
            "allowed_updates": ["message", "edited_message"],
        }
        if secret:
            body["secret_token"] = secret
        try:
            result = call_set_webhook_sync(r.bot_token, body)
        except HTTPError as e:
            err_body = ""
            try:
                err_body = e.read().decode("utf-8", errors="replace")[:500]
            except Exception:
                pass
            console_print(
                f"[red]Telegram setWebhook[/] {r.bot_name}: HTTP {e.code} {err_body or e.reason}"
            )
            continue
        except URLError as e:
            console_print(f"[red]Telegram setWebhook[/] {r.bot_name}: red: {e.reason}")
            continue
        except TimeoutError:
            console_print(f"[red]Telegram setWebhook[/] {r.bot_name}: timeout")
            continue
        except json.JSONDecodeError as e:
            console_print(f"[red]Telegram setWebhook[/] {r.bot_name}: JSON inválido ({e})")
            continue
        except Exception as e:  # noqa: BLE001
            console_print(f"[red]Telegram setWebhook[/] {r.bot_name}: {e}")
            continue
        if result.get("ok"):
            console_print(f"[green]Telegram setWebhook OK[/] {r.bot_name} → {hook_url}")
            ok_any = True
        else:
            desc = result.get("description") or str(result)
            console_print(f"[red]Telegram setWebhook rechazado[/] {r.bot_name}: {desc}")
    if ok_any:
        console_print(
            "[dim]Comprueba:[/] ``getWebhookInfo`` por token; cada bot debe tener su propio path "
            "(no ``…/webhook`` genérico si usas multiplex por ruta)."
        )
    else:
        console_print(
            "[yellow]Ningún setWebhook compacto devolvió OK; revisa tokens/red. "
            "No se usará la URL única del borrador para no pisar el multiplex.[/]"
        )
    return True


def register_telegram_webhook_after_deploy(
    repo_root: Path,
    draft: SovereignDraft,
    console_print: Callable[[str], None],
) -> None:
    """
    Llama a setWebhook si hay token (borrador o .env) y URL HTTPS pública válida.
    No interrumpe el deploy: errores de red o API se muestran como aviso.

    Si existe ``DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES`` en formato compacto y ``DUCKCLAW_PUBLIC_URL``,
    registra un webhook por bot y **no** usa la URL única ``…/telegram/webhook`` del borrador.
    """
    if register_compact_telegram_webhooks_if_configured(repo_root, console_print):
        return

    token = _effective_telegram_bot_token(repo_root, draft)
    body = build_set_webhook_body(repo_root, draft)
    if not token:
        console_print(
            "[dim]Telegram setWebhook omitido: no hay token en el borrador ni "
            "TELEGRAM_<ID_AGENT>_TOKEN / TELEGRAM_BOT_TOKEN en .env ni "
            "config/dotenv_wizard_proposed.env (según default_worker_id del borrador).[/]"
        )
        return
    if not body:
        console_print(
            "[dim]Telegram setWebhook omitido: falta URL HTTPS pública del webhook "
            "(Tailscale Funnel / manual).[/]"
        )
        return

    try:
        result = call_set_webhook_sync(token, body)
    except HTTPError as e:
        err_body = ""
        try:
            err_body = e.read().decode("utf-8", errors="replace")[:500]
        except Exception:
            pass
        console_print(
            f"[red]Telegram setWebhook error HTTP {e.code}[/]: {err_body or e.reason}"
        )
        return
    except URLError as e:
        console_print(f"[red]Telegram setWebhook error de red:[/] {e.reason}")
        return
    except TimeoutError:
        console_print("[red]Telegram setWebhook:[/] timeout al contactar api.telegram.org")
        return
    except json.JSONDecodeError as e:
        console_print(f"[red]Telegram setWebhook:[/] JSON inválido en respuesta ({e})")
        return
    except Exception as e:  # noqa: BLE001
        console_print(f"[red]Telegram setWebhook:[/] {e}")
        return

    if result.get("ok"):
        url_set = body.get("url", "")
        console_print(f"[green]Telegram setWebhook OK[/] → [bold]{url_set}[/]")
        console_print(
            "[dim]Comprueba:[/] curl -sS \"https://api.telegram.org/bot<TOKEN>/getWebhookInfo\""
        )
        return

    desc = result.get("description") or result.get("error_code") or str(result)
    console_print(f"[red]Telegram setWebhook rechazado:[/] {desc}")
