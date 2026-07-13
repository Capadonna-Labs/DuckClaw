"""LLM bootstrap — DB-first API keys + platform triplet (provider/model/base_url)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_PROVIDER_INTEGRATION_IDS: dict[str, str] = {
    "deepseek": "deepseek",
    "groq": "groq",
    "openai": "openai",
    "anthropic": "anthropic",
    "openrouter": "openrouter",
    "or": "openrouter",
    "router": "openrouter",
    "gemini": "google",
    "google": "google",
    "huggingface": "huggingface",
    "hf": "huggingface",
}

_LOCAL_LLM_PROVIDERS = frozenset({"mlx", "ollama", "local", "iotcorelabs"})

_PROVIDER_ENV_KEYS: dict[str, tuple[str, ...]] = {
    "deepseek": ("DEEPSEEK_API_KEY",),
    "groq": ("GROQ_API_KEY",),
    "openai": ("OPENAI_API_KEY",),
    "anthropic": ("ANTHROPIC_API_KEY",),
    "openrouter": ("OPENROUTER_API_KEY",),
    "or": ("OPENROUTER_API_KEY",),
    "router": ("OPENROUTER_API_KEY",),
    "gemini": ("GOOGLE_API_KEY", "GEMINI_API_KEY"),
    "google": ("GOOGLE_API_KEY", "GEMINI_API_KEY"),
    "huggingface": ("HUGGINGFACE_API_KEY", "HF_TOKEN"),
    "hf": ("HUGGINGFACE_API_KEY", "HF_TOKEN"),
}


def normalize_llm_provider(provider: str) -> str:
    p = (provider or "").strip().lower()
    if p in ("or", "router"):
        return "openrouter"
    return p


def integration_id_for_llm_provider(provider: str) -> str | None:
    return _PROVIDER_INTEGRATION_IDS.get(normalize_llm_provider(provider))


def is_local_llm_provider(provider: str) -> bool:
    return normalize_llm_provider(provider) in _LOCAL_LLM_PROVIDERS


def _env_first(keys: tuple[str, ...]) -> str:
    for key in keys:
        val = (os.environ.get(key) or "").strip()
        if val:
            return val
    return ""


def resolve_llm_api_key(
    provider: str,
    *,
    db: Any | None = None,
    tenant_id: str = "default",
    actor_email: str = "",
) -> str:
    """DB-first API key for a cloud LLM provider."""
    integration_id = integration_id_for_llm_provider(provider)
    if integration_id:
        from duckclaw.integration_secrets import resolve_integration_api_key

        resolved = resolve_integration_api_key(
            integration_id,
            db=db,
            tenant_id=tenant_id,
            actor_email=actor_email,
        )
        if resolved:
            return resolved
    env_keys = _PROVIDER_ENV_KEYS.get(normalize_llm_provider(provider), ())
    return _env_first(env_keys)


def llm_api_key_configured(
    provider: str,
    *,
    db: Any | None = None,
    tenant_id: str = "default",
    actor_email: str = "",
    base_url: str = "",
) -> bool:
    p = normalize_llm_provider(provider)
    if is_local_llm_provider(p):
        url = (base_url or os.environ.get("DUCKCLAW_LLM_BASE_URL") or "").strip()
        return bool(url)
    if not integration_id_for_llm_provider(p) and not _PROVIDER_ENV_KEYS.get(p):
        return True
    return bool(resolve_llm_api_key(p, db=db, tenant_id=tenant_id, actor_email=actor_email))


def resolve_platform_llm_triplet(
    *,
    repo_root: Path | None = None,
    db: Any | None = None,
    tenant_id: str = "default",
    actor_email: str = "",
) -> dict[str, str]:
    """Effective platform LLM settings: env bootstrap → llm domain runtime settings."""
    env: dict[str, str] = {}
    if repo_root is not None:
        from duckclaw.dotenv_immutable import merged_root_and_proposed_flat_env

        env = merged_root_and_proposed_flat_env(repo_root)

    provider = (
        (os.environ.get("DUCKCLAW_LLM_PROVIDER") or env.get("DUCKCLAW_LLM_PROVIDER") or "deepseek")
        .strip()
        .lower()
    )
    model = (os.environ.get("DUCKCLAW_LLM_MODEL") or env.get("DUCKCLAW_LLM_MODEL") or "").strip()
    base_url = (os.environ.get("DUCKCLAW_LLM_BASE_URL") or env.get("DUCKCLAW_LLM_BASE_URL") or "").strip()

    if db is not None:
        from duckclaw.admin_runtime_settings import resolve_runtime_setting

        for key, out_key in (("provider", "provider"), ("model", "model"), ("base_url", "base_url")):
            row = resolve_runtime_setting(
                db,
                tenant_id=tenant_id,
                actor_email=actor_email,
                domain="llm",
                key=key,
                default="",
            )
            if str(row.get("source") or "") == "db" and str(row.get("value") or "").strip():
                if out_key == "provider":
                    provider = str(row["value"]).strip().lower()
                elif out_key == "model":
                    model = str(row["value"]).strip()
                else:
                    base_url = str(row["value"]).strip()

    return {"provider": provider, "model": model, "base_url": base_url}


@dataclass(frozen=True)
class LlmBootstrapStatus:
    ok: bool
    provider: str
    model: str
    detail: str
    integration_id: str | None = None
    integration_label: str | None = None

    def gap_payload(self) -> dict[str, str] | None:
        if self.ok:
            return None
        label = self.integration_label or self.provider
        return {
            "provider": self.provider,
            "integration_id": self.integration_id or "",
            "label": label,
            "admin_href": "/integraciones?tab=keys",
            "message": (
                f"Proveedor LLM «{label}» activo pero falta API key "
                "(Admin -> Integraciones -> API keys o .env bootstrap)."
            ),
        }


def evaluate_llm_bootstrap(
    *,
    repo_root: Path | None = None,
    db: Any | None = None,
    tenant_id: str = "default",
    actor_email: str = "",
) -> LlmBootstrapStatus:
    triplet = resolve_platform_llm_triplet(
        repo_root=repo_root,
        db=db,
        tenant_id=tenant_id,
        actor_email=actor_email,
    )
    provider = normalize_llm_provider(triplet["provider"])
    model = triplet["model"]
    base_url = triplet["base_url"]

    integration_id = integration_id_for_llm_provider(provider)
    integration_label = None
    if integration_id:
        from duckclaw.integration_catalog import get_integration_catalog_entry

        entry = get_integration_catalog_entry(integration_id)
        if entry is not None:
            integration_label = entry.label

    if is_local_llm_provider(provider):
        if llm_api_key_configured(provider, base_url=base_url):
            return LlmBootstrapStatus(
                ok=True,
                provider=provider,
                model=model,
                detail=f"{provider} · {model or 'local'} · {base_url or 'base URL en .env'}",
            )
        return LlmBootstrapStatus(
            ok=False,
            provider=provider,
            model=model,
            detail=f"{provider} sin DUCKCLAW_LLM_BASE_URL (inferencia local)",
        )

    if llm_api_key_configured(provider, db=db, tenant_id=tenant_id, actor_email=actor_email):
        source = "DB/Integraciones" if db is not None else "env"
        return LlmBootstrapStatus(
            ok=True,
            provider=provider,
            model=model,
            detail=f"{provider} · {model or 'default'} · clave OK ({source})",
            integration_id=integration_id,
            integration_label=integration_label,
        )

    env_keys = _PROVIDER_ENV_KEYS.get(provider, ())
    keys_label = " o ".join(env_keys) if env_keys else "API key"
    return LlmBootstrapStatus(
        ok=False,
        provider=provider,
        model=model,
        detail=f"falta {keys_label} para {provider} (Integraciones -> API keys o duckops init)",
        integration_id=integration_id,
        integration_label=integration_label,
    )


def build_llm_gap(
    db: Any | None,
    *,
    provider: str,
    tenant_id: str = "default",
    actor_email: str = "",
) -> dict[str, str] | None:
    p = normalize_llm_provider(provider)
    if is_local_llm_provider(p):
        return None
    if llm_api_key_configured(p, db=db, tenant_id=tenant_id, actor_email=actor_email):
        return None
    integration_id = integration_id_for_llm_provider(p)
    label = p
    if integration_id:
        from duckclaw.integration_catalog import get_integration_catalog_entry

        entry = get_integration_catalog_entry(integration_id)
        if entry is not None:
            label = entry.label
    return {
        "provider": p,
        "integration_id": integration_id or "",
        "label": label,
        "admin_href": "/integraciones?tab=keys",
        "message": (
            f"Proveedor LLM «{label}» activo pero falta API key "
            "(Admin -> Integraciones -> API keys o .env bootstrap)."
        ),
    }
