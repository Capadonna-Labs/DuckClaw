"""Metadatos y persistencia de artefactos visuales (ComfyUI, fly charts)."""

from __future__ import annotations

import json
import uuid
from typing import Any

from core.sandbox_figure_b64 import decode_sandbox_figure_base64, decode_valid_sandbox_image_bytes


def visual_artifact_id_from_messages(messages: Any) -> str:
    """Fallback: artifact_id del último generate_visual_asset OK en mensajes del turno."""
    try:
        from langchain_core.messages import ToolMessage
    except ImportError:
        return ""
    if not isinstance(messages, list):
        return ""
    for msg in reversed(messages):
        if not isinstance(msg, ToolMessage):
            continue
        if (msg.name or "") not in ("generate_visual_asset", "edit_visual_asset"):
            continue
        try:
            payload = json.loads(str(msg.content or ""))
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict) or not payload.get("ok"):
            continue
        aid = str(payload.get("artifact_id") or "").strip()
        if aid:
            return aid
    return ""


def persist_admin_fly_charts(tenant_id: str, fly_charts_b64: list[str]) -> list[str]:
    """Escribe PNG de fly commands en db/private/{tenant}/artifacts/ (evita SSE gigante)."""
    from duckclaw.forge.skills.comfyui_bridge import tenant_artifacts_dir

    tid = (tenant_id or "default").strip() or "default"
    art_dir = tenant_artifacts_dir(tid)
    ids: list[str] = []
    for photo_b64 in fly_charts_b64:
        png_bytes = decode_valid_sandbox_image_bytes(photo_b64)
        if not png_bytes:
            png_bytes = decode_sandbox_figure_base64(photo_b64)
        if not png_bytes:
            continue
        aid = str(uuid.uuid4())
        (art_dir / f"{aid}.png").write_bytes(png_bytes)
        ids.append(aid)
    return ids


def collect_visual_artifact_ids_for_history(result: dict[str, Any]) -> list[str]:
    """Artifact UUIDs to embed in Redis history for admin chart reload."""
    if not isinstance(result, dict):
        return []
    seen: set[str] = set()
    ordered: list[str] = []
    fly_raw = result.get("fly_chart_artifact_ids")
    if isinstance(fly_raw, list):
        for raw in fly_raw:
            aid = str(raw or "").strip()
            if aid and aid not in seen:
                seen.add(aid)
                ordered.append(aid)
    for key in ("artifact_id", "visual_artifact_id"):
        aid = str(result.get(key) or "").strip()
        if aid and aid not in seen:
            seen.add(aid)
            ordered.append(aid)
    return ordered


def embed_visual_artifact_markers_for_history(
    text: str,
    result: dict[str, Any],
    *,
    chart_names: list[str] | None = None,
) -> str:
    """
    Append ``visual_artifact_id`` lines so admin UI can rebuild chart previews from Redis history.
    """
    aids = collect_visual_artifact_ids_for_history(result)
    if not aids:
        return text or ""
    names = [str(n or "").strip() for n in (chart_names or []) if str(n or "").strip()]
    lines: list[str] = []
    for i, aid in enumerate(aids):
        suffix = f"  # {names[i]}" if i < len(names) else ""
        lines.append(f"visual_artifact_id: {aid}{suffix}")
    block = "\n".join(lines)
    base = (text or "").rstrip()
    return f"{base}\n\n{block}" if base else block


def admin_visual_fields_from_invoke_result(
    session_id: str,
    result: dict[str, Any],
    tenant_id: str,
) -> dict[str, Any]:
    """Metadatos de imagen para SSE/JSON del playground admin (ComfyUI → artifacts/)."""
    from duckclaw.graphs.chat_heartbeat import is_admin_ui_chat_session

    if not is_admin_ui_chat_session(session_id):
        return {}
    out: dict[str, Any] = {}
    tid = (tenant_id or "default").strip() or "default"
    fly_artifact_ids_raw = result.get("fly_chart_artifact_ids")
    fly_artifact_ids: list[str] = []
    if isinstance(fly_artifact_ids_raw, list):
        fly_artifact_ids = [str(x).strip() for x in fly_artifact_ids_raw if str(x).strip()]
    if fly_artifact_ids:
        out["fly_chart_artifact_ids"] = fly_artifact_ids
        out["artifact_tenant_id"] = tid
        if not (result.get("visual_artifact_id") or result.get("artifact_id") or "").strip():
            out["artifact_id"] = fly_artifact_ids[0]
    fly_chart_names_raw = result.get("fly_chart_names")
    fly_chart_names: list[str] = []
    if isinstance(fly_chart_names_raw, list):
        fly_chart_names = [str(x).strip() for x in fly_chart_names_raw if str(x).strip()]
    if fly_chart_names:
        out["fly_chart_names"] = fly_chart_names
    fly_charts_raw = result.get("fly_charts_b64")
    fly_charts: list[str] = []
    if isinstance(fly_charts_raw, list):
        fly_charts = [str(c).strip() for c in fly_charts_raw if str(c).strip()]
    b64 = (result.get("sandbox_photo_base64") or result.get("figure_base64") or "").strip()
    if not b64 and fly_charts:
        b64 = fly_charts[0]
    if b64:
        out["figure_base64"] = b64
    if fly_charts:
        out["fly_charts_b64"] = fly_charts
    aid = (result.get("visual_artifact_id") or result.get("artifact_id") or "").strip()
    if not aid:
        aid = visual_artifact_id_from_messages(result.get("messages"))
    if aid:
        out["artifact_id"] = aid
        out["artifact_tenant_id"] = tid
    return out
