"""TUI por pasos (prompt_toolkit + Rich)."""

from __future__ import annotations

import platform
import subprocess
import unicodedata
from pathlib import Path
from typing import Callable

from prompt_toolkit import PromptSession
from rich.console import Console
from rich.panel import Panel

from duckops.sovereign.cloudflared_tunnel import (
    cloudflared_available,
    pm2_available,
    provision_trycloudflare_quick_tunnel,
)
from duckops.sovereign.domain_labels import (
    STEP_UI,
    TAILSCALE_FUNNEL_KB_URL,
    WizardStep,
    step_header,
    step_header_compact,
    tailscale_funnel_wizard_panel_content,
)
from duckops.sovereign.tailscale_funnel import (
    provision_tailscale_funnel_bg,
    tailscale_cli_available,
)
from duckops.sovereign.draft import SovereignDraft, WizardProfile
from duckops.sovereign.keys import (
    NAV_AUTOFILL,
    NAV_BACK,
    NAV_QUICK_SAVE,
    NAV_SERVICE_TEST,
    build_key_bindings,
)
from duckops.sovereign.materialize import load_draft_json, save_draft_json
from duckops.sovereign.state_machine import (
    next_step_in,
    prev_step_in,
    step_order_for_profile,
)
from duckops.sovereign.validate import (
    is_port_in_use,
    private_db_dir_writable,
    redis_ping_url,
    suggest_gateway_port,
)
from duckops.sovereign.wizard_theme import (
    PANEL_BORDER,
    PANEL_BORDER_SUCCESS,
    dim_technical,
    panel_title,
    print_dim_rule,
    section_label,
)

_CONFIRM_EXIT = 2


def _parse_wizard_profile_choice(val: str) -> WizardProfile | None:
    """Acepta rápida/manual (con o sin tilde), 1/2 y alias express/full."""
    s = (val or "").strip().lower()
    if not s:
        return None
    folded = "".join(
        c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)
    )
    if s == "1" or folded in ("rapida", "rapido", "express"):
        return "express"
    if s == "2" or folded in ("manual", "full", "completo", "completa"):
        return "full"
    return None


def _want_yes(val: str) -> bool:
    return (val or "").strip().lower() not in ("n", "no", "0")


def _want_no(val: str) -> bool:
    return (val or "").strip().lower() in ("n", "no", "0")


def _footer() -> str:
    return (
        "Atajos: Ctrl+Z/Esc (atrás) | Ctrl+S (guardar borrador y salir) | "
        "Ctrl+R (probar Redis en pasos Core/Orchestration) | Tab (autofill default)\n"
        "Ctrl+C (abortar)"
    )


def _footer_step_intro() -> str:
    """Atajos del paso 1: una sola línea."""
    return (
        "[dim]Enter continuar · Ctrl+S guardar borrador · Ctrl+C cancelar · "
        "Esc/Ctrl+Z atrás en pasos siguientes[/]"
    )


def _footer_core_services() -> str:
    """Paso 2: incluye prueba de Redis (Ctrl+R)."""
    return (
        "[dim]Tab valor sugerido · Ctrl+R probar conexión Redis · Esc/Ctrl+Z atrás · "
        "Ctrl+S guardar borrador · Ctrl+C cancelar[/]"
    )


def _footer_identity_setup() -> str:
    """Paso 3: sin prueba Redis."""
    return (
        "[dim]Tab valor sugerido · Esc/Ctrl+Z atrás · Ctrl+S guardar borrador · Ctrl+C cancelar[/]"
    )


def _friendly_os_name(system: str) -> str:
    s = (system or "").strip()
    if s == "Darwin":
        return "Mac"
    if s == "Windows":
        return "Windows"
    if s == "Linux":
        return "Linux"
    return s or "este equipo"


def _processor_display(os_name: str, machine: str) -> str:
    """
    Nombre legible del CPU (p. ej. «Apple M4» vía sysctl en macOS).
    En Linux/Windows usa heurísticas; si falla, devuelve arquitectura o «no identificado».
    """
    os_n = (os_name or "").strip()
    mach = (machine or "").strip()

    if os_n == "Darwin":
        try:
            out = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True,
                text=True,
                timeout=4,
            )
            if out.returncode == 0:
                brand = (out.stdout or "").strip()
                if brand:
                    return brand
        except (OSError, subprocess.TimeoutExpired):
            pass
        if mach == "arm64":
            return "Apple Silicon (modelo no identificado)"
        if mach == "x86_64":
            return "Intel u otro (64 bits)"
        return mach or "no identificado"

    if os_n == "Linux":
        try:
            txt = Path("/proc/cpuinfo").read_text(encoding="utf-8", errors="ignore")
            model = ""
            hardware = ""
            for line in txt.splitlines():
                low = line.lower()
                if low.startswith("model name"):
                    _, _, rest = line.partition(":")
                    model = (rest or "").strip()
                elif low.startswith("hardware"):
                    _, _, rest = line.partition(":")
                    hardware = (rest or "").strip()
            if model:
                return model
            if hardware:
                return hardware
        except OSError:
            pass
        proc = (platform.processor() or "").strip()
        if proc:
            return proc
        return mach or "no identificado"

    if os_n == "Windows":
        proc = (platform.processor() or "").strip()
        if proc:
            return proc
        return mach or "no identificado"

    proc = (platform.processor() or "").strip()
    if proc:
        return proc
    return mach or "no identificado"


