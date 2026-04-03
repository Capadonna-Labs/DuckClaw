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
        title_sovereign="Datos y cola de mensajes",
        subtitle_technical="Redis y DuckDB",
        description=(
            "Tres preguntas cortas: dónde está el servicio de mensajes (Redis), dónde guardar el archivo de "
            "memoria de DuckClaw en tu disco y, solo en casos avanzados, una ruta extra. "
            "En la mayoría de equipos basta pulsar Enter en las dos primeras."
        ),
    ),
    WizardStep.IDENTITY_SETUP: StepCopy(
        title_sovereign="Tu proyecto y asistente por defecto",
        subtitle_technical="Nombre, servidor y perfil",
        description=(
            "[bold]Nombre para esta instalación[/] — cómo quieres llamar a esta copia de DuckClaw en tus datos "
            "(ej. «Mi tienda», «casa»). Solo organiza archivos y permisos; no es Telegram.\n\n"
            "[bold]Gateway[/] — el programa-servidor que recibe mensajes y habla con los agentes.\n\n"
            "[bold]PM2[/] — herramienta que mantiene ese servidor encendido en segundo plano.\n\n"
            "[bold]Manager[/] te atiende primero; [bold]worker[/] es el asistente especializado (finanzas, empleo…); "
            "más abajo eliges cuál usar por defecto."
        ),
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


def step_header_compact(step: WizardStep, *, index_1_based: int, total: int) -> str:
    """Encabezado corto: número de paso destacado, título y aire entre bloques."""
    copy = STEP_UI[step]
    return (
        f"[bold bright_white]Paso {index_1_based} de {total}[/] [dim]· DuckClaw[/]\n"
        "\n"
        f"[bold]{copy.title_sovereign}[/]\n"
        f"[dim]{copy.subtitle_technical}[/]\n"
        "\n"
        f"{copy.description}"
    )


def step_header(step: WizardStep, *, index_1_based: int, total: int) -> str:
    """Encabezado largo (pasos 4–6): misma jerarquía visual, sin banda de guiones."""
    copy = STEP_UI[step]
    return (
        f"[dim]DuckClaw · asistente de configuración[/]\n"
        f"[bold bright_white]Paso {index_1_based} de {total}[/]\n"
        "\n"
        f"[bold]{copy.title_sovereign}[/] · [dim]{copy.subtitle_technical}[/]\n"
        "\n"
        f"{copy.description}"
    )
