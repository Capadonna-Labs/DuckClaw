"""Skill: handoff_trigger — solicita transferencia a humano (HITL).

Spec: specs/Protocolo_Escalamiento_Humano_HITL_Handoff.md
"""

from __future__ import annotations

import json
import os
from typing import Any

from langchain_core.tools import StructuredTool

from duckclaw.activity.handoff_context import get_handoff_thread_id


def get_tools(db: Any, schema_name: str, spec: Any = None) -> list:
    def handoff_trigger(reason: str, context_summary: str) -> str:
        """
        Solicita transferencia a un especialista humano. Usa cuando no puedes resolver
        la consulta, el cliente pide asesor humano, o hay frustración/urgencia.
        """
        reason = (reason or "").strip()[:200]
        context = (context_summary or "").strip()[:500]
        if not reason and not context:
            return json.dumps({"error": "Indica reason o context_summary."})

        try:
            from duckclaw.activity.session_state import SessionStateManager
            mgr = SessionStateManager()
            thread_id = get_handoff_thread_id()
            mgr.request_handoff(thread_id, reason or "Escalamiento solicitado", context)

            # Webhook n8n (opcional)
            webhook = os.environ.get("HITL_N8N_WEBHOOK_URL", "").strip()
            if webhook:
                try:
                    import urllib.request
                    data = json.dumps({
                        "thread_id": thread_id,
                        "reason": reason,
                        "context_summary": context,
                        "status": "HANDOFF_REQUESTED",
                    }).encode("utf-8")
                    req = urllib.request.Request(
                        webhook,
                        data=data,
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    urllib.request.urlopen(req, timeout=5)
                except Exception:
                    pass

            return json.dumps({
                "message": "He notificado a un especialista. Te contactarán en breve.",
                "status": "HANDOFF_REQUESTED",
            })
        except Exception as e:
            return json.dumps({"error": str(e), "message": "No se pudo notificar. Intenta de nuevo."})

    return [
        StructuredTool.from_function(
            handoff_trigger,
            name="handoff_trigger",
            description="Solicita transferencia a un humano. Usa cuando: el cliente pide asesor/llamada, no encuentras el producto, o detectas frustración. reason: motivo; context_summary: resumen de la necesidad.",
        )
    ]
