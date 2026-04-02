"""Lectura read-only de ``main.semantic_memory`` para ``/context --summary`` (sin encolar escrituras)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

_log = logging.getLogger("duckclaw.gateway.context_stored_snapshot")

DEFAULT_MAX_ROWS = 80
DEFAULT_MAX_CHARS = 14_000


def _semantic_rows_to_text(rows: list[tuple[Any, Any, Any]], cap: int) -> str:
    if not rows:
        return ""
    parts: list[str] = []
    for i, (content, source, created) in enumerate(rows, start=1):
        block = (
            f"--- registro {i} (source={source}, created_at={created}) ---\n"
            f"{(content or '').strip() if content is not None else ''}"
        )
        parts.append(block)
    raw = "\n\n".join(parts)
    if len(raw) > cap:
        raw = raw[: max(0, cap - 24)].rstrip() + "\n\n[… truncado …]"
    return raw


def _rows_from_query_json(raw: str) -> list[tuple[str, str, str]]:
    try:
        data = json.loads(raw) if isinstance(raw, str) else []
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    out: list[tuple[str, str, str]] = []
    for r in data:
        if not isinstance(r, dict):
            continue
        lk = {str(k).lower(): v for k, v in r.items()}
        content = lk.get("content")
        source = lk.get("sm_source", lk.get("source", ""))
        created = lk.get("sm_created", lk.get("created_at", ""))
        out.append(
            (
                "" if content is None else str(content),
                "" if source is None else str(source),
                "" if created is None else str(created),
            )
        )
    return out


def _snapshot_via_reuse_connection(db: Any, *, lim: int, cap: int) -> str:
    """Usa DuckClaw (u objeto con .query) ya abierto; evita segundo connect al mismo archivo."""
    if not hasattr(db, "query"):
        return ""
    try:
        raw = db.query(
            f"""
            SELECT content,
                   COALESCE(source, '') AS sm_source,
                   COALESCE(CAST(created_at AS VARCHAR), '') AS sm_created
            FROM main.semantic_memory
            ORDER BY created_at DESC NULLS LAST
            LIMIT {int(lim)}
            """
        )
    except Exception as exc:  # noqa: BLE001
        _log.debug("semantic snapshot via reuse connection: %s", exc)
        return ""
    rows = _rows_from_query_json(raw)
    return _semantic_rows_to_text(rows, cap)


def fetch_semantic_memory_snapshot(
    db_path: str,
    *,
    max_rows: int = DEFAULT_MAX_ROWS,
    max_chars: int = DEFAULT_MAX_CHARS,
    reuse_readonly_connection: Any | None = None,
) -> str:
    """
    Devuelve texto concatenado de las filas más recientes de ``main.semantic_memory``.
    Cadena vacía si no hay archivo, tabla, o filas.

    ``reuse_readonly_connection`` es opcional; el gateway ya no mantiene un handle RO persistente
    al vault. Si se pasa y coincide la ruta, se intenta primero; si no hay filas, se abre una
    conexión RO efímera (p. ej. datos recién escritos por db-writer).
    """
    path = Path(db_path).expanduser().resolve()
    if not path.is_file():
        return ""
    lim = max(1, min(int(max_rows), 500))
    cap = max(1024, int(max_chars))

    reuse_matched_but_empty = False
    if reuse_readonly_connection is not None:
        try:
            rpath_raw = str(getattr(reuse_readonly_connection, "_path", "") or "").strip()
            if rpath_raw:
                rpath = Path(rpath_raw).expanduser().resolve()
                if rpath == path:
                    text = _snapshot_via_reuse_connection(reuse_readonly_connection, lim=lim, cap=cap)
                    if text:
                        return text
                    reuse_matched_but_empty = True
                    _log.debug(
                        "semantic snapshot: reuse sin filas; intentando lectura RO efímera al mismo archivo."
                    )
        except Exception as exc:  # noqa: BLE001
            _log.debug("semantic snapshot reuse path compare failed: %s", exc)

    try:
        import duckdb
    except ImportError:
        _log.warning("fetch_semantic_memory_snapshot: duckdb no disponible")
        return ""

    con = None
    rows: list[tuple[Any, Any, Any]] = []
    try:
        con = duckdb.connect(str(path), read_only=True)
        rows = con.execute(
            """
            SELECT content, COALESCE(source, ''), COALESCE(CAST(created_at AS VARCHAR), '')
            FROM main.semantic_memory
            ORDER BY created_at DESC NULLS LAST
            LIMIT ?
            """,
            [lim],
        ).fetchall()
    except Exception as exc:  # noqa: BLE001
        msg = str(exc).lower()
        if "lock" in msg or "conflicting" in msg:
            _log.warning(
                "fetch_semantic_memory_snapshot: DuckDB bloqueado por otro proceso (%s). "
                "Cierra conexiones exclusivas o reintenta; no es lo mismo que tabla vacía.",
                exc,
            )
        else:
            _log.debug("fetch_semantic_memory_snapshot: sin datos o error: %s", exc)
        return ""
    finally:
        if con is not None:
            try:
                con.close()
            except Exception:
                pass
    out = _semantic_rows_to_text(rows, cap)
    if reuse_matched_but_empty and out:
        _log.debug(
            "semantic snapshot: lectura efímera devolvió filas tras reuse vacío (conexión del grafo desfasada)."
        )
    return out
