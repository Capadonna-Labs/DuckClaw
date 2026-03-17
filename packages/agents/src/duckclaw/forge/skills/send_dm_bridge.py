from __future__ import annotations

"""
SendPrivateMessage skill — enrutamiento cruzado (DM) para juegos tipo The Mind.

Contrato: send_dm(user_id: str, text: str)
Implementación: hace POST a un webhook de n8n configurado por entorno.
"""

import json
import os
from typing import Any, Optional


def _send_dm_tool(config: Optional[dict] = None) -> Optional[Any]:
    """
    Crea un StructuredTool para enviar mensajes privados (DM) vía n8n.

    Requiere:
    - DUCKCLAW_SEND_DM_WEBHOOK_URL: URL del webhook de n8n (p. ej. https://n8n/.../send-dm)
    - N8N_AUTH_KEY (opcional): cabecera de autenticación si n8n la exige.
    """
    cfg = config or {}
    if cfg.get("enabled") is False:
        return None

    url = cfg.get("webhook_url") or os.environ.get("DUCKCLAW_SEND_DM_WEBHOOK_URL", "").strip()
    if not url:
        # Sin URL configurada: no registrar la herramienta.
        return None

    try:
        from langchain_core.tools import StructuredTool
    except Exception:
        return None

    import urllib.request

    def _send_dm(user_id: str, text: str) -> str:
        user_id_str = (user_id or "").strip()
        if not user_id_str:
            return "Debes indicar user_id para enviar un DM."
        payload = {"user_id": user_id_str, "text": text or ""}
        body = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        auth_key = os.environ.get("N8N_AUTH_KEY", "").strip()
        if auth_key:
            headers["X-N8N-Auth"] = auth_key
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                status = resp.status
                if status in (200, 201, 202):
                    return "DM enviado (n8n aceptó la petición)."
                return f"n8n respondió con status={status} al enviar el DM."
        except Exception as e:  # noqa: BLE001
            return f"No se pudo enviar el DM vía n8n: {e}"

    return StructuredTool.from_function(
        _send_dm,
        name="send_dm",
        description=(
            "Envía un mensaje privado (DM) a un usuario específico. "
            "Parámetros: user_id (string), text (contenido del mensaje). "
            "Usa un webhook de n8n configurado en DUCKCLAW_SEND_DM_WEBHOOK_URL."
        ),
    )


def register_send_dm_skill(
    tools_list: list[Any],
    send_dm_config: Optional[dict] = None,
) -> None:
    """
    Registra la herramienta send_dm en la lista de tools.

    Llamar desde build_general_graph o desde build_worker_graph cuando el manifest/tools
    incluya 'send_dm'.
    """
    if not send_dm_config:
        send_dm_config = {"enabled": True}
    try:
        tool = _send_dm_tool(send_dm_config)
        if tool:
            tools_list.append(tool)
    except Exception:
        return

