"""HITL service for SLM adapter promotion (Model-Guard)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _pending_path() -> Path:
    root = Path(os.environ.get("DUCKCLAW_REPO_ROOT") or ".").resolve()
    return root / "db" / "private" / "slm_model_approvals_pending.json"


def request_model_approval(
    *,
    adapter_path: str,
    summary: str = "",
    chat_id: str = "",
) -> str:
    """Registra solicitud pendiente de promoción de adapter LoRA."""
    adapter = (adapter_path or "").strip()
    if not adapter:
        return json.dumps({"ok": False, "error": "adapter_path requerido"}, ensure_ascii=False)
    pending_file = _pending_path()
    pending_file.parent.mkdir(parents=True, exist_ok=True)
    record: dict[str, Any] = {
        "adapter_path": adapter,
        "summary": (summary or "").strip(),
        "chat_id": (chat_id or "").strip(),
        "status": "pending",
    }
    try:
        existing: list[dict[str, Any]] = []
        if pending_file.is_file():
            raw = json.loads(pending_file.read_text(encoding="utf-8") or "[]")
            if isinstance(raw, list):
                existing = [r for r in raw if isinstance(r, dict)]
        existing = [r for r in existing if r.get("adapter_path") != adapter]
        existing.append(record)
        pending_file.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)
    return json.dumps(
        {
            "ok": True,
            "status": "pending",
            "adapter_path": adapter,
            "message": (
                "Solicitud HITL registrada. Un admin debe ejecutar "
                f"/approve-model {adapter} tras revisar el veredicto."
            ),
        },
        ensure_ascii=False,
    )


def approve_model_adapter(
    *,
    adapter_path: str,
    chat_id: str = "",
) -> dict[str, Any]:
    """
    Aprueba promoción: actualiza registro pendiente y devuelve instrucciones PM2.
    La aplicación real de MLX_ADAPTER_PATH requiere recycle MLX-Inference en el host Mac.
    """
    adapter = (adapter_path or "").strip()
    if not adapter:
        return {"ok": False, "error": "adapter_path requerido"}
    pending_file = _pending_path()
    updated = False
    try:
        if pending_file.is_file():
            raw = json.loads(pending_file.read_text(encoding="utf-8") or "[]")
            rows = raw if isinstance(raw, list) else []
            for row in rows:
                if isinstance(row, dict) and row.get("adapter_path") == adapter:
                    row["status"] = "approved"
                    row["approved_chat_id"] = (chat_id or "").strip()
                    updated = True
            pending_file.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    return {
        "ok": True,
        "adapter_path": adapter,
        "pending_updated": updated,
        "message": (
            f"✅ Modelo aprobado: {adapter}\n"
            "En el Mac mini:\n"
            f"  1. MLX_ADAPTER_PATH={adapter}\n"
            "  2. pm2 restart MLX-Inference --update-env\n"
            "  3. Verifica GET /v1/models en :8080"
        ),
    }
