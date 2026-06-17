"""Elección post-``duckops up``: chat TUI o consola web (bucle persistente)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable, Literal

PrintFn = Callable[[str], None]

LaunchMode = Literal["tui", "web", "exit"]


def _default_print(msg: str) -> None:
    print(msg, flush=True)


def prompt_launch_mode(
    *,
    skip_admin: bool,
    print_fn: PrintFn = _default_print,
) -> LaunchMode:
    """Pregunta cómo continuar; el stack PM2 no se toca entre elecciones."""
    print_fn("")
    print_fn("¿Cómo quieres continuar? (PM2 y gateway siguen activos)")
    if skip_admin:
        print_fn("  [1] Chat TUI con agentes (terminal)")
        print_fn("  [2] Salir de duckops up")
        choices = {"1": "tui", "2": "exit", "t": "tui", "q": "exit"}
        default = "1"
    else:
        print_fn("  [1] Chat TUI con agentes (terminal; /web abre la consola)")
        print_fn("  [2] Consola web — Playground en el navegador")
        print_fn("  [3] Salir de duckops up")
        choices = {"1": "tui", "2": "web", "3": "exit", "t": "tui", "w": "web", "q": "exit"}
        default = "2"

    if not sys.stdin.isatty():
        print_fn("Entrada no interactiva → saliendo (usa --ui tui|web).")
        return "exit"

    try:
        raw = input(f"Elige [{default}]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print_fn("")
        return "exit"

    if not raw:
        return choices[default]  # type: ignore[return-value]
    return choices.get(raw, choices[default])  # type: ignore[return-value]


def resolve_launch_mode(
    *,
    ui: str | None,
    no_prompt: bool,
    skip_admin: bool,
    print_fn: PrintFn = _default_print,
) -> LaunchMode:
    if ui is not None:
        normalized = ui.strip().lower()
        if normalized in ("tui", "chat"):
            return "tui"
        if normalized in ("web", "ui", "browser"):
            return "web" if not skip_admin else "exit"
        if normalized in ("none", "exit", "skip"):
            return "exit"
        print_fn(f"Valor --ui desconocido: {ui!r} (usa tui, web o none).")
        return "exit"
    if no_prompt:
        return "exit"
    return prompt_launch_mode(skip_admin=skip_admin, print_fn=print_fn)


def _prepare_admin_for_tui(repo_root: Path, print_fn: PrintFn) -> None:
    """Consola web en segundo plano para que TUI + /web compartan el mismo stack."""
    from duckops.admin_dev_server import admin_login_url, ensure_admin_web_ready

    print_fn("Preparando consola web en segundo plano (mismo gateway)…")
    if ensure_admin_web_ready(repo_root, print_fn):
        print_fn(f"  Web lista: {admin_login_url(repo_root)}")
        print_fn("  En el chat TUI: /web para abrir el navegador sin salir.")
    else:
        print_fn(
            "  Web no lista aún; el TUI sigue vía gateway. "
            "Manual: cd apps/duckclaw-admin && pnpm dev"
        )


def run_post_up_session(
    repo_root: Path,
    mode: LaunchMode,
    *,
    skip_admin: bool,
    no_browser: bool,
    print_fn: PrintFn = _default_print,
) -> int:
    """Una vuelta del menú (TUI o web); vuelve al menú salvo error fatal en TUI."""
    if mode == "exit":
        print_fn("Stack listo. PM2 y Redis siguen en segundo plano.")
        return 0

    if mode == "tui":
        if not skip_admin:
            _prepare_admin_for_tui(repo_root, print_fn)
        from duckops.sovereign.runner import run_sovereign_chat

        print_fn("Entrando al chat TUI (/salir para volver al menú)…")
        code = int(run_sovereign_chat(repo_root))
        if code != 0:
            return code
        print_fn("\nChat TUI cerrado. Puedes abrir la web o volver al chat.")
        return 0

    if skip_admin:
        print_fn("Consola web omitida (--skip-admin).")
        return 0

    from duckops.admin_dev_server import (
        admin_login_url,
        ensure_admin_web_ready,
        open_admin_browser,
    )

    if not ensure_admin_web_ready(repo_root, print_fn):
        print_fn("No se pudo arrancar admin. Manual: cd apps/duckclaw-admin && pnpm dev")
        return 1

    url = admin_login_url(repo_root)
    print_fn(f"Consola web: {url}")
    if not no_browser:
        open_admin_browser(repo_root, print_fn=print_fn)

    print_fn("")
    print_fn("Pulsa Enter para volver al menú (PM2 y admin siguen activos).")
    try:
        input()
    except (EOFError, KeyboardInterrupt):
        print_fn("")
    return 0


def run_post_up_loop(
    repo_root: Path,
    *,
    skip_admin: bool,
    no_browser: bool,
    ui: str | None,
    no_prompt: bool,
    print_fn: PrintFn = _default_print,
) -> int:
    """
    Bucle interactivo: TUI ↔ web sin bajar el stack.
    Con ``--no-prompt`` o ``--ui`` ejecuta una sola elección y sale.
    """
    if no_prompt or ui is not None:
        mode = resolve_launch_mode(
            ui=ui,
            no_prompt=no_prompt,
            skip_admin=skip_admin,
            print_fn=print_fn,
        )
        return run_post_up_session(
            repo_root,
            mode,
            skip_admin=skip_admin,
            no_browser=no_browser,
            print_fn=print_fn,
        )

    while True:
        mode = prompt_launch_mode(skip_admin=skip_admin, print_fn=print_fn)
        if mode == "exit":
            print_fn("Stack listo. PM2 y Redis siguen en segundo plano.")
            return 0
        code = run_post_up_session(
            repo_root,
            mode,
            skip_admin=skip_admin,
            no_browser=no_browser,
            print_fn=print_fn,
        )
        if code != 0:
            return code
