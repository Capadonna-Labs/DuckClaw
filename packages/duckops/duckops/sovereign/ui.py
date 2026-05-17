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
from duckops.sovereign.domain_labels import STEP_UI, TAILSCALE_FUNNEL_KB_URL, WizardStep
from duckops.sovereign.tailscale_funnel import (
    provision_tailscale_funnel_bg,
    tailscale_cli_available,
)
from duckops.sovereign.draft import SovereignDraft, WizardProfile
from duckops.sovereign.keys import (
    NAV_AUTOFILL,
    NAV_BACK,
    NAV_QUICK_SAVE,
    NAV_RESET,
    NAV_SERVICE_TEST,
    build_key_bindings,
)
from duckops.sovereign.materialize import load_draft_json, save_draft_json
from duckops.sovereign.duckdb_catalog import (
    build_neutral_duckdb_picker,
    discover_duckdb_files,
    ensure_duckdb_vault,
    format_db_folder_summary,
)
from duckops.sovereign.duckdb_health import audit_duckdb, format_duckdb_health_rich
from duckops.sovereign.stack_health import audit_stack, format_stack_health_rich
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
    panel_title,
)
from duckops.sovereign.tui_picker import (
    PickerCancelled,
    WizardResetRequested,
    pick_one_index,
    run_list_picker,
)
from duckops.sovereign.tui_shell import TuiShell
from duckops.sovereign.wizard_reset import (
    clear_wizard_state,
    default_worker_for_fresh,
    describe_saved_state,
    fresh_sovereign_draft,
    has_saved_wizard_state,
    load_saved_draft_or_none,
)
from duckops.sovereign.workers_catalog import (
    format_worker_picker_block,
    list_worker_picks,
    resolve_worker_choice,
)

_CONFIRM_EXIT = 2


def _express_apply_confirm(val: str) -> bool:
    """Enter vacío o CONFIRMAR aplican en perfil rápido."""
    v = (val or "").strip().upper()
    return v in ("", "CONFIRMAR", "S", "SI", "SÍ", "Y", "YES")


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


def _sovereignty_line(draft: SovereignDraft) -> str:
    os_friendly = _friendly_os_name(draft.detected_os)
    cpu = _processor_display(draft.detected_os, platform.machine())
    return f"[dim]{os_friendly} · {cpu}[/]"


def _fresh_draft_for_repo(repo_root: Path) -> SovereignDraft:
    picks = list_worker_picks(repo_root)
    return fresh_sovereign_draft(
        worker_id=default_worker_for_fresh([p.worker_id for p in picks]),
    )


def _show_wizard_start_menu(
    console: Console,
    draft: SovereignDraft,
    shell: TuiShell,
    repo_root: Path,
) -> tuple[SovereignDraft, int]:
    """
    Menú inicial: nueva config, continuar o borrar local.
    Devuelve (borrador, código). 1 = salir.
    """
    shell.show_welcome()
    console.print(
        "[dim]Sin datos de tu .env en pantalla: elige en listas (Espacio + Enter). "
        "Ctrl+Shift+R reinicia en cualquier paso.[/]\n"
    )
    labels = ["Nueva configuración (usuario limpio)"]
    if has_saved_wizard_state():
        desc = describe_saved_state()
        labels.append(f"Continuar sesión guardada ({desc})" if desc else "Continuar sesión guardada")
        labels.append("Eliminar borrador local y empezar de cero")
    idx = 0
    while True:
        try:
            idx = pick_one_index(
                "¿Cómo quieres configurar DuckClaw?",
                labels,
                initial_index=0,
            )
            break
        except WizardResetRequested:
            removed = clear_wizard_state()
            draft = _fresh_draft_for_repo(repo_root)
            if removed:
                console.print("[green]Borrador local eliminado.[/]")
            continue
        except PickerCancelled:
            console.print("[dim]Cancelado.[/]")
            return draft, 1

    if idx == 0:
        draft = _fresh_draft_for_repo(repo_root)
        shell.note("Nueva configuración")
        console.print("[green]Perfil limpio[/] — elige DuckDB y worker en los siguientes pasos.\n")
        return draft, 0

    if has_saved_wizard_state() and idx == 1:
        saved = load_saved_draft_or_none()
        if saved is not None:
            shell.note("Continuar borrador")
            console.print("[dim]Cargado borrador local (no es el .env del repo).[/]\n")
            return saved, 0
        console.print("[yellow]No hay borrador válido; empezamos limpio.[/]\n")
        return _fresh_draft_for_repo(repo_root), 0

    if has_saved_wizard_state() and idx == 2:
        removed = clear_wizard_state()
        if removed:
            console.print("[green]Eliminado:[/] " + ", ".join(str(p.name) for p in removed))
        draft = _fresh_draft_for_repo(repo_root)
        shell.note("Reinicio total")
        return draft, 0

    return draft, 0