def _sovereignty_card_content(draft: SovereignDraft, *, index_1_based: int, total: int) -> str:
    """Una sola tarjeta: reconocimiento, SO, CPU, ayuda breve y atajos."""
    os_friendly = _friendly_os_name(draft.detected_os)
    cpu = _processor_display(draft.detected_os, platform.machine())
    copy = STEP_UI[WizardStep.SOVEREIGNTY_AUDIT]
    intro = (copy.description or "Reconociendo tu sistema operativo.").strip()
    return (
        f"[bold bright_white]Paso {index_1_based} de {total}[/] [dim]· DuckClaw[/]\n"
        "\n"
        f"{intro}\n"
        "\n"
        f"Tipo de sistema operativo: [bold]{os_friendly}[/]\n"
        f"Procesador: [bold]{cpu}[/]\n"
        "\n"
        "[dim]¿Es correcto? Enter para seguir. Si no coincide, puedes seguir igual (solo sugerencias) "
        "o Ctrl+C para salir.[/]\n"
        f"{_footer_step_intro()}"
    )


def _show_wizard_concepts_primer(session: PromptSession, console: Console, draft: SovereignDraft) -> int:
    """
    Pantalla inicial de bienvenida y conceptos. Devuelve 0 para continuar, 1 si guardó borrador y sale.
    """
    body = (
        f"{section_label('Bienvenida')}"
        "Hola. Este asistente te va a acompañar para dejar DuckClaw instalado y configurado en "
        "este equipo, con tus datos y tus reglas.\n"
        "\n"
        f"{section_label('Qué es DuckClaw')}"
        "DuckClaw es tu sistema agéntico: varios programas que actúan como un equipo de "
        "asistentes de inteligencia artificial. Pueden hablar contigo por un canal como Telegram, "
        "recordar contexto, usar herramientas y pasarte a perfiles más concretos cuando haga falta. "
        "Está pensado para integrarse en tu vida o tu trabajo sin que pierdas el control: la memoria "
        "y la configuración viven donde tú elijas, en tu máquina o tu infraestructura.\n"
        "\n"
        f"{section_label('Qué puede hacer por ti')}"
        "- Ofrecerte un bot que mantiene coherencia entre conversaciones gracias a una memoria local.\n"
        "- Orquestar un coordinador y trabajadores especializados (finanzas, análisis, ofertas, etc.; "
        "elegirás el perfil que prefieras en la configuración).\n"
        "- Mantener servicios en segundo plano de forma estable, para que no dependas de ventanas abiertas.\n"
        "\n"
        f"{section_label('Qué va a crear en tu proyecto')}"
        "Si al final confirmas, el asistente escribirá en esta carpeta del proyecto archivos de "
        "configuración (por ejemplo .env), apuntará a un archivo de memoria (base de datos DuckDB), "
        "y dejará preparado el arranque del servidor y la conexión con Telegram u otros enlaces que configures. "
        "Antes de tocar nada verás un resumen: nada se aplica a ciegas.\n"
        "\n"
        f"{section_label('Cómo lo haremos juntos')}"
        "Te haré preguntas en orden; la mayoría traen ya una respuesta sugerida (suele bastar Enter). "
        "Podrás elegir configuración rápida o repasar cada bloque. No necesitas saber programar. "
        "Ctrl+S guarda borrador y sale; Ctrl+C cancela.\n"
        "\n"
        f"{section_label('Palabras que verás más adelante')}"
        "- Nombre para esta instalación: cómo quieres llamar a esta copia de DuckClaw "
        "en tu ordenador (por ejemplo el nombre de tu negocio). No es tu usuario de Telegram.\n\n"
        "- Archivo de memoria: donde DuckClaw guarda conversaciones y datos en tu disco "
        "(un solo archivo; el asistente te sugerirá una ruta).\n\n"
        "- Cola de mensajes (Redis): ayuda a que los programas de DuckClaw se hablen entre sí. "
        "En casa casi siempre vale el valor que te proponemos.\n\n"
        "- Servidor en segundo plano: el programa que se queda escuchando cuando llegan mensajes "
        "(por ejemplo desde Telegram). Una herramienta llamada PM2 ayuda a que siga encendido aunque cierres la ventana.\n\n"
        "- Quién te atiende primero: un coordinador y luego un perfil más concreto "
        "(finanzas, ofertas de trabajo, etc.); elegirás el perfil en un paso.\n\n"
        "[dim]Enter = continuar  |  Ctrl+S = guardar borrador y salir  |  Ctrl+C = cancelar[/]"
    )
    console.print()
    console.print(
        Panel(
            body,
            title=panel_title("Bienvenida a DuckClaw"),
            title_align="left",
            border_style=PANEL_BORDER,
        )
    )
    console.print()
    while True:
        tok, _ = _ask_until(session, "Pulsa Enter para continuar. ", default="")
        if tok == NAV_BACK:
            console.print(
                "[dim]Aún no hay paso anterior. Pulsa Enter para comenzar o Ctrl+C para salir.[/]"
            )
            continue
        if tok == NAV_QUICK_SAVE:
            p = save_draft_json(draft)
            console.print(f"[green]Borrador en {p}[/]. Saliendo.")
            return 1
        break
    console.print()
    return 0


