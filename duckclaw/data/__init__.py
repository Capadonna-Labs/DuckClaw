"""duckclaw.data — Pipeline zero-copy basado en PyArrow.

Spec: specs/Pipeline_de_Datos_Zero-Copy_con_PyArrow.md
"""

from .arrow_bridge import (
    ArrowBridge,
    StreamingBatchReader,
    LLMContextSerializer,
    SandboxDataChannel,
    arrow_available,
)

__all__ = [
    "ArrowBridge",
    "StreamingBatchReader",
    "LLMContextSerializer",
    "SandboxDataChannel",
    "arrow_available",
]
