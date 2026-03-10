"""
AudioTranscriber — transcripción local con MLX Whisper.

Spec: specs/Pipeline_Ingestion_Multimodal_Voz_Vision.md
Habeas Data: el archivo DEBE borrarse tras transcripción.
"""

from __future__ import annotations

from pathlib import Path


def transcribe_audio(file_path: str) -> str:
    """
    Transcribe audio a texto. Usa mlx-whisper si disponible.
    Retorna texto vacío si falla. El caller debe borrar el archivo en finally.
    """
    p = Path(file_path)
    if not p.is_file():
        return ""

    try:
        import mlx_whisper
        result = mlx_whisper.transcribe(str(p))
        text = result.get("text", "") if isinstance(result, dict) else str(result)
        return (text or "").strip() if text else ""
    except ImportError:
        return ""
    except Exception:
        return ""
