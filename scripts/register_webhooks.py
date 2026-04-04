#!/usr/bin/env python3
"""
Registra ``setWebhook`` en la Bot API para ``DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES`` (formato compacto).

Usa ``DUCKCLAW_PUBLIC_URL`` + ``webhook_path`` de cada entrada y el token embebido en la variable.

Ejecución desde la raíz del repo::

    python scripts/register_webhooks.py

Requisitos: ``.env`` en la raíz con ``DUCKCLAW_PUBLIC_URL``, ``DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES`` compacto.
Opcional: ``TELEGRAM_WEBHOOK_SECRET`` → ``secret_token`` en el body (mismo valor para todos los bots).
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv_if_present() -> None:
    env_path = REPO_ROOT / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            key = k.strip()
            if not key or key in os.environ:
                continue
            os.environ[key] = v.strip().strip("'\"")


def main() -> int:
    _load_dotenv_if_present()
    os.environ.setdefault("DUCKCLAW_REPO_ROOT", str(REPO_ROOT))

    sys.path.insert(0, str(REPO_ROOT / "services" / "api-gateway"))
    from core.telegram_compact_webhook_routes import parse_compact_telegram_webhook_routes  # noqa: PLC0415

    public = (os.environ.get("DUCKCLAW_PUBLIC_URL") or "").strip().rstrip("/")
    raw = (os.environ.get("DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES") or "").strip()
    secret = (os.environ.get("TELEGRAM_WEBHOOK_SECRET") or "").strip()

    if not public:
        print("error: DUCKCLAW_PUBLIC_URL vacío", file=sys.stderr)
        return 1
    try:
        routes = parse_compact_telegram_webhook_routes(raw)
    except ValueError as exc:
        print(f"error: no se pudo parsear DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES: {exc}", file=sys.stderr)
        return 1
    if not routes:
        print(
            "error: no hay rutas compactas (esperado bot:token:/api/v1/telegram/… separado por comas). "
            "Si usas multiplex JSON, registra webhooks con otro método.",
            file=sys.stderr,
        )
        return 1

    for r in routes:
        hook_url = f"{public}{r.webhook_path}"
        body: dict[str, object] = {
            "url": hook_url,
            "allowed_updates": ["message", "edited_message"],
        }
        if secret:
            body["secret_token"] = secret
        payload = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{r.bot_token}/setWebhook",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")[:500]
            print(f"error: {r.bot_name} HTTP {e.code}: {err_body}", file=sys.stderr)
            return 1
        except OSError as e:
            print(f"error: {r.bot_name} red: {e}", file=sys.stderr)
            return 1
        if not isinstance(data, dict) or not data.get("ok"):
            print(f"error: {r.bot_name} API: {data}", file=sys.stderr)
            return 1
        print(f"OK  {r.bot_name}  setWebhook  {hook_url}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