def _make_session(on_test: Callable[[], None] | None) -> PromptSession:
    return PromptSession(key_bindings=build_key_bindings(on_service_test=on_test))


def _ask(
    session: PromptSession,
    message: str,
    *,
    default: str = "",
    password: bool = False,
) -> tuple[str | None, str]:
    # prompt_toolkit no interpreta marcado Rich; el texto debe ser plano.
    raw = session.prompt(message, default=default, is_password=password)
    if raw == NAV_BACK:
        return NAV_BACK, ""
    if raw == NAV_QUICK_SAVE:
        return NAV_QUICK_SAVE, ""
    if raw == NAV_SERVICE_TEST:
        return NAV_SERVICE_TEST, ""
    if raw == NAV_AUTOFILL:
        return None, default
    if not raw.strip() and default:
        return None, default
    return None, raw.strip()


def _ask_until(
    session: PromptSession,
    message: str,
    *,
    default: str = "",
    password: bool = False,
) -> tuple[str | None, str]:
    while True:
        tok, val = _ask(session, message, default=default, password=password)
        if tok != NAV_SERVICE_TEST:
            return tok, val


def _show_wizard_profile_choice(
    session: PromptSession, console: Console, draft: SovereignDraft
) -> int:
    """
    Elige configuración rápida (express) vs manual (full).
    Devuelve 0 para continuar, 1 si guardó borrador y sale (igual que el primer).
    """
    default_word = "rápida" if draft.wizard_profile == "express" else "manual"
    body = (
        f"{section_label('Tipo de configuración')}"
        "[bold]Rápida[/] — Recomendada para empezar. Dejamos los valores habituales del proyecto "
        "(cola de mensajes, archivo de memoria, PM2, puerto). Solo preguntamos lo imprescindible para "
        "Telegram y el enlace público (admin, token, HTTPS, etc.) y la confirmación final.\n\n"
        "[bold]Manual[/] — Revisas cada bloque: memoria y rutas, nombre de la instalación, "
        "cómo arrancar servicios (PM2 o Docker), puerto y Redis, y después Telegram.\n\n"
        "[dim]Escribe la palabra «rápida» o «manual» y Enter (también valen 1 / 2). "
        "Tab usa la sugerida entre corchetes · Ctrl+S guardar borrador · Ctrl+C cancelar[/]"
    )
    console.print()
    console.print(
        Panel(
            body,
            title=panel_title("Tipo de configuración"),
            title_align="left",
            border_style=PANEL_BORDER,
        )
    )
    console.print()
    while True:
        tok, val = _ask_until(
            session,
            "Tipo de configuración (rápida / manual): ",
            default=default_word,
        )
        if tok == NAV_BACK:
            console.print("[yellow]Escribe rápida o manual para seguir. (Aún no hay paso anterior.)[/]")
            continue
        if tok == NAV_QUICK_SAVE:
            p = save_draft_json(draft)
            console.print(f"[green]Borrador en {p}[/]. Saliendo.")
            return 1
        parsed = _parse_wizard_profile_choice(val)
        if parsed is not None:
            draft.wizard_profile = parsed
            break
        console.print("[yellow]Escribe «rápida» o «manual» (o 1 / 2) y pulsa Enter.[/]")
    console.print()
    return 0


