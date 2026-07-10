from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, Query

from routers.admin_domains.admin_common import problem, require_admin_key as _require_admin_key_impl

router = APIRouter(prefix="/train", tags=["admin-train"])

_REPO_ROOT = Path(__file__).resolve().parents[4]
_TRAIN_DIR = _REPO_ROOT / "packages" / "agents" / "train"
_GEMMA4_DIR = _TRAIN_DIR / "gemma4"


def require_admin_key(x_admin_key: str | None = Header(None, alias="X-Admin-Key")) -> None:
    _require_admin_key_impl(x_admin_key)


def _problem(status_code: int, title: str, detail: str):
    return problem(status_code, title, detail)


def _trace_lake_root(lake: str) -> Path:
    if lake == "gemma4":
        return _GEMMA4_DIR
    if lake == "conversation_traces":
        from duckclaw.graphs.conversation_traces import get_conversation_traces_dir

        return get_conversation_traces_dir()
    raise _problem(400, "Lake no válido", lake)


def _scan_jsonl_lake(root: Path, *, limit: int = 30) -> list[dict[str, Any]]:
    if not root.is_dir():
        return []
    rows: list[tuple[str, float, dict[str, Any]]] = []
    for path in root.rglob("traces.jsonl"):
        if not path.is_file():
            continue
        try:
            stat = path.stat()
            rel = path.relative_to(root).as_posix()
            line_count = 0
            with path.open(encoding="utf-8", errors="replace") as fh:
                for line_count, _ in enumerate(fh, start=1):
                    pass
            rows.append(
                (
                    rel,
                    stat.st_mtime,
                    {
                        "relative_path": rel,
                        "size_bytes": stat.st_size,
                        "line_count": line_count,
                    },
                )
            )
        except OSError:
            continue
    rows.sort(key=lambda item: item[1], reverse=True)
    return [item[2] for item in rows[:limit]]


def _message_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                text = block.get("text") or block.get("content")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts).strip()
    return str(content).strip()


def _preview_from_record(record: dict[str, Any]) -> dict[str, str]:
    messages = record.get("messages")
    if isinstance(messages, list) and messages:
        users = [
            _message_text(m.get("content"))
            for m in messages
            if isinstance(m, dict) and (m.get("role") or "").lower() == "user"
        ]
        assistants = [
            _message_text(m.get("content"))
            for m in messages
            if isinstance(m, dict) and (m.get("role") or "").lower() == "assistant"
        ]
        return {
            "instruction": (users[-1] if users else "")[:500],
            "response": (assistants[-1] if assistants else "")[:500],
        }
    prompt = record.get("prompt")
    if isinstance(prompt, list):
        users = [
            _message_text(m.get("content"))
            for m in prompt
            if isinstance(m, dict) and (m.get("role") or "").lower() == "user"
        ]
        return {
            "instruction": (users[-1] if users else "")[:500],
            "response": "",
        }
    return {"instruction": "", "response": ""}


def _read_trace_samples(path: Path, *, limit: int) -> tuple[list[dict[str, Any]], int]:
    if not path.is_file():
        raise _problem(404, "Archivo no encontrado", str(path))
    lines: list[str] = []
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            stripped = line.strip()
            if stripped:
                lines.append(stripped)
    total = len(lines)
    tail = lines[-max(1, min(limit, 50)) :]
    samples: list[dict[str, Any]] = []
    for raw in tail:
        try:
            record = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        preview = _preview_from_record(record)
        samples.append(
            {
                "instruction": preview["instruction"],
                "response": preview["response"],
                "worker_id": record.get("worker_id"),
                "session_id": record.get("session_id"),
                "timestamp": record.get("timestamp"),
                "status": record.get("status"),
            }
        )
    return samples, total


@router.get("/status", dependencies=[Depends(require_admin_key)])
async def train_status() -> dict[str, Any]:
    from duckclaw.graphs.conversation_traces import get_conversation_traces_dir

    conv_root = get_conversation_traces_dir()
    conv_recent = _scan_jsonl_lake(conv_root)
    gemma_recent = _scan_jsonl_lake(_GEMMA4_DIR)
    trace_format = (os.environ.get("DUCKCLAW_CONVERSATION_TRACES_FORMAT") or "sft").strip().lower()
    save_traces = (os.environ.get("DUCKCLAW_SAVE_CONVERSATION_TRACES") or "true").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )
    return {
        "trace_format": "grpo" if trace_format == "grpo" else "sft",
        "paths": {
            "conversation_traces": str(conv_root),
            "gemma4": str(_GEMMA4_DIR),
        },
        "files": {
            "conversation_traces": {
                "exists": conv_root.is_dir(),
                "path": str(conv_root),
            },
            "gemma4": {
                "exists": _GEMMA4_DIR.is_dir(),
                "path": str(_GEMMA4_DIR),
            },
        },
        "conversation_traces": {
            "file_count": len(conv_recent),
            "recent": conv_recent,
            "save_enabled": save_traces,
        },
        "gemma4_sanitized": {
            "file_count": len(gemma_recent),
            "recent": gemma_recent,
        },
        "pipeline": {
            "sft": [
                "collect (trazas JSONL)",
                "sanitize_traces_for_gemma.py",
                "materialize_sft_data_dir_from_gemma4_sanitized.py",
                "mlx LoRA train",
            ],
            "grpo": ["classify_traces", "grpo train"],
        },
        "docs": ["docs/COMANDOS.md#train--trazas-sft-cli-sin-admin-train"],
    }


@router.get("/traces/sample", dependencies=[Depends(require_admin_key)])
async def train_trace_sample(
    lake: str = Query("conversation_traces"),
    relative_path: str = Query(...),
    limit: int = Query(5, ge=1, le=50),
) -> dict[str, Any]:
    root = _trace_lake_root((lake or "").strip())
    rel = (relative_path or "").strip().replace("\\", "/").lstrip("/")
    if not rel or ".." in rel.split("/"):
        raise _problem(400, "Ruta relativa inválida", relative_path)
    target = (root / rel).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError as exc:
        raise _problem(400, "Ruta fuera del lake", relative_path) from exc
    samples, total = _read_trace_samples(target, limit=limit)
    return {
        "lake": lake,
        "relative_path": rel,
        "total_lines_estimate": total,
        "samples": samples,
    }
