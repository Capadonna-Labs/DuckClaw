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
        title_sovereign="Tu equipo",
        subtitle_technical="Sistema operativo",
        description="Comprobación rápida del entorno.",
    ),
    WizardStep.CORE_SERVICES: StepCopy(
        title_sovereign="Datos y cola",
        subtitle_technical="Redis · DuckDB",
        description="Comprueba Redis y rutas DuckDB (Enter con valores por defecto).",
    ),
    WizardStep.IDENTITY_SETUP: StepCopy(
        title_sovereign="Proyecto y agentes",
        subtitle_technical="Tenant · worker",
        description="Tenant, PM2 y plantilla por defecto.",
    ),
    WizardStep.ORCHESTRATION: StepCopy(
        title_sovereign="Servicios",
        subtitle_technical="Gateway · DB-Writer · worker",
        description="Inicia PM2 (gateway + DB-Writer) y confirma el worker por defecto.",
    ),
    WizardStep.CONNECTIVITY: StepCopy(
        title_sovereign="Telegram",
        subtitle_technical="Bot · HTTPS",
        description="Solo perfil manual; en rápida usa la consola admin.",
    ),
    WizardStep.REVIEW_DEPLOY: StepCopy(
        title_sovereign="Revisión",
        subtitle_technical="Confirmar",
        description="Salud Redis/Gateway/DB-Writer y Enter para aplicar.",
    ),
}


TAILSCALE_FUNNEL_KB_URL = "https://tailscale.com/kb/1223/funnel/"


def tailscale_funnel_wizard_panel_content(gateway_port: int) -> str:
    p = int(gateway_port)
    return (
        f"HTTPS público → puerto [bold]{p}[/]. Requiere Tailscale con funnel.\n"
        f"[dim]{TAILSCALE_FUNNEL_KB_URL}[/]"
    )


def step_header_compact(step: WizardStep, *, index_1_based: int, total: int) -> str:
    copy = STEP_UI[step]
    return (
        f"[bold bright_white]Paso {index_1_based}/{total}[/] · [bold]{copy.title_sovereign}[/]\n"
        f"[dim]{copy.description}[/]"
    )


def step_header(step: WizardStep, *, index_1_based: int, total: int) -> str:
    return step_header_compact(step, index_1_based=index_1_based, total=total)
