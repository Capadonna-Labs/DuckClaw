"""Verificación de firma Discord Interactions API y PATCH de follow-up (defer → mensaje)."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

_log = logging.getLogger(__name__)

DISCORD_API = "https://discord.com/api/v10"


def verify_discord_request_signature(
    *,
    body: bytes,
    signature_hex: str,
    timestamp_header: str,
    public_key_hex: str,
) -> bool:
    """
    Discord ed25519: message = timestamp (utf8) || body.
    Raises nothing; solo bool.
    """
    try:
        from nacl.signing import VerifyKey

        vk = VerifyKey(bytes.fromhex((public_key_hex or "").strip()))
        msg = (timestamp_header or "").encode("utf-8") + body
        vk.verify(msg, bytes.fromhex((signature_hex or "").strip()))
        return True
    except Exception as exc:
        _log.warning("Discord firma inválida: %s", exc)
        return False


def discord_followup_edit_original_sync(
    *,
    application_id: str,
    interaction_token: str,
    bot_token: str,
    content: str,
) -> bool:
    """
    Tras responder type 5 defer, PATCH al mensaje @original (primer chunk ≤2000).
    """
    app_id = (application_id or "").strip()
    tok = (interaction_token or "").strip()
    token = (bot_token or "").strip()
    if not app_id or not tok or not token:
        _log.warning("discord follow-up: falta application_id, token o bot_token")
        return False
    url = f"{DISCORD_API}/webhooks/{app_id}/{tok}/messages/@original"
    raw = content or ""
    chunk = raw[:1950]
    if len(raw) > 1950:
        chunk = chunk + "\n… (truncado)"

    payload: dict[str, Any] = {"content": chunk}
    try:
        with httpx.Client(timeout=45.0) as client:
            r = client.patch(
                url,
                json=payload,
                headers={"Authorization": f"Bot {token}"},
            )
            if not r.is_success:
                _log.warning("Discord PATCH follow-up HTTP %s: %s", r.status_code, r.text[:400])
                return False
            return True
    except Exception as exc:
        _log.warning("Discord PATCH error: %s", exc)
        return False


def parse_slash_duckclaw(interaction_json: dict[str, Any]) -> tuple[str, str | None]:
    """Devuelve (texto_usuario, error_msg). Comando slash ``duckclaw`` con opción ``mensaje`` (string)."""
    data = interaction_json.get("data") if isinstance(interaction_json, dict) else None
    if not isinstance(data, dict):
        return "", "sin data"
    if str(data.get("name") or "").strip().lower() != "duckclaw":
        return "", "comando no soportado"
    options = data.get("options") or []
    if not isinstance(options, list) or not options:
        return "", "uso: /duckclaw mensaje:<texto>"
    for opt in options:
        if not isinstance(opt, dict):
            continue
        if str(opt.get("name") or "").strip().lower() == "mensaje":
            v = opt.get("value")
            if v is not None:
                txt = str(v).strip()
                if txt:
                    return txt, None
            return "", "mensaje vacío"
    fir = options[0]
    if isinstance(fir, dict) and fir.get("value") is not None:
        txt = str(fir["value"]).strip()
        if txt:
            return txt, None
    return "", "uso: /duckclaw mensaje:<texto>"


def discord_interaction_deferred_payload() -> dict[str, Any]:
    return {"type": 5}
