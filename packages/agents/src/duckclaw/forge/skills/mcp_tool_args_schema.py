"""
Construye modelos Pydantic v2 desde inputSchema JSON de MCP para StructuredTool.args_schema.

Sin esto, StructuredTool.from_function(**kwargs) suele generar esquemas inválidos o vacíos y
ChatOpenAI/MLX puede omitir la tool en bind_tools (ver llm_providers.bind_tools_with_parallel_default).
"""

from __future__ import annotations

import re
from typing import Any, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, create_model


def _sanitize_model_name(name: str) -> str:
    safe = re.sub(r"[^0-9a-zA-Z_]", "_", (name or "mcp_tool").strip())
    if not safe:
        safe = "McpToolArgs"
    if safe[0].isdigit():
        safe = "M_" + safe
    return safe[:79]


def _annotation_for_property(spec: dict[str, Any]) -> Any:
    if not isinstance(spec, dict):
        return Any
    if "enum" in spec and isinstance(spec["enum"], list) and spec["enum"]:
        return str
    jt = spec.get("type")
    if jt == "string":
        return str
    if jt == "number":
        return float
    if jt == "integer":
        return int
    if jt == "boolean":
        return bool
    if jt == "array":
        return list[Any]
    if jt == "object":
        return dict[str, Any]
    return Any


def mcp_input_schema_to_args_model(
    input_schema: Optional[dict[str, Any]],
    model_name_base: str,
) -> type[BaseModel]:
    """
    Convierte el dict inputSchema de una tool MCP (tipo objeto + properties) en un BaseModel.

    - Campos opcionales según `required`.
    - Propiedades no listadas o tipos desconocidos → Any.
    - `model_config.extra = "allow"` para reenviar claves extra al servidor MCP.
    """
    cls_name = _sanitize_model_name(model_name_base)
    cfg = ConfigDict(extra="allow")

    if not isinstance(input_schema, dict):
        return create_model(cls_name, __config__=cfg)  # type: ignore[call-overload]

    props = input_schema.get("properties")
    if not isinstance(props, dict) or not props:
        return create_model(cls_name, __config__=cfg)  # type: ignore[call-overload]

    raw_required = input_schema.get("required")
    if isinstance(raw_required, (list, tuple, set)):
        required_set = {str(x) for x in raw_required if isinstance(x, str)}
    else:
        required_set = set()

    field_defs: dict[str, Any] = {}
    for key, p_spec in props.items():
        if not isinstance(key, str) or not key:
            continue
        p_dict = p_spec if isinstance(p_spec, dict) else {}
        ann = _annotation_for_property(p_dict)
        desc = ""
        if isinstance(p_dict.get("description"), str):
            desc = p_dict["description"].strip()
        default_any = p_dict.get("default")
        if key in required_set:
            field_defs[key] = (
                ann,
                Field(..., description=desc) if desc else Field(...),
            )
        else:
            if "default" in p_dict:
                field_defs[key] = (
                    ann,
                    Field(default=default_any, description=desc) if desc else Field(default=default_any),
                )
            else:
                field_defs[key] = (
                    Union[ann, None],
                    Field(default=None, description=desc) if desc else Field(default=None),
                )

    if not field_defs:
        return create_model(cls_name, __config__=cfg)  # type: ignore[call-overload]

    return create_model(cls_name, __config__=cfg, **field_defs)  # type: ignore[call-overload]
