"""Traducción de dominio (spec §2 — lenguaje soberano)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class WizardStep(str, Enum):
    """Pasos cognitivos del wizard (spec §3)."""

    SOVEREIGNTY_AUDIT = "sovereignty_audit"
    CORE_SERVICES = "core_services"
    IDENTITY_SETUP = "identity_setup"
    CONNECTIVITY = "connectivity"
    ORCHESTRATION = "orchestration"
    REVIEW_DEPLOY = "review_deploy"


@dataclass(frozen=True)
class StepCopy:
    title_sovereign: str
    subtitle_technical: str
    description: str


STEP_UI: dict[WizardStep, StepCopy] = {
    WizardStep.SOVEREIGNTY_AUDIT: StepCopy(
        title_sovereign="Soberanía del entorno",
        subtitle_technical="Sovereignty Audit",
        description="Detectamos tu sistema (macOS, Linux, Docker) para adaptar rutas y servicios.",
    ),
    WizardStep.CORE_SERVICES: StepCopy(
        title_sovereign="Canal de comunicación y bóveda de memoria",
        subtitle_technical="Redis + DuckDB",
        description=(
            "Redis como canal; DuckDB principal en «Bóveda» (DUCKCLAW_DB_PATH del gateway PM2). "
            "El campo opcional «compartida» es una segunda base (p. ej. Leila); si dejas la bóveda "
            "por defecto y solo tienes un .duckdb analítico (BI), puedes indicarlo ahí y se usará como principal."
        ),
    ),
    WizardStep.IDENTITY_SETUP: StepCopy(
        title_sovereign="Identidad del orquestador",
        subtitle_technical="Manager + Worker",
        description="Tenant, nombre PM2 del gateway y plantilla del primer worker.",
    ),
    WizardStep.CONNECTIVITY: StepCopy(
        title_sovereign="Puente de integración y acceso",
        subtitle_technical="Telegram / Tailscale / MCP",
        description="Tokens y túneles: el agente habla con Telegram y herramientas externas (MCP).",
    ),
    WizardStep.ORCHESTRATION: StepCopy(
        title_sovereign="Orquestación",
        subtitle_technical="PM2 vs Docker",
        description="¿Proceso local (PM2) o contenedores (Docker)? Puerto del gateway y Redis local.",
    ),
    WizardStep.REVIEW_DEPLOY: StepCopy(
        title_sovereign="Revisión e ignición",
        subtitle_technical="Review & Deploy",
        description=(
            "Resumen; al confirmar se escriben .env y artefactos. "
            "Quick Save (Ctrl+S) guarda borrador sin desplegar."
        ),
    ),
}


def step_header(step: WizardStep, *, index_1_based: int, total: int) -> str:
    copy = STEP_UI[step]
    return (
        f"── DuckClaw Sovereign Wizard v2.0 ──────────────────────────────────────────\n"
        f"[ Paso {index_1_based} de {total}: {copy.title_sovereign} ({copy.subtitle_technical}) ]\n"
        f"{copy.description}"
    )
