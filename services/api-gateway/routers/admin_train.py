"""
Admin API — pipeline Train (SFT / GRPO / conversation_traces / Gemma4).

Spec: specs/features/platform/ADMIN_TRAIN_UI.md
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from routers.admin import (
    _actor_from_header,
    _admin_audit,
    _problem,
    _repo_root,
    _require_admin_key,
)

router = APIRouter(prefix="/train", tags=["admin-train"])

_AGENTS_TRAIN = "packages/agents/train"


def _agents_train_dir(repo: Path) -> Path:
    return (repo / _AGENTS_TRAIN).resolve()


def _safe_train_subpath(repo: Path, rel: str, *, lake: str) -> Path:
    """Resuelve ruta bajo packages/agents/train/{lake} sin path traversal."""
    if lake not in ("conversation_traces", "gemma4"):
        raise _problem(400, "lake inválido", lake)
    rel_clean = (rel or "").strip().replace("\\", "/").lstrip("/")
    if ".." in rel_clean.split("/"):
        raise _problem(400, "Ruta inválida", rel)
    base = (_agents_train_dir(repo) / lake).resolve()
    candidate = (base / rel_clean).resolve() if rel_clean else base
    try:
        candidate.relative_to(base)
    except ValueError as exc:
        raise _problem(400, "Ruta fuera de train permitido", rel) from exc
    return candidate


def _file_stats(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"exists": False, "path": str(path)}
    st = path.stat()
    return {
        "exists": True,
        "path": str(path),
        "size_bytes": st.st_size,
        "modified_utc": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
    }


def _count_jsonl_lines(path: Path, *, max_scan: int = 500_000) -> int:
    if not path.is_file():
        return 0
    n = 0
    try:
        with path.open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    n += 1
                if n >= max_scan:
                    break
    except OSError:
        return -1
    return n


def _scan_trace_lake(root: Path, *, limit_files: int = 200) -> list[dict[str, Any]]:
    if not root.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for fp in sorted(root.rglob("traces.jsonl"), reverse=True):
        if len(out) >= limit_files:
            break
        try:
            rel = fp.relative_to(root).as_posix()
        except ValueError:
            continue
        out.append(
            {
                "relative_path": rel,
                "size_bytes": fp.stat().st_size,
                "line_count": _count_jsonl_lines(fp, max_scan=50_000),
            }
        )
    return out


@router.get("/status", dependencies=[Depends(_require_admin_key)])
async def train_status() -> dict[str, Any]:
    repo = _repo_root()
    train_dir = _agents_train_dir(repo)

    try:
        from duckclaw.graphs.conversation_traces import (
            get_conversation_traces_dir,
            get_conversation_traces_format,
        )

        traces_dir = get_conversation_traces_dir()
        trace_fmt = get_conversation_traces_format()
    except ImportError:
        traces_dir = train_dir / "conversation_traces"
        trace_fmt = (os.environ.get("DUCKCLAW_CONVERSATION_TRACES_FORMAT") or "sft").strip()

    gemma4_dir = train_dir / "gemma4"
    dataset_sft = gemma4_dir / "dataset_sft.jsonl"
    sft_data_dir = gemma4_dir / "sft_data_dir"
    lora_config = repo / "config" / "lora_config.yaml"

    lake_files = _scan_trace_lake(traces_dir, limit_files=80)
    gemma_files = _scan_trace_lake(gemma4_dir, limit_files=40) if gemma4_dir.is_dir() else []

    return {
        "trace_format": trace_fmt,
        "paths": {
            "conversation_traces": str(traces_dir),
            "gemma4": str(gemma4_dir),
            "dataset_sft": str(dataset_sft),
            "sft_data_dir": str(sft_data_dir),
            "lora_config": str(lora_config),
        },
        "files": {
            "dataset_sft": _file_stats(dataset_sft),
            "train_jsonl": _file_stats(sft_data_dir / "train.jsonl"),
            "valid_jsonl": _file_stats(sft_data_dir / "valid.jsonl"),
            "lora_config": _file_stats(lora_config),
        },
        "conversation_traces": {
            "file_count": len(lake_files),
            "recent": lake_files[:15],
        },
        "gemma4_sanitized": {
            "file_count": len(gemma_files),
            "recent": gemma_files[:10],
        },
        "pipeline": {
            "sft": [
                "1. Gateway guarda trazas → conversation_traces/YYYY/MM/DD/traces.jsonl",
                "2. collect_traces_to_sft → gemma4/dataset_sft.jsonl",
                "3. sanitize_traces_for_gemma → gemma4/YYYY/MM/DD/traces.jsonl (text)",
                "4. materialize_sft_data_dir → gemma4/sft_data_dir/train.jsonl",
                "5. duckops train / train_sft.py → adapters LoRA",
            ],
            "grpo": [
                "DUCKCLAW_CONVERSATION_TRACES_FORMAT=grpo en .env",
                "Salida: prompt + reward_metadata (spec SFT_DATASET_FORMAT §3)",
            ],
        },
        "docs": [
            "packages/agents/train/SFT_MLX_PIPELINE.md",
            "docs/agents/sft_conversation_traces.md",
            "specs/features/platform/SFT_DATASET_FORMAT.md",
        ],
    }


@router.get("/traces/sample", dependencies=[Depends(_require_admin_key)])
async def train_trace_sample(
    lake: str = Query("conversation_traces", pattern="^(conversation_traces|gemma4)$"),
    relative_path: str = Query(..., min_length=1, max_length=512),
    limit: int = Query(5, ge=1, le=20),
) -> dict[str, Any]:
    repo = _repo_root()
    fp = _safe_train_subpath(repo, relative_path, lake=lake)
    if not fp.is_file():
        raise _problem(404, "Archivo no encontrado", str(fp))
    lines: list[dict[str, Any]] = []
    raw_lines: list[str] = []
    try:
        text = fp.read_text(encoding="utf-8")
    except OSError as exc:
        raise _problem(500, "No se pudo leer el archivo", str(exc)) from exc
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        raw_lines.append(line)
        if len(lines) >= limit:
            continue
        try:
            lines.append(json.loads(line))
        except json.JSONDecodeError:
            lines.append({"_parse_error": True, "raw": line[:2000]})
    return {
        "lake": lake,
        "relative_path": relative_path,
        "total_lines_estimate": len(raw_lines),
        "samples": lines,
    }


class TrainCollectBody(BaseModel):
    require_valid_sql: bool = True


@router.post("/pipeline/collect", dependencies=[Depends(_require_admin_key)])
async def train_pipeline_collect(
    body: TrainCollectBody,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    def _run() -> dict[str, Any]:
        from duckclaw.forge.sft import collect_traces_to_sft

        records, stats = collect_traces_to_sft(require_valid_sql=body.require_valid_sql)
        return {"records": len(records), "stats": stats}

    try:
        result = await asyncio.to_thread(_run)
    except Exception as exc:
        raise _problem(500, "collect_traces_to_sft falló", str(exc)) from exc
    _admin_audit("train.collect_sft", "gemma4/dataset_sft.jsonl", "", actor=actor, meta=result)
    return {"ok": True, **result}


class TrainScriptBody(BaseModel):
    dry_run: bool = False


@router.post("/pipeline/sanitize", dependencies=[Depends(_require_admin_key)])
async def train_pipeline_sanitize(
    body: TrainScriptBody,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    repo = _repo_root()
    argv = ["uv", "run", "python", "scripts/sanitize_traces_for_gemma.py"]
    if body.dry_run:
        argv.append("--dry-run")

    def _run() -> dict[str, Any]:
        proc = subprocess.run(
            argv,
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=600,
        )
        return {
            "exit_code": proc.returncode,
            "stdout": (proc.stdout or "")[-16000:],
            "stderr": (proc.stderr or "")[-8000:],
        }

    try:
        result = await asyncio.to_thread(_run)
    except subprocess.TimeoutExpired:
        raise _problem(408, "Timeout sanitize", "sanitize_traces_for_gemma") from None
    _admin_audit("train.sanitize", "gemma4/", " ".join(argv), actor=actor, meta=result)
    return {"ok": result.get("exit_code") == 0, **result}


@router.post("/pipeline/materialize", dependencies=[Depends(_require_admin_key)])
async def train_pipeline_materialize(
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    repo = _repo_root()
    argv = ["uv", "run", "python", "scripts/materialize_sft_data_dir_from_gemma4_sanitized.py"]

    def _run() -> dict[str, Any]:
        proc = subprocess.run(
            argv,
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=300,
        )
        return {
            "exit_code": proc.returncode,
            "stdout": (proc.stdout or "")[-16000:],
            "stderr": (proc.stderr or "")[-8000:],
        }

    try:
        result = await asyncio.to_thread(_run)
    except subprocess.TimeoutExpired:
        raise _problem(408, "Timeout materialize", "materialize_sft_data_dir") from None
    _admin_audit("train.materialize", "gemma4/sft_data_dir", " ".join(argv), actor=actor, meta=result)
    return {"ok": result.get("exit_code") == 0, **result}


class TrainRunBody(BaseModel):
    use_lora_config: bool = Field(
        True,
        description="Si true, duckops train -c config/lora_config.yaml; si no, train_sft.py",
    )


@router.post("/pipeline/run", dependencies=[Depends(_require_admin_key)])
async def train_pipeline_run(
    body: TrainRunBody,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    repo = _repo_root()
    if body.use_lora_config:
        argv = ["uv", "run", "duckops", "train", "-c", "config/lora_config.yaml"]
    else:
        argv = ["uv", "run", "python", "packages/agents/train/train_sft.py"]

    def _run() -> dict[str, Any]:
        proc = subprocess.run(
            argv,
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=7200,
        )
        return {
            "exit_code": proc.returncode,
            "stdout": (proc.stdout or "")[-24000:],
            "stderr": (proc.stderr or "")[-12000:],
        }

    try:
        result = await asyncio.to_thread(_run)
    except subprocess.TimeoutExpired:
        raise _problem(408, "Timeout entrenamiento", "train") from None
    _admin_audit(
        "train.run",
        "mlx_lora",
        " ".join(argv),
        actor=actor,
        meta={"exit_code": result.get("exit_code")},
    )
    return {"ok": result.get("exit_code") == 0, **result}
