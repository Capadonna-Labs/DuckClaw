"""DuckClaw document toolbox — transversal ingest, extract, author, Word→PDF."""

from duckclaw.document_toolbox.export_pdf import export_docx_to_pdf_file, libreoffice_available
from duckclaw.document_toolbox.extract import (
    convert_bytes_to_text,
    convert_file_path_to_text,
    extract_document_text_from_path,
    markitdown_available,
)
from duckclaw.document_toolbox.pack import baseline_document_tools, load_document_toolbox
from duckclaw.document_toolbox.registry import (
    AUTHOR_BINARY_REJECT_SUFFIXES,
    AUTHOR_TEXT_SUFFIXES,
    EXTRACT_SUFFIXES,
    INGEST_NATIVE_SUFFIXES,
    INGEST_SUFFIXES,
    assert_author_text_path,
    is_author_text_suffix,
)
from duckclaw.document_toolbox.templates import (
    docxtpl_available,
    list_document_templates,
    render_docx_template,
)

__all__ = [
    "AUTHOR_BINARY_REJECT_SUFFIXES",
    "AUTHOR_TEXT_SUFFIXES",
    "EXTRACT_SUFFIXES",
    "INGEST_NATIVE_SUFFIXES",
    "INGEST_SUFFIXES",
    "assert_author_text_path",
    "baseline_document_tools",
    "convert_bytes_to_text",
    "convert_file_path_to_text",
    "docxtpl_available",
    "export_docx_to_pdf_file",
    "extract_document_text_from_path",
    "is_author_text_suffix",
    "libreoffice_available",
    "list_document_templates",
    "load_document_toolbox",
    "markitdown_available",
    "render_docx_template",
]
