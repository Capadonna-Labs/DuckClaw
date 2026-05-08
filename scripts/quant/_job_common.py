"""Utilidades internas scripts Core-Satellite (Telegram cola escritura vault)."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any


def _is_duckdb_file_lock_error(exc: BaseException) -> bool:
    """Contención al abrir el mismo archivo (db-writer RW u otro RO/RW ver packages/agents/.../graph_server.py)."""
    msg = str(exc).lower()
    return (
        "lock" in msg
        or "conflicting" in msg
        or "different configuration" in msg
    )


def open_duckclaw_readonly_retry(db_path: str) -> Any:
    """
    Abre DuckClaw en RO al vault con backoff si DuckDB rechaza por lock externo.

    Replica criterios de ``graph_server._open_duckclaw_readonly_with_retry`` para jobs PM2
    (singleton db-writer u otra conexión sobre el mismo .duckdb).
    """
    from duckclaw import DuckClaw

    resolved = str(Path(db_path).expanduser().resolve())
    raw_attempts = (
        os.environ.get("DUCKCLAW_GATEWAY_RO_LOCK_ATTEMPTS")
        or os.environ.get("DUCKCLAW_QUANT_JOB_RO_LOCK_ATTEMPTS")
        or "40"
    ).strip()
    try:
        attempts = max(1, min(int(raw_attempts), 120))
    except ValueError:
        attempts = 40
    raw_sleep = (os.environ.get("DUCKCLAW_GATEWAY_RO_LOCK_BASE_SLEEP_S") or "0.18").strip()
    try:
        base_sleep_s = float(raw_sleep)
    except ValueError:
        base_sleep_s = 0.18
    base_sleep_s = max(0.05, base_sleep_s)

    last: BaseException | None = None
    for i in range(attempts):
        try:
            db = DuckClaw(resolved, read_only=True)
            return db
        except Exception as exc:
            last = exc
            if _is_duckdb_file_lock_error(exc):
                delay_s = base_sleep_s * min(i + 1, 15)
                if i + 1 < attempts:
                    print(
                        f"[quant_job] DuckDB lock intento {i + 1}/{attempts} ({type(exc).__name__}); "
                        f"reintento en {delay_s:.2f}s",
                        file=sys.stderr,
                        flush=True,
                    )
                    time.sleep(delay_s)
                continue
            raise

    assert last is not None
    raise last

try:
    import httpx  # noqa: TID252
except ImportError:
    httpx = None  # type: ignore[misc, assignment]


def infer_vault_user_id(db_path: str) -> str:
    parts = Path(db_path).expanduser().resolve().parts
    if "private" in parts:
        i = parts.index("private")
        if i + 1 < len(parts):
            return str(parts[i + 1])
    return os.environ.get("DUCKCLAW_QUANT_JOB_USER_ID", "default").strip() or "default"


def enqueue_vault_sql(
    *,
    db_path: str,
    sql: str,
    params: list[Any] | None = None,
    tenant_id: str = "default",
    timeout_sec: float = 45.0,
    user_id_override: str | None = None,
) -> tuple[bool, str]:
    """Encola escritura DuckDB singleton y espera resultado."""
    from duckclaw.db_write_queue import DbWriteTaskStatus, enqueue_duckdb_write_sync, poll_task_status_sync

    resolved = str(Path(db_path).expanduser().resolve())
    uid = (user_id_override or infer_vault_user_id(resolved)).strip() or "default"
    tid = enqueue_duckdb_write_sync(
        db_path=resolved,
        query=sql,
        params=list(params or []),
        user_id=uid,
        tenant_id=str(tenant_id or "default").strip() or "default",
    )
    st: DbWriteTaskStatus | None = poll_task_status_sync(tid, timeout_sec=timeout_sec)
    if st is None:
        return False, "db-writer: timeout sin confirmación"
    if st.status != "success":
        return False, (st.detail or "writer failed").strip()
    return True, ""


def send_quant_alert_message(text: str) -> None:
    if not httpx:
        return
    webhook_url = os.environ.get("N8N_OUTBOUND_WEBHOOK_URL", "").strip()
    chat = os.environ.get("DUCKCLAW_QUANT_ALERT_CHAT_ID", "").strip()
    if not webhook_url or not chat:
        return
    headers: dict[str, str] = {}
    auth_key = os.environ.get("N8N_AUTH_KEY", "").strip()
    if auth_key:
        headers["X-DuckClaw-Secret"] = auth_key
    body = {"chat_id": chat, "text": str(text).replace("<", "&lt;"), "parse_mode": "HTML"}
    try:
        httpx.post(webhook_url, json=body, headers=headers, timeout=12.0)
    except Exception:
        pass


def fetch_ibkr_equity_and_positions_mv() -> tuple[float, dict[str, float], str]:
    """
    Retorna ``(equity_total, ticker_upper -> market_value_usd_nonneg, "")``;
    ante fallo configuración/red ``(0.0, {{}}, mensaje_corto)``.
    """
    import os

    from duckclaw.forge.skills.ibkr_bridge import _ibkr_resolve_payload_with_optional_alt

    api_url = (os.environ.get("IBKR_PORTFOLIO_API_URL") or "").strip()
    api_key = (
        os.environ.get("IBKR_PORTFOLIO_API_KEY") or os.environ.get("IBKR_MARKET_DATA_API_KEY") or ""
    ).strip()
    positions_url = (os.environ.get("IBKR_PORTFOLIO_POSITIONS_URL") or "").strip()
    if not api_url or not api_key:
        return 0.0, {}, "IBKR_PORTFOLIO_API_URL/KEY ausentes"

    try:
        data, _, _ = _ibkr_resolve_payload_with_optional_alt(api_url, api_key, positions_url)
    except Exception as exc:  # noqa: BLE001
        return 0.0, {}, str(exc)[:240]

    if not isinstance(data, dict):
        return 0.0, {}, "snapshot no dict"

    portfolio = data.get("portfolio") or data.get("positions") or []
    if isinstance(portfolio, dict):
        portfolio = list(portfolio.values()) if portfolio else []

    total_value = data.get("total_value")
    if total_value is None:
        total_value = data.get("net_liquidation") or data.get("equity") or data.get("value") or 0
    try:
        equity = float(total_value)
    except (TypeError, ValueError):
        equity = 0.0

    pos_mv: dict[str, float] = {}
    if isinstance(portfolio, list):
        for pos in portfolio:
            if not isinstance(pos, dict):
                continue
            sym = str(pos.get("symbol") or pos.get("ticker") or "").strip().upper()
            if not sym:
                continue
            mv = pos.get("market_value") or pos.get("marketValue") or pos.get("value") or 0
            try:
                pos_mv[sym] = pos_mv.get(sym, 0.0) + max(0.0, float(mv))
            except (TypeError, ValueError):
                continue

    if equity <= 0:
        equity = sum(pos_mv.values())

    return equity, pos_mv, ""


def enqueue_task_audit_warning(
    db_path: str,
    *,
    tenant_id: str,
    worker_id: str,
    plan_title: str,
    query_prefix: str,
) -> None:
    """Mejor esfuerzo: INSERT task_audit_log vía singleton writer."""
    import time
    import uuid

    task_id = f"TASK-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"

    def sq_esc(s: str | None, mx: int = 256) -> str:
        return (s or "").replace("'", "''")[:mx]

    sql = (
        f"""
        INSERT INTO task_audit_log (task_id, tenant_id, worker_id, query_prefix, status, duration_ms, plan_title)
        VALUES ('{sq_esc(task_id)}', '{sq_esc(tenant_id)}', '{sq_esc(worker_id)}', '{sq_esc(query_prefix)}', 'FAILED', 0, '{sq_esc(plan_title)}')
        """
    )
    enqueue_vault_sql(
        db_path=db_path,
        sql=sql,
        tenant_id=tenant_id,
        timeout_sec=45.0,
    )
