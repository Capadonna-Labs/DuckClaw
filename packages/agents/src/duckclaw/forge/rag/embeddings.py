"""Embeddings locales: endpoint HTTP MLX/OpenAI-compatible, luego sentence-transformers."""

from __future__ import annotations

import json as _json
import os
import urllib.error
import urllib.request
from typing import Any, List, Optional

_EMBEDDING_MODEL: Any = None
_EMBEDDING_DIM = 384  # all-MiniLM-L6-v2


def _embed_openai_compatible_http(text: str) -> Optional[List[float]]:
    """
    POST a DUCKCLAW_MLX_EMBEDDINGS_URL (URL completa del endpoint, p. ej. .../v1/embeddings).
    Respuesta estilo OpenAI: {"data":[{"embedding":[...]}]}.
    """
    url = (os.environ.get("DUCKCLAW_MLX_EMBEDDINGS_URL") or "").strip()
    if not url:
        return None
    model = (os.environ.get("DUCKCLAW_MLX_EMBEDDINGS_MODEL") or "mlx-embed").strip()
    body = _json.dumps({"input": text, "model": model}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = _json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, _json.JSONDecodeError, OSError):
        return None
    except Exception:
        return None
    try:
        data = payload.get("data")
        if isinstance(data, list) and data:
            emb = data[0].get("embedding") if isinstance(data[0], dict) else None
            if isinstance(emb, list) and emb and all(isinstance(x, (int, float)) for x in emb):
                out = [float(x) for x in emb]
                if len(out) == _EMBEDDING_DIM:
                    return out
    except Exception:
        return None
    return None


def get_embedding_model():
    """Carga el modelo de embeddings (lazy). Retorna None si no está disponible."""
    global _EMBEDDING_MODEL
    if _EMBEDDING_MODEL is not None:
        return _EMBEDDING_MODEL
    try:
        from sentence_transformers import SentenceTransformer

        _EMBEDDING_MODEL = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        return _EMBEDDING_MODEL
    except ImportError:
        return None


def embed_text(text: str) -> Optional[List[float]]:
    """Vectoriza texto: primero HTTP MLX/OpenAI-compatible (si URL), luego sentence-transformers."""
    if not (text or "").strip():
        return None
    http_vec = _embed_openai_compatible_http(text)
    if http_vec is not None:
        return http_vec
    model = get_embedding_model()
    if model is None:
        return None
    emb = model.encode(text, convert_to_numpy=True)
    return emb.tolist()
