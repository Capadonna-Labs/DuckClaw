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
        description="Reconociendo tu sistema operativo...",
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
    WizardStep.ORCHESTRATION: StepCopy(
        title_sovereign="Orquestación",
        subtitle_technical="PM2 vs Docker",
        description=(
            "Puerto del API Gateway y Redis local. El puerto se fija aquí antes de Telegram para poder "
            "usar Tailscale Funnel (--bg) o, en su defecto, otro túnel hacia 127.0.0.1:puerto."
        ),
    ),
    WizardStep.CONNECTIVITY: StepCopy(
        title_sovereign="Puente de integración y acceso",
        subtitle_technical="Telegram / Tailscale Funnel / MCP",
        description=(
            "Token de Telegram; URL HTTPS pública vía Tailscale Funnel (recomendado) hacia el puerto ya definido; "
            "secreto de webhook; Cloudflare Quick Tunnel solo como alternativa; clave Tailscale opcional."
        ),
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


TAILSCALE_FUNNEL_KB_URL = "https://tailscale.com/kb/1223/funnel/"
TAILSCALE_FUNNEL_CLI_URL = "https://tailscale.com/docs/reference/tailscale-cli/funnel"


def tailscale_funnel_wizard_panel_content(gateway_port: int) -> str:
    """
    Instrucciones para exponer este gateway vía Tailscale Funnel (webhook Telegram HTTPS).
    Resumen alineado con la documentación oficial (MagicDNS, HTTPS, nodeAttrs funnel).
    """
    p = int(gateway_port)
    return "\n".join(
        [
            "[bold]Qué es[/]: Funnel enruta tráfico de Internet a un servicio TCP en esta máquina "
            "(tu API Gateway). Telegram puede hacer [bold]POST[/] a esa URL HTTPS.",
            "",
            "[bold]Requisitos en el tailnet[/] (consola admin Tailscale):",
            "  • MagicDNS activo",
            "  • Certificados HTTPS del tailnet configurados",
            "  • Política ACL con atributo de nodo [bold]funnel[/] para quien ejecute el comando "
            "(p. ej. «Add Funnel to policy» en Access controls)",
            "",
            f"[bold]Documentación[/]: {TAILSCALE_FUNNEL_KB_URL}",
            f"[bold]Referencia CLI[/]: {TAILSCALE_FUNNEL_CLI_URL}",
            "",
            f"Con el gateway escuchando en [bold]127.0.0.1:{p}[/] (PM2 / uvicorn), en esta máquina:",
            f"  [cyan]tailscale funnel --bg --yes {p}[/]",
            "  ([bold]--bg[/] mantiene el mapeo en segundo plano; tras reinicio del nodo suele reanudarse.)",
            "",
            "La CLI mostrará una URL pública del tipo "
            "[bold]https://NOMBRE-MÁQUINA.<tu-tailnet>.ts.net[/] "
            f"proxando a [bold]http://127.0.0.1:{p}[/].",
            "Usa como base del webhook de Telegram (sin barra final) esa URL; el [bold]setWebhook[/] completo será:",
            "  [dim]…/api/v1/telegram/webhook[/] al final.",
            "",
            "[bold]Varios gateways[/] (Finanz :8000, JobHunter :8283, etc.): el modo recomendado es que "
            "cada bot tenga una URL HTTPS que termine en el puerto de [italic]ese[/] PM2. Opciones: varios "
            "túneles/hostnames (p. ej. Cloudflare) hacia cada puerto; varios funnels si el tailnet lo permite; "
            "o [bold]Tailscale Serve[/] / reverse proxy con reglas por ruta o host y un solo funnel al frontal.",
            "",
            "[dim]Estado: tailscale funnel status  ·  Reiniciar mapeos: tailscale funnel reset[/]",
        ]
    )


def step_header(step: WizardStep, *, index_1_based: int, total: int) -> str:
    copy = STEP_UI[step]
    return (
        f"── DuckClaw Sovereign Wizard v2.0 ──────────────────────────────────────────\n"
        f"[ Paso {index_1_based} de {total}: {copy.title_sovereign} ({copy.subtitle_technical}) ]\n"
        f"{copy.description}"
    )
