"""Embeddings locales: endpoint HTTP MLX/OpenAI-compatible, luego sentence-transformers."""

from __future__ import annotations

import json as _json
import os
import urllib.error
import urllib.request
from typing import Any, List, Optional

_EMBEDDING_MODEL: Any = None
_EMBEDDING_DIM = 384  # all-MiniLM-L6-v2


def _parse_openai_embedding_vector(raw: object) -> Optional[List[float]]:
    if not isinstance(raw, list) or not raw or not all(isinstance(x, (int, float)) for x in raw):
        return None
    out = [float(x) for x in raw]
    if len(out) == _EMBEDDING_DIM:
        return out
    return None


def _embed_openai_compatible_http_batch(texts: List[str]) -> Optional[List[Optional[List[float]]]]:
    """
    POST a DUCKCLAW_MLX_EMBEDDINGS_URL (URL completa del endpoint, p. ej. .../v1/embeddings).
    Respuesta estilo OpenAI: {"data":[{"embedding":[...]}, ...]}.
    """
    url = (os.environ.get("DUCKCLAW_MLX_EMBEDDINGS_URL") or "").strip()
    if not url or not texts:
        return None
    model = (os.environ.get("DUCKCLAW_MLX_EMBEDDINGS_MODEL") or "mlx-embed").strip()
    body = _json.dumps({"input": texts, "model": model}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = _json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, _json.JSONDecodeError, OSError):
        return None
    except Exception:
        return None
    try:
        data = payload.get("data")
        if not isinstance(data, list) or len(data) != len(texts):
            return None
        out: list[Optional[List[float]]] = []
        for item in data:
            emb = item.get("embedding") if isinstance(item, dict) else None
            out.append(_parse_openai_embedding_vector(emb))
        if all(vec is not None for vec in out):
            return out
    except Exception:
        return None
    return None


def _embed_openai_compatible_http(text: str) -> Optional[List[float]]:
    batch = _embed_openai_compatible_http_batch([text])
    if batch is None:
        return None
    return batch[0]


def get_embedding_model():
    """Carga el modelo de embeddings (lazy). Retorna None si no está disponible."""
    global _EMBEDDING_MODEL
    if _EMBEDDING_MODEL is not None:
        return _EMBEDDING_MODEL
    try:
        from duckclaw.process_role import gateway_embedding_policy, is_gateway_process

        if is_gateway_process() and gateway_embedding_policy() == "remote_only":
            return None
    except ImportError:
        pass
    try:
        from sentence_transformers import SentenceTransformer

        _EMBEDDING_MODEL = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        return _EMBEDDING_MODEL
    except ImportError:
        return None


def embed_text(text: str) -> Optional[List[float]]:
    """Vectoriza texto: primero HTTP MLX/OpenAI-compatible (si URL), luego sentence-transformers."""
    vecs = embed_texts([text])
    return vecs[0] if vecs else None


def embed_texts(texts: List[str]) -> List[Optional[List[float]]]:
    """Vectoriza textos en batch cuando el backend lo soporta."""
    if not texts:
        return []
    from duckclaw.knowledge_indexer_config import knowledge_embed_batch_size

    batch_size = knowledge_embed_batch_size()
    out: list[Optional[List[float]]] = [None] * len(texts)
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        non_empty: list[tuple[int, str]] = [
            (start + idx, text) for idx, text in enumerate(batch) if (text or "").strip()
        ]
        if not non_empty:
            continue
        payload = [text for _, text in non_empty]
        http_vecs = _embed_openai_compatible_http_batch(payload)
        if http_vecs is not None:
            for (global_idx, _text), vec in zip(non_empty, http_vecs):
                out[global_idx] = vec
            continue
        model = get_embedding_model()
        if model is None:
            continue
        encoded = model.encode(
            payload,
            batch_size=min(batch_size, len(payload)),
            convert_to_numpy=True,
        )
        for (global_idx, _text), emb in zip(non_empty, encoded):
            out[global_idx] = emb.tolist()
    return out
