"""TUI por pasos (prompt_toolkit + Rich)."""

from __future__ import annotations

import platform
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
    TAILSCALE_FUNNEL_KB_URL,
    WizardStep,
    step_header,
    tailscale_funnel_wizard_panel_content,
)
from duckops.sovereign.tailscale_funnel import (
    provision_tailscale_funnel_bg,
    tailscale_cli_available,
)
from duckops.sovereign.draft import SovereignDraft
from duckops.sovereign.keys import (
    NAV_AUTOFILL,
    NAV_BACK,
    NAV_QUICK_SAVE,
    NAV_SERVICE_TEST,
    build_key_bindings,
)
from duckops.sovereign.materialize import load_draft_json, save_draft_json
from duckops.sovereign.state_machine import STEP_ORDER, next_step, prev_step
from duckops.sovereign.validate import (
    is_port_in_use,
    private_db_dir_writable,
    redis_ping_url,
    suggest_gateway_port,
)

_CONFIRM_EXIT = 2


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


def _make_session(on_test: Callable[[], None] | None) -> PromptSession:
    return PromptSession(key_bindings=build_key_bindings(on_service_test=on_test))


def _ask(
    session: PromptSession,
    message: str,
    *,
    default: str = "",
    password: bool = False,
) -> tuple[str | None, str]:
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


