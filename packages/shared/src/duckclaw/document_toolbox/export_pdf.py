"""Export Word (.docx) → PDF via LibreOffice/soffice (no pandoc)."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


def libreoffice_binary() -> str | None:
    """Path to soffice/libreoffice if installed."""
    for name in ("soffice", "libreoffice"):
        found = shutil.which(name)
        if found:
            return found
    # macOS app bundle (common with brew --cask libreoffice)
    mac = Path("/Applications/LibreOffice.app/Contents/MacOS/soffice")
    if mac.is_file():
        return str(mac)
    return None


def libreoffice_available() -> bool:
    return libreoffice_binary() is not None


def export_docx_to_pdf_file(
    *,
    source: Path,
    target: Path | None = None,
    timeout_sec: int = 180,
) -> dict[str, Any]:
    """
    Convert a .docx under disk to .pdf beside it (or to ``target``).

    Uses LibreOffice headless. Source must exist and end with .docx.
    """
    src = source.expanduser().resolve()
    if not src.is_file():
        raise ValueError(f"No existe el Word fuente: {src}")
    if src.suffix.lower() != ".docx":
        raise ValueError("export_docx_to_pdf solo acepta archivos .docx")

    binary = libreoffice_binary()
    if not binary:
        raise ValueError(
            "LibreOffice no está instalado en el host "
            "(macOS: brew install --cask libreoffice; Linux: apt install libreoffice-writer)."
        )

    out = (target.expanduser().resolve() if target else src.with_suffix(".pdf"))
    if out.suffix.lower() != ".pdf":
        raise ValueError("target debe terminar en .pdf")
    out.parent.mkdir(parents=True, exist_ok=True)

    # LibreOffice writes into --outdir using the source basename; then we move if needed.
    with tempfile.TemporaryDirectory(prefix="duckclaw_pdf_") as tmp:
        tmp_dir = Path(tmp)
        cmd = [
            binary,
            "--headless",
            "--nologo",
            "--nofirststartwizard",
            "--convert-to",
            "pdf",
            "--outdir",
            str(tmp_dir),
            str(src),
        ]
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
        if completed.returncode != 0:
            stderr = (completed.stderr or completed.stdout or "").strip()
            raise ValueError(f"LibreOffice falló: {stderr[:2000]}")

        produced = tmp_dir / f"{src.stem}.pdf"
        if not produced.is_file():
            pdfs = list(tmp_dir.glob("*.pdf"))
            if len(pdfs) == 1:
                produced = pdfs[0]
            else:
                raise ValueError("LibreOffice no generó el PDF")

        shutil.move(str(produced), str(out))

    if not out.is_file():
        raise ValueError("No se pudo escribir el PDF de salida")

    return {
        "source_path": str(src),
        "path": str(out),
        "relative_path": out.name,
        "format": "pdf",
        "byte_size": out.stat().st_size,
        "engine": "libreoffice",
    }
