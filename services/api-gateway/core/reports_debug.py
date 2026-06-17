"""Debug NDJSON para flujo custom reports (sesión 97f3cb)."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

_DEBUG_BASENAMES = ("debug-97f3cb.log",)


def reports_debug_log(*, hypothesis_id: str, location: str, message: str, data: dict[str, Any]) -> None:
    # region agent log
    payload = {
        "sessionId": "97f3cb",
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    roots: list[Path] = []
    for key in ("DUCKCLAW_EXTENSION_ROOT", "DUCKCLAW_REPO_ROOT"):
        raw = (os.environ.get(key) or "").strip()
        if raw:
            roots.append(Path(raw).expanduser())
    roots.append(Path.cwd())
    for root in roots:
        for name in _DEBUG_BASENAMES:
            try:
                path = (root / name).resolve()
                with path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
                return
            except OSError:
                continue
    # endregion
