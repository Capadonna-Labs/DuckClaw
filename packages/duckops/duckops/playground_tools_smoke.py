"""Smoke HTTP: capabilities del worker + turno chat que fuerza read_sql."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import re

import httpx

from duckops.admin_path_smoke import _pick_worker_id

_TOOL_PROBE_SQL = "SELECT 8742 AS smoke_tool_test"
_TOOL_PROBE_MESSAGE = (
    "Smoke test de tools: debes invocar read_sql con exactamente esta query: "
    f"{_TOOL_PROBE_SQL}. Responde solo con el número devuelto por la tool."
)

_PROBE_VALUE = "8742"

_BASELINE_TOOLS = frozenset({"read_sql", "inspect_schema"})


@dataclass(frozen=True)
class PlaygroundToolsSmokeCheck:
    name: str
    ok: bool
    detail: str


def _has_baseline_tool(tools_runtime: list[Any]) -> bool:
    names = {str(item).strip() for item in tools_runtime if str(item).strip()}
    return bool(names & _BASELINE_TOOLS)


def _response_suggests_read_sql(response_text: str) -> bool:
    text = (response_text or "").strip().lower()
    if not text:
        return False
    if "smoke_tool_test" in text:
        return True
    if _PROBE_VALUE in text:
        return True
    return bool(re.search(rf"\b{_PROBE_VALUE}\b", text))


def run_playground_tools_smoke(
    *,
    base_url: str,
    admin_email: str,
    admin_password: str,
    admin_api_key: str,
    actor_email: str | None = None,
    worker_id: str | None = None,
    chat_timeout: float = 90.0,
) -> tuple[PlaygroundToolsSmokeCheck, ...]:
    root = base_url.rstrip("/")
    actor = (actor_email or admin_email).strip()
    admin_headers = {
        "X-Admin-Key": admin_api_key.strip(),
        "X-Duckclaw-Actor": actor,
    }
    checks: list[PlaygroundToolsSmokeCheck] = []

    with httpx.Client(timeout=httpx.Timeout(chat_timeout, connect=5.0)) as client:
        try:
            login = client.post(
                f"{root}/api/v1/admin/auth/login",
                json={"email": admin_email.strip(), "password": admin_password},
            )
        except httpx.HTTPError as exc:
            checks.append(PlaygroundToolsSmokeCheck("Tools smoke login", False, str(exc)[:160]))
            return tuple(checks)

        if login.status_code != 200:
            checks.append(
                PlaygroundToolsSmokeCheck(
                    "Tools smoke login",
                    False,
                    f"HTTP {login.status_code}",
                )
            )
            return tuple(checks)

        checks.append(PlaygroundToolsSmokeCheck("Tools smoke login", True, actor))

        try:
            config_resp = client.get(
                f"{root}/api/v1/admin/playground/config",
                headers=admin_headers,
            )
        except httpx.HTTPError as exc:
            checks.append(
                PlaygroundToolsSmokeCheck("Tools smoke config", False, str(exc)[:160])
            )
            return tuple(checks)

        if config_resp.status_code != 200:
            checks.append(
                PlaygroundToolsSmokeCheck(
                    "Tools smoke config",
                    False,
                    f"HTTP {config_resp.status_code}",
                )
            )
            return tuple(checks)

        config = config_resp.json()
        wid = (worker_id or _pick_worker_id(config)).strip() or "default"
        llm_gap = config.get("llm_gap")
        gap_msg = str((llm_gap or {}).get("message") or "").strip() if isinstance(llm_gap, dict) else ""
        if gap_msg:
            checks.append(
                PlaygroundToolsSmokeCheck(
                    "Tools smoke capabilities",
                    False,
                    "LLM sin clave — omitido",
                )
            )
            return tuple(checks)

        try:
            cap_resp = client.get(
                f"{root}/api/v1/admin/workers/{wid}/capabilities",
                headers=admin_headers,
            )
        except httpx.HTTPError as exc:
            checks.append(
                PlaygroundToolsSmokeCheck(
                    "Tools smoke capabilities",
                    False,
                    str(exc)[:160],
                )
            )
            return tuple(checks)

        if cap_resp.status_code != 200:
            checks.append(
                PlaygroundToolsSmokeCheck(
                    "Tools smoke capabilities",
                    False,
                    f"HTTP {cap_resp.status_code} worker={wid}",
                )
            )
            return tuple(checks)

        cap = cap_resp.json()
        tools_runtime = list(cap.get("tools_runtime") or [])
        gaps = list(cap.get("gaps") or [])
        tool_count = len(tools_runtime)
        cap_ok = _has_baseline_tool(tools_runtime)
        cap_detail = f"worker={wid} · {tool_count} tools"
        if tools_runtime[:5]:
            cap_detail += f" · {', '.join(str(t) for t in tools_runtime[:5])}"
            if tool_count > 5:
                cap_detail += ", …"
        if gaps:
            cap_detail += f" · gaps: {gaps[0][:80]}"
        checks.append(
            PlaygroundToolsSmokeCheck(
                "Tools smoke capabilities",
                cap_ok,
                cap_detail,
            )
        )

        if not cap_ok:
            return tuple(checks)

        try:
            chat_resp = client.post(
                f"{root}/api/v1/admin/playground/chat",
                headers=admin_headers,
                json={"worker_id": wid, "message": _TOOL_PROBE_MESSAGE},
                timeout=chat_timeout,
            )
        except httpx.HTTPError as exc:
            checks.append(
                PlaygroundToolsSmokeCheck(
                    "Tools smoke read_sql turn",
                    False,
                    str(exc)[:160],
                )
            )
            return tuple(checks)

        if chat_resp.status_code != 200:
            checks.append(
                PlaygroundToolsSmokeCheck(
                    "Tools smoke read_sql turn",
                    False,
                    f"HTTP {chat_resp.status_code}",
                )
            )
            return tuple(checks)

        chat_data = chat_resp.json()
        if not chat_data.get("ok"):
            checks.append(
                PlaygroundToolsSmokeCheck(
                    "Tools smoke read_sql turn",
                    False,
                    str(chat_data.get("error") or chat_data.get("message") or "ok=false")[:160],
                )
            )
            return tuple(checks)

        response_text = str(chat_data.get("response") or "")
        tool_ok = _response_suggests_read_sql(response_text)
        preview = response_text.strip().replace("\n", " ")[:100]
        checks.append(
            PlaygroundToolsSmokeCheck(
                "Tools smoke read_sql turn",
                tool_ok,
                preview or "(respuesta vacía)",
            )
        )

    return tuple(checks)