def run_wizard_loop(repo_root: Path, console: Console, draft: SovereignDraft) -> int:
    total = len(STEP_ORDER)
    step = STEP_ORDER[0]
    if load_draft_json():
        console.print(
            "[dim]Hay un borrador en ~/.config/duckclaw/wizard_draft.json "
            "(usa Ctrl+S para sobrescribirlo).[/]"
        )

    def redis_test() -> None:
        ok, msg = redis_ping_url(draft.redis_url)
        console.print(
            Panel(
                f"Redis: {'OK ' + msg if ok else msg}",
                title="Ctrl+R — Canal de comunicación",
                border_style="cyan",
            )
        )

    session = _make_session(redis_test)

    while True:
        idx = STEP_ORDER.index(step) + 1
        hdr = step_header(step, index_1_based=idx, total=total)
        console.print(Panel(hdr + "\n\n" + _footer(), border_style="green"))

        if step == WizardStep.SOVEREIGNTY_AUDIT:
            draft.detected_os = platform.system()
            draft.is_apple_silicon = platform.machine() == "arm64" and draft.detected_os == "Darwin"
            console.print(
                f"Sistema: [bold]{draft.detected_os}[/] | "
                f"machine={platform.machine()} | "
                f"Apple Silicon: {draft.is_apple_silicon}"
            )
            tok, _ = _ask_until(session, "Enter continuar → siguiente paso (Esc atrás) ", default="")
            if tok == NAV_BACK:
                console.print("[yellow]Ya estás en el primer paso.[/]")
                continue
            if tok == NAV_QUICK_SAVE:
                p = save_draft_json(draft)
                console.print(f"[green]Borrador en {p}[/]. Saliendo.")
                return 0
            n = next_step(step)
            if n:
                step = n
            continue

        if step == WizardStep.CORE_SERVICES:
            if not private_db_dir_writable(repo_root):
                console.print(
                    "[red]Sin permiso de escritura en db/private. Corrige antes de continuar.[/]"
                )
            tok, val = _ask_until(
                session,
                f"Redis URL [Canal de comunicación] [{draft.redis_url}]: ",
                default=draft.redis_url,
            )
            if tok == NAV_BACK:
                p = prev_step(step)
                if p:
                    step = p
                continue
            if tok == NAV_QUICK_SAVE:
                console.print(f"[green]{save_draft_json(draft)}[/]")
                return 0
            if val:
                draft.redis_url = val
            tok, val = _ask_until(
                session,
                f"DuckDB vault path [Bóveda] [{draft.duckdb_vault_path}]: ",
                default=draft.duckdb_vault_path,
            )
            if tok == NAV_BACK:
                continue
            if tok == NAV_QUICK_SAVE:
                console.print(f"[green]{save_draft_json(draft)}[/]")
                return 0
            if val:
                draft.duckdb_vault_path = val
            tok, val = _ask_until(
                session,
                (
                    "DuckDB segunda / compartida (opcional; Enter vacío = omitir) "
                    f"[{draft.duckdb_shared_path}]: "
                ),
                default=draft.duckdb_shared_path,
            )
            if tok == NAV_BACK:
                continue
            if tok == NAV_QUICK_SAVE:
                console.print(f"[green]{save_draft_json(draft)}[/]")
                return 0
            draft.duckdb_shared_path = val
            n = next_step(step)
            if n:
                step = n
            continue

        if step == WizardStep.IDENTITY_SETUP:
            tok, val = _ask_until(
                session,
                f"Tenant / Manager [DUCKCLAW_GATEWAY_TENANT_ID] [{draft.tenant_id}]: ",
                default=draft.tenant_id,
            )
            if tok == NAV_BACK:
                p = prev_step(step)
                if p:
                    step = p
                continue
            if tok == NAV_QUICK_SAVE:
                console.print(f"[green]{save_draft_json(draft)}[/]")
                return 0
            if val:
                draft.tenant_id = val
            tok, val = _ask_until(
                session,
                f"Nombre PM2 del Gateway [{draft.gateway_pm2_name}]: ",
                default=draft.gateway_pm2_name,
            )
            if tok == NAV_BACK:
                continue
            if tok == NAV_QUICK_SAVE:
                console.print(f"[green]{save_draft_json(draft)}[/]")
                return 0
            if val:
                draft.gateway_pm2_name = val
            console.print(
                "Worker por defecto (carpeta en forge/templates): "
                "BI-Analyst | Job-Hunter | LeilaAssistant | SIATA-Analyst | finanz | TheMindCrupier"
            )
            tok, val = _ask_until(
                session,
                f"Default worker id [{draft.default_worker_id}]: ",
                default=draft.default_worker_id,
            )
            if tok == NAV_BACK:
                continue
            if tok == NAV_QUICK_SAVE:
                console.print(f"[green]{save_draft_json(draft)}[/]")
                return 0
            if val:
                draft.default_worker_id = val
            n = next_step(step)
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
                "Orquestación [pm2 / docker] (default pm2): ",
                default=draft.orchestration,
            )
            if tok == NAV_BACK:
                p = prev_step(step)
                if p:
                    step = p
                continue
            if tok == NAV_QUICK_SAVE:
                console.print(f"[green]{save_draft_json(draft)}[/]")
                return 0
            if val in ("docker", "pm2"):
                draft.orchestration = val  # type: ignore[assignment]
            tok, val = _ask_until(
                session,
                f"Puerto gateway [{draft.gateway_port}]: ",
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
                f"[dim]Siguiente paso: [cyan]tailscale funnel --bg --yes {draft.gateway_port}[/] "
                f"(o el asistente lo lanzará). Doc: {TAILSCALE_FUNNEL_KB_URL}[/]"
            )
            tok, val = _ask_until(
                session,
                "¿Intentar Redis local gestionado (brew / hint Linux)? [y/N]: ",
                default="n",
            )
            if tok == NAV_BACK:
                continue
            if tok == NAV_QUICK_SAVE:
                console.print(f"[green]{save_draft_json(draft)}[/]")
                return 0
            draft.redis_local_managed = val.lower() in ("y", "yes", "s", "sí", "si", "1")
            if draft.orchestration == "docker":
                tok, val = _ask_until(
                    session,
                    "¿Generar docker-compose.override.yml con Redis? [Y/n]: ",
                    default="y",
                )
                if tok == NAV_BACK:
                    continue
                if tok == NAV_QUICK_SAVE:
                    console.print(f"[green]{save_draft_json(draft)}[/]")
                    return 0
                draft.generate_docker_compose = val.lower() not in ("n", "no", "0")
            n = next_step(step)
            if n:
                step = n
            continue

        if step == WizardStep.CONNECTIVITY:
            console.print(
                Panel(
                    "[bold]Telegram Guard[/]: solo los user_id que estén en la BD del gateway "
                    "(tabla [cyan]main.authorized_users[/]) pueden usar el bot.\n\n"
                    "Te registramos a ti como [green]admin[/] con el ID que indiques y un "
                    "[bold]nombre[/] para mostrar (como en `/team --add … nombre`). "
                    "Tu ID numérico: escríbele a [bold]@userinfobot[/] en Telegram o revisa "
                    "los datos raw de un mensaje tuyo.\n\n"
                    "Luego podrás añadir más admins (IDs separados por coma).",
                    title="Quién puede usar el bot",
                    border_style="cyan",
                )
            )
            while True:
                tok, val = _ask_until(
                    session,
                    "Tu [bold]user_id de Telegram[/] (solo dígitos; quedarás como admin) "
                    f"[{draft.wizard_creator_telegram_user_id or 'obligatorio'}]: ",
                    default=draft.wizard_creator_telegram_user_id,
                )
                if tok == NAV_BACK:
                    p = prev_step(step)
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

            tok, val = _ask_until(
                session,
                "Tu [bold]nombre[/] como admin (para listados /team; ej. Juan; Enter = último valor o vacío) "
                f"[{draft.wizard_creator_admin_display_name or 'opcional'}]: ",
                default=draft.wizard_creator_admin_display_name,
            )
            if tok == NAV_BACK:
                continue
            if tok == NAV_QUICK_SAVE:
                console.print(f"[green]{save_draft_json(draft)}[/]")
                return 0
            draft.wizard_creator_admin_display_name = (val or "").strip()

            tok, val = _ask_until(
                session,
                "¿Más usuarios [bold]admin[/]? (IDs de Telegram separados por coma; vacío = ninguno) "
                f"[{draft.wizard_extra_admin_telegram_ids}]: ",
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

            tok, val = _ask_until(
                session,
                "TELEGRAM_BOT_TOKEN (password; vacío = no actualizar desde wizard): ",
                password=True,
                default="",
            )
            if tok == NAV_BACK:
                p = prev_step(step)
                if p:
                    step = p
                continue
            if tok == NAV_QUICK_SAVE:
                console.print(f"[green]{save_draft_json(draft)}[/]")
                return 0
            if val:
                draft.telegram_bot_token = val
                draft.telegram_bot_token_masked = True

            console.print(
                Panel(
                    tailscale_funnel_wizard_panel_content(draft.gateway_port),
                    title="Tailscale Funnel (webhook HTTPS)",
                    border_style="cyan",
                )
            )
            tok, val = _ask_until(
                session,
                "¿Activar Funnel ahora con [bold]tailscale funnel --bg --yes[/] "
                f"hacia el puerto [bold]{draft.gateway_port}[/]? (requiere Tailscale logueado y ACL funnel) [Y/n]: ",
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
                        url_f, err_f = provision_tailscale_funnel_bg(draft.gateway_port)
                    if url_f:
                        draft.telegram_webhook_public_base_url = url_f
                        draft.tailscale_funnel_bg_via_wizard = True
                        draft.cloudflared_pm2_process_name = ""
                        console.print(
                            Panel(
                                f"[green]Base HTTPS (Funnel)[/]\n{url_f}\n\n"
                                f"[green]Ruta webhook Telegram[/]\n{url_f}/api/v1/telegram/webhook\n\n"
                                "[dim]Estado: [bold]tailscale funnel status[/]  ·  Quitar: [bold]tailscale funnel reset[/][/]",
                                title="Tailscale Funnel",
                                border_style="green",
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
                                    title="Cloudflare Quick Tunnel",
                                    border_style="green",
                                )
                            )
                        else:
                            console.print(f"[red]Quick Tunnel: {err_cf}[/]")

            tok, val = _ask_until(
                session,
                "TELEGRAM_WEBHOOK_SECRET (opcional, password; debe coincidir con setWebhook): ",
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
                    "URL HTTPS pública hacia este gateway, sin barra final (si no usaste túnel; vacío = plantilla al final): ",
                    default="",
                )
                if tok == NAV_BACK:
                    continue
                if tok == NAV_QUICK_SAVE:
                    console.print(f"[green]{save_draft_json(draft)}[/]")
                    return 0
                if val:
                    draft.telegram_webhook_public_base_url = val

            tok, val = _ask_until(
                session,
                "DUCKCLAW_TAILSCALE_AUTH_KEY (opcional): ",
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
            tok, val = _ask_until(
                session,
                "¿Habilitar MCP Telegram? [Y/n]: ",
                default="y",
            )
            if tok == NAV_BACK:
                continue
            if tok == NAV_QUICK_SAVE:
                console.print(f"[green]{save_draft_json(draft)}[/]")
                return 0
            draft.enable_telegram_mcp = val.lower() not in ("n", "no", "0")
            n = next_step(step)
            if n:
                step = n
            continue

        if step == WizardStep.REVIEW_DEPLOY:
            masked_tok = "•••• (configurado)" if draft.telegram_bot_token else "(vacío / .env existente)"
            summary = (
                f"Redis: {draft.redis_url}\n"
                f"DuckDB vault: {draft.duckdb_vault_path}\n"
                f"Shared: {draft.duckdb_shared_path or '(ninguna)'}\n"
                f"Tenant: {draft.tenant_id}\n"
                f"PM2 name: {draft.gateway_pm2_name}\n"
                f"Worker: {draft.default_worker_id}\n"
                f"Telegram Guard — admin (tú): {draft.wizard_creator_telegram_user_id or '(falta ID)'} "
                f"({draft.wizard_creator_admin_display_name or 'sin nombre'})\n"
                f"Telegram Guard — admins extra: {draft.wizard_extra_admin_telegram_ids or '(ninguno)'}\n"
                f"Telegram token: {masked_tok}\n"
                f"Webhook HTTPS base: {draft.telegram_webhook_public_base_url or '(plantilla con marcador al final)'}\n"
                f"Tailscale Funnel (--bg vía wizard): {'sí' if draft.tailscale_funnel_bg_via_wizard else 'no'}\n"
                f"Cloudflare PM2 (quick tunnel): {draft.cloudflared_pm2_process_name or '(ninguno)'}\n"
                f"MCP Telegram: {draft.enable_telegram_mcp}\n"
                f"Orquestación: {draft.orchestration} | Puerto: {draft.gateway_port}\n"
            )
            console.print(Panel(summary, title="Review — confirmar escritura", border_style="blue"))
            tok, val = _ask_until(
                session,
                "Escribe CONFIRMAR para escribir .env y artefactos (otro texto cancela): ",
                default="",
            )
            if tok == NAV_BACK:
                p = prev_step(step)
                if p:
                    step = p
                continue
            if tok == NAV_QUICK_SAVE:
                console.print(f"[green]{save_draft_json(draft)}[/]")
                return 0
            if val.strip().upper() != "CONFIRMAR":
                console.print("[yellow]Cancelado — no se escribió nada en el repo.[/]")
                return 0
            return _CONFIRM_EXIT

    return 0