def _pick_worker(
    console: Console,
    draft: SovereignDraft,
    repo_root: Path,
    *,
    title: str = "Worker por defecto",
) -> None:
    picks = list_worker_picks(repo_root)
    if not picks:
        return
    labels = [f"{p.worker_id} — {p.label}" for p in picks]
    values = [p.worker_id for p in picks]
    initial = 0
    for i, wid in enumerate(values):
        if wid == draft.default_worker_id:
            initial = i
            break
    console.print()
    try:
        draft.default_worker_id = run_list_picker(
            title,
            labels,
            values=values,
            initial_index=initial,
        )
    except PickerCancelled:
        raise


def _apply_wizard_reset(
    console: Console,
    shell: TuiShell,
    repo_root: Path,
    order: tuple,
) -> tuple[SovereignDraft, WizardStep]:
    removed = clear_wizard_state()
    if removed:
        console.print(
            "[green]Configuración local eliminada:[/] "
            + ", ".join(p.name for p in removed)
        )
    draft = _fresh_draft_for_repo(repo_root)
    shell.draft = draft
    shell.init_steps(list(order))
    shell.note("Wizard reiniciado")
    console.print("[yellow]Empezando de cero (perfil limpio).[/]\n")
    return draft, order[0]


def _make_session(on_test: Callable[[], None] | None) -> PromptSession:
    return PromptSession(key_bindings=build_key_bindings(on_service_test=on_test))


def _worker_picks_for_repo(repo_root: Path) -> list:
    return list_worker_picks(repo_root)


def _prompt_default_worker(
    session: PromptSession,
    console: Console,
    draft: SovereignDraft,
    repo_root: Path,
) -> tuple[str | None, bool]:
    """Lista interactiva de plantillas (Espacio + Enter)."""
    _ = session
    try:
        _pick_worker(console, draft, repo_root)
        return None, True
    except PickerCancelled:
        return NAV_BACK, False


def _prompt_gateway_team_optional(
    session: PromptSession,
    console: Console,
    draft: SovereignDraft,
    repo_root: Path,
) -> tuple[str | None, bool]:
    """Equipo inicial opcional (coma-separado)."""
    picks = _worker_picks_for_repo(repo_root)
    hint = draft.gateway_team_templates or "(vacío = todas las plantillas)"
    tok, val = _ask_until(
        session,
        f"Equipo /workers (coma, vacío=todos) [{hint}]: ",
        default=draft.gateway_team_templates,
    )
    if tok in (NAV_BACK, NAV_QUICK_SAVE):
        return tok, False
    raw = (val or "").strip()
    if not raw:
        draft.gateway_team_templates = ""
        return None, True
    resolved_ids: list[str] = []
    for part in raw.replace(";", ",").split(","):
        token = part.strip()
        if not token:
            continue
        wid = resolve_worker_choice(token, picks, repo_root) if picks else token
        if not wid:
            console.print(f"[yellow]Ignoro «{token}» (no es una plantilla válida).[/]")
            continue
        if wid not in resolved_ids:
            resolved_ids.append(wid)
    draft.gateway_team_templates = ", ".join(resolved_ids)
    return None, True


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
    if raw == NAV_RESET:
        return NAV_RESET, ""
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
        if tok == NAV_RESET:
            return NAV_RESET, val
        if tok != NAV_SERVICE_TEST:
            return tok, val


