"""Android MCP screenshots → vault artifacts + compact tool results."""

from __future__ import annotations

import base64
import json
import re
import uuid
from pathlib import Path
from typing import Any

_ANDROID_SCREENSHOT_RE = re.compile(
    r"type\s*=\s*['\"]image['\"][^'\"]*data\s*=\s*['\"]([A-Za-z0-9+/=\s]+)['\"]",
    re.DOTALL,
)
_B64_DATA_URI_RE = re.compile(
    r"data:image/[a-zA-Z0-9.+-]+;base64,([A-Za-z0-9+/=\s]+)",
)


def is_android_screenshot_tool(tool_name: str) -> bool:
    name = (tool_name or "").strip().lower()
    return name.endswith("__get_screenshot") or name.endswith("__get_screenshot_screen")


def parse_mcp_screenshot_bytes(raw: str) -> bytes | None:
    """Extract PNG/JPEG bytes from MCP screenshot tool text/ImageContent repr."""
    text = (raw or "").strip()
    if not text or text.lower().startswith("error"):
        return None
    for pattern in (_ANDROID_SCREENSHOT_RE, _B64_DATA_URI_RE):
        m = pattern.search(text)
        if m:
            try:
                return base64.b64decode("".join(m.group(1).split()), validate=False)
            except Exception:
                continue
    if len(text) > 256 and re.fullmatch(r"[A-Za-z0-9+/=\s]+", text):
        try:
            return base64.b64decode("".join(text.split()), validate=False)
        except Exception:
            return None
    return None


def _tenant_artifacts_dir(tenant_id: str) -> Path:
    from duckclaw.vaults import user_vault_dir

    tid = (tenant_id or "default").strip() or "default"
    path = user_vault_dir(tid) / "artifacts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def persist_android_screenshot_artifact(
    image_bytes: bytes,
    *,
    tenant_id: str = "default",
) -> dict[str, Any]:
    tid = (tenant_id or "default").strip() or "default"
    if not image_bytes or len(image_bytes) < 32:
        return {"ok": False, "error": "screenshot vacío o demasiado pequeño"}
    artifact_id = str(uuid.uuid4())
    art_dir = _tenant_artifacts_dir(tid)
    out_path = art_dir / f"{artifact_id}.png"
    out_path.write_bytes(image_bytes)
    b64 = base64.standard_b64encode(image_bytes).decode("ascii")
    return {
        "ok": True,
        "artifact_id": artifact_id,
        "figure_base64": b64,
        "path": str(out_path),
    }


def compact_android_screenshot_tool_result(
    artifact_id: str,
    *,
    hint: str = "",
) -> str:
    payload: dict[str, Any] = {
        "ok": True,
        "artifact_id": artifact_id,
        "vision": True,
        "hint": hint
        or (
            "Captura guardada como artefacto visual. "
            "Usa get_ui_dump para navegar; la imagen se muestra en el playground."
        ),
    }
    return json.dumps(payload, ensure_ascii=False)


def process_android_screenshot_tool_result(
    raw: str,
    *,
    tenant_id: str = "default",
) -> tuple[str, dict[str, Any]]:
    """
    Parse MCP screenshot output, persist artifact, return compact JSON for the LLM.

    Returns (tool_message_content, sidecar) where sidecar may include figure_base64.
    """
    image_bytes = parse_mcp_screenshot_bytes(raw)
    if not image_bytes:
        return raw, {}
    saved = persist_android_screenshot_artifact(image_bytes, tenant_id=tenant_id)
    if not saved.get("ok"):
        return raw, {}
    aid = str(saved.get("artifact_id") or "").strip()
    if not aid:
        return raw, {}
    return compact_android_screenshot_tool_result(aid), saved
