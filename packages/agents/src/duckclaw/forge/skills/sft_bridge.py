"""
SFT Bridge — tool para generar dataset SFT desde trazas.

Spec: specs/Migracion_de_Pipeline_de_Entrenamiento_(GRPO_a_SFT_con_MLX).md
"""

from __future__ import annotations

from typing import Any, Optional


def _collect_sft_dataset_impl(
    traces_root: Optional[str] = None,
    output_path: Optional[str] = None,
) -> str:
    """Genera dataset SFT Gemma desde conversation_traces (status SUCCESS)."""
    from duckclaw.forge.sft import collect_traces_to_sft

    records, stats = collect_traces_to_sft(
        traces_root=traces_root,
        output_path=output_path,
    )
    return (
        f"Generado {stats['total_output']} ejemplos en {stats['output_path']}. "
        f"Omitidos: {stats['skipped_sql']} SQL inválido, "
        f"{stats['skipped_non_success']} no SUCCESS, "
        f"{stats['skipped_malformed']} malformados."
    )


def _collect_sft_dataset_tool(config: Optional[dict] = None) -> Optional[Any]:
    """
    Crea un StructuredTool para generar dataset SFT.
    config: sft_enabled (bool).
    """
    cfg = config or {}
    if cfg.get("sft_enabled") is False:
        return None

    from langchain_core.tools import StructuredTool

    return StructuredTool.from_function(
        _collect_sft_dataset_impl,
        name="collect_sft_dataset",
        description=(
            "Genera dataset SFT Gemma (messages user/assistant) desde conversation_traces/*.jsonl, "
            "solo status SUCCESS. DataMasker + validación SQL (sqlglot). "
            "Salida por defecto train/gemma4/dataset_sft.jsonl. "
            "Argumentos opcionales: traces_root, output_path."
        ),
    )


def register_sft_skill(
    tools_list: list[Any],
    sft_config: Optional[dict] = None,
) -> None:
    """
    Registra la herramienta collect_sft_dataset en la lista.
    Llamar desde build_worker_graph o build_general_graph cuando el manifest tiene skills.sft.
    """
    if not sft_config:
        return
    try:
        tool = _collect_sft_dataset_tool(sft_config)
        if tool:
            tools_list.append(tool)
    except Exception:
        pass
