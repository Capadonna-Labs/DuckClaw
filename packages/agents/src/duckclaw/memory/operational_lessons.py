"""Read tenant-scoped operational lessons for proactive reviews."""

from __future__ import annotations

import json
from typing import Any


def fetch_operational_lessons(
    db: Any,
    *,
    tenant_id: str,
    limit: int = 5,
    max_chars: int = 4_000,
) -> str:
    """Return recent operational lessons, never failing a proactive turn."""

    if not hasattr(db, "query"):
        return ""
    tenant = str(tenant_id or "default").strip() or "default"
    safe_tenant = tenant.replace("'", "''")[:256]
    rows_limit = max(1, min(int(limit), 20))
    cap = max(256, min(int(max_chars), 20_000))
    try:
        raw = db.query(
            "SELECT topic, COALESCE(NULLIF(insight, ''), content) AS lesson, created_at "
            "FROM main.semantic_memory "
            f"WHERE tenant_id = '{safe_tenant}' "
            "AND lower(COALESCE(source, '')) LIKE '%operational_lesson' "
            "ORDER BY created_at DESC NULLS LAST "
            f"LIMIT {rows_limit}"
        )
        data = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return ""
    if not isinstance(data, list):
        return ""

    blocks: list[str] = []
    used = 0
    for row in data:
        if not isinstance(row, dict):
            continue
        lesson = str(row.get("lesson") or "").strip()
        if not lesson:
            continue
        topic = str(row.get("topic") or "Lección operativa").strip()
        block = f"[{topic}]\n{lesson}"
        remaining = cap - used
        if remaining <= 0:
            break
        if len(block) > remaining:
            blocks.append(block[:remaining].rstrip() + "\n[… truncado …]")
            break
        blocks.append(block)
        used += len(block) + 2
    return "\n\n".join(blocks)
