"""Shell TUI estilo Claude Code para el Sovereign Wizard."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from duckops.sovereign.domain_labels import STEP_UI, WizardStep
from duckops.sovereign.duck_mascot import DuckMascot, MascotState
from duckops.sovereign.tui_layout import ChromeLayout, build_chrome, build_main_panel
from duckops.sovereign.wizard_theme import (
    DUCK_ACCENT,
    PANEL_BORDER,
    STATUS_ACTIVE,
    STATUS_DONE,
    STATUS_PENDING,
    panel_title,
)

if TYPE_CHECKING:
    from duckops.sovereign.draft import SovereignDraft

# Compat: tests antiguos buscaban «claw» en arte estático.
MASCOT_ART = "mallard claw"


class StepStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    DONE = "done"


@dataclass
class StepInfo:
    """Contexto del paso actual para la cabecera."""

    step: WizardStep | None = None
    index_1_based: int = 0
    total: int = 0
    profile_label: str = ""


@dataclass
class StatusLog:
    """Flujo de estado append-only (● completado / en curso / pendiente)."""

    _lines: list[tuple[str, StepStatus, str]] = field(default_factory=list)

    def set_step(self, label: str, status: StepStatus, *, detail: str = "") -> None:
        for i, (lbl, _, _) in enumerate(self._lines):
            if lbl == label:
                self._lines[i] = (label, status, detail)
                return
        self._lines.append((label, status, detail))

    def complete(self, label: str, *, detail: str = "") -> None:
        self.set_step(label, StepStatus.DONE, detail=detail)

    def active(self, label: str, *, detail: str = "") -> None:
        self.set_step(label, StepStatus.ACTIVE, detail=detail)

    def pending(self, label: str, *, detail: str = "") -> None:
        self.set_step(label, StepStatus.PENDING, detail=detail)

    def render(self) -> str:
        parts: list[str] = []
        for label, status, detail in self._lines:
            if status == StepStatus.DONE:
                bullet = f"[{STATUS_DONE}]●[/]"
            elif status == StepStatus.ACTIVE:
                bullet = f"[{STATUS_ACTIVE}]●[/]"
            else:
                bullet = f"[{STATUS_PENDING}]○[/]"
            line = f"  {bullet} {label}"
            if detail:
                line += f" [dim]— {detail}[/]"
            parts.append(line)
        return "\n".join(parts) if parts else "[dim]  (iniciando…)[/]"


def _step_label(step: WizardStep) -> str:
    return STEP_UI[step].title_sovereign


def render_header(
    draft: SovereignDraft,
    repo_root: Path,
    step_info: StepInfo,
    *,
    status_log: StatusLog | None = None,
    recent: list[str] | None = None,
    mascot: DuckMascot | None = None,
    show_tenant: bool = False,
    duckdb_summary: str = "",
) -> Panel:
    """Compat: delega en ``build_chrome`` (layout Chrome)."""
    return build_chrome(
        ChromeLayout(
            draft=draft,
            repo_root=repo_root,
            step_info=step_info,
            status_log=status_log,
            recent=recent,
            mascot=mascot,
            show_tenant=show_tenant,
            duckdb_summary=duckdb_summary,
        )
    )


class TuiShell:
    """Orquesta cabecera + log de estado entre pasos del wizard."""

    def __init__(
        self,
        console: Console,
        draft: SovereignDraft,
        repo_root: Path,
    ) -> None:
        self.console = console
        self.draft = draft
        self.repo_root = repo_root
        self.status = StatusLog()
        self._recent: list[str] = []
        self._order: list[WizardStep] = []
        self._step_info = StepInfo(profile_label="")
        self.mascot = DuckMascot(state=MascotState.IDLE)
        self.show_tenant_in_chrome = False

    def note(self, message: str) -> None:
        self._recent.append(message)
        if len(self._recent) > 12:
            self._recent = self._recent[-12:]

    def init_steps(self, order: list[WizardStep]) -> None:
        self._order = list(order)
        for step in order:
            self.status.pending(_step_label(step))

    def _header_panel(self, step_info: StepInfo | None = None) -> Panel:
        info = step_info or self._step_info
        return render_header(
            self.draft,
            self.repo_root,
            info,
            status_log=self.status,
            recent=self._recent,
            mascot=self.mascot,
            show_tenant=self.show_tenant_in_chrome,
        )

    def refresh_header(self, step_info: StepInfo | None = None) -> None:
        info = step_info or self._step_info
        if self.mascot.state != MascotState.WORKING:
            self.mascot.tick()
        self.console.print()
        self.console.print(self._header_panel(info))
        self.console.print()

    @contextmanager
    def render_live_working(self, task_name: str) -> Generator[Any, None, None]:
        """
        Cabecera animada in-place (Rich Live) mientras corre una tarea larga.
        transient=True evita ensuciar el scroll del historial.
        """
        self.note(task_name)
        self.mascot.set_state(MascotState.WORKING)
        info = self._step_info
        bounds_x, bounds_y = 5, 0

        def get_renderable() -> Panel:
            self.mascot.update_logic(bounds_x, bounds_y)
            return self._header_panel(info)

        self.console.print()
        with Live(
            get_renderable(),
            console=self.console,
            refresh_per_second=10,
            transient=True,
        ) as live:
            try:
                yield live
            finally:
                self.mascot.set_state(MascotState.IDLE)
                self.mascot.x = self.mascot.target_x = 0
                self.mascot.y = self.mascot.target_y = 0
                self.refresh_header(info)

    def begin_step(self, step: WizardStep, *, index_1_based: int, total: int) -> None:
        self.mascot.set_state(MascotState.WALKING)
        self._step_info = StepInfo(
            step=step,
            index_1_based=index_1_based,
            total=total,
        )
        label = _step_label(step)
        for s in self._order:
            sl = _step_label(s)
            if s == step:
                self.status.active(sl)
            elif self._order.index(s) < self._order.index(step):
                self.status.complete(sl)
        self.note(f"Paso {index_1_based}: {label}")
        self.refresh_header(self._step_info)

    def complete_step(self, step: WizardStep) -> None:
        self.status.complete(_step_label(step))
        self.mascot.set_state(MascotState.IDLE)

    def set_working(self) -> None:
        """Marca working sin Live (preferir render_live_working)."""
        self.mascot.set_state(MascotState.WORKING)

    def show_welcome(self) -> None:
        self.mascot.set_state(MascotState.IDLE)
        self._step_info = StepInfo(profile_label="Introducción")
        self.note("Bienvenida al asistente")
        self.refresh_header(self._step_info)

    def show_profile_choice(self) -> None:
        self._step_info = StepInfo(profile_label="Elige rápida o manual")
        self.refresh_header(self._step_info)

    def print_content_panel(self, body: str, *, title: str = "") -> None:
        self.console.print(build_main_panel(body, title=title))
        self.console.print()

    @staticmethod
    def print_deploy_next_steps(console: Console, draft: SovereignDraft) -> None:
        """Cuadro final tras materializar."""
        from duckclaw.gateway_port import DEFAULT_GATEWAY_PORT

        port = int(getattr(draft, "gateway_port", DEFAULT_GATEWAY_PORT) or DEFAULT_GATEWAY_PORT)
        pm2 = (getattr(draft, "gateway_pm2_name", "") or "DuckClaw-Gateway").strip()
        lines = [
            f"[bold {DUCK_ACCENT}]Stack listo[/]",
            f"  Consola admin: cd apps/duckclaw-admin && pnpm dev",
            "    · Telegram: user id, token bot, whitelist",
            "    · Integraciones y Tailscale (mejor UX que el CLI)",
            "    · Agentes / plantillas / playground",
            f"  Gateway PM2: {pm2} · :{port}",
            "  Chat CLI (si no abres la UI): uv run duckops init --chat",
            "  Bot (cuando Telegram esté en admin): /workers · /team",
        ]
        owner = (getattr(draft, "wizard_creator_telegram_user_id", "") or "").strip()
        if owner:
            lines.append(f"  Dueño ya en .env (Playground): ID {owner}")
        console.print()
        console.print(
            Panel(
                "\n".join(lines),
                title=panel_title("Siguientes pasos"),
                border_style=STATUS_DONE,
                padding=(1, 2),
            )
        )
        console.print()
