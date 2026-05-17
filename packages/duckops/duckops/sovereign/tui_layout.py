"""Layout del chrome TUI (cabecera dashboard + mascota + ayuda)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from rich.columns import Columns
from rich.panel import Panel
from duckops import __version__ as DUCKOPS_VERSION
from duckops.sovereign.domain_labels import STEP_UI, WizardStep
from duckops.sovereign.duck_mascot import DuckMascot
from duckops.sovereign.wizard_theme import (
    DUCK_ACCENT,
    DUCK_ACCENT_ALT,
    HEADER_BORDER,
    PANEL_BORDER,
    SIDEBAR_STYLE,
    panel_title,
)

from duckops.sovereign.duckdb_health import audit_duckdb, duckdb_chrome_summary

if TYPE_CHECKING:
    from duckops.sovereign.draft import SovereignDraft
    from duckops.sovereign.tui_shell import StatusLog, StepInfo

_TIPS = (
    "Ctrl+S guarda borrador en ~/.config/duckclaw/",
    "Ctrl+R prueba Redis en pasos de datos",
    "Esc / Ctrl+Z vuelve al paso anterior",
    "Telegram y Tailscale: consola admin (pnpm dev)",
    "Playground: uv run duckops init --chat",
)


@dataclass(frozen=True)
class ChromeLayout:
    """Datos para renderizar el chrome (no el panel MAIN ni el prompt FOOTER)."""

    draft: SovereignDraft
    repo_root: Path
    step_info: StepInfo
    status_log: StatusLog | None = None
    recent: list[str] | None = None
    mascot: DuckMascot | None = None
    #: Tenant solo en ``duckops init --chat``; el wizard de configuración no lo muestra.
    show_tenant: bool = False
    duckdb_summary: str = ""


def _friendly_os() -> str:
    import platform

    s = platform.system()
    if s == "Darwin":
        return "macOS"
    if s == "Linux":
        return "Linux"
    if s == "Windows":
        return "Windows"
    return s or "desconocido"


def build_chrome(layout: ChromeLayout) -> Panel:
    """Chrome del wizard (mascota izquierda) o chat (mascota + tenant)."""
    if layout.show_tenant:
        return _build_chat_chrome(layout)
    return _build_wizard_chrome(layout)


def _build_wizard_chrome(layout: ChromeLayout) -> Panel:
    """Estilo Claude Code: pato a la izquierda, estado a la derecha."""
    draft = layout.draft
    step_info = layout.step_info
    profile = (
        "Rápida"
        if getattr(draft, "wizard_profile", "express") == "express"
        else "Manual"
    )
    port = getattr(draft, "gateway_port", 8282)
    worker = (draft.default_worker_id or "—").strip()

    info_lines = [
        f"[bold {DUCK_ACCENT}]DuckClaw[/] [dim]v{DUCKOPS_VERSION}[/]",
        f"[dim]{_friendly_os()}[/] · perfil {profile} · :[cyan]{port}[/]",
        f"[dim]Worker[/] [cyan]{worker}[/]",
    ]
    duck_summary = layout.duckdb_summary
    if not duck_summary:
        try:
            duck_summary = duckdb_chrome_summary(
                audit_duckdb(layout.repo_root, layout.draft, quick=True)
            )
        except Exception:
            duck_summary = ""
    if duck_summary:
        info_lines.append(duck_summary)
    if step_info.step is not None and step_info.total:
        copy = STEP_UI[step_info.step]
        info_lines.append(
            f"Paso [bold]{step_info.index_1_based}/{step_info.total}[/] · "
            f"[{DUCK_ACCENT_ALT}]{copy.title_sovereign}[/]"
        )
    elif step_info.profile_label:
        info_lines.append(f"[dim]{step_info.profile_label}[/]")

    status_block = (layout.status_log.render() if layout.status_log else "").strip()
    if status_block:
        info_lines.extend(["", status_block])

    tip_idx = (step_info.index_1_based or 1) % len(_TIPS)
    info_lines.append(f"\n[dim]{_TIPS[tip_idx]}[/]")

    duck = layout.mascot or DuckMascot()
    mascot_text = duck.render_rich(pad_x=duck.x, pad_y=duck.y)
    mascot_panel = Panel(
        mascot_text,
        border_style=DUCK_ACCENT,
        padding=(0, 1),
        width=22,
    )
    info_panel = Panel(
        "\n".join(info_lines),
        border_style=HEADER_BORDER,
        padding=(0, 1),
    )
    body = Columns([mascot_panel, info_panel], expand=True, equal=False)
    return Panel(
        body,
        border_style=HEADER_BORDER,
        padding=(0, 0),
    )


def _build_chat_chrome(layout: ChromeLayout) -> Panel:
    """Cabecera compacta del modo chat (tenant visible)."""
    draft = layout.draft
    step_info = layout.step_info
    tenant = (draft.tenant_id or "default").strip()
    worker = (draft.default_worker_id or "—").strip()

    info_lines = [
        f"[bold {DUCK_ACCENT}]DuckClaw Chat[/] [dim]v{DUCKOPS_VERSION}[/]",
        f"[dim]tenant[/] [cyan]{tenant}[/] · worker [cyan]{worker}[/]",
    ]
    if step_info.profile_label:
        info_lines.append(f"[dim]{step_info.profile_label}[/]")

    duck = layout.mascot or DuckMascot()
    mascot_text = duck.render_rich(pad_x=duck.x, pad_y=duck.y)
    mascot_panel = Panel(mascot_text, border_style=DUCK_ACCENT, padding=(0, 1), width=18)
    info_panel = Panel("\n".join(info_lines), border_style=HEADER_BORDER, padding=(0, 1))
    return Panel(
        Columns([mascot_panel, info_panel], expand=True),
        border_style=HEADER_BORDER,
        padding=(0, 0),
    )


def build_main_panel(body: str, *, title: str = "") -> Panel:
    """Panel MAIN bajo el chrome."""
    return Panel(
        body,
        title=panel_title(title) if title else "",
        title_align="left",
        border_style=PANEL_BORDER,
        padding=(0, 1),
    )
