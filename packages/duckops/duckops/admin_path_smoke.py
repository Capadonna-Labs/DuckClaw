"""Smoke HTTP del happy path admin: login → playground config → (opcional) chat."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class AdminPathSmokeCheck:
    name: str
    ok: bool
    detail: str


def _pick_worker_id(config: dict[str, Any]) -> str:
    selected = str(config.get("selected_worker_id") or "").strip()
    if selected:
        return selected
    workers = config.get("workers") or []
    if isinstance(workers, list):
        for row in workers:
            if not isinstance(row, dict):
                continue
            wid = str(row.get("id") or "").strip()
            if wid:
                return wid
    return "default"


def run_admin_path_smoke(
    *,
    base_url: str,
    admin_email: str,
    admin_password: str,
    admin_api_key: str,
    actor_email: str | None = None,
    chat_turn: bool = True,
    chat_timeout: float = 60.0,
) -> tuple[AdminPathSmokeCheck, ...]:
    """Probes en vivo contra el API Gateway (sin Playwright)."""
    root = base_url.rstrip("/")
    actor = (actor_email or admin_email).strip()
    admin_headers = {
        "X-Admin-Key": admin_api_key.strip(),
        "X-Duckclaw-Actor": actor,
    }
    checks: list[AdminPathSmokeCheck] = []

    with httpx.Client(timeout=httpx.Timeout(chat_timeout, connect=5.0)) as client:
        try:
            login = client.post(
                f"{root}/api/v1/admin/auth/login",
                json={"email": admin_email.strip(), "password": admin_password},
            )
        except httpx.HTTPError as exc:
            checks.append(AdminPathSmokeCheck("Smoke admin login", False, str(exc)[:160]))
            return tuple(checks)

        if login.status_code != 200:
            body = (login.text or "")[:120]
            checks.append(
                AdminPathSmokeCheck(
                    "Smoke admin login",
                    False,
                    f"HTTP {login.status_code}" + (f" · {body}" if body else ""),
                )
            )
            return tuple(checks)

        try:
            payload = login.json()
        except ValueError:
            payload = {}
        user_email = str((payload.get("user") or {}).get("email") or admin_email)
        checks.append(
            AdminPathSmokeCheck(
                "Smoke admin login",
                True,
                user_email,
            )
        )

        try:
            config_resp = client.get(
                f"{root}/api/v1/admin/playground/config",
                headers=admin_headers,
            )
        except httpx.HTTPError as exc:
            checks.append(AdminPathSmokeCheck("Smoke playground config", False, str(exc)[:160]))
            return tuple(checks)

        if config_resp.status_code != 200:
            body = (config_resp.text or "")[:120]
            checks.append(
                AdminPathSmokeCheck(
                    "Smoke playground config",
                    False,
                    f"HTTP {config_resp.status_code}" + (f" · {body}" if body else ""),
                )
            )
            return tuple(checks)

        try:
            config = config_resp.json()
        except ValueError:
            config = {}

        llm = config.get("llm") or {}
        provider = str(llm.get("provider") or "—")
        model = str(llm.get("model") or "—")
        llm_gap = config.get("llm_gap")
        gap_msg = str((llm_gap or {}).get("message") or "").strip() if isinstance(llm_gap, dict) else ""
        config_detail = f"{provider} · {model}"
        if gap_msg:
            config_detail += f" · {gap_msg[:80]}"
        checks.append(
            AdminPathSmokeCheck(
                "Smoke playground config",
                True,
                config_detail,
            )
        )

        if gap_msg:
            checks.append(
                AdminPathSmokeCheck(
                    "Smoke playground chat",
                    False,
                    "LLM sin clave — Integraciones → API keys",
                )
            )
            return tuple(checks)

        if not chat_turn:
            checks.append(
                AdminPathSmokeCheck(
                    "Smoke playground chat",
                    True,
                    "omitido (--smoke-admin sin chat)",
                )
            )
            return tuple(checks)

        worker_id = _pick_worker_id(config)
        try:
            chat_resp = client.post(
                f"{root}/api/v1/admin/playground/chat",
                headers=admin_headers,
                json={"worker_id": worker_id, "message": "smoke ping (duckops)"},
                timeout=chat_timeout,
            )
        except httpx.HTTPError as exc:
            checks.append(
                AdminPathSmokeCheck(
                    "Smoke playground chat",
                    False,
                    str(exc)[:160],
                )
            )
            return tuple(checks)

        if chat_resp.status_code != 200:
            body = (chat_resp.text or "")[:120]
            checks.append(
                AdminPathSmokeCheck(
                    "Smoke playground chat",
                    False,
                    f"HTTP {chat_resp.status_code} worker={worker_id}"
                    + (f" · {body}" if body else ""),
                )
            )
            return tuple(checks)

        try:
            chat_data = chat_resp.json()
        except ValueError:
            chat_data = {}
        response_text = str(chat_data.get("response") or "").strip()
        if not chat_data.get("ok"):
            checks.append(
                AdminPathSmokeCheck(
                    "Smoke playground chat",
                    False,
                    str(chat_data.get("error") or chat_data.get("message") or "ok=false")[:160],
                )
            )
            return tuple(checks)

        preview = response_text[:80] + ("…" if len(response_text) > 80 else "")
        checks.append(
            AdminPathSmokeCheck(
                "Smoke playground chat",
                True,
                f"worker={worker_id}" + (f" · {preview}" if preview else ""),
            )
        )

    return tuple(checks)
