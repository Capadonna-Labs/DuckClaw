"""REPL de chat TUI contra el playground admin del gateway."""

from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from prompt_toolkit import PromptSession
from rich.console import Console
from rich.panel import Panel

from duckops.admin_dev_server import (
    admin_login_url,
    ensure_admin_web_ready,
    open_admin_browser,
)
from duckclaw.gateway_db import DEFAULT_SESSION_DB_RELPATH
from duckops.sovereign.draft import SovereignDraft
from duckops.sovereign.materialize import load_draft_json
from duckops.sovereign.tui_chat_columns import render_chat_turn, render_input_chrome
from duckops.sovereign.tui_chat_keys import WorkerTabCycle, build_chat_key_bindings
from duckops.sovereign.tui_chat_layout import render_chat_intro
from duckops.sovereign.tui_chat_sidebar import TuiChatSidebarState
from duckops.sovereign.tui_chat_status import resolve_tui_llm_label
from duckops.sovereign.tui_shell import TuiShell
from duckops.sovereign.duckdb_health import open_repo_duckdb_readonly
from duckops.sovereign.workers_catalog import (
    list_worker_picks,
    resolve_worker_choice,
    suggest_default_worker_id,
)


@dataclass(frozen=True)
class GatewayChatConfig:
    base_url: str
    admin_key: str
    tenant_id: str
    telegram_user_id: str
    default_worker_id: str
    chat_id: str = "sovereign-tui-chat"


def _parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        k = key.strip()
        v = val.strip().strip("'\"")
        if k:
            out[k] = v
    return out


def _draft_from_dotenv(repo_root: Path, cfg: "GatewayChatConfig") -> SovereignDraft:
    """Bóveda/tenant/worker del chat desde ``.env`` (no borrador viejo SIATA/Geo)."""
    env = _parse_env_file(repo_root / ".env")
    vault = (env.get("DUCKDB_PATH") or env.get("DUCKCLAW_DB_PATH") or "").strip()
    return SovereignDraft(
        duckdb_vault_path=vault or DEFAULT_SESSION_DB_RELPATH,
        tenant_id=cfg.tenant_id,
        default_worker_id=cfg.default_worker_id,
    )


def load_gateway_chat_config(
    repo_root: Path,
    draft: SovereignDraft | None = None,
) -> GatewayChatConfig:
    """Lee URL, clave admin y tenant desde .env / entorno / borrador."""
    from duckclaw.dotenv_immutable import merged_root_and_proposed_flat_env
    from duckclaw.gateway_port import gateway_base_url

    env = merged_root_and_proposed_flat_env(repo_root)
    if draft is not None:
        tenant = (draft.tenant_id or "default").strip() or "default"
        worker = (draft.default_worker_id or "").strip()
        owner = (draft.wizard_creator_telegram_user_id or "").strip()
    else:
        tenant = "default"
        worker = ""
        owner = ""
    base = (
        os.environ.get("DUCKCLAW_GATEWAY_URL")
        or env.get("DUCKCLAW_GATEWAY_URL")
        or gateway_base_url(repo_root)
    ).rstrip("/")
    admin_key = (
        os.environ.get("DUCKCLAW_ADMIN_API_KEY")
        or env.get("DUCKCLAW_ADMIN_API_KEY")
        or ""
    ).strip()
    if draft is None:
        saved = load_draft_json()
        if saved is not None:
            draft = saved
    if draft is not None:
        tenant = (draft.tenant_id or tenant).strip() or "default"
        worker = (draft.default_worker_id or worker).strip()
        owner = owner or (draft.wizard_creator_telegram_user_id or "").strip()
    tenant = (env.get("DUCKCLAW_GATEWAY_TENANT_ID") or env.get("DUCKCLAW_TELEGRAM_DEFAULT_TENANT") or tenant).strip()
    worker = (env.get("DUCKCLAW_DEFAULT_WORKER_ID") or worker).strip()
    owner = owner or (env.get("DUCKCLAW_OWNER_ID") or env.get("DUCKCLAW_ADMIN_CHAT_ID") or "").strip()
    return GatewayChatConfig(
        base_url=base,
        admin_key=admin_key,
        tenant_id=tenant,
        telegram_user_id=owner,
        default_worker_id=worker,
    )


