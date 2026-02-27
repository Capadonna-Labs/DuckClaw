#!/usr/bin/env python3
"""
Crea un ZIP con Channels_Integration.md + duckclaw_olist_eda.ipynb para entrega.

Uso:
  uv run python scripts/create_delivery_package.py
  # o: python scripts/create_delivery_package.py

Genera: output/duckclaw_delivery.zip
"""

from __future__ import annotations

import zipfile
from pathlib import Path


def create_delivery_package(
    output_dir: str = "output",
    zip_name: str = "duckclaw_delivery.zip",
) -> Path:
    """Crea ZIP con Channels_Integration.md + duckclaw_olist_eda.ipynb."""
    root = Path(__file__).resolve().parent.parent

    # Prioridad: prueba idata (entrega) > docs
    channels_candidates = [
        root / "prueba idata" / "Channels_Integration.md",
        root / "docs" / "Channels_Integration.md",
    ]
    channels_md = next((p for p in channels_candidates if p.is_file()), None)
    notebook_candidates = [
        root / "prueba idata" / "duckclaw_olist_eda.ipynb",
        root / "notebooks" / "duckclaw_olist_eda.ipynb",
    ]
    notebook = next((p for p in notebook_candidates if p.is_file()), None)

    if not channels_md or not channels_md.is_file():
        raise FileNotFoundError(f"No existe Channels_Integration.md en: {[str(p) for p in channels_candidates]}")
    if not notebook:
        raise FileNotFoundError(
            f"No existe el notebook en: {[str(p) for p in notebook_candidates]}"
        )

    out_dir = root / output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = out_dir / zip_name

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(channels_md, "Channels_Integration.md")
        zf.write(notebook, notebook.name)

    return zip_path


if __name__ == "__main__":
    p = create_delivery_package()
    print(f"✅ ZIP creado: {p}")