def run_wizard_loop(repo_root: Path, console: Console, draft: SovereignDraft) -> int:
    if load_draft_json():
        console.print(
            "[yellow]Tienes un borrador guardado[/] (se puede sobrescribir con Ctrl+S al guardar).\n"
            "[dim]Archivo: ~/.config/duckclaw/wizard_draft.json[/]"
        )

    def redis_test() -> None:
        ok, msg = redis_ping_url(draft.redis_url)
        console.print(
            Panel(
                f"Redis: {'OK ' + msg if ok else msg}",
                title=panel_title("Ctrl+R — Redis"),
                border_style=PANEL_BORDER,
            )
        )

    session = _make_session(redis_test)
    if _show_wizard_concepts_primer(session, console, draft) != 0:
        return 0
    if _show_wizard_profile_choice(session, console, draft) != 0:
        return 0

    order = step_order_for_profile(draft.wizard_profile)
    total = len(order)
    step = order[0]

    while True:
        idx = order.index(step) + 1

        if step == WizardStep.SOVEREIGNTY_AUDIT:
            draft.detected_os = platform.system()
            draft.is_apple_silicon = platform.machine() == "arm64" and draft.detected_os == "Darwin"
            console.print(
                Panel(
                    _sovereignty_card_content(draft, index_1_based=idx, total=total),
                    title=panel_title("Tu equipo"),
                    border_style=PANEL_BORDER,
                )
            )
            console.print()
            tok, _ = _ask_until(
                session,
                "¿Seguimos al siguiente paso? Pulsa Enter. ",
                default="",
            )
            if tok == NAV_BACK:
                console.print("[yellow]Ya estás en el primer paso.[/]")
                continue
            if tok == NAV_QUICK_SAVE:
                p = save_draft_json(draft)
                console.print(f"[green]Borrador en {p}[/]. Saliendo.")
                return 0
            n = next_step_in(order, step)
            if n:
                step = n
            continue

        if step == WizardStep.CORE_SERVICES:
            hdr = step_header_compact(WizardStep.CORE_SERVICES, index_1_based=idx, total=total)
            footer = _footer_core_services()
        elif step == WizardStep.IDENTITY_SETUP:
            hdr = step_header_compact(WizardStep.IDENTITY_SETUP, index_1_based=idx, total=total)
            footer = _footer_identity_setup()
        elif step == WizardStep.ORCHESTRATION:
            hdr = step_header_compact(WizardStep.ORCHESTRATION, index_1_based=idx, total=total)
            footer = _footer_core_services()
        elif step == WizardStep.CONNECTIVITY:
            hdr = step_header_compact(WizardStep.CONNECTIVITY, index_1_based=idx, total=total)
            footer = _footer_core_services()
        else:
            hdr = step_header(step, index_1_based=idx, total=total)
            footer = _footer()
        if step != WizardStep.REVIEW_DEPLOY:
            console.print(
                Panel(
                    hdr + "\n\n" + footer,
                    border_style=PANEL_BORDER,
                )
            )
            console.print()

        if step == WizardStep.CORE_SERVICES:
            if not private_db_dir_writable(repo_root):
                console.print(
                    "[red]No hay permiso de escritura en la carpeta db/private. "
                    "Ajusta permisos antes de seguir.[/]"
                )
            tok, val = _ask_until(
                session,
                (
                    "1/3 — Servicio de mensajes entre programas (Redis). "
                    "Si no sabes qué es, deja el valor entre corchetes y pulsa Enter.\n"
                    f"Redis [{draft.redis_url}]: "
                ),
                default=draft.redis_url,
            )
            if tok == NAV_BACK:
                p = prev_step_in(order, step)
                if p:
                    step = p
                continue
            if tok == NAV_QUICK_SAVE:
                console.print(f"[green]{save_draft_json(draft)}[/]")
                return 0
            if val:
                draft.redis_url = val
            console.print()
            tok, val = _ask_until(
                session,
                (
                    "2/3 — Archivo en tu disco donde DuckClaw guardará conversaciones y datos "
                    "(es un solo archivo; la ruta sugerida suele valer). Enter para aceptarla.\n"
                    f"Archivo de memoria [{draft.duckdb_vault_path}]: "
                ),
                default=draft.duckdb_vault_path,
            )
            if tok == NAV_BACK:
                continue
            if tok == NAV_QUICK_SAVE:
                console.print(f"[green]{save_draft_json(draft)}[/]")
                return 0
            if val:
                draft.duckdb_vault_path = val
            console.print()
            tok, val = _ask_until(
                session,
                (
                    "3/3 — ¿Otro archivo de datos aparte del anterior? (casi siempre no). "
                    "Déjalo vacío y pulsa Enter; solo rellénalo si ya sabes que necesitas una segunda ruta.\n"
                    f"Ruta extra (opcional) [{draft.duckdb_shared_path}]: "
                ),
                default=draft.duckdb_shared_path,
            )
            if tok == NAV_BACK:
                continue
            if tok == NAV_QUICK_SAVE:
                console.print(f"[green]{save_draft_json(draft)}[/]")
                return 0
            draft.duckdb_shared_path = val
            n = next_step_in(order, step)
            if n:
                step = n
            continue

        if step == WizardStep.IDENTITY_SETUP:
            tok, val = _ask_until(
                session,
                (
                    "1/3 — Nombre para esta instalación: una etiqueta tuya (ej. «Mi negocio») para separar "
                    "estos datos de otros proyectos. No es Telegram. Enter para el valor sugerido.\n"
                    f"Nombre [{draft.tenant_id}]: "
                ),
                default=draft.tenant_id,
            )
            if tok == NAV_BACK:
                p = prev_step_in(order, step)
                if p:
                    step = p
                continue
            if tok == NAV_QUICK_SAVE:
                console.print(f"[green]{save_draft_json(draft)}[/]")
                return 0
            if val:
                draft.tenant_id = val
            console.print()
            tok, val = _ask_until(
                session,
                (
                    "2/3 — Nombre del proceso en segundo plano (PM2) para el servidor (gateway): "
                    "es cómo verás en la lista el programa que mantiene encendido el API que habla con los agentes. "
                    "Enter si te vale el sugerido.\n"
                    f"Nombre del servicio [{draft.gateway_pm2_name}]: "
                ),
                default=draft.gateway_pm2_name,
            )
            if tok == NAV_BACK:
                continue
            if tok == NAV_QUICK_SAVE:
                console.print(f"[green]{save_draft_json(draft)}[/]")
                return 0
            if val:
                draft.gateway_pm2_name = val
            console.print()
            tok, val = _ask_until(
                session,
                (
                    "3/3 — Asistente especializado por defecto (worker): el manager te atiende primero y suele "
                    "pasarte a uno de estos perfiles. Escribe el id exacto o Enter para el sugerido.\n"
                    "Opciones: BI-Analyst | Job-Hunter | LeilaAssistant | SIATA-Analyst | finanz | TheMindCrupier\n"
                    f"Worker por defecto [{draft.default_worker_id}]: "
                ),
                default=draft.default_worker_id,
            )
            if tok == NAV_BACK:
                continue
            if tok == NAV_QUICK_SAVE:
                console.print(f"[green]{save_draft_json(draft)}[/]")
                return 0
            if val:
                draft.default_worker_id = val
            n = next_step_in(order, step)
            if n:
                step = n
            continue

        if step == WizardStep.ORCHESTRATION:
            host = "127.0.0.1"
            if is_port_in_use(host, draft.gateway_port):
                alt = suggest_gateway_port(host, draft.gateway_port)
                console.print(f"[yellow]Puerto {draft.gateway_port} ocupado; sugerido {alt}[/]")
                draft.gateway_port = alt
            tok, val = _ask_until(
                session,
                (
                    "1/4 — ¿Cómo quieres ejecutar los servicios en este equipo?\n"
                    "Escribe pm2 (recomendado: procesos en segundo plano en esta máquina) "
                    "o docker (contenedores).\n"
                    f"Modo [{draft.orchestration}]: "
                ),
                default=draft.orchestration,
            )
            if tok == NAV_BACK:
                p = prev_step_in(order, step)
                if p:
                    step = p
                continue
            if tok == NAV_QUICK_SAVE:
                console.print(f"[green]{save_draft_json(draft)}[/]")
                return 0
            if val in ("docker", "pm2"):
                draft.orchestration = val  # type: ignore[assignment]
            console.print()
            tok, val = _ask_until(
                session,
                (
                    "2/4 — Puerto del servidor web (número). Telegram y los túneles usarán este puerto.\n"
                    f"Puerto [{draft.gateway_port}]: "
                ),
                default=str(draft.gateway_port),
            )
            if tok == NAV_BACK:
                continue
            if tok == NAV_QUICK_SAVE:
                console.print(f"[green]{save_draft_json(draft)}[/]")
                return 0
            try:
                if val:
                    draft.gateway_port = int(val)
            except ValueError:
                console.print("[red]Puerto inválido[/]")
                continue
            console.print(
                f"[dim]Paso siguiente: enlace público HTTPS hacia este puerto. "
                f"Comando avanzado (Tailscale): tailscale funnel --bg --yes {draft.gateway_port} · "
                f"{TAILSCALE_FUNNEL_KB_URL}[/]"
            )
            console.print()
            tok, val = _ask_until(
                session,
                (
                    "3/4 — ¿Intentar instalar o activar Redis en esta máquina con ayuda del asistente "
                    "(Homebrew en Mac, pistas en Linux)? [y/N]: "
                ),
                default="n",
            )
            if tok == NAV_BACK:
                continue
            if tok == NAV_QUICK_SAVE:
                console.print(f"[green]{save_draft_json(draft)}[/]")
                return 0
            draft.redis_local_managed = val.lower() in ("y", "yes", "s", "sí", "si", "1")
            if draft.orchestration == "docker":
                console.print()
                tok, val = _ask_until(
                    session,
                    (
                        "4/4 — ¿Crear un archivo extra de Docker Compose que incluya Redis? [Y/n] "
                        "(archivo: docker-compose.override.yml)"
                    ),
                    default="y",
                )
                if tok == NAV_BACK:
                    continue
                if tok == NAV_QUICK_SAVE:
                    console.print(f"[green]{save_draft_json(draft)}[/]")
                    return 0
                draft.generate_docker_compose = val.lower() not in ("n", "no", "0")
            n = next_step_in(order, step)
            if n:
                step = n
            continue

        if step == WizardStep.CONNECTIVITY:
            if draft.wizard_profile == "express":
                host = "127.0.0.1"
                if is_port_in_use(host, draft.gateway_port):
                    alt = suggest_gateway_port(host, draft.gateway_port)
                    console.print(
                        f"[yellow]El puerto {draft.gateway_port} está ocupado; "
                        f"usaremos el sugerido {alt} para el servidor web.[/]"
                    )
                    draft.gateway_port = alt
            _tg_intro = (
                f"{section_label('Quién puede usar el bot')}"
                "Solo las personas que tú autorices podrán hablar con este bot. "
                "Te registramos como [green]administrador principal[/] con tu número de usuario de Telegram "
                "y un nombre para reconocerte en listas internas.\n\n"
                "Para ver tu número: escribe a [bold]@userinfobot[/] en Telegram o revisa los detalles "
                "de cualquier mensaje tuyo en Telegram (aparece como número largo, solo dígitos).\n\n"
                "Más adelante podrás indicar otros administradores (también por número).\n\n"
                + dim_technical(
                    "Técnico: lista de usuarios autorizados en la base de datos del servidor "
                    "(tabla main.authorized_users)"
                )
            )
            console.print(
                Panel(
                    _tg_intro,
                    title=panel_title("Telegram"),
                    border_style=PANEL_BORDER,
                )
            )
            print_dim_rule(console)
            while True:
                tok, val = _ask_until(
                    session,
                    (
                        "Tu número de usuario de Telegram (solo dígitos, sin @). "
                        "Quedarás como administrador principal.\n"
                        f"Número [{draft.wizard_creator_telegram_user_id or 'obligatorio'}]: "
                    ),
                    default=draft.wizard_creator_telegram_user_id,
                )
                if tok == NAV_BACK:
                    p = prev_step_in(order, step)
                    if p:
                        step = p
                    break
                if tok == NAV_QUICK_SAVE:
                    console.print(f"[green]{save_draft_json(draft)}[/]")
                    return 0
                cid = (val or "").strip()
                if not cid.isdigit():
                    console.print("[red]El ID debe ser numérico (solo dígitos), sin @ ni espacios.[/]")
                    continue
                draft.wizard_creator_telegram_user_id = cid
                break
            if step != WizardStep.CONNECTIVITY:
                continue

            console.print()
            tok, val = _ask_until(
                session,
                (
                    "Tu nombre para mostrar en listas del bot (ej. Juan). Enter para dejar vacío o el valor entre corchetes.\n"
                    f"Nombre [{draft.wizard_creator_admin_display_name or 'opcional'}]: "
                ),
                default=draft.wizard_creator_admin_display_name,
            )
            if tok == NAV_BACK:
                continue
            if tok == NAV_QUICK_SAVE:
                console.print(f"[green]{save_draft_json(draft)}[/]")
                return 0
            draft.wizard_creator_admin_display_name = (val or "").strip()

            console.print()
            tok, val = _ask_until(
                session,
                (
                    "¿Otros administradores del bot? Escribe números de Telegram separados por coma; "
                    "vacío + Enter = ninguno.\n"
                    f"Números extra [{draft.wizard_extra_admin_telegram_ids}]: "
                ),
                default=draft.wizard_extra_admin_telegram_ids,
            )
            if tok == NAV_BACK:
                continue
            if tok == NAV_QUICK_SAVE:
                console.print(f"[green]{save_draft_json(draft)}[/]")
                return 0
            extra = (val or "").strip()
            if extra:
                bad = [x.strip() for x in extra.replace(";", ",").split(",") if x.strip() and not x.strip().isdigit()]
                if bad:
                    console.print(
                        "[yellow]Aviso:[/] ignora entradas no numéricas; guardamos solo dígitos válidos."
                    )
                draft.wizard_extra_admin_telegram_ids = extra
            else:
                draft.wizard_extra_admin_telegram_ids = ""

            console.print()
            console.print(dim_technical("Variable de entorno: TELEGRAM_BOT_TOKEN"))
            tok, val = _ask_until(
                session,
                (
                    "Token del bot de Telegram (el que te dio BotFather). "
                    "Si ya lo tienes en un archivo .env, deja vacío y pulsa Enter para no cambiarlo aquí.\n"
                    "Token: "
                ),
                password=True,
                default="",
            )
            if tok == NAV_BACK:
                p = prev_step_in(order, step)
                if p:
                    step = p
                continue
            if tok == NAV_QUICK_SAVE:
                console.print(f"[green]{save_draft_json(draft)}[/]")
                return 0
            if val:
                draft.telegram_bot_token = val
                draft.telegram_bot_token_masked = True

            print_dim_rule(console)
            console.print(
                Panel(
                    tailscale_funnel_wizard_panel_content(draft.gateway_port),
                    title=panel_title("Enlace público (Tailscale Funnel)"),
                    border_style=PANEL_BORDER,
                )
            )
            tok, val = _ask_until(
                session,
                (
                    f"¿Quieres que el asistente intente abrir ahora un enlace HTTPS público con Tailscale "
                    f"hacia el puerto {draft.gateway_port}? "
                    "Hace falta Tailscale instalado, sesión iniciada y permiso de funnel en tu red. [Y/n]: "
                ),
                default="y",
            )
            if tok == NAV_BACK:
                continue
            if tok == NAV_QUICK_SAVE:
                console.print(f"[green]{save_draft_json(draft)}[/]")
                return 0
            if _want_yes(val):
                if not tailscale_cli_available():
                    console.print(
                        "[yellow]No hay `tailscale` en PATH. Instala la app/CLI o pega la URL HTTPS más abajo.[/]"
                    )
                else:
                    with console.status("[bold cyan]Configurando Tailscale Funnel (--bg)…[/]"):
                        url_f, err_f, warn_f = provision_tailscale_funnel_bg(
                            draft.gateway_port
                        )
                    if warn_f:
                        console.print(
                            Panel(
                                warn_f,
                                title="Aviso: Funnel cambia el puerto de destino",
                                border_style="yellow",
                            )
                        )
                    if url_f:
                        draft.telegram_webhook_public_base_url = url_f
                        draft.tailscale_funnel_bg_via_wizard = True
                        draft.cloudflared_pm2_process_name = ""
                        console.print(
                            Panel(
                                f"[green]Base HTTPS (Funnel)[/]\n{url_f}\n\n"
                                f"[green]Ruta webhook Telegram[/]\n{url_f}/api/v1/telegram/webhook\n\n"
                                "[dim]Estado: [bold]tailscale funnel status[/]  ·  Quitar: [bold]tailscale funnel reset[/][/]",
                                title=panel_title("Tailscale Funnel — listo"),
                                border_style=PANEL_BORDER_SUCCESS,
                            )
                        )
                    else:
                        console.print(f"[red]Tailscale Funnel: {err_f}[/]")

            if not (draft.telegram_webhook_public_base_url or "").strip():
                tok, val = _ask_until(
                    session,
                    "¿Usar Cloudflare Quick Tunnel [trycloudflare.com] como alternativa (sin Tailscale)? [y/N]: ",
                    default="n",
                )
                if tok == NAV_BACK:
                    continue
                if tok == NAV_QUICK_SAVE:
                    console.print(f"[green]{save_draft_json(draft)}[/]")
                    return 0
                if _want_yes(val):
                    if not cloudflared_available():
                        console.print(
                            "[yellow]No hay `cloudflared` en PATH. Instálalo (p. ej. brew install cloudflared) "
                            "o indica la URL HTTPS a mano más abajo.[/]"
                        )
                    else:
                        use_pm2_tunnel = True
                        if pm2_available():
                            tok_p, val_p = _ask_until(
                                session,
                                "¿Registrar cloudflared en PM2? [Y/n]: ",
                                default="y",
                            )
                            if tok_p == NAV_BACK:
                                continue
                            if tok_p == NAV_QUICK_SAVE:
                                console.print(f"[green]{save_draft_json(draft)}[/]")
                                return 0
                            use_pm2_tunnel = not _want_no(val_p)
                        else:
                            console.print(
                                "[dim]PM2 no está en PATH; cloudflared en segundo plano.[/]"
                            )
                            use_pm2_tunnel = False
                        with console.status("[bold cyan]Arrancando Quick Tunnel (cloudflared)…[/]"):
                            url_cf, err_cf, pm2n = provision_trycloudflare_quick_tunnel(
                                draft.gateway_port,
                                gateway_pm2_name=draft.gateway_pm2_name,
                                use_pm2=use_pm2_tunnel,
                            )
                        if url_cf:
                            draft.telegram_webhook_public_base_url = url_cf
                            draft.cloudflared_pm2_process_name = pm2n or ""
                            draft.tailscale_funnel_bg_via_wizard = False
                            extra = (
                                f"PM2: [cyan]{pm2n}[/]. Considera [dim]pm2 save[/]."
                                if pm2n
                                else "cloudflared en segundo plano sin PM2."
                            )
                            console.print(
                                Panel(
                                    f"[green]Base HTTPS[/]\n{url_cf}\n\n"
                                    f"[green]Webhook[/]\n{url_cf}/api/v1/telegram/webhook\n\n"
                                    f"{extra}",
                                    title=panel_title("Cloudflare Quick Tunnel — listo"),
                                    border_style=PANEL_BORDER_SUCCESS,
                                )
                            )
                        else:
                            console.print(f"[red]Quick Tunnel: {err_cf}[/]")

            console.print()
            console.print(
                dim_technical(
                    "Variable: TELEGRAM_WEBHOOK_SECRET · Debe coincidir con la configuración del webhook en Telegram"
                )
            )
            tok, val = _ask_until(
                session,
                (
                    "Frase secreta del webhook (opcional). Si la configuras, debe ser la misma "
                    "que pongas al registrar el webhook en Telegram.\n"
                    "Secreto (opcional): "
                ),
                password=True,
                default="",
            )
            if tok == NAV_BACK:
                continue
            if tok == NAV_QUICK_SAVE:
                console.print(f"[green]{save_draft_json(draft)}[/]")
                return 0
            if val:
                draft.telegram_webhook_secret = val
                draft.telegram_webhook_secret_masked = True

            if not (draft.telegram_webhook_public_base_url or "").strip():
                tok, val = _ask_until(
                    session,
                    (
                        "Dirección HTTPS pública que apunte a tu servidor (sin barra al final). "
                        "Úsala si no activaste un túnel arriba; vacío = se completará más tarde con una plantilla.\n"
                        "URL HTTPS: "
                    ),
                    default="",
                )
                if tok == NAV_BACK:
                    continue
                if tok == NAV_QUICK_SAVE:
                    console.print(f"[green]{save_draft_json(draft)}[/]")
                    return 0
                if val:
                    draft.telegram_webhook_public_base_url = val

            console.print()
            console.print(dim_technical("Variable: DUCKCLAW_TAILSCALE_AUTH_KEY"))
            tok, val = _ask_until(
                session,
                (
                    "Clave de acceso a la red Tailscale (opcional). Solo si tu instalación la necesita.\n"
                    "Clave (opcional): "
                ),
                password=True,
                default="",
            )
            if tok == NAV_BACK:
                continue
            if tok == NAV_QUICK_SAVE:
                console.print(f"[green]{save_draft_json(draft)}[/]")
                return 0
            if val:
                draft.duckclaw_tailscale_auth_key = val
            console.print(dim_technical("Opción técnica: integración MCP (herramientas para desarrolladores)"))
            tok, val = _ask_until(
                session,
                (
                    "¿Activar herramientas extra para desarrolladores vinculadas a Telegram? "
                    "La mayoría puede dejar Sí o Enter.\n"
                    "[Y/n]: "
                ),
                default="y",
            )
            if tok == NAV_BACK:
                continue
            if tok == NAV_QUICK_SAVE:
                console.print(f"[green]{save_draft_json(draft)}[/]")
                return 0
            draft.enable_telegram_mcp = val.lower() not in ("n", "no", "0")
            n = next_step_in(order, step)
            if n:
                step = n
            continue

        if step == WizardStep.REVIEW_DEPLOY:
            masked_tok = "•••• (configurado)" if draft.telegram_bot_token else "(sin cambiar aquí / ya en .env)"
            extra_path = draft.duckdb_shared_path.strip() or "(ninguna)"
            orch_sp = "Docker" if draft.orchestration == "docker" else "PM2 en esta máquina"
            funnel_sí = "sí" if draft.tailscale_funnel_bg_via_wizard else "no"
            cf_pm2 = draft.cloudflared_pm2_process_name.strip() or "(ninguno)"
            mcp_sí = "sí" if draft.enable_telegram_mcp else "no"
            url_pub = (draft.telegram_webhook_public_base_url or "").strip() or "(se definirá después / plantilla)"
            profile_es = (
                "Rápida (valores por defecto; solo canal y secretos en detalle)"
                if draft.wizard_profile == "express"
                else "Manual (revisaste memoria, identidad y orquestación paso a paso)"
            )
            summary = (
                f"{section_label('Tipo de configuración')}"
                f"{profile_es}\n"
                "\n"
                f"{section_label('Datos y mensajes')}"
                f"Redis (cola): {draft.redis_url}\n"
                f"Archivo de memoria principal: {draft.duckdb_vault_path}\n"
                f"Archivo de memoria extra: {extra_path}\n"
                "\n"
                f"{section_label('Tu instalación')}"
                f"Nombre para esta instalación: {draft.tenant_id}\n"
                f"Nombre del servicio en segundo plano: {draft.gateway_pm2_name}\n"
                f"Asistente especializado por defecto: {draft.default_worker_id}\n"
                "\n"
                f"{section_label('Telegram')}"
                f"Tu número (admin principal): {draft.wizard_creator_telegram_user_id or '(falta)'} "
                f"— nombre: {draft.wizard_creator_admin_display_name or '(sin nombre)'}\n"
                f"Otros administradores: {draft.wizard_extra_admin_telegram_ids or '(ninguno)'}\n"
                f"Token del bot: {masked_tok}\n"
                f"Dirección HTTPS pública: {url_pub}\n"
                f"Enlace abierto con Tailscale Funnel desde el asistente: {funnel_sí}\n"
                f"Túnel Cloudflare (proceso en PM2 si aplica): {cf_pm2}\n"
                f"Integración MCP con Telegram: {mcp_sí}\n"
                "\n"
                f"{section_label('Arranque')}"
                f"Modo: {orch_sp} · Puerto del servidor web: {draft.gateway_port}\n"
            )
            confirm_help = (
                "\n"
                f"{section_label('Cómo confirmar')}"
                "Si todo te parece bien y quieres guardar los cambios en esta carpeta del proyecto, "
                "escribe exactamente la palabra CONFIRMAR (las ocho letras, todo en mayúsculas) "
                "en la línea que verás justo debajo de este cuadro, y pulsa Enter.\n\n"
                "Si no quieres guardar nada todavía, escribe cualquier otra cosa en esa línea; "
                "también puedes pulsar Esc o Ctrl+Z para volver atrás y corregir un paso.\n\n"
                f"{dim_technical('Al confirmar se actualizan .env y los archivos de arranque del repositorio')}"
            )
            review_full = hdr + "\n\n" + footer + "\n\n" + summary + confirm_help
            console.print(
                Panel(
                    review_full,
                    title=panel_title("Última comprobación"),
                    border_style=PANEL_BORDER,
                )
            )
            console.print()
            tok, val = _ask_until(
                session,
                "Tu respuesta (CONFIRMAR u otra cosa): ",
                default="",
            )
            if tok == NAV_BACK:
                p = prev_step_in(order, step)
                if p:
                    step = p
                continue
            if tok == NAV_QUICK_SAVE:
                console.print(f"[green]{save_draft_json(draft)}[/]")
                return 0
            if val.strip().upper() != "CONFIRMAR":
                console.print("[yellow]Cancelado: no se ha modificado la configuración en el proyecto.[/]")
                return 0
            return _CONFIRM_EXIT

    return 0