class PlaygroundChatClient:
    """Cliente HTTP al endpoint admin playground (sync wrapper sobre httpx async)."""

    def __init__(self, config: GatewayChatConfig) -> None:
        self.config = config

    async def _post_chat_async(
        self,
        message: str,
        *,
        worker_id: str,
        stream: bool = False,
    ) -> dict[str, Any]:
        url = f"{self.config.base_url}/api/v1/admin/playground/chat"
        headers = {"X-Admin-Key": self.config.admin_key, "Content-Type": "application/json"}
        body: dict[str, Any] = {
            "worker_id": worker_id,
            "message": message,
            "tenant_id": self.config.tenant_id,
            "chat_id": self.config.chat_id,
            "stream": stream,
        }
        if self.config.telegram_user_id:
            body["telegram_user_id"] = self.config.telegram_user_id
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
            if not stream:
                r = await client.post(url, headers=headers, json=body)
                r.raise_for_status()
                data = r.json()
                if not isinstance(data, dict):
                    return {"ok": True, "response": str(data)}
                return data
            headers["Accept"] = "text/event-stream"
            parts: list[str] = []
            async with client.stream("POST", url, headers=headers, json=body) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        chunk = json.loads(payload)
                    except json.JSONDecodeError:
                        parts.append(payload)
                        continue
                    if isinstance(chunk, dict):
                        token = chunk.get("token") or chunk.get("delta") or chunk.get("text")
                        if token:
                            parts.append(str(token))
                    elif isinstance(chunk, str):
                        parts.append(chunk)
            return {"ok": True, "response": "".join(parts), "worker_id": worker_id}

    def post_chat(
        self,
        message: str,
        *,
        worker_id: str | None = None,
        stream: bool = False,
    ) -> dict[str, Any]:
        wid = (worker_id or self.config.default_worker_id).strip() or "default"
        return asyncio.run(
            self._post_chat_async(message, worker_id=wid, stream=stream)
        )


def _help_text() -> str:
    return (
        "Comandos: /workers · /worker <id> · Tab ciclar · /new · /retry · /status · /web · /quit\n"
        "/new abre sesión nueva (chat_id distinto).\n"
        "/retry reenvía el último mensaje.\n"
        "/status refresca el panel Context (derecha).\n"
        "/web abre la consola Playground en el navegador."
    )


def _build_sidebar_state(
    *,
    cfg: GatewayChatConfig,
    repo_root: Path,
    shell_draft: SovereignDraft,
    picks: list[Any],
    llm_label: str,
    policy_health: Any,
    last_usage: Any = None,
    turn_count: int = 0,
) -> TuiChatSidebarState:
    from duckops.sovereign.duckdb_health import audit_duckdb, duckdb_chrome_summary

    duck = audit_duckdb(repo_root, shell_draft, quick=True)
    return TuiChatSidebarState(
        worker_id=cfg.default_worker_id,
        tenant_id=cfg.tenant_id,
        llm_label=llm_label,
        gateway_url=cfg.base_url,
        duck_line=duckdb_chrome_summary(duck),
        policy_summary=policy_health.summary(),
        policy_ok=policy_health.ok,
        policy_degraded=policy_health.degraded,
        worker_picks=picks,
        last_usage=last_usage,
        turn_count=turn_count,
        chat_id=cfg.chat_id,
        repo_label=str(repo_root),
    )


