"""Infrastructure health and heartbeat chat commands."""

from __future__ import annotations

import os
import time
import urllib.request
from typing import Any, Protocol


class HeartbeatAdapter(Protocol):
    def heartbeat_redis_configured(self) -> bool: ...

    def heartbeat_outbound_configured(self) -> bool: ...

    def is_admin_ui_chat_session(self, chat_id: str) -> bool: ...

    def is_chat_heartbeat_enabled(self, tenant_id: str, chat_id: str) -> bool: ...

    def set_chat_heartbeat_enabled(
        self, tenant_id: str, chat_id: str, on: bool
    ) -> tuple[bool, str]: ...


_heartbeat_adapter: HeartbeatAdapter | None = None


def configure_heartbeat_adapter(adapter: HeartbeatAdapter | None) -> None:
    """Inject the runtime heartbeat backend from the graph facade."""
    global _heartbeat_adapter
    _heartbeat_adapter = adapter


def execute_heartbeat(db: Any, chat_id: Any, on_off: str, *, tenant_id: Any = None) -> str:
    """/heartbeat on|off — DM proactivos mientras el agente usa herramientas."""
    del db
    adapter = _heartbeat_adapter
    tid = str(tenant_id or "default").strip() or "default"
    cid = str(chat_id if chat_id is not None else "unknown").strip() or "unknown"
    v = (on_off or "").strip().lower()

    if adapter is None or not adapter.heartbeat_redis_configured():
        return (
            "Heartbeat requiere Redis (REDIS_URL o DUCKCLAW_REDIS_URL). Sin eso no se puede guardar el estado."
        )
    if v in ("on", "1", "true", "sí", "si"):
        if adapter.is_chat_heartbeat_enabled(tid, cid):
            return "✅ Heartbeat ya estaba activado."
        ok, err = adapter.set_chat_heartbeat_enabled(tid, cid, True)
        if not ok:
            return f"No se pudo activar heartbeat: {err}"
        if adapter.is_admin_ui_chat_session(cid):
            return "✅ Heartbeat activado. Verás plan y herramientas en este chat mientras ejecuto la tarea."
        if not adapter.heartbeat_outbound_configured():
            return (
                "Heartbeat activado en Redis, pero falta TELEGRAM_BOT_TOKEN (recomendado) o un webhook "
                "(TELEGRAM_BOT_TOKEN o DUCKCLAW_HEARTBEAT_WEBHOOK_URL); no se enviarán DMs."
            )
        return "✅ Heartbeat activado. Te avisaré por DM mientras uso herramientas."
    if v in ("off", "0", "false"):
        if not adapter.is_chat_heartbeat_enabled(tid, cid):
            return "Heartbeat ya estaba desactivado."
        ok, err = adapter.set_chat_heartbeat_enabled(tid, cid, False)
        if not ok:
            return f"No se pudo desactivar heartbeat: {err}"
        return "✅ Heartbeat desactivado."

    st = "on" if adapter.is_chat_heartbeat_enabled(tid, cid) else "off"
    return f"Heartbeat: {st}\nUso: /heartbeat on | /heartbeat off"


def execute_health(db: Any) -> str:
    """/health: estado de infraestructura (MLX, DuckDB, latencia)."""
    lines: list[str] = []
    try:
        db.query("SELECT 1")
        lines.append("✅ DuckDB: conectado")
    except Exception as exc:
        lines.append(f"❌ DuckDB: {exc}")

    base_url = (
        os.environ.get("DUCKCLAW_LLM_BASE_URL", "").strip()
        or "http://127.0.0.1:8080"
    )
    if base_url:
        base = base_url.rstrip("/")
        if base.endswith("/v1"):
            base = base[:-3]
        url = base + "/health"
        try:
            t0 = time.perf_counter()
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=3) as _resp:
                elapsed = int((time.perf_counter() - t0) * 1000)
                lines.append(f"✅ Inferencia ({url[:40]}...): {elapsed} ms")
        except Exception as exc:
            lines.append(f"⚠️ Inferencia: {exc}")
    return "\n".join(lines) or "Sin comprobaciones."
