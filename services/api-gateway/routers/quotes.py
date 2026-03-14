"""
Router de cotizaciones del microservicio API Gateway (services/api-gateway).

Spec: specs/core/04_Cognitive_Agent_Logic.md — GET /api/v1/quotes/download/{quote_id}
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

router = APIRouter(prefix="/api/v1/quotes", tags=["quotes"])


def _gateway_db_path() -> str:
    """Ruta de la BD del Gateway (misma que usa el agente). Resuelve desde repo root."""
    path = os.environ.get("DUCKCLAW_DB_PATH", "").strip()
    if path:
        return path
    # Default relativo al repo (cuando cwd es repo root)
    return os.environ.get("DUCKDB_PATH", "db/duckclaw.duckdb").strip() or "db/duckclaw.duckdb"


@router.get("/download/{quote_id}")
async def download_quote(
    quote_id: str,
    token: str = Query(..., description="Token de descarga un solo uso"),
) -> FileResponse:
    """Descarga el PDF de la cotización si el token es válido."""
    try:
        from duckclaw.forge.quotes.schema import QUOTES_DIR
        from duckclaw import DuckClaw
    except ImportError:
        raise HTTPException(status_code=501, detail="Módulo de cotizaciones no disponible")

    db_path = _gateway_db_path()
    if not os.path.isabs(db_path):
        # Resolver respecto al repo root (parent de services/)
        _root = Path(__file__).resolve().parent.parent.parent
        db_path = str(_root / db_path)
    db = DuckClaw(db_path)
    # Escapar comillas para SQL (DuckClaw.query solo acepta sql string)
    qid_esc = (quote_id or "").replace("'", "''")[:128]
    tok_esc = (token or "").replace("'", "''")[:256]
    try:
        r = db.query(
            f"SELECT pdf_path, download_token FROM quotes WHERE quote_id = '{qid_esc}' AND download_token = '{tok_esc}'"
        )
    except Exception:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")

    rows = r if isinstance(r, list) else json.loads(r) if isinstance(r, str) else []
    if not rows or not isinstance(rows, list):
        try:
            rows = json.loads(r) if isinstance(r, str) else []
        except Exception:
            rows = []
    if not rows:
        raise HTTPException(status_code=404, detail="Cotización no encontrada o token inválido")

    row = rows[0] if isinstance(rows[0], dict) else {}
    pdf_path = (row.get("pdf_path") or "").strip()
    if not pdf_path or not Path(pdf_path).is_file():
        # Buscar en QUOTES_DIR por quote_id
        candidates = list(Path(QUOTES_DIR).glob(f"*{quote_id}*.pdf"))
        if not candidates:
            raise HTTPException(status_code=404, detail="PDF no generado aún")
        pdf_path = str(candidates[0])

    return FileResponse(pdf_path, media_type="application/pdf", filename=f"cotizacion_{quote_id}.pdf")
