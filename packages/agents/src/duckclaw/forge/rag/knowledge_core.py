"""Transversal DB-first RAG helpers.

This module owns document normalization, deterministic chunk payloads and
read-only retrieval. Writes are still applied by typed DB-writer commands.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from duckclaw.forge.rag.markitdown_convert import (
    MARKITDOWN_SUFFIXES,
    convert_bytes_to_text,
    convert_file_path_to_text,
)

_ALLOWED_SUFFIXES = {".md", ".markdown", ".txt", ".json", ".csv"}
_INGEST_SUFFIXES = _ALLOWED_SUFFIXES | MARKITDOWN_SUFFIXES
_SECRET_NAME_RE = re.compile(r"(secret|token|password|api[_-]?key|apikey|\.env)", re.I)
_WORD_RE = re.compile(r"\w+", re.UNICODE)
_LEX_SKIP = {
    "el",
    "la",
    "los",
    "las",
    "de",
    "del",
    "que",
    "con",
    "por",
    "para",
    "una",
    "uno",
    "the",
    "and",
    "for",
    "with",
    "sobre",
    "buscar",
    "busca",
}


@dataclass(frozen=True)
class KnowledgeDocumentPayload:
    document: dict[str, Any]
    chunks: list[dict[str, Any]]


def sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def stable_id(prefix: str, *parts: str, length: int = 16) -> str:
    raw = "\n".join(str(p) for p in parts)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]
    return f"{prefix}_{digest}"


def safe_relative_path(root: str | Path, path: str | Path) -> str:
    base = Path(root).expanduser().resolve()
    target = Path(path).expanduser().resolve()
    try:
        rel = target.relative_to(base)
    except ValueError as exc:
        raise ValueError("knowledge path outside allowed root") from exc
    parts = rel.parts
    if any(part.startswith(".") for part in parts):
        raise ValueError("hidden knowledge files are not allowed")
    if any(_SECRET_NAME_RE.search(part) for part in parts):
        raise ValueError("knowledge file name looks secret-bearing")
    return rel.as_posix()


def _relative_parts_under_root(base: Path, candidate: Path) -> tuple[str, ...] | None:
    try:
        rel = candidate.expanduser().resolve().relative_to(base.expanduser().resolve())
    except ValueError:
        return None
    return rel.parts


def _should_skip_knowledge_candidate(parts: tuple[str, ...]) -> bool:
    if any(part.startswith(".") for part in parts):
        return True
    if any(_SECRET_NAME_RE.search(part) for part in parts):
        return True
    return False


@dataclass(frozen=True)
class FolderScanStats:
    files: list[Path]
    skipped_hidden: int = 0
    skipped_secret: int = 0
    skipped_unsupported: int = 0

    @property
    def file_count(self) -> int:
        return len(self.files)


def scan_knowledge_folder(root: str | Path) -> FolderScanStats:
    """List ingest-eligible files; skip Obsidian/.git/etc. without failing the scan."""
    base = Path(root).expanduser().resolve()
    if not base.exists():
        raise FileNotFoundError(f"knowledge root not found: {root}")
    candidates = [base] if base.is_file() else sorted(p for p in base.rglob("*") if p.is_file())
    base_for_rel = base if base.is_dir() else base.parent
    files: list[Path] = []
    skipped_hidden = 0
    skipped_secret = 0
    skipped_unsupported = 0
    for candidate in candidates:
        if candidate.suffix.lower() not in _INGEST_SUFFIXES:
            skipped_unsupported += 1
            continue
        parts = _relative_parts_under_root(base_for_rel, candidate)
        if parts is None:
            continue
        if any(part.startswith(".") for part in parts):
            skipped_hidden += 1
            continue
        if any(_SECRET_NAME_RE.search(part) for part in parts):
            skipped_secret += 1
            continue
        files.append(candidate)
    return FolderScanStats(
        files=files,
        skipped_hidden=skipped_hidden,
        skipped_secret=skipped_secret,
        skipped_unsupported=skipped_unsupported,
    )


def iter_allowed_files(root: str | Path) -> list[Path]:
    return scan_knowledge_folder(root).files


def read_document_text(path: str | Path) -> tuple[str, str]:
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix in MARKITDOWN_SUFFIXES:
        text = convert_file_path_to_text(p)
        if not text.strip():
            raise ValueError(f"markitdown no extrajo texto de: {p.name}")
        return text, "text/markdown"
    if suffix not in _ALLOWED_SUFFIXES:
        raise ValueError(f"unsupported knowledge file type: {suffix}")
    if suffix == ".json":
        raw = p.read_text(encoding="utf-8", errors="replace")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON inválido en {p.name}: {exc}") from exc
        return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), "application/json"
    if suffix == ".csv":
        with p.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        return json.dumps(rows, ensure_ascii=False, indent=2), "text/csv"
    mime = "text/markdown" if suffix in {".md", ".markdown"} else "text/plain"
    return p.read_text(encoding="utf-8", errors="replace"), mime


def normalize_uploaded_document(filename: str, data: bytes) -> tuple[str, str, str]:
    relative_path = _safe_uploaded_relative_path(filename)
    suffix = Path(relative_path).suffix.lower()
    if suffix in MARKITDOWN_SUFFIXES:
        text = convert_bytes_to_text(data=data, filename=relative_path)
        if not text.strip():
            raise ValueError(f"no se extrajo texto de {relative_path}")
        return relative_path, text, "text/markdown"
    if suffix not in _ALLOWED_SUFFIXES:
        raise ValueError(f"unsupported knowledge file type: {suffix}")
    raw = data.decode("utf-8", errors="replace")
    if suffix == ".json":
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON inválido en {relative_path}: {exc}") from exc
        return relative_path, json.dumps(parsed, ensure_ascii=False, indent=2, sort_keys=True), "application/json"
    if suffix == ".csv":
        rows = list(csv.DictReader(raw.splitlines()))
        return relative_path, json.dumps(rows, ensure_ascii=False, indent=2), "text/csv"
    mime = "text/markdown" if suffix in {".md", ".markdown"} else "text/plain"
    return relative_path, raw, mime


def _safe_uploaded_relative_path(filename: str) -> str:
    cleaned = (filename or "").replace("\\", "/").strip().lstrip("/")
    if not cleaned:
        raise ValueError("knowledge upload filename is empty")
    path = Path(cleaned)
    parts = path.parts
    if any(part in ("", ".", "..") for part in parts):
        raise ValueError("knowledge upload filename is unsafe")
    if any(_SECRET_NAME_RE.search(part) for part in parts):
        raise ValueError("knowledge file name looks secret-bearing")
    if any(part.startswith(".") for part in parts):
        raise ValueError("hidden knowledge files are not allowed")
    return "/".join(parts)


def build_uploaded_document_payload(
    *,
    filename: str,
    data: bytes,
    source_id: str,
    max_chars: int = 3200,
) -> KnowledgeDocumentPayload:
    relative_path, text, mime_type = normalize_uploaded_document(filename, data)
    checksum = sha256_text(text)
    document_id = stable_id("kdoc", source_id, relative_path)
    chunks: list[dict[str, Any]] = []
    cursor = 0
    for index, content in enumerate(chunk_text(text, max_chars=max_chars)):
        start = text.find(content[: min(80, len(content))], cursor)
        if start < 0:
            start = cursor
        end = start + len(content)
        cursor = max(end, cursor)
        content_hash = sha256_text(content)
        chunks.append(
            {
                "chunk_id": stable_id("kchk", document_id, str(index), content_hash),
                "document_id": document_id,
                "source_id": source_id,
                "chunk_index": index,
                "content": content,
                "content_hash": content_hash,
                "start_offset": start,
                "end_offset": end,
                "token_count": max(1, len(_WORD_RE.findall(content))),
                "embedding_status": "PENDING",
                "metadata": {"relative_path": relative_path, "upload": True},
            }
        )
    return KnowledgeDocumentPayload(
        document={
            "document_id": document_id,
            "source_id": source_id,
            "relative_path": relative_path,
            "title": Path(relative_path).stem.replace("_", " ").replace("-", " ").strip() or relative_path,
            "mime_type": mime_type,
            "checksum": checksum,
            "byte_size": len(data),
            "metadata": {"suffix": Path(relative_path).suffix.lower(), "upload": True},
        },
        chunks=chunks,
    )


def chunk_text(text: str, *, max_chars: int = 3200, overlap_chars: int = 240) -> list[str]:
    clean = (text or "").strip()
    if not clean:
        return []
    max_chars = max(400, int(max_chars))
    overlap_chars = max(0, min(int(overlap_chars), max_chars // 4))

    sections = _split_markdown_sections(clean)
    chunks: list[str] = []
    for section in sections:
        if len(section) <= max_chars:
            chunks.append(section)
            continue
        chunks.extend(_split_long_text(section, max_chars=max_chars, overlap_chars=overlap_chars))
    return [chunk.strip() for chunk in chunks if chunk.strip()]


def _split_markdown_sections(text: str) -> list[str]:
    lines = text.splitlines()
    sections: list[str] = []
    buf: list[str] = []
    for line in lines:
        if line.startswith("#") and buf:
            sections.append("\n".join(buf).strip())
            buf = [line]
        else:
            buf.append(line)
    if buf:
        sections.append("\n".join(buf).strip())
    return sections or [text]


def _split_long_text(text: str, *, max_chars: int, overlap_chars: int) -> list[str]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    buf = ""
    for para in paragraphs:
        candidate = f"{buf}\n\n{para}".strip() if buf else para
        if len(candidate) <= max_chars:
            buf = candidate
            continue
        if buf:
            chunks.append(buf)
            overlap = buf[-overlap_chars:] if overlap_chars else ""
            buf = f"{overlap}\n\n{para}".strip() if overlap else para
        while len(buf) > max_chars:
            chunks.append(buf[:max_chars].strip())
            tail = buf[max(0, max_chars - overlap_chars):max_chars] if overlap_chars else ""
            buf = f"{tail}{buf[max_chars:]}".strip()
    if buf:
        chunks.append(buf)
    return chunks


def build_document_payload(
    *,
    root: str | Path,
    path: str | Path,
    source_id: str,
    max_chars: int = 3200,
) -> KnowledgeDocumentPayload:
    base = Path(root).expanduser().resolve()
    target = Path(path).expanduser().resolve()
    relative_path = safe_relative_path(base, target)
    text, mime_type = read_document_text(target)
    checksum = sha256_text(text)
    document_id = stable_id("kdoc", source_id, relative_path)
    chunks: list[dict[str, Any]] = []
    cursor = 0
    for index, content in enumerate(chunk_text(text, max_chars=max_chars)):
        start = text.find(content[: min(80, len(content))], cursor)
        if start < 0:
            start = cursor
        end = start + len(content)
        cursor = max(end, cursor)
        content_hash = sha256_text(content)
        chunks.append(
            {
                "chunk_id": stable_id("kchk", document_id, str(index), content_hash),
                "document_id": document_id,
                "source_id": source_id,
                "chunk_index": index,
                "content": content,
                "content_hash": content_hash,
                "start_offset": start,
                "end_offset": end,
                "token_count": max(1, len(_WORD_RE.findall(content))),
                "embedding_status": "PENDING",
                "metadata": {"relative_path": relative_path},
            }
        )
    return KnowledgeDocumentPayload(
        document={
            "document_id": document_id,
            "source_id": source_id,
            "relative_path": relative_path,
            "title": target.stem.replace("_", " ").replace("-", " ").strip() or relative_path,
            "mime_type": mime_type,
            "checksum": checksum,
            "byte_size": target.stat().st_size,
            "metadata": {"suffix": target.suffix.lower()},
        },
        chunks=chunks,
    )


def embed_chunk_payloads(
    chunks: list[dict[str, Any]],
    embedding_fn: Callable[[str], list[float] | None],
) -> list[dict[str, Any]]:
    if not chunks:
        return []
    from duckclaw.forge.rag.embeddings import embed_text, embed_texts

    if embedding_fn is embed_text:
        texts = [str(chunk.get("content") or "") for chunk in chunks]
        vectors = embed_texts(texts)
    else:
        vectors = [embedding_fn(str(chunk.get("content") or "")) for chunk in chunks]
    out: list[dict[str, Any]] = []
    for chunk, vec in zip(chunks, vectors):
        item = dict(chunk)
        if isinstance(vec, list) and len(vec) == 384:
            item["embedding"] = [float(x) for x in vec]
            item["embedding_status"] = "READY"
        else:
            item["embedding_status"] = "PENDING"
        out.append(item)
    return out


def fold_search_text(text: str) -> str:
    """Lowercase + strip accents for Spanish/English fuzzy match."""
    raw = (text or "").strip().lower()
    if not raw:
        return ""
    decomposed = unicodedata.normalize("NFD", raw)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def lexical_tokens(query: str, *, max_tokens: int = 8) -> list[str]:
    tokens: list[str] = []
    for raw in _WORD_RE.findall((query or "").lower()):
        token = raw.strip()[:48]
        if len(token) < 2 or token in _LEX_SKIP:
            continue
        tokens.append(token)
        folded = fold_search_text(token)
        if folded and folded != token and folded not in tokens:
            tokens.append(folded)
        if len(tokens) >= max_tokens:
            break
    return tokens[:max_tokens]


def search_knowledge(
    con: Any,
    *,
    query: str,
    tenant_id: str,
    project_id: str = "",
    worker_uid: str = "",
    source_id: str = "",
    knowledge_scope: str = "both",
    limit: int = 8,
    embedding_fn: Callable[[str], list[float] | None] | None = None,
) -> list[dict[str, Any]]:
    q = (query or "").strip()
    if not q:
        return []
    lim = max(1, min(int(limit), 40))
    if embedding_fn is None:
        try:
            from duckclaw.forge.rag.embeddings import embed_text

            embedding_fn = embed_text
        except Exception:
            embedding_fn = lambda _text: None
    vec = embedding_fn(q)
    if isinstance(vec, list) and len(vec) == 384:
        rows = _search_knowledge_vector(
            con,
            vec,
            tenant_id=tenant_id,
            project_id=project_id,
            worker_uid=worker_uid,
            source_id=source_id,
            knowledge_scope=knowledge_scope,
            limit=lim,
        )
        if rows:
            return rows
    return _search_knowledge_lexical(
        con,
        q,
        tenant_id=tenant_id,
        project_id=project_id,
        worker_uid=worker_uid,
        source_id=source_id,
        knowledge_scope=knowledge_scope,
        limit=lim,
    )


def _scope_where(
    *,
    tenant_id: str,
    project_id: str,
    worker_uid: str,
    source_id: str,
    knowledge_scope: str = "both",
) -> tuple[str, list[Any]]:
    from duckclaw.knowledge_scope import build_knowledge_scope_clauses

    clauses = ["c.active = true", "d.active = true", "s.active = true", "c.tenant_id = ?"]
    params: list[Any] = [tenant_id]
    scope_clauses, scope_params = build_knowledge_scope_clauses(
        knowledge_scope=knowledge_scope,
        project_id=project_id,
        source_alias="s",
        chunk_alias="c",
    )
    clauses.extend(scope_clauses)
    params.extend(scope_params)
    if worker_uid:
        clauses.append("(c.worker_uid = ? OR c.worker_uid = '')")
        params.append(worker_uid)
    if source_id:
        clauses.append("c.source_id = ?")
        params.append(source_id)
    return " AND ".join(clauses), params


def _row_dicts(cur: Any, names: list[str] | None = None) -> list[dict[str, Any]]:
    if hasattr(cur, "fetchall"):
        rows = cur.fetchall()
        names = [str(d[0]) for d in (cur.description or [])]
    else:
        rows = cur if isinstance(cur, list) else []
        names = names or []
    return [dict(zip(names, row)) for row in rows]


def _search_knowledge_vector(
    con: Any,
    vector: list[float],
    *,
    tenant_id: str,
    project_id: str,
    worker_uid: str,
    source_id: str,
    knowledge_scope: str = "both",
    limit: int,
) -> list[dict[str, Any]]:
    vec_str = "[" + ",".join(str(float(x)) for x in vector) + "]"
    where_sql, params = _scope_where(
        tenant_id=tenant_id,
        project_id=project_id,
        worker_uid=worker_uid,
        source_id=source_id,
        knowledge_scope=knowledge_scope,
    )
    sql = f"""
        SELECT c.chunk_id, c.source_id, c.document_id, d.relative_path, c.chunk_index,
               c.content AS text,
               array_cosine_distance(c.embedding, {vec_str}::FLOAT[384]) AS score,
               'vector' AS match_type
        FROM main.admin_knowledge_chunks c
        JOIN main.admin_knowledge_documents d ON d.document_id = c.document_id
        JOIN main.admin_knowledge_sources s ON s.source_id = c.source_id
        WHERE {where_sql}
          AND c.embedding IS NOT NULL
          AND c.embedding_status = 'READY'
        ORDER BY score ASC
        LIMIT {limit}
    """
    try:
        return _row_dicts(
            con.execute(sql, params),
            ["chunk_id", "source_id", "document_id", "relative_path", "chunk_index", "text", "score", "match_type"],
        )
    except Exception:
        return []


def _search_knowledge_lexical(
    con: Any,
    query: str,
    *,
    tenant_id: str,
    project_id: str,
    worker_uid: str,
    source_id: str,
    knowledge_scope: str = "both",
    limit: int,
) -> list[dict[str, Any]]:
    tokens = lexical_tokens(query)
    if not tokens:
        return []
    where_sql, params = _scope_where(
        tenant_id=tenant_id,
        project_id=project_id,
        worker_uid=worker_uid,
        source_id=source_id,
        knowledge_scope=knowledge_scope,
    )
    token_clauses = []
    for token in tokens:
        token_clauses.append(
            "(strpos(lower(c.content), lower(?)) >= 1 OR strpos(lower(d.relative_path), lower(?)) >= 1)"
        )
        params.append(token)
        params.append(token)
    sql = f"""
        SELECT c.chunk_id, c.source_id, c.document_id, d.relative_path, c.chunk_index,
               c.content AS text,
               NULL::DOUBLE AS score,
               'lexical' AS match_type
        FROM main.admin_knowledge_chunks c
        JOIN main.admin_knowledge_documents d ON d.document_id = c.document_id
        JOIN main.admin_knowledge_sources s ON s.source_id = c.source_id
        WHERE {where_sql}
          AND ({' OR '.join(token_clauses)})
        ORDER BY c.updated_at DESC
        LIMIT {limit}
    """
    return _row_dicts(
        con.execute(sql, params),
        ["chunk_id", "source_id", "document_id", "relative_path", "chunk_index", "text", "score", "match_type"],
    )


def read_knowledge_document(
    con: Any,
    *,
    relative_path: str,
    tenant_id: str,
    project_id: str,
    worker_uid: str = "",
    knowledge_scope: str = "both",
    limit: int = 40,
) -> list[dict[str, Any]]:
    """Return all active chunks for a document matched by relative_path substring."""
    needle = (relative_path or "").strip().lstrip("/")
    if not needle:
        return []
    lim = max(1, min(int(limit), 80))
    where_sql, params = _scope_where(
        tenant_id=tenant_id,
        project_id=project_id,
        worker_uid=worker_uid,
        source_id="",
        knowledge_scope=knowledge_scope,
    )
    folded = fold_search_text(needle)
    params.extend([f"%{needle.lower()}%", f"%{folded}%"])
    sql = f"""
        SELECT c.chunk_id, c.source_id, c.document_id, d.relative_path, c.chunk_index,
               c.content AS text,
               NULL::DOUBLE AS score,
               'read' AS match_type
        FROM main.admin_knowledge_chunks c
        JOIN main.admin_knowledge_documents d ON d.document_id = c.document_id
        JOIN main.admin_knowledge_sources s ON s.source_id = c.source_id
        WHERE {where_sql}
          AND c.active = true
          AND d.active = true
          AND (
            lower(d.relative_path) LIKE lower(?)
            OR lower(d.relative_path) LIKE lower(?)
          )
        ORDER BY d.relative_path ASC, c.chunk_index ASC
        LIMIT {lim}
    """
    return _row_dicts(
        con.execute(sql, params),
        ["chunk_id", "source_id", "document_id", "relative_path", "chunk_index", "text", "score", "match_type"],
    )
