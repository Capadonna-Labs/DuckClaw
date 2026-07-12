"""Onboarding checks for clueless devs (duckops doctor / up summary)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_LLM_PROVIDER_ENV_KEYS: dict[str, tuple[str, ...]] = {
    "deepseek": ("DEEPSEEK_API_KEY",),
    "groq": ("GROQ_API_KEY",),
    "openai": ("OPENAI_API_KEY",),
    "anthropic": ("ANTHROPIC_API_KEY",),
    "openrouter": ("OPENROUTER_API_KEY",),
    "google": ("GOOGLE_API_KEY", "GEMINI_API_KEY"),
    "gemini": ("GOOGLE_API_KEY", "GEMINI_API_KEY"),
}
_LOCAL_LLM_PROVIDERS = frozenset({"mlx", "ollama", "local"})


@dataclass(frozen=True)
class LlmBootstrapHealth:
    ok: bool
    provider: str
    detail: str


@dataclass(frozen=True)
class AgentCatalogHealth:
    ok: bool
    custom_count: int
    detail: str


@dataclass(frozen=True)
class IntegrationBootstrapHealth:
    missing_labels: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.missing_labels

    def summary(self) -> str:
        if self.ok:
            return "integraciones empaquetadas con clave o sin uso aún"
        return "sin clave: " + ", ".join(self.missing_labels)


def _flat_env(repo_root: Path) -> dict[str, str]:
    from duckclaw.dotenv_immutable import merged_root_and_proposed_flat_env

    return merged_root_and_proposed_flat_env(repo_root)


def _env_has_any(keys: tuple[str, ...]) -> bool:
    for key in keys:
        if (os.environ.get(key) or "").strip():
            return True
    return False


def check_llm_bootstrap(repo_root: Path) -> LlmBootstrapHealth:
    env = _flat_env(repo_root)
    provider = (
        (os.environ.get("DUCKCLAW_LLM_PROVIDER") or env.get("DUCKCLAW_LLM_PROVIDER") or "deepseek")
        .strip()
        .lower()
    )
    model = (os.environ.get("DUCKCLAW_LLM_MODEL") or env.get("DUCKCLAW_LLM_MODEL") or "").strip()

    if provider in _LOCAL_LLM_PROVIDERS:
        base = (os.environ.get("DUCKCLAW_LLM_BASE_URL") or env.get("DUCKCLAW_LLM_BASE_URL") or "").strip()
        if base:
            return LlmBootstrapHealth(
                ok=True,
                provider=provider,
                detail=f"{provider} · {model or 'local'} · {base}",
            )
        return LlmBootstrapHealth(
            ok=False,
            provider=provider,
            detail=f"{provider} sin DUCKCLAW_LLM_BASE_URL (inferencia local)",
        )

    env_keys = _LLM_PROVIDER_ENV_KEYS.get(provider, ())
    if not env_keys:
        return LlmBootstrapHealth(
            ok=True,
            provider=provider,
            detail=f"{provider} · {model or 'default'} (sin env key conocida — revisa .env)",
        )

    if _env_has_any(env_keys):
        key_name = next(k for k in env_keys if (os.environ.get(k) or "").strip())
        return LlmBootstrapHealth(
            ok=True,
            provider=provider,
            detail=f"{provider} · {model or 'default'} · {key_name} presente",
        )

    keys_label = " o ".join(env_keys)
    return LlmBootstrapHealth(
        ok=False,
        provider=provider,
        detail=f"falta {keys_label} para {provider} (wizard o .env)",
    )


def check_custom_agents_in_catalog(db: Any) -> AgentCatalogHealth:
    row = db.execute(
        """
        SELECT count(*)
        FROM main.admin_worker_catalog
        WHERE active = true AND worker_id != 'default'
        """
    ).fetchone()
    count = int(row[0] if row else 0)
    if count > 0:
        return AgentCatalogHealth(
            ok=True,
            custom_count=count,
            detail=f"{count} agente(s) en catálogo (además del template default)",
        )
    return AgentCatalogHealth(
        ok=False,
        custom_count=0,
        detail="sin agentes propios — Plantillas → Crear agente (wizard)",
    )


def check_integration_bootstrap(db: Any, *, tenant_id: str = "default") -> IntegrationBootstrapHealth:
    from duckclaw.integration_catalog import list_integration_catalog_entries
    from duckclaw.integration_secrets import integration_api_key_configured

    missing: list[str] = []
    for entry in list_integration_catalog_entries():
        if integration_api_key_configured(entry.integration_id, db=db, tenant_id=tenant_id):
            continue
        missing.append(entry.label)
    return IntegrationBootstrapHealth(missing_labels=tuple(missing))


def format_dev_next_steps(*, agents: AgentCatalogHealth, llm: LlmBootstrapHealth) -> list[str]:
    lines: list[str] = []
    if not agents.ok:
        lines.append("Plantillas → Crear agente (wizard de 2 pasos)")
    if not llm.ok:
        lines.append("Configura LLM en .env o vuelve a ejecutar duckops init (proveedor + API key)")
    lines.append("Playground → chatea con el agente que creaste")
    lines.append("Opcional: Integraciones → API keys (Tavily, OpenWeather, …)")
    return lines
