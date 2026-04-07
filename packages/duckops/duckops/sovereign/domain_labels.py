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
            "memoria de DuckClaw (DuckDB principal o «Bóveda») y, solo en casos avanzados, una ruta extra "
            "compartida. En la mayoría de equipos basta pulsar Enter en las dos primeras."
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
        title_sovereign="Cómo arranca el servidor",
        subtitle_technical="PM2, Docker y puerto",
        description=(
            "Indica si los programas correrán en esta máquina con PM2 (lo habitual) o con Docker, "
            "qué puerto usará el servidor web y, si quieres, ayuda para Redis local. "
            "El puerto importa para el siguiente paso (enlace público hacia Telegram)."
        ),
    ),
    WizardStep.CONNECTIVITY: StepCopy(
        title_sovereign="Telegram y enlace seguro",
        subtitle_technical="Bot, túnel HTTPS y opciones",
        description=(
            "Registramos quién puede usar el bot, el token del bot y una dirección HTTPS pública "
            "(Tailscale Funnel u otra) para que Telegram llegue a tu servidor. "
            "Lo opcional va al final (clave de red, integración avanzada)."
        ),
    ),
    WizardStep.REVIEW_DEPLOY: StepCopy(
        title_sovereign="Última comprobación",
        subtitle_technical="Revisa y confirma",
        description=(
            "Aquí ves todo lo que elegiste. Léelo con calma antes de continuar. "
            "Más abajo te diremos cómo confirmar para guardar los cambios en la carpeta del proyecto. "
            "Si solo quieres un borrador sin aplicar, usa Ctrl+S."
        ),
    ),
}


TAILSCALE_FUNNEL_KB_URL = "https://tailscale.com/kb/1223/funnel/"


def tailscale_funnel_wizard_panel_content(gateway_port: int) -> str:
    """Texto breve para el paso Telegram; el detalle técnico queda en dim y en la KB."""
    p = int(gateway_port)
    return "\n".join(
        [
            "Tailscale Funnel abre una dirección [bold]https://…[/] en Internet hacia el servidor "
            f"que ya escucha en tu equipo en el puerto [bold]{p}[/]. Así Telegram puede enviar mensajes al bot.",
            "",
            "Necesitas la app Tailscale instalada, sesión iniciada y permisos de «funnel» en tu red "
            "(en la consola de administración de Tailscale).",
            "",
            f"[dim]Guía: {TAILSCALE_FUNNEL_KB_URL} · Comando que puede ejecutar el asistente: "
            f"tailscale funnel --bg --yes {p} · Ruta del webhook: …/api/v1/telegram/webhook[/]",
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