def _show_wizard_profile_choice(
    session: PromptSession,
    console: Console,
    draft: SovereignDraft,
    shell: TuiShell,
) -> int:
    """
    Elige configuración rápida (express) vs manual (full).
    Devuelve 0 para continuar, 1 si guardó borrador y sale (igual que el primer).
    """
    default_word = "rápida" if draft.wizard_profile == "express" else "manual"
    shell.show_profile_choice()
    while True:
        tok, val = _ask_until(
            session,
            "rápida o manual [1/2]: ",
            default=default_word,
        )
        if tok == NAV_BACK:
            console.print("[yellow]Escribe rápida o manual para seguir. (Aún no hay paso anterior.)[/]")
            continue
        if tok == NAV_QUICK_SAVE:
            p = save_draft_json(draft)
            shell.note("Borrador guardado")
            console.print(f"[green]Borrador en {p}[/]. Saliendo.")
            return 1
        parsed = _parse_wizard_profile_choice(val)
        if parsed is not None:
            draft.wizard_profile = parsed
            shell.note(f"Perfil: {'rápida' if parsed == 'express' else 'manual'}")
            break
        console.print("[yellow]Escribe «rápida» o «manual» (o 1 / 2) y pulsa Enter.[/]")
    return 0


def run_wizard_loop(
    repo_root: Path,
    console: Console,
    draft: SovereignDraft,
    *,
    manual: bool = False,
) -> tuple[int, TuiShell]:
    shell = TuiShell(console, draft, repo_root)

    def redis_test() -> None:
        ok, msg = redis_ping_url(draft.redis_url)
        shell.note(f"Redis: {'OK' if ok else 'fallo'}")
        console.print(
            Panel(
                f"Redis: {'OK ' + msg if ok else msg}",
                title=panel_title("Ctrl+R — Redis"),
                border_style=PANEL_BORDER_SUCCESS if ok else PANEL_BORDER,
            )
        )

    session = _make_session(redis_test)
    draft, start_code = _show_wizard_start_menu(console, draft, shell, repo_root)
    if start_code != 0:
        return 0, shell
    shell.draft = draft

    if manual:
        if _show_wizard_profile_choice(session, console, draft, shell) != 0:
            return 0, shell
    else:
        draft.wizard_profile = "express"
        shell.note("Perfil rápido (usa --manual para Telegram en CLI)")

    order = step_order_for_profile(draft.wizard_profile)
    shell.init_steps(order)
    total = len(order)
    step = order[0]

    while True:
        idx = order.index(step) + 1
        shell.begin_step(step, index_1_based=idx, total=total)

        if step == WizardStep.SOVEREIGNTY_AUDIT:
            draft.detected_os = platform.system()
            draft.is_apple_silicon = platform.machine() == "arm64" and draft.detected_os == "Darwin"
            console.print(_sovereignty_line(draft))
            try:
                pick_one_index(
                    "Tu equipo",
                    [f"Continuar en {_friendly_os_name(draft.detected_os)}"],
                    initial_index=0,
                )
            except WizardResetRequested:
                draft, step = _apply_wizard_reset(console, shell, repo_root, order)
                continue
            except PickerCancelled:
                continue
            shell.complete_step(step)
            n = next_step_in(order, step)
            if n:
                step = n
            continue

        if step == WizardStep.CORE_SERVICES:
            if draft.wizard_profile == "express":
                if not private_db_dir_writable(repo_root):
                    console.print(
                        "[red]Sin permiso de escritura en db/private. Ajusta permisos.[/]"
                    )
                ok, msg = redis_ping_url(draft.redis_url)
                shell.note(f"Redis: {'OK' if ok else 'pendiente'}")
                redis_line = f"{'OK ' + msg if ok else msg}"
                shell.print_content_panel(
                    f"[dim]Estado Redis:[/] {redis_line}\n\n"
                    f"{format_db_folder_summary(repo_root, discover_duckdb_files(repo_root))}",
                    title="Datos y cola",
                )
                try:
                    draft.redis_url = run_list_picker(
                        "Conexión Redis",
                        [
                            f"redis://localhost:6379/0  ({'detectado' if ok else 'sin respuesta'})",
                        ],
                        values=["redis://localhost:6379/0"],
                        initial_index=0,
                    )
                except WizardResetRequested:
                    draft, step = _apply_wizard_reset(console, shell, repo_root, order)
                    continue
                except PickerCancelled:
                    p = prev_step_in(order, step)
                    if p:
                        step = p
                    continue
                db_labels, db_values, db_initial = build_neutral_duckdb_picker(repo_root)
                console.print()
                try:
                    draft.duckdb_vault_path = run_list_picker(
                        "Bóveda DuckDB (archivo .duckdb)",
                        db_labels,
                        values=db_values,
                        initial_index=db_initial,
                    )
                except WizardResetRequested:
                    draft, step = _apply_wizard_reset(console, shell, repo_root, order)
                    continue
                except PickerCancelled:
                    continue
                if not draft.duckdb_vault_path.endswith(".duckdb"):
                    draft.duckdb_vault_path = db_values[db_initial]
                abs_p = repo_root / draft.duckdb_vault_path
                if not abs_p.is_file():
                    if ensure_duckdb_vault(repo_root, draft.duckdb_vault_path):
                        console.print(f"[green]Creada[/] {draft.duckdb_vault_path}")
                duck = audit_duckdb(repo_root, draft, quick=False)
                shell.note(f"DuckDB: {'OK' if duck.ok else 'revisar'}")
                shell.print_content_panel(
                    format_duckdb_health_rich(duck),
                    title="DuckDB seleccionada",
                )
                try:
                    pick_one_index(
                        "Confirmar DuckDB",
                        ["Continuar con esta bóveda"],
                        initial_index=0,
                    )
                except WizardResetRequested:
                    draft, step = _apply_wizard_reset(console, shell, repo_root, order)
                    continue
                except PickerCancelled:
                    continue
                shell.complete_step(step)
                n = next_step_in(order, step)
                if n:
                    step = n
                continue

            if not private_db_dir_writable(repo_root):
                console.print(
                    "[red]No hay permiso de escritura en la carpeta db/private. "
                    "Ajusta permisos antes de seguir.[/]"
                )
            tok, val = _ask_until(
                session,
                f"Redis [{draft.redis_url}]: ",
                default=draft.redis_url,
            )
            if tok == NAV_BACK:
                p = prev_step_in(order, step)
                if p:
                    step = p
                continue
            if tok == NAV_QUICK_SAVE:
                console.print(f"[green]{save_draft_json(draft)}[/]")
                return 0, shell
            if val:
                draft.redis_url = val
            console.print()
            tok, val = _ask_until(
                session,
                f"DuckDB [{draft.duckdb_vault_path}]: ",
                default=draft.duckdb_vault_path,
            )
            if tok == NAV_BACK:
                continue
            if tok == NAV_QUICK_SAVE:
                console.print(f"[green]{save_draft_json(draft)}[/]")
                return 0, shell
            if val:
                draft.duckdb_vault_path = val
            console.print()
            tok, val = _ask_until(
                session,
                f"DuckDB extra (opcional) [{draft.duckdb_shared_path}]: ",
                default=draft.duckdb_shared_path,
            )
            if tok == NAV_BACK:
                continue
            if tok == NAV_QUICK_SAVE:
                console.print(f"[green]{save_draft_json(draft)}[/]")
                return 0, shell
            draft.duckdb_shared_path = val
            n = next_step_in(order, step)
            if n:
                step = n
            continue

        if step == WizardStep.IDENTITY_SETUP:
            tok, val = _ask_until(
                session,
                f"Tenant [{draft.tenant_id}]: ",
                default=draft.tenant_id,
            )
            if tok == NAV_BACK:
                p = prev_step_in(order, step)
                if p:
                    step = p
                continue
            if tok == NAV_QUICK_SAVE:
                console.print(f"[green]{save_draft_json(draft)}[/]")
                return 0, shell
            if val:
                draft.tenant_id = val
            console.print()
            tok, val = _ask_until(
                session,
                f"PM2 [{draft.gateway_pm2_name}]: ",
                default=draft.gateway_pm2_name,
            )
            if tok == NAV_BACK:
                continue
            if tok == NAV_QUICK_SAVE:
                console.print(f"[green]{save_draft_json(draft)}[/]")
                return 0, shell
            if val:
                draft.gateway_pm2_name = val
            console.print()
            nav, ok = _prompt_default_worker(session, console, draft, repo_root)
            if nav == NAV_BACK:
                continue
            if nav == NAV_QUICK_SAVE:
                console.print(f"[green]{save_draft_json(draft)}[/]")
                return 0, shell
            if not ok:
                continue
            console.print()
            nav, ok = _prompt_gateway_team_optional(session, console, draft, repo_root)
            if nav == NAV_BACK:
                continue
            if nav == NAV_QUICK_SAVE:
                console.print(f"[green]{save_draft_json(draft)}[/]")
                return 0, shell
            if not ok:
                continue
            n = next_step_in(order, step)
            if n:
                step = n
            continue

        if step == WizardStep.ORCHESTRATION:
            if draft.wizard_profile == "express":
                host = "127.0.0.1"
                if is_port_in_use(host, draft.gateway_port):
                    alt = suggest_gateway_port(host, draft.gateway_port)
                    console.print(f"[yellow]Puerto {draft.gateway_port} ocupado → {alt}[/]")
                    draft.gateway_port = alt
                draft.orchestration = "pm2"
                duck_rel = (draft.duckdb_vault_path or "").strip()
                body = (
                    "[bold]Al aplicar se iniciará en PM2:[/]\n"
                    f"  · Gateway [cyan]{draft.gateway_pm2_name}[/] → puerto {draft.gateway_port}\n"
                    f"  · DuckClaw-DB-Writer → Redis → [cyan]{duck_rel}[/]\n\n"
                    "[dim]Elige el worker por defecto (playground / Telegram en consola admin).[/]"
                )
                shell.print_content_panel(body, title="Servicios")
                try:
                    _pick_worker(console, draft, repo_root, title="Worker por defecto")
                except WizardResetRequested:
                    draft, step = _apply_wizard_reset(console, shell, repo_root, order)
                    continue
                except PickerCancelled:
                    p = prev_step_in(order, step)
                    if p:
                        step = p
                    continue
                try:
                    pick_one_index(
                        "Confirmar arranque",
                        ["Iniciar gateway y DB-Writer al aplicar"],
                        initial_index=0,
                    )
                except PickerCancelled:
                    continue
                shell.complete_step(step)
                n = next_step_in(order, step)
                if n:
                    step = n
                continue

            host = "127.0.0.1"
            if is_port_in_use(host, draft.gateway_port):
                alt = suggest_gateway_port(host, draft.gateway_port)
                console.print(f"[yellow]Puerto {draft.gateway_port} ocupado; sugerido {alt}[/]")
                draft.gateway_port = alt
            tok, val = _ask_until(
                session,
                f"Modo pm2|docker [{draft.orchestration}]: ",
                default=draft.orchestration,
            )
            if tok == NAV_BACK:
                p = prev_step_in(order, step)
                if p:
                    step = p
                continue
            if tok == NAV_QUICK_SAVE:
                console.print(f"[green]{save_draft_json(draft)}[/]")
                return 0, shell
            if val in ("docker", "pm2"):
                draft.orchestration = val  # type: ignore[assignment]
            console.print()
            tok, val = _ask_until(
                session,
                f"Puerto [{draft.gateway_port}]: ",
                default=str(draft.gateway_port),
            )
            if tok == NAV_BACK:
                continue
            if tok == NAV_QUICK_SAVE:
                console.print(f"[green]{save_draft_json(draft)}[/]")
                return 0, shell
            try:
                if val:
                    draft.gateway_port = int(val)
            except ValueError:
                console.print("[red]Puerto inválido[/]")
                continue
            tok, val = _ask_until(
                session,
                "¿Instalar Redis local? [y/N]: ",
                default="n",
            )
            if tok == NAV_BACK:
                continue
            if tok == NAV_QUICK_SAVE:
                console.print(f"[green]{save_draft_json(draft)}[/]")
                return 0, shell
            draft.redis_local_managed = val.lower() in ("y", "yes", "s", "sí", "si", "1")
            if draft.orchestration == "docker":
                console.print()
                tok, val = _ask_until(
                    session,
                    "docker-compose.override con Redis? [Y/n]: ",
                    default="y",
                )
                if tok == NAV_BACK:
                    continue
                if tok == NAV_QUICK_SAVE:
                    console.print(f"[green]{save_draft_json(draft)}[/]")
                    return 0, shell
                draft.generate_docker_compose = val.lower() not in ("n", "no", "0")
            n = next_step_in(order, step)
            if n:
                step = n
            continue

        if step == WizardStep.CONNECTIVITY:
            host = "127.0.0.1"
            if is_port_in_use(host, draft.gateway_port):
                alt = suggest_gateway_port(host, draft.gateway_port)
                console.print(
                    f"[yellow]El puerto {draft.gateway_port} está ocupado; "
                    f"usaremos el sugerido {alt} para el servidor web.[/]"
                )
                draft.gateway_port = alt
            while True:
                tok, val = _ask_until(
                    session,
                    f"Tu ID Telegram [@userinfobot] [{draft.wizard_creator_telegram_user_id or ''}]: ",
                    default=draft.wizard_creator_telegram_user_id,
                )
                if tok == NAV_BACK:
                    p = prev_step_in(order, step)
                    if p:
                        step = p
                    break
                if tok == NAV_QUICK_SAVE:
                    console.print(f"[green]{save_draft_json(draft)}[/]")
                    return 0, shell
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
                f"Nombre visible [{draft.wizard_creator_admin_display_name}]: ",
                default=draft.wizard_creator_admin_display_name,
            )
            if tok == NAV_BACK:
                continue
            if tok == NAV_QUICK_SAVE:
                console.print(f"[green]{save_draft_json(draft)}[/]")
                return 0, shell
            draft.wizard_creator_admin_display_name = (val or "").strip()

            console.print()
            tok, val = _ask_until(
                session,
                f"Admins extra (coma) [{draft.wizard_extra_admin_telegram_ids}]: ",
                default=draft.wizard_extra_admin_telegram_ids,
            )
            if tok == NAV_BACK:
                continue
            if tok == NAV_QUICK_SAVE:
                console.print(f"[green]{save_draft_json(draft)}[/]")
                return 0, shell
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

            tok, val = _ask_until(
                session,
                "Token BotFather (vacío = no cambiar): ",
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
                return 0, shell
            if val:
                draft.telegram_bot_token = val
                draft.telegram_bot_token_masked = True

            tok, val = _ask_until(
                session,
                f"Tailscale Funnel → :{draft.gateway_port}? [Y/n]: ",
                default="y",
            )
            if tok == NAV_BACK:
                continue
            if tok == NAV_QUICK_SAVE:
                console.print(f"[green]{save_draft_json(draft)}[/]")
                return 0, shell
            if _want_yes(val):
                if not tailscale_cli_available():
                    console.print(
                        "[yellow]No hay `tailscale` en PATH. Instala la app/CLI o pega la URL HTTPS más abajo.[/]"
                    )
                else:
                    with shell.render_live_working("Tailscale Funnel"):
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
                        console.print(f"[green]Funnel:[/] {url_f}")
                    else:
                        console.print(f"[red]Tailscale Funnel: {err_f}[/]")

            if not (draft.telegram_webhook_public_base_url or "").strip():
                tok, val = _ask_until(
                    session,
                    "Cloudflare Quick Tunnel? [y/N]: ",
                    default="n",
                )
                if tok == NAV_BACK:
                    continue
                if tok == NAV_QUICK_SAVE:
                    console.print(f"[green]{save_draft_json(draft)}[/]")
                    return 0, shell
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
                                return 0, shell
                            use_pm2_tunnel = not _want_no(val_p)
                        else:
                            console.print(
                                "[dim]PM2 no está en PATH; cloudflared en segundo plano.[/]"
                            )
                            use_pm2_tunnel = False
                        with shell.render_live_working("Cloudflare Quick Tunnel"):
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
                            console.print(f"[green]Tunnel:[/] {url_cf} {extra}")
                        else:
                            console.print(f"[red]Quick Tunnel: {err_cf}[/]")

            tok, val = _ask_until(
                session,
                "Webhook secret (opcional): ",
                password=True,
                default="",
            )
            if tok == NAV_BACK:
                continue
            if tok == NAV_QUICK_SAVE:
                console.print(f"[green]{save_draft_json(draft)}[/]")
                return 0, shell
            if val:
                draft.telegram_webhook_secret = val
                draft.telegram_webhook_secret_masked = True

            if not (draft.telegram_webhook_public_base_url or "").strip():
                tok, val = _ask_until(session, "URL HTTPS (opcional): ", default="")
                if tok == NAV_BACK:
                    continue
                if tok == NAV_QUICK_SAVE:
                    console.print(f"[green]{save_draft_json(draft)}[/]")
                    return 0, shell
                if val:
                    draft.telegram_webhook_public_base_url = val

            tok, val = _ask_until(
                session,
                "Tailscale auth key (opcional): ",
                password=True,
                default="",
            )
            if tok == NAV_BACK:
                continue
            if tok == NAV_QUICK_SAVE:
                console.print(f"[green]{save_draft_json(draft)}[/]")
                return 0, shell
            if val:
                draft.duckclaw_tailscale_auth_key = val
            tok, val = _ask_until(session, "MCP Telegram [Y/n]: ", default="y")
            if tok == NAV_BACK:
                continue
            if tok == NAV_QUICK_SAVE:
                console.print(f"[green]{save_draft_json(draft)}[/]")
                return 0, shell
            draft.enable_telegram_mcp = val.lower() not in ("n", "no", "0")
            n = next_step_in(order, step)
            if n:
                step = n
            continue

        if step == WizardStep.REVIEW_DEPLOY:
            duck = audit_duckdb(repo_root, draft, quick=False)
            report = audit_stack(repo_root, draft)
            health = format_stack_health_rich(
                report,
                duck_block=format_duckdb_health_rich(duck),
            )
            if draft.wizard_profile == "express":
                summary = (
                    health
                    + "\n\n"
                    f"[dim]PM2[/] {draft.gateway_pm2_name} · :{draft.gateway_port} · "
                    f"worker {draft.default_worker_id}"
                )
                shell.print_content_panel(summary, title="Revisión")
                try:
                    choice = run_list_picker(
                        "Revisión final",
                        [
                            "Aplicar configuración y arrancar servicios",
                            "Cancelar sin cambios",
                        ],
                        values=["apply", "cancel"],
                        initial_index=0,
                    )
                except WizardResetRequested:
                    draft, step = _apply_wizard_reset(console, shell, repo_root, order)
                    continue
                except PickerCancelled:
                    p = prev_step_in(order, step)
                    if p:
                        step = p
                    continue
                if choice == "cancel":
                    console.print("[yellow]Cancelado.[/]")
                    return 0, shell
                shell.note("Aplicando configuración")
                return _CONFIRM_EXIT, shell

            masked_tok = "•••• (configurado)" if draft.telegram_bot_token else "(sin cambiar aquí / ya en .env)"
            extra_path = draft.duckdb_shared_path.strip() or "(ninguna)"
            orch_sp = "Docker" if draft.orchestration == "docker" else "PM2 en esta máquina"
            funnel_sí = "sí" if draft.tailscale_funnel_bg_via_wizard else "no"
            cf_pm2 = draft.cloudflared_pm2_process_name.strip() or "(ninguno)"
            mcp_sí = "sí" if draft.enable_telegram_mcp else "no"
            url_pub = (draft.telegram_webhook_public_base_url or "").strip() or "(admin / después)"
            team_line = (draft.gateway_team_templates or "").strip() or "(sin límite; todas las plantillas)"
            prof = "rápida" if draft.wizard_profile == "express" else "manual"
            owner = draft.wizard_creator_telegram_user_id or "(consola admin)"
            summary = (
                health
                + "\n\n"
                f"[dim]Perfil[/] {prof} · [dim]worker[/] {draft.default_worker_id} · "
                f"[dim]equipo[/] {team_line}\n"
                f"[dim]Redis[/] {draft.redis_url}\n"
                f"[dim]DuckDB[/] {draft.duckdb_vault_path}"
                + (f" · extra {extra_path}" if extra_path != "(ninguna)" else "")
                + "\n"
                f"[dim]PM2[/] {draft.gateway_pm2_name} · {orch_sp} :{draft.gateway_port}\n"
                f"[dim]Telegram[/] {owner} · token {masked_tok} · HTTPS {url_pub}\n"
                f"[dim]Funnel[/] {funnel_sí} · CF {cf_pm2} · MCP {mcp_sí}\n\n"
                "[dim]Escribe CONFIRMAR para aplicar · Esc atrás[/]"
            )
            shell.print_content_panel(summary, title="Revisión")
            tok, val = _ask_until(session, "CONFIRMAR: ", default="")
            if tok == NAV_BACK:
                p = prev_step_in(order, step)
                if p:
                    step = p
                continue
            if tok == NAV_QUICK_SAVE:
                console.print(f"[green]{save_draft_json(draft)}[/]")
                return 0, shell
            if val.strip().upper() != "CONFIRMAR":
                console.print("[yellow]Cancelado: no se ha modificado la configuración en el proyecto.[/]")
                return 0, shell
            shell.note("Confirmado — aplicando configuración")
            return _CONFIRM_EXIT, shell

    return 0, shell
