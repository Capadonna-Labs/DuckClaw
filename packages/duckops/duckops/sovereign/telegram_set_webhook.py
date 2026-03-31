"""Registrar webhook en Telegram Bot API tras el deploy del Sovereign Wizard."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from duckops.sovereign.draft import SovereignDraft

_WEBHOOK_PATH = "/api/v1/telegram/webhook"
_SET_WEBHOOK_TIMEOUT_SEC = 45


def _effective_telegram_bot_token(repo_root: Path, draft: SovereignDraft) -> str:
    t = (draft.telegram_bot_token or "").strip()
    if t:
        return t
    env_path = repo_root / ".env"
    if not env_path.is_file():
        return ""
    for line in env_path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith("#") or "=" not in s:
            continue
        key, _, val = s.partition("=")
        if key.strip() == "TELEGRAM_BOT_TOKEN":
            return val.strip().strip("'\"")
    return ""


def _effective_telegram_webhook_secret(repo_root: Path, draft: SovereignDraft) -> str:
    """Mismo valor que verá el gateway: borrador si existe, si no la clave ya fusionada en .env."""
    s = (draft.telegram_webhook_secret or "").strip()
    if s:
        return s
    env_path = repo_root / ".env"
    if not env_path.is_file():
        return ""
    for line in env_path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if raw.startswith("#") or "=" not in raw:
            continue
        key, _, val = raw.partition("=")
        if key.strip() == "TELEGRAM_WEBHOOK_SECRET":
            return val.strip().strip("'\"")
    return ""


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


def register_telegram_webhook_after_deploy(
    repo_root: Path,
    draft: SovereignDraft,
    console_print: Callable[[str], None],
) -> None:
    """
    Llama a setWebhook si hay token (borrador o .env) y URL HTTPS pública válida.
    No interrumpe el deploy: errores de red o API se muestran como aviso.
    """
    token = _effective_telegram_bot_token(repo_root, draft)
    body = build_set_webhook_body(repo_root, draft)
    if not token:
        console_print(
            "[dim]Telegram setWebhook omitido: no hay TELEGRAM_BOT_TOKEN en el borrador ni en .env.[/]"
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
