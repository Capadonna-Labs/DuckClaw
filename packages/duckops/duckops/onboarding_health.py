"""Onboarding checks for clueless devs (duckops doctor / up summary)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


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


def check_llm_bootstrap(repo_root: Path, db: Any | None = None) -> LlmBootstrapHealth:
    from duckclaw.llm_bootstrap import evaluate_llm_bootstrap

    env = _flat_env(repo_root)
    tenant_id = "default"
    if db is not None:
        try:
            row = db.execute("SELECT tenant_id FROM main.admin_user_profiles LIMIT 1").fetchone()
            if row:
                tenant_id = str(row[0] if not isinstance(row, dict) else row.get("tenant_id") or "default")
        except Exception:
            pass
    status = evaluate_llm_bootstrap(repo_root=repo_root, db=db, tenant_id=tenant_id)
    return LlmBootstrapHealth(ok=status.ok, provider=status.provider, detail=status.detail)


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
        detail="sin agentes propios - Plantillas -> Crear agente (wizard)",
    )


def check_integration_bootstrap(db: Any, *, tenant_id: str = "default") -> IntegrationBootstrapHealth:
    from duckclaw.integration_readiness import missing_integration_labels

    missing = missing_integration_labels(db, tenant_id=tenant_id)
    return IntegrationBootstrapHealth(missing_labels=missing)


def format_dev_next_steps(*, agents: AgentCatalogHealth, llm: LlmBootstrapHealth) -> list[str]:
    lines: list[str] = []
    if not agents.ok:
        lines.append("Plantillas -> Crear agente (wizard de 2 pasos)")
    if not llm.ok:
        lines.append("Integraciones -> API keys (grupo LLM e inferencia) o duckops init")
    lines.append("Playground -> chatea con el agente que creaste")
    lines.append("Opcional: Integraciones -> API keys (Tavily, OpenWeather, ...)")
    return lines
