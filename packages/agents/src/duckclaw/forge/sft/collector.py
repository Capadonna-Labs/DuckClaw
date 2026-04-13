"""
SFT_DataCollector — trazas de conversación (SUCCESS) → dataset Gemma/MLX (`messages`).

Spec: specs/features/Formateo de Datasets (SFT & GRPO).md
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from duckclaw.forge.sft.datamasker import DataMasker
from duckclaw.forge.sft.gemma_message_flatten import flatten_messages_for_gemma
from duckclaw.forge.sft.sql_tool_validation import validate_sql_in_openai_messages
from duckclaw.graphs.conversation_traces import get_conversation_traces_dir

# forge/sft/ es un nivel más profundo que graphs/; usar parents[4] para alinear con agents/train.
TRAIN_DIR = Path(__file__).resolve().parents[4] / "train"
GEMMA4_TRAIN_DIR = TRAIN_DIR / "gemma4"
DEFAULT_SFT_DATASET_PATH = GEMMA4_TRAIN_DIR / "dataset_sft.jsonl"


def collect_traces_to_sft(
    traces_root: Optional[Path | str] = None,
    output_path: Optional[Path | str] = None,
    *,
    datamasker: Optional[DataMasker] = None,
    require_valid_sql: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Lee todos los ``*.jsonl`` bajo ``traces_root`` (recursivo), conserva líneas con
    ``status == "SUCCESS"``, aplica flattening Gemma y escribe un JSONL con
    ``{"messages": [...]}`` por línea.

    - ``traces_root``: raíz del datalake (default: ``get_conversation_traces_dir()``).
    - ``output_path``: salida (default: ``train/gemma4/dataset_sft.jsonl``), sobrescritura total.
    - ``require_valid_sql``: si True, descarta ejemplos cuyo SQL en ``tool_calls`` no parsea (sqlglot).
    """
    root = Path(traces_root) if traces_root else get_conversation_traces_dir()
    out = Path(output_path) if output_path else DEFAULT_SFT_DATASET_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    masker = datamasker or DataMasker()

    if not root.is_dir():
        stats: dict[str, Any] = {
            "traces_root": str(root),
            "output_path": str(out),
            "files_scanned": 0,
            "lines_read": 0,
            "total_output": 0,
            "skipped_non_success": 0,
            "skipped_sql": 0,
            "skipped_malformed": 0,
        }
        return [], stats

    records: list[dict[str, Any]] = []
    files_scanned = 0
    lines_read = 0
    skipped_non_success = 0
    skipped_sql = 0
    skipped_malformed = 0

    jsonl_files = sorted(root.rglob("*.jsonl"))
    files_scanned = len(jsonl_files)

    for fp in jsonl_files:
        try:
            text = fp.read_text(encoding="utf-8")
        except OSError:
            skipped_malformed += 1
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            lines_read += 1
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                skipped_malformed += 1
                continue
            if not isinstance(row, dict):
                skipped_malformed += 1
                continue
            if (row.get("status") or "") != "SUCCESS":
                skipped_non_success += 1
                continue
            messages = row.get("messages")
            if not isinstance(messages, list) or not messages:
                skipped_malformed += 1
                continue
            if require_valid_sql and not validate_sql_in_openai_messages(messages):
                skipped_sql += 1
                continue
            flat = flatten_messages_for_gemma([m for m in messages if isinstance(m, dict)])
            if not flat:
                skipped_malformed += 1
                continue
            masked = [
                {"role": m["role"], "content": masker.mask(m.get("content") or "")}
                for m in flat
            ]
            records.append({"messages": masked})

    with open(out, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    stats = {
        "traces_root": str(root.resolve()),
        "output_path": str(out.resolve()),
        "files_scanned": files_scanned,
        "lines_read": lines_read,
        "total_output": len(records),
        "skipped_non_success": skipped_non_success,
        "skipped_sql": skipped_sql,
        "skipped_malformed": skipped_malformed,
    }
    return records, stats