def _policy_preflight_health(repo_root: Path) -> tuple[bool, Any]:
    """Comprueba policies framework; retorna (continuar, health)."""

    from duckops.policy_health import check_framework_prompt_policies
    from duckops.sovereign.duckdb_health import open_repo_duckdb_readonly

    shell_draft = _draft_from_dotenv(
        repo_root,
        load_gateway_chat_config(repo_root),
    )
    db = open_repo_duckdb_readonly(repo_root, shell_draft)
    if db is None:
        from duckops.policy_health import FrameworkPolicyHealth

        return True, FrameworkPolicyHealth(ok=True, degraded_keys=(), missing_keys=())
    try:
        return True, check_framework_prompt_policies(db)
    finally:
        if hasattr(db, "close"):
            try:
                db.close()
            except Exception:
                pass


def _run_policy_preflight(repo_root: Path, console: Console) -> tuple[bool, Any]:
    _, health = _policy_preflight_health(repo_root)
    if not health.ok:
        console.print(
            Panel(
                f"{health.summary()}\n\n"
                "[dim]Ejecuta: uv run duckclaw-migrate[/]",
                title="[red]Policies framework[/]",
                border_style="red",
                padding=(0, 1),
            )
        )
        return False, health
    if health.degraded:
        console.print(
            Panel(
                f"{health.summary()}\n\n"
                "[dim]El chat arrancará con airbag capa 0. "
                "Recomendado: uv run duckclaw-migrate[/]",
                title="[yellow]Policies degradadas[/]",
                border_style="yellow",
                padding=(0, 1),
            )
        )
    return True, health


def _new_chat_id() -> str:
    import uuid

    return f"sovereign-tui-{uuid.uuid4().hex[:8]}"


def _format_http_chat_error(exc: httpx.HTTPStatusError) -> str:
    detail = ""
    try:
        payload = exc.response.json()
        if isinstance(payload, dict):
            detail = str(payload.get("detail") or payload.get("title") or "")
    except Exception:
        detail = exc.response.text[:240] if exc.response else ""
    if "prompt policy not found" in detail.lower():
        return (
            f"[red]HTTP {exc.response.status_code}[/] Falta policy en DuckDB.\n"
            "[dim]Ejecuta: uv run duckclaw-migrate[/]"
        )
    return f"[red]HTTP {exc.response.status_code}[/] {detail}".strip()


