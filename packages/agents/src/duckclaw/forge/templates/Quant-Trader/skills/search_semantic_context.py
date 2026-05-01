"""Skill: VSS sobre main.semantic_memory (igual contrato Finanz — Quant Trader)."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from langchain_core.tools import StructuredTool

_DEBUG_SESSION_LOG = Path(
    "/Users/juanjosearevalocamargo/Desktop/duckclaw/.cursor/debug-c964f7.log"
)


def _agent_dbg_skill(data: dict[str, Any], *, hypothesis_id: str, location: str) -> None:
    # region agent log
    try:
        payload = {
            "sessionId": "c964f7",
            "hypothesisId": hypothesis_id,
            "location": location,
            "timestamp": int(time.time() * 1000),
            "runId": "pre-fix",
            **data,
        }
        with _DEBUG_SESSION_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass

    # endregion


def get_tools(db: Any, schema_name: str, spec: Any = None) -> list:
    _ = schema_name
    _ = spec

    def search_semantic_context(query: str, limit: int = 3) -> str:
        """Embeddings cosine si están disponibles; si no hay PyTorch/MLX, búsqueda léxica en texto persistido."""
        q = (query or "").strip()
        if not q:
            return ""
        try:
            from duckclaw.forge.atoms.semantic_memory_hybrid import (
                lexical_tokens,
                search_semantic_memory_hybrid,
            )
            from duckclaw.forge.rag.embeddings import embed_text

            has_mlx_url = bool((os.environ.get("DUCKCLAW_MLX_EMBEDDINGS_URL") or "").strip())
            emb_chk = embed_text(q[:384])
            emb_runtime_ok = isinstance(emb_chk, list) and len(emb_chk) == 384
            rows, diag = search_semantic_memory_hybrid(db, q, max(1, min(int(limit), 20)))
            ready_count: int | None = None
            try:
                cr = db.query(
                    """
                    SELECT COUNT(*) AS c FROM main.semantic_memory
                    WHERE embedding IS NOT NULL
                      AND lower(trim(COALESCE(embedding_status, ''))) = 'ready'
                    """
                )
                cj = json.loads(cr) if isinstance(cr, str) else (cr or [])
                if cj and isinstance(cj[0], dict) and cj[0].get("c") is not None:
                    ready_count = int(cj[0]["c"])
            except Exception:
                pass
            mode = diag.get("mode") or "none"
            # region agent log
            _agent_dbg_skill(
                {
                    "message": "search_semantic_context_hybrid_diag",
                    "data": {
                        "has_mlx_embeddings_url": has_mlx_url,
                        "emb_runtime_ok": emb_runtime_ok,
                        "ready_rows_approx": ready_count,
                        "mode": mode,
                        "matching_rows": len(rows),
                        "tokens": lexical_tokens(q)[:6],
                    },
                },
                hypothesis_id="H_vss_hybrid_gateway",
                location="Quant-Trader/skills/search_semantic_context:hybrid",
            )
            # endregion
            if not rows:
                return ""
            badge = "[vector]" if mode == "vector" else "[lexical]"
            lines: list[str] = []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                cid = str(row.get("id") or "")
                content = str(row.get("content") or "").strip()
                src = str(row.get("source") or "")
                dist = row.get("dist")
                st = str(row.get("embedding_status") or "").strip()
                lines.append(
                    f"- [{cid[:8]}…] {badge} ({src}) status={st} dist={dist}\n  {content[:500]}"
                )
            hdr = "(vector READY)" if mode == "vector" else "(fallback léxico sobre texto persistido)"
            return hdr + "\n" + "\n".join(lines) if lines else ""
        except Exception:  # noqa: BLE001
            return ""

    return [
        StructuredTool.from_function(
            search_semantic_context,
            name="search_semantic_context",
            description=(
                "Busca en main.semantic_memory: VSS cosine si embeddings OK; si el Gateway sin PyTorch/MLX,"
                " hace fallback léxico (palabras). Incluye filas sólo texto (PENDING)."
            ),
        )
    ]
