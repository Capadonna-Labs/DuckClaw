"""Pandoc conversion lane — text sources to deliverable formats (never binary ingest)."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from duckclaw.document_toolbox.registry import PANDOC_INPUT_SUFFIXES, PANDOC_OUTPUT_FORMATS


def pandoc_available() -> bool:
    return shutil.which("pandoc") is not None


def _pdf_engine_args() -> list[str] | None:
    engine = shutil.which("pdflatex") or shutil.which("xelatex")
    if engine:
        return ["--pdf-engine", Path(engine).name]
    if shutil.which("wkhtmltopdf"):
        return ["--pdf-engine", "wkhtmltopdf"]
    return None


def convert_document_file(
    *,
    source: Path,
    output_format: str,
    target: Path | None = None,
    timeout_sec: int = 180,
) -> dict[str, Any]:
    fmt = (output_format or "docx").strip().lower()
    if fmt not in PANDOC_OUTPUT_FORMATS:
        raise ValueError(f"output_format debe ser uno de: {', '.join(sorted(PANDOC_OUTPUT_FORMATS))}")

    suffix = source.suffix.lower()
    if suffix not in PANDOC_INPUT_SUFFIXES:
        raise ValueError(
            f"convert_document solo acepta fuentes de texto: {', '.join(sorted(PANDOC_INPUT_SUFFIXES))}"
        )

    pandoc = shutil.which("pandoc")
    if not pandoc:
        raise ValueError(
            "pandoc no está instalado en el host (macOS: brew install pandoc)."
        )

    if not source.is_file():
        raise ValueError(f"No existe el archivo fuente: {source.name}")

    out = target or source.with_suffix(f".{fmt}")
    cmd = [pandoc, str(source), "-o", str(out), f"--from={_pandoc_from_suffix(suffix)}"]
    if fmt == "pdf":
        pdf_args = _pdf_engine_args()
        if not pdf_args:
            raise ValueError(
                "PDF requiere pdflatex, xelatex o wkhtmltopdf además de pandoc."
            )
        cmd.extend(pdf_args)

    completed = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout_sec,
        check=False,
    )
    if completed.returncode != 0:
        stderr = (completed.stderr or completed.stdout or "").strip()
        raise ValueError(f"pandoc falló: {stderr[:2000]}")

    if not out.is_file():
        raise ValueError("pandoc no generó el archivo de salida")

    return {
        "source_path": str(source),
        "path": str(out),
        "relative_path": out.name,
        "format": fmt,
        "byte_size": out.stat().st_size,
    }


def convert_document_result_json(**kwargs: Any) -> str:
    try:
        payload = convert_document_file(**kwargs)
        return json.dumps(payload, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)


def _pandoc_from_suffix(suffix: str) -> str:
    if suffix in {".md", ".markdown"}:
        return "markdown"
    if suffix in {".html", ".htm"}:
        return "html"
    return "plain"