def run_tui_chat(
    repo_root: Path,
    draft: SovereignDraft | None = None,
    *,
    console: Console | None = None,
    use_stream: bool = False,
) -> int:
    """Bucle REPL; requiere gateway activo y DUCKCLAW_ADMIN_API_KEY."""
    console = console or Console()
    cfg = load_gateway_chat_config(repo_root, draft)
    if not cfg.admin_key:
        console.print(
            "[red]Falta DUCKCLAW_ADMIN_API_KEY[/] en .env o entorno. "
            "Configúrala en el monorepo antes del chat TUI."
        )
        return 1

    worker_id = cfg.default_worker_id
    port_match = re.search(r":(\d+)$", cfg.base_url)
    from duckclaw.gateway_port import resolve_gateway_port

    gw_port = int(port_match.group(1)) if port_match else resolve_gateway_port(repo_root)
    shell_draft = _draft_from_dotenv(repo_root, cfg)
    shell_draft = shell_draft.model_copy(
        update={
            "wizard_creator_telegram_user_id": cfg.telegram_user_id,
            "gateway_port": gw_port,
        }
    )
    shell = TuiShell(console, shell_draft, repo_root)
    shell.show_tenant_in_chrome = True
    shell.note("Modo chat TUI")

    db = open_repo_duckdb_readonly(repo_root, shell_draft)
    admin_email = (_parse_env_file(repo_root / ".env").get("DUCKCLAW_ADMIN_EMAIL") or "").strip()
    try:
        picks = list_worker_picks(
            repo_root,
            db=db,
            tenant_id=cfg.tenant_id,
            actor_email=admin_email,
            source="catalog",
        )
    finally:
        if db is not None and hasattr(db, "close"):
            try:
                db.close()
            except Exception:
                pass

    worker_id = suggest_default_worker_id(picks, worker_id)
    cfg = GatewayChatConfig(
        base_url=cfg.base_url,
        admin_key=cfg.admin_key,
        tenant_id=cfg.tenant_id,
        telegram_user_id=cfg.telegram_user_id,
        default_worker_id=worker_id,
        chat_id="sovereign-tui-chat",
    )

    llm_label = resolve_tui_llm_label(repo_root)
    preflight_ok, policy_health = _run_policy_preflight(repo_root, console)
    if not preflight_ok:
        return 1

    sidebar = _build_sidebar_state(
        cfg=cfg,
        repo_root=repo_root,
        shell_draft=shell_draft,
        picks=picks,
        llm_label=llm_label,
        policy_health=policy_health,
    )

    render_chat_intro(
        console,
        base_url=cfg.base_url,
        tenant_id=cfg.tenant_id,
        repo_root=repo_root,
        draft=shell_draft,
        worker_id=worker_id,
        sidebar_state=sidebar,
    )
    console.print()

    client = PlaygroundChatClient(cfg)
    last_usage: Any = None
    last_user_message = ""
    turn_count = 0
    tab_cycle = WorkerTabCycle(picks=picks)
    if picks:
        for i, pick in enumerate(picks):
            if pick.worker_id == worker_id:
                tab_cycle.index = i
                break

    def _set_active_worker(new_worker_id: str) -> None:
        nonlocal worker_id, cfg, client, sidebar
        worker_id = new_worker_id
        cfg = GatewayChatConfig(
            base_url=cfg.base_url,
            admin_key=cfg.admin_key,
            tenant_id=cfg.tenant_id,
            telegram_user_id=cfg.telegram_user_id,
            default_worker_id=worker_id,
            chat_id=cfg.chat_id,
        )
        client = PlaygroundChatClient(cfg)
        sidebar = _build_sidebar_state(
            cfg=cfg,
            repo_root=repo_root,
            shell_draft=shell_draft,
            picks=picks,
            llm_label=llm_label,
            policy_health=policy_health,
            last_usage=last_usage,
            turn_count=turn_count,
        )

    session = PromptSession(key_bindings=build_chat_key_bindings(tab_cycle, on_worker_change=_set_active_worker))
    conversation_started = False

    while True:
        render_input_chrome(
            console,
            llm_label=llm_label,
            worker_id=worker_id,
            tenant_id=cfg.tenant_id,
        )
        try:
            raw = session.prompt("› ", default="")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Chat finalizado.[/]")
            return 0
        line = (raw or "").strip()
        if not line:
            continue
        low = line.lower()
        if low in ("/help", "/ayuda", "?"):
            console.print(_help_text())
            continue
        if low in ("/quit", "/salir", "/q"):
            console.print("[dim]Hasta luego.[/]")
            return 0
        if low in ("/new", "/nuevo"):
            cfg = GatewayChatConfig(
                base_url=cfg.base_url,
                admin_key=cfg.admin_key,
                tenant_id=cfg.tenant_id,
                telegram_user_id=cfg.telegram_user_id,
                default_worker_id=worker_id,
                chat_id=_new_chat_id(),
            )
            client = PlaygroundChatClient(cfg)
            last_usage = None
            last_user_message = ""
            turn_count = 0
            sidebar = _build_sidebar_state(
                cfg=cfg,
                repo_root=repo_root,
                shell_draft=shell_draft,
                picks=picks,
                llm_label=llm_label,
                policy_health=policy_health,
            )
            console.print(f"[green]Nueva sesión:[/] {cfg.chat_id}")
            render_chat_turn(
                console,
                user_line="(sesión reiniciada)",
                reply="Historial limpio en gateway. Escribe tu primer mensaje.",
                agent_title="Sistema",
                sidebar_state=sidebar,
            )
            continue
        if low in ("/retry", "/reintentar"):
            if not last_user_message:
                console.print("[yellow]No hay mensaje previo para reintentar.[/]")
                continue
            line = last_user_message
            low = line.lower()
        if low in ("/web", "/ui", "/browser", "/navegador"):
            if ensure_admin_web_ready(repo_root, print_fn=lambda m: console.print(m)):
                console.print(f"[green]Consola web:[/] {admin_login_url(repo_root)}")
                open_admin_browser(repo_root, print_fn=lambda m: console.print(m))
            else:
                console.print(
                    "[yellow]No se pudo levantar la consola.[/] "
                    "cd apps/duckclaw-admin && pnpm dev"
                )
            continue
        if low == "/workers":
            if not picks:
                console.print("[yellow]No hay workers en el catálogo.[/]")
                continue
            for p in picks:
                mark = " ← activo" if p.worker_id == worker_id else ""
                console.print(f"  [bold]{p.worker_id}[/] — {p.label}{mark}")
            continue
        if low == "/status":
            sidebar = _build_sidebar_state(
                cfg=cfg,
                repo_root=repo_root,
                shell_draft=shell_draft,
                picks=picks,
                llm_label=llm_label,
                policy_health=policy_health,
                last_usage=last_usage,
                turn_count=turn_count,
            )
            render_chat_turn(
                console,
                user_line="(status)",
                reply="Panel Context actualizado.",
                agent_title="Sistema",
                sidebar_state=sidebar,
            )
            continue
        if low.startswith("/worker"):
            parts = line.split(maxsplit=1)
            if len(parts) < 2 or not parts[1].strip():
                console.print("[yellow]Uso: /worker <id>[/] · o pulsa [cyan]Tab[/] para ciclar")
                continue
            resolved = resolve_worker_choice(parts[1].strip(), picks, repo_root)
            if not resolved:
                console.print(f"[yellow]Worker desconocido:[/] {parts[1].strip()}")
                continue
            _set_active_worker(resolved)
            for i, pick in enumerate(picks):
                if pick.worker_id == worker_id:
                    tab_cycle.index = i
                    break
            console.print(f"[green]Worker activo:[/] {worker_id}")
            continue

        last_user_message = line
        try:
            result = client.post_chat(line, worker_id=worker_id, stream=use_stream)
        except httpx.HTTPStatusError as exc:
            console.print(_format_http_chat_error(exc))
            continue
        except httpx.RequestError as exc:
            console.print(
                f"[red]No se pudo conectar a {cfg.base_url}[/]. "
                "¿Está el gateway en marcha? (duckops serve --pm2 --gateway)"
            )
            console.print(f"[dim]{exc}[/]")
            continue
        except Exception as exc:
            console.print(f"[red]Error:[/] {exc}")
            continue

        reply = str(result.get("response") or result.get("reply") or "").strip()
        last_usage = result.get("usage_tokens")
        turn_count += 1
        assigned = result.get("assigned_worker_id")
        title = f"Agente ({worker_id})"
        if assigned and assigned != worker_id:
            title += f" → {assigned}"
        sidebar = _build_sidebar_state(
            cfg=GatewayChatConfig(
                base_url=cfg.base_url,
                admin_key=cfg.admin_key,
                tenant_id=cfg.tenant_id,
                telegram_user_id=cfg.telegram_user_id,
                default_worker_id=assigned or worker_id,
                chat_id=cfg.chat_id,
            ),
            repo_root=repo_root,
            shell_draft=shell_draft,
            picks=picks,
            llm_label=llm_label,
            policy_health=policy_health,
            last_usage=last_usage,
            turn_count=turn_count,
        )
        if not conversation_started:
            console.clear()
            conversation_started = True
        render_chat_turn(
            console,
            user_line=line,
            reply=reply,
            agent_title=title,
            sidebar_state=sidebar,
        )
        shell.note(f"Chat · {worker_id}")
