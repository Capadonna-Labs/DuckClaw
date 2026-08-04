"""Harness de ejecución: riesgo, envelope, circuit breaker, presupuesto de resultado."""

from __future__ import annotations

import json
import logging
from typing import Any, Literal

RiskTier = Literal["read", "write", "network", "destructive"]
ApprovalMode = Literal["auto", "suggest", "never"]

_log = logging.getLogger(__name__)

DEFAULT_MAX_FAILURES_PER_TOOL = 2
DEFAULT_MAX_TOOL_RESULT_CHARS = 12_000
DEFAULT_APPROVAL_MODE: ApprovalMode = "suggest"

# Sandbox tools are destructive tier but admin playground toggle = explicit consent.
_SANDBOX_DESTRUCTIVE_TOOLS = frozenset(
    {"run_sandbox", "run_browser_sandbox", "execute_sandbox_script"}
)

_DESTRUCTIVE_EXACT = frozenset(
    {
        "delete_report_instance",
        "delete_output_document",
        "delete_report_template",
    }
)
_DESTRUCTIVE_PREFIXES = (
    "delete_",
    "drop_",
    "purge_",
)
_DESTRUCTIVE_SUBSTRINGS = (
    "push_files",
    "create_or_update_file",
    "merge_pull_request",
    "delete_file",
    "delete_repo",
    "force_push",
)
_WRITE_PREFIXES = (
    "patch_",
    "register_",
    "create_",
    "render_",
    "write_",
    "publish_",
    "update_",
    "append_",
    "generate_",
)
_NETWORK_PREFIXES = (
    "mcp__",
    "web_",
    "tavily_",
    "kiwix_",
    "research_",
    "reddit_",
    "fal_",
    "comfy",
)
_READ_EXACT = frozenset(
    {
        "read_sql",
        "inspect_schema",
        "get_project_context",
        "get_current_time",
        "list_tool_packs",
        "unlock_tool_pack",
        "search_project_knowledge",
        "list_project_knowledge",
        "read_project_knowledge",
        "list_disk_roots",
        "list_disk_folder",
        "read_disk_text",
        "extract_document_text",
        "list_report_templates",
        "list_report_instances",
        "get_report_status",
        "resolve_report_instance",
        "inspect_report_images",
    }
)


def resolve_harness_config(spec: Any | None) -> dict[str, Any]:
    """Lee ``tool_surface.harness`` (o ``tool_surface_config.harness``)."""
    section = _harness_section(spec)
    mode_raw = str(section.get("approval_mode") or DEFAULT_APPROVAL_MODE).strip().lower()
    mode: ApprovalMode = mode_raw if mode_raw in ("auto", "suggest", "never") else DEFAULT_APPROVAL_MODE
    try:
        max_fail = max(1, int(section.get("max_failures_per_tool") or DEFAULT_MAX_FAILURES_PER_TOOL))
    except (TypeError, ValueError):
        max_fail = DEFAULT_MAX_FAILURES_PER_TOOL
    try:
        max_chars = max(500, int(section.get("max_tool_result_chars") or DEFAULT_MAX_TOOL_RESULT_CHARS))
    except (TypeError, ValueError):
        max_chars = DEFAULT_MAX_TOOL_RESULT_CHARS
    return {
        "approval_mode": mode,
        "max_failures_per_tool": max_fail,
        "max_tool_result_chars": max_chars,
    }


def classify_tool_risk(tool_name: str) -> RiskTier:
    name = (tool_name or "").strip().lower()
    if not name:
        return "read"
    if name in _DESTRUCTIVE_EXACT:
        return "destructive"
    if any(name.startswith(p) for p in _DESTRUCTIVE_PREFIXES):
        return "destructive"
    if any(s in name for s in _DESTRUCTIVE_SUBSTRINGS):
        return "destructive"
    if name in {"run_sandbox", "run_browser_sandbox", "execute_sandbox_script"}:
        return "destructive"
    if name in _READ_EXACT or name.startswith("list_") or name.startswith("get_"):
        if name.startswith("get_") and any(s in name for s in ("delete", "remove")):
            return "destructive"
        return "read"
    if any(name.startswith(p) for p in _NETWORK_PREFIXES):
        # MCP mutators named delete_* already caught; remaining MCP ≈ network.
        if any(s in name for s in _DESTRUCTIVE_SUBSTRINGS):
            return "destructive"
        return "network"
    if any(name.startswith(p) for p in _WRITE_PREFIXES):
        return "write"
    return "read"


def tool_result_envelope(
    *,
    ok: bool,
    error: str = "",
    hint: str = "",
    retry: bool = False,
    code: str = "",
    **extra: Any,
) -> str:
    payload: dict[str, Any] = {"ok": bool(ok)}
    if error:
        payload["error"] = error
    if hint:
        payload["hint"] = hint
    if code:
        payload["code"] = code
    payload["retry"] = bool(retry) if not ok else False
    for key, value in extra.items():
        if key not in payload:
            payload[key] = value
    return json.dumps(payload, ensure_ascii=False)


