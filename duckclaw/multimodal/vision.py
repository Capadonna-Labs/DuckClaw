"""
VisionInterpreter — descripción de imágenes local (Moondream2 / Llama-Vision).

Spec: specs/Pipeline_Ingestion_Multimodal_Voz_Vision.md
"""

from __future__ import annotations

from pathlib import Path

_VISION_PROMPT = (
    "Describe detalladamente este objeto industrial, prestando atención a materiales, "
    "formas, números de serie o daños visibles."
)


def describe_image(file_path: str, prompt: str | None = None) -> str:
    """
    Genera descripción de imagen. Usa mlx-vlm o transformers si disponible.
    Retorna texto vacío si falla.
    """
    p = Path(file_path)
    if not p.is_file():
        return ""

    prompt = (prompt or _VISION_PROMPT).strip()

    try:
        from mlx_vlm import load, generate
        model, processor = load("mlx-community/Moondream2")
        image = processor.image_processor.load(str(p))
        out = generate(model, processor, image, prompt, max_tokens=256)
        return (out or "").strip()
    except ImportError:
        pass
    except Exception:
        pass

    try:
        from transformers import AutoModelForCausalLM
        from PIL import Image
        model = AutoModelForCausalLM.from_pretrained(
            "vikhyatk/moondream2", trust_remote_code=True
        )
        img = Image.open(str(p)).convert("RGB")
        result = model.caption(img, length="medium")
        return (result.get("caption", "") or "").strip()
    except ImportError:
        pass
    except Exception:
        pass

    return ""
