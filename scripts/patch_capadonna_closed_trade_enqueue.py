#!/usr/bin/env python3
"""Patch Capadonna trading_session_fly._enqueue_closed_trade to use typed commands.

Applies on the Capadonna-Driller tree (VPS). Safe to re-run (idempotent marker).

Usage (on VPS)::

    python scripts/patch_capadonna_closed_trade_enqueue.py \\
      --root /root/Capadonna-Driller
"""

from __future__ import annotations

import argparse
from pathlib import Path

MARKER = "duckclaw.closed_trade_enqueue"

OLD = '''def _enqueue_closed_trade(db: Any, tenant_id: str, draft: Any) -> bool:
    from capadonna_driller_lib.closed_trade_ledger import draft_to_mutation
    from .quant_state_delta import push_closed_trade_recorded_sync
    from .vault_sql import infer_user_id_for_audit_queue

    path = str(getattr(db, "_path", "") or "").strip()
    if not path or path == ":memory:":
        return False
    payload_base = {
        "tenant_id": str(tenant_id or "default").strip() or "default",
        "user_id": infer_user_id_for_audit_queue(path),
        "target_db_path": path,
    }
    mut = draft_to_mutation(draft, session_uid=_active_session_uid_for_close(db))
    ok = push_closed_trade_recorded_sync(payload_base, mut, duckclaw_db=db)
    _resume_vault_handle(db)
    return bool(ok)
'''

NEW = '''def _enqueue_closed_trade(db: Any, tenant_id: str, draft: Any) -> bool:
    """Enqueue verified close via DuckClaw InsertClosedTradeCommand (DB-Writer)."""
    from capadonna_driller_lib.closed_trade_ledger import draft_to_mutation
    from .vault_sql import infer_user_id_for_audit_queue

    path = str(getattr(db, "_path", "") or "").strip()
    if not path or path == ":memory:":
        return False
    mut = draft_to_mutation(draft, session_uid=_active_session_uid_for_close(db))
    uid = infer_user_id_for_audit_queue(path)
    tenant = str(tenant_id or "default").strip() or "default"
    try:
        from duckclaw.closed_trade_enqueue import enqueue_closed_trade_recorded

        tid = enqueue_closed_trade_recorded(
            mut,
            db_path=path,
            user_id=uid,
            tenant_id=tenant,
            duckclaw_db=db,
        )
        ok = bool(tid)
    except Exception:
        # Fallback: legacy quant state-delta path if typed enqueue unavailable.
        from .quant_state_delta import push_closed_trade_recorded_sync

        payload_base = {
            "tenant_id": tenant,
            "user_id": uid,
            "target_db_path": path,
        }
        ok = push_closed_trade_recorded_sync(payload_base, mut, duckclaw_db=db)
    _resume_vault_handle(db)
    return bool(ok)
'''


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True)
    args = ap.parse_args()
    target = (
        args.root
        / "workers"
        / "duckclaw"
        / "lib"
        / "trading_session_fly.py"
    )
    text = target.read_text(encoding="utf-8")
    if MARKER in text or "enqueue_closed_trade_recorded" in text:
        print(f"already patched: {target}")
        return 0
    if OLD not in text:
        print(f"expected block not found in {target}", flush=True)
        return 1
    target.write_text(text.replace(OLD, NEW, 1), encoding="utf-8")
    print(f"patched: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
