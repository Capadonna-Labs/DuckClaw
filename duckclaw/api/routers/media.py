"""Media router: upload de voz/imagen para pipeline multimodal."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

router = APIRouter(prefix="/api/v1/agent", tags=["media"])

MEDIA_DIR = Path(os.environ.get("DUCKCLAW_MEDIA_DIR", "/tmp/duckclaw_media"))
ALLOWED_AUDIO = {"audio/ogg", "audio/mpeg", "audio/mp3", "audio/wav"}
ALLOWED_IMAGE = {"image/jpeg", "image/png", "image/jpg"}


def _ensure_media_dir() -> Path:
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    return MEDIA_DIR


@router.post("/{worker_id}/media/{thread_id}", summary="Upload de medio (voz/imagen)")
async def upload_media(worker_id: str, thread_id: str, file: UploadFile = File(...)):
    """
    Recibe archivo multipart. Guarda en /tmp/duckclaw_media/, encola en ARQ.
    Retorna task_id para polling. Habeas Data: audio se borra tras transcripción.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Archivo requerido")

    content_type = (file.content_type or "").lower()
    if content_type not in ALLOWED_AUDIO and content_type not in ALLOWED_IMAGE:
        raise HTTPException(
            status_code=400,
            detail=f"MIME no permitido. Audio: {ALLOWED_AUDIO}; Imagen: {ALLOWED_IMAGE}",
        )

    ext = Path(file.filename).suffix or (".ogg" if "audio" in content_type else ".jpg")
    task_id = str(uuid.uuid4())
    safe_ext = ext.lower()[:8]
    dest = _ensure_media_dir() / f"{'audio' if content_type in ALLOWED_AUDIO else 'img'}_{task_id}{safe_ext}"

    try:
        content = await file.read()
        dest.write_bytes(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error guardando archivo: {e}")

    redis_url = os.environ.get("REDIS_URL") or os.environ.get("ARQ_REDIS_URL")
    if not redis_url:
        raise HTTPException(
            status_code=503,
            detail="REDIS_URL no configurado. Modo síncrono no soportado para media.",
        )

    try:
        from arq import create_pool
        from arq.connections import RedisSettings

        parts = redis_url.replace("redis://", "").split("/")[0].split(":")
        settings = RedisSettings(host=parts[0], port=int(parts[1]) if len(parts) > 1 else 6379)
        pool = await create_pool(settings)
        try:
            job = await pool.enqueue_job(
                "process_multimodal_input",
                worker_id,
                thread_id,
                str(dest),
                content_type,
            )
            return {"status": "processing", "task_id": job.job_id}
        finally:
            await pool.close()
    except ImportError:
        raise HTTPException(status_code=503, detail="arq no instalado. uv sync --extra queue")
    except Exception as e:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=503, detail=str(e))
