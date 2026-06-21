"""Load document_toolbox_v1 seed pack."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

PACK_FILENAME = "document_toolbox_v1.json"


def document_toolbox_path() -> Path:
    return Path(__file__).resolve().parent.parent / "seeds" / PACK_FILENAME


@lru_cache(maxsize=1)
def load_document_toolbox() -> dict[str, Any]:
    path = document_toolbox_path()
    if not path.is_file():
        raise FileNotFoundError(f"document toolbox pack not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("document toolbox pack must be a JSON object")
    return data


def baseline_document_tools() -> list[str]:
    pack = load_document_toolbox()
    tools = pack.get("baseline_tools")
    if not isinstance(tools, list):
        return []
    return [str(t).strip() for t in tools if str(t).strip()]