def normalize_tool_failure(content: str | None, *, exc: BaseException | None = None) -> str:
    """Fuerza envelope en fallos; deja éxitos JSON intactos cuando ya traen ok."""
    if exc is not None:
        return tool_result_envelope(
            ok=False,
            error=str(exc)[:500],
            hint="Revisa args o cambia de tool; no reintentes idéntico si vuelve a fallar.",
            retry=True,
            code="tool_exception",
        )
    text = content if isinstance(content, str) else ""
    if not text.strip():
        return tool_result_envelope(
            ok=False,
            error="Resultado vacío",
            hint="La tool no devolvió contenido.",
            retry=True,
            code="empty_result",
        )
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        if text.startswith("Error:") or text.lower().startswith("error "):
            return tool_result_envelope(
                ok=False,
                error=text[:500],
                hint="Fallo de tool; ajusta args o usa otra capacidad.",
                retry=True,
                code="plain_error",
            )
        return text
    if not isinstance(payload, dict):
        return text
    if payload.get("ok") is False:
        payload.setdefault("retry", True)
        payload.setdefault("hint", payload.get("hint") or "Revisa el error y cambia de enfoque.")
        return json.dumps(payload, ensure_ascii=False)
    return text


def truncate_tool_result(content: str, max_chars: int) -> tuple[str, bool]:
    if max_chars < 1 or len(content) <= max_chars:
        return content, False
    trimmed = content[: max(0, max_chars - 80)]
    note = f"\n…[truncated {len(content) - len(trimmed)} chars; harness max_tool_result_chars={max_chars}]"
    return trimmed + note, True


def circuit_should_block(fail_counts: dict[str, int], tool_name: str, max_failures: int) -> bool:
    return int(fail_counts.get(tool_name) or 0) >= max(1, max_failures)


def record_tool_failure(fail_counts: dict[str, int], tool_name: str) -> dict[str, int]:
    out = dict(fail_counts)
    key = (tool_name or "").strip()
    if not key:
        return out
    out[key] = int(out.get(key) or 0) + 1
    return out


def record_tool_success(fail_counts: dict[str, int], tool_name: str) -> dict[str, int]:
    """Éxito no borra el historial del turno (rompe loops de martilleo tras 1 ok)."""
    return dict(fail_counts)


def content_indicates_failure(content: str) -> bool:
    text = (content or "").strip()
    if not text:
        return True
    if text.startswith("Error:"):
        return True
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return False
    if isinstance(payload, dict) and payload.get("ok") is False:
        return True
    return False


def sandbox_toggle_bypasses_harness(tool_name: str, *, sandbox_enabled: bool) -> bool:
    """Admin activó sandbox en sesión → no exigir HITL harness para tools de contenedor."""
    return bool(sandbox_enabled) and (tool_name or "").strip() in _SANDBOX_DESTRUCTIVE_TOOLS


def approval_blocks_execution(risk: RiskTier, approval_mode: ApprovalMode) -> bool:
    """Fase 1: solo ``destructive`` se frena en suggest/never."""
    if risk != "destructive":
        return False
    return approval_mode in ("suggest", "never")


def destructive_gate_envelope(tool_name: str, approval_mode: ApprovalMode) -> str:
    if approval_mode == "never":
        return tool_result_envelope(
            ok=False,
            error=f"Tool destructiva bloqueada por approval_mode=never: {tool_name}",
            hint="Cambia tool_surface.harness.approval_mode o usa una tool de solo lectura.",
            retry=False,
            code="harness_never",
            risk="destructive",
        )
    return tool_result_envelope(
        ok=False,
        error=f"Tool destructiva requiere aprobación (approval_mode=suggest): {tool_name}",
        hint=(
            "Fase 1: no se ejecutó. Usa capacidad de lectura o pide unlock/HITL admin. "
            "Fase 2 cableará PENDING_HITL + /approve."
        ),
        retry=False,
        code="harness_suggest_gate",
        risk="destructive",
    )


def circuit_block_envelope(tool_name: str, fail_count: int) -> str:
    return tool_result_envelope(
        ok=False,
        error=f"Circuit breaker: «{tool_name}» falló {fail_count} veces en este turno",
        hint="No reintentes la misma tool. Cambia args, usa otra tool o list_tool_packs.",
        retry=False,
        code="harness_circuit",
    )


def log_harness_metric(worker_label: str, payload: dict[str, Any]) -> None:
    _log.info("[%s] harness_metric %s", worker_label, payload)


def _harness_section(spec: Any | None) -> dict[str, Any]:
    if spec is None:
        return {}
    raw = getattr(spec, "tool_surface_config", None)
    if not isinstance(raw, dict):
        # Algunos specs exponen tool_surface anidado.
        surface = getattr(spec, "tool_surface", None)
        if isinstance(surface, dict):
            raw = surface
        else:
            return {}
    section = raw.get("harness")
    return dict(section) if isinstance(section, dict) else {}
