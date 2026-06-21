"""DuckClaw document toolbox — transversal ingest, extract, author, convert."""

from duckclaw.document_toolbox.convert import convert_document_file, pandoc_available
from duckclaw.document_toolbox.extract import (
    convert_bytes_to_text,
    convert_file_path_to_text,
    extract_document_text_from_path,
    markitdown_available,
)
from duckclaw.document_toolbox.pack import baseline_document_tools, load_document_toolbox
from duckclaw.document_toolbox.registry import (
    EXTRACT_SUFFIXES,
    INGEST_NATIVE_SUFFIXES,
    INGEST_SUFFIXES,
    PANDOC_INPUT_SUFFIXES,
    PANDOC_OUTPUT_FORMATS,
)
from duckclaw.document_toolbox.templates import (
    docxtpl_available,
    list_document_templates,
    render_docx_template,
)

__all__ = [
    "EXTRACT_SUFFIXES",
    "INGEST_NATIVE_SUFFIXES",
    "INGEST_SUFFIXES",
    "PANDOC_INPUT_SUFFIXES",
    "PANDOC_OUTPUT_FORMATS",
    "baseline_document_tools",
    "convert_document_file",
    "convert_bytes_to_text",
    "convert_file_path_to_text",
    "docxtpl_available",
    "extract_document_text_from_path",
    "list_document_templates",
    "load_document_toolbox",
    "markitdown_available",
    "pandoc_available",
    "render_docx_template",
]
