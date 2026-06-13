"""Cancelación de señales en ledger finance_worker / quant_core (fly + tool Quant)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable

_FULL_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)

CANCEL_SIGNAL_STATUSES_NORMAL: tuple[str, ...] = (
    "PENDING_HITL",
    "AWAITING_HITL",
    "PENDING",
    "FAILED",
)
CANCEL_SIGNAL_STATUS_IN_SQL = (
    "'PENDING_HITL','AWAITING_HITL','PENDING','FAILED'"
)


@dataclass(frozen=True)
class CancelSignalOutcome:
    ok: bool
    message: str
    signal_id: str = ""
    previous_status: str = ""
    already_cancelled: bool = False


def resolve_trade_signal_status(db: Any, sid: str) -> tuple[str, str]:
    """
    Estado actual de la señal: finance_worker primero, luego quant_core.
    Retorna (status_upper, source_label) o ("", "") si no existe.
    """
    if db is None:
        return "", ""
    qsid = sid.replace("'", "''")
    for schema, label in (
        ("finance_worker", "finance_worker"),
        ("quant_core", "quant_core"),
    ):
        try:
            raw = db.query(
                f"SELECT status FROM {schema}.trade_signals "
                f"WHERE signal_id = '{qsid}' LIMIT 1"
            )
            rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
        except Exception:
            rows = []
        if rows and isinstance(rows[0], dict):
            st = str(rows[0].get("status") or "").strip().upper()
            return st, label
    return "", ""


def _collect_signal_ids_by_prefix(db: Any, prefix: str) -> list[str]:
    """IDs únicos que empiezan por prefix (hex, case-insensitive)."""
    if db is None or not prefix:
        return []
    esc = prefix.replace("'", "''")
    seen: set[str] = set()
    ordered: list[str] = []
    for schema in ("finance_worker", "quant_core"):
        try:
            raw = db.query(
                f"SELECT signal_id FROM {schema}.trade_signals "
                f"WHERE LOWER(signal_id) LIKE '{esc}%' "
                "ORDER BY signal_id LIMIT 16"
            )
            rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
        except Exception:
            rows = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            sid = str(row.get("signal_id") or "").strip().lower()
            if sid and sid not in seen:
                seen.add(sid)
                ordered.append(sid)
    return ordered


def resolve_signal_id_from_input(db: Any, raw: str) -> tuple[str | None, str | None]:
    """
    UUID completo o prefijo único.
    Retorna (signal_id, error_msg).
    """
    text = (raw or "").strip().lower()
    if not text:
        return None, "signal_id requerido"
    if _FULL_UUID_RE.match(text):
        return text, None
    prefix = re.sub(r"[^0-9a-f]", "", text)
    if len(prefix) < 4:
        return None, "Prefijo UUID demasiado corto (mínimo 4 caracteres hex)"
    matches = _collect_signal_ids_by_prefix(db, prefix)
    if not matches:
        return None, f"Ninguna señal coincide con prefijo '{prefix}'"
    if len(matches) > 1:
        sample = ", ".join(matches[:8])
        extra = f" (+{len(matches) - 8} más)" if len(matches) > 8 else ""
        return None, f"Prefijo ambiguo ({len(matches)} señales): {sample}{extra}"
    return matches[0], None


def cancel_signal_sql_statements(*, sid: str, force: bool) -> list[tuple[str, list[str]]]:
    """Pares (sql, params) para finance_worker y quant_core."""
    if force:
        where = "signal_id = ? AND UPPER(TRIM(COALESCE(status,''))) != 'EXECUTED'"
    else:
        where = (
            f"signal_id = ? AND UPPER(TRIM(COALESCE(status,''))) IN "
            f"({CANCEL_SIGNAL_STATUS_IN_SQL})"
        )
    return [
        (
            f"UPDATE finance_worker.trade_signals SET status='CANCELLED' WHERE {where}",
            [sid],
        ),
        (
            f"UPDATE quant_core.trade_signals SET status='CANCELLED', updated_at=now() "
            f"WHERE {where}",
            [sid],
        ),
    ]


def cancel_trade_signal_in_ledger(
    db: Any,
    signal_id: str,
    *,
    force: bool = False,
    tenant_id: str = "default",
    apply_sql: Callable[..., tuple[bool, str]] | None = None,
    resolve_prefix: bool = True,
) -> CancelSignalOutcome:
    """
    Cancela una señal en el ledger. Usa apply_sql(db, statements, tenant_id=…) para persistir.
    """
    tid = str(tenant_id or "default").strip() or "default"
    sid = (signal_id or "").strip().lower()
    if resolve_prefix and not _FULL_UUID_RE.match(sid):
        resolved, err = resolve_signal_id_from_input(db, sid)
        if err:
            return CancelSignalOutcome(ok=False, message=err)
        sid = resolved or ""

    if not sid:
        return CancelSignalOutcome(ok=False, message="signal_id requerido")

    st, _src = resolve_trade_signal_status(db, sid)
    if not st:
        return CancelSignalOutcome(
            ok=False,
            message="Señal no encontrada en finance_worker.trade_signals ni quant_core.trade_signals.",
            signal_id=sid,
        )
    if st == "CANCELLED":
        return CancelSignalOutcome(
            ok=True,
            message=f"Señal {sid} ya está CANCELLED.",
            signal_id=sid,
            previous_status=st,
            already_cancelled=True,
        )
    if force and st == "EXECUTED":
        return CancelSignalOutcome(
            ok=False,
            message="No se puede cancelar: la señal ya está EXECUTED.",
            signal_id=sid,
            previous_status=st,
        )
    if not force and st not in CANCEL_SIGNAL_STATUSES_NORMAL:
        return CancelSignalOutcome(
            ok=False,
            message=(
                f"No se puede cancelar: estado actual {st}. "
                "Solo se pueden cancelar señales pendientes o fallidas."
            ),
            signal_id=sid,
            previous_status=st,
        )

    if apply_sql is None:
        from duckclaw.graphs.on_the_fly_commands import _vault_apply_sql_statements

        apply_sql = _vault_apply_sql_statements

    ok, detail = apply_sql(
        db,
        cancel_signal_sql_statements(sid=sid, force=force),
        tenant_id=tid,
    )
    if not ok:
        return CancelSignalOutcome(
            ok=False,
            message=f"No se pudo cancelar la señal: {detail}",
            signal_id=sid,
            previous_status=st,
        )
    return CancelSignalOutcome(
        ok=True,
        message=f"Señal {sid} cancelada (era {st}).",
        signal_id=sid,
        previous_status=st,
    )
