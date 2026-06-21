"""Convert office/PDF uploads to text via Microsoft MarkItDown (optional dep).

Deprecated import path — use duckclaw.document_toolbox.extract.
"""

from __future__ import annotations

from duckclaw.document_toolbox.registry import EXTRACT_SUFFIXES as MARKITDOWN_SUFFIXES
from duckclaw.document_toolbox.extract import (
    convert_bytes_to_text,
    convert_file_path_to_text,
    markitdown_available,
)

__all__ = [
    "MARKITDOWN_SUFFIXES",
    "convert_bytes_to_text",
    "convert_file_path_to_text",
    "markitdown_available",
]
