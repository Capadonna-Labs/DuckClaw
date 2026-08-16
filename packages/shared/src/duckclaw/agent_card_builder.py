"""Build A2A v1.0 Agent Card JSON from worker ADF snapshots (public metadata only)."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from duckclaw.framework_tool_pack import ensure_baseline_skills, should_apply_framework_baseline
from duckclaw.worker_adf_snapshot import load_worker_adf_snapshot

# TODO(A2A-SIGN): AgentCardSignature — JWS over RFC8785-canonicalized card (signatures excluded).
# Env: DUCKCLAW_A2A_SIGNING_KEY_ID, DUCKCLAW_A2A_SIGNING_PRIVATE_KEY_PEM

_SECRET_KEY_RE = re.compile(r"(api[_-]?key|secret|token|password|authorization|credential)", re.I)
_SOUL_EXCERPT_MAX = 500

_DEFAULT_PROVIDER = {
    "organization": "IoTCoreLabs",
    "url": "https://github.com/Capadonna-Labs/duckclaw",
}


def resolve_public_gateway_urls() -> tuple[str, str]:
    """Return (public_base_url, gateway_a2a_url)."""
    base = (os.environ.get("DUCKCLAW_PUBLIC_URL") or os.environ.get("DUCKCLAW_GATEWAY_URL") or "").strip()
    if not base:
        base = "http://127.0.0.1:8000"
    base = base.rstrip("/")
    a2a_url = f"{base}/api/v1/agent/chat"
    return base, a2a_url


def _soul_excerpt(files: dict[str, str], manifest: dict[str, Any]) -> str:
    soul = str(files.get("soul.md") or "").strip()
    if soul:
        paragraph = soul.split("\n\n", 1)[0].replace("\n", " ").strip()
        if len(paragraph) > _SOUL_EXCERPT_MAX:
            return paragraph[: _SOUL_EXCERPT_MAX - 3].rstrip() + "..."
        return paragraph
    return str(manifest.get("description") or manifest.get("display_name") or "").strip() or "DuckClaw worker agent"


def _parse_skill_names(manifest: dict[str, Any]) -> list[str]:
    raw = manifest.get("skills") or []
    if isinstance(raw, str):
        raw = [s.strip() for s in raw.split(",") if s.strip()]
    names: list[str] = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            names.append(item.strip().lower().replace("-", "_"))
        elif isinstance(item, dict):
            key = str(item.get("name") or item.get("skill") or "").strip()
            if not key:
                for k in item:
                    key = str(k).strip()
                    break
            if key:
                names.append(key.lower().replace("-", "_"))
    if should_apply_framework_baseline(manifest):
        names = ensure_baseline_skills(names, manifest=manifest)
    seen: set[str] = set()
    out: list[str] = []
    for name in names:
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    return out


def _skill_tags(skill_id: str, manifest: dict[str, Any]) -> list[str]:
    tags = [skill_id]
    topology = str(manifest.get("topology") or "general").strip().lower()
    if topology and topology not in tags:
        tags.append(topology)
    profile = str(manifest.get("tool_profile") or "").strip().lower()
    if profile and profile not in tags:
        tags.append(profile)
    return tags[:8] or ["duckclaw"]


def _build_skills(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    skills: list[dict[str, Any]] = []
    for skill_id in _parse_skill_names(manifest):
        skills.append(
            {
                "id": skill_id,
                "name": skill_id.replace("_", " ").title(),
                "description": f"DuckClaw skill: {skill_id}",
                "tags": _skill_tags(skill_id, manifest),
            }
        )
    if not skills:
        skills.append(
            {
                "id": "general",
                "name": "General Assistant",
                "description": "General-purpose DuckClaw worker",
                "tags": ["duckclaw", "general"],
            }
        )
    return skills


def _redact_secrets(obj: Any, *, path: str = "") -> None:
    if isinstance(obj, dict):
        for key, value in list(obj.items()):
            key_path = f"{path}.{key}" if path else str(key)
            if _SECRET_KEY_RE.search(str(key)):
                raise ValueError(f"Agent card must not contain sensitive field: {key_path}")
            _redact_secrets(value, path=key_path)
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            _redact_secrets(item, path=f"{path}[{idx}]")


def build_a2a_agent_card(
    worker_id: str,
    *,
    manifest: dict[str, Any],
    files: dict[str, str],
    public_base_url: str | None = None,
    gateway_a2a_url: str | None = None,
) -> dict[str, Any]:
    """Build A2A v1.0 AgentCard dict (no prompts, no secrets)."""
    if public_base_url is None or gateway_a2a_url is None:
        public_base_url, gateway_a2a_url = resolve_public_gateway_urls()
    name = str(manifest.get("id") or worker_id).strip()
    card: dict[str, Any] = {
        "name": name,
        "description": _soul_excerpt(files, manifest),
        "supportedInterfaces": [
            {
                "url": gateway_a2a_url,
                "protocolBinding": "HTTP+JSON",
                "protocolVersion": "1.0",
            }
        ],
        "provider": dict(_DEFAULT_PROVIDER),
        "version": str(manifest.get("version") or "1.0.0"),
        "capabilities": {
            "streaming": True,
            "pushNotifications": False,
        },
        "defaultInputModes": ["text/plain"],
        "defaultOutputModes": ["text/plain"],
        "securitySchemes": {
            "bearerAuth": {
                "type": "http",
                "scheme": "bearer",
            }
        },
        "securityRequirements": [{"bearerAuth": []}],
        "skills": _build_skills(manifest),
    }
    icon = str(manifest.get("icon_url") or manifest.get("iconUrl") or "").strip()
    if icon.startswith("http"):
        card["iconUrl"] = icon
    docs = str(manifest.get("documentation_url") or manifest.get("documentationUrl") or "").strip()
    if docs.startswith("http"):
        card["documentationUrl"] = docs
    _redact_secrets(card)
    # Only scan public description — skill ids like ``update_system_prompt`` are valid.
    desc_l = str(card.get("description") or "").lower()
    for marker in (
        "system_prompt.md",
        "domain_closure.md",
        "# system_prompt",
        "## system_prompt",
        "# domain_closure",
        "## domain_closure",
    ):
        if marker in desc_l:
            raise ValueError("Agent card must not embed prompt file content")
    return card


def build_a2a_agent_card_from_db(
    db: Any,
    worker_id: str,
    *,
    tenant_id: str = "default",
    public_base_url: str | None = None,
    gateway_a2a_url: str | None = None,
) -> dict[str, Any]:
    manifest, files, _cat = load_worker_adf_snapshot(db, worker_id, tenant_id=tenant_id)
    return build_a2a_agent_card(
        worker_id,
        manifest=manifest,
        files=files,
        public_base_url=public_base_url,
        gateway_a2a_url=gateway_a2a_url,
    )


def worker_is_a2a_public(cat: dict[str, Any] | None, *, worker_id: str) -> bool:
    if not cat:
        return worker_id == "default"
    visibility = str(cat.get("visibility") or "private").strip().lower()
    discoverable = cat.get("a2a_discoverable")
    if discoverable is True or str(discoverable).lower() in {"1", "true", "yes"}:
        return True
    return visibility == "public"
