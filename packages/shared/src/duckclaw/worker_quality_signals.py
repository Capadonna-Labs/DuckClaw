"""DB-first worker quality signals.

Product name: quality signals. Internally these can feed homeostasis beliefs.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from duckclaw.admin_runtime_settings import resolve_runtime_setting, upsert_runtime_setting

QUALITY_SIGNALS_DOMAIN = "worker.quality_signals"
_KEY_RE = re.compile(r"[^a-z0-9_]+")


@dataclass(frozen=True)
class WorkerQualitySignal:
    key: str
    target: float
    threshold: float
    comparison: str = "symmetric"
    label: str = ""
    enabled: bool = True


def normalize_quality_signal_key(value: str) -> str:
    key = _KEY_RE.sub("_", str(value or "").strip().lower()).strip("_")
    return key[:96]


def _settings_key(worker_id: str) -> str:
    raw = str(worker_id or "default").strip() or "default"
    return normalize_quality_signal_key(raw.replace("-", "_")) or "default"


def _coerce_signal(raw: Any) -> WorkerQualitySignal | None:
    if not isinstance(raw, dict):
        return None
    key = normalize_quality_signal_key(str(raw.get("key") or ""))
    if not key:
        return None
    try:
        target = float(raw.get("target", 0))
        threshold = max(0.0, float(raw.get("threshold", 0)))
    except (TypeError, ValueError):
        return None
    comp = str(raw.get("comparison") or "symmetric").strip().lower()
    comparison = comp if comp in ("symmetric", "ceiling") else "symmetric"
    return WorkerQualitySignal(
        key=key,
        target=target,
        threshold=threshold,
        comparison=comparison,
        label=str(raw.get("label") or key).strip()[:120],
        enabled=bool(raw.get("enabled", True)),
    )


def list_worker_quality_signals(
    db: Any,
    *,
    tenant_id: str,
    worker_id: str,
) -> list[WorkerQualitySignal]:
    if db is None:
        return []
    try:
        resolved = resolve_runtime_setting(
            db,
            tenant_id=str(tenant_id or "default").strip() or "default",
            actor_email="",
            domain=QUALITY_SIGNALS_DOMAIN,
            key=_settings_key(worker_id),
            default="[]",
        )
        raw = str(resolved.get("value") or "[]").strip() or "[]"
        data = json.loads(raw)
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    out: list[WorkerQualitySignal] = []
    for item in data:
        signal = _coerce_signal(item)
        if signal and signal.enabled:
            out.append(signal)
    return out


def upsert_worker_quality_signal(
    db: Any,
    *,
    tenant_id: str,
    worker_id: str,
    key: str,
    target: float,
    threshold: float,
    comparison: str = "symmetric",
    label: str = "",
    updated_by: str = "system",
) -> None:
    signal = WorkerQualitySignal(
        key=normalize_quality_signal_key(key),
        target=float(target),
        threshold=max(0.0, float(threshold)),
        comparison=(comparison if comparison in ("symmetric", "ceiling") else "symmetric"),
        label=(label or key)[:120],
        enabled=True,
    )
    if not signal.key:
        raise ValueError("quality signal key required")

    existing = {
        item.key: item
        for item in list_worker_quality_signals(
            db,
            tenant_id=tenant_id,
            worker_id=worker_id,
        )
    }
    existing[signal.key] = signal
    payload = [
        {
            "key": item.key,
            "target": item.target,
            "threshold": item.threshold,
            "comparison": item.comparison,
            "label": item.label,
            "enabled": item.enabled,
        }
        for item in sorted(existing.values(), key=lambda x: x.key)
    ]
    upsert_runtime_setting(
        db,
        tenant_id=str(tenant_id or "default").strip() or "default",
        actor_email="",
        domain=QUALITY_SIGNALS_DOMAIN,
        key=_settings_key(worker_id),
        value_text=json.dumps(payload, ensure_ascii=False, sort_keys=True),
        value_kind="string",
        updated_by=updated_by,
    )
