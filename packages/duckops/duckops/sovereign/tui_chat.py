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

from duckops.sovereign.draft import SovereignDraft
from duckops.sovereign.materialize import load_draft_json
from duckops.sovereign.tui_chat_layout import render_chat_intro
from duckops.sovereign.tui_shell import TuiShell
from duckops.sovereign.wizard_theme import DUCK_ACCENT, PANEL_BORDER, panel_title
from duckops.sovereign.workers_catalog import list_worker_picks


@dataclass(frozen=True)
class GatewayChatConfig:
    base_url: str
    admin_key: str
    tenant_id: str
    telegram_user_id: str
    default_worker_id: str


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
        duckdb_vault_path=vault or "db/sovereign_memory.duckdb",
        tenant_id=cfg.tenant_id,
        default_worker_id=cfg.default_worker_id,
    )


def load_gateway_chat_config(
    repo_root: Path,
    draft: SovereignDraft | None = None,
) -> GatewayChatConfig:
    """Lee URL, clave admin y tenant desde .env / entorno / borrador."""
    env = _parse_env_file(repo_root / ".env")
    port = 8282
    if draft is not None:
        port = int(getattr(draft, "gateway_port", None) or port)
        tenant = (draft.tenant_id or "default").strip() or "default"
        worker = (draft.default_worker_id or "default").strip() or "default"
        owner = (draft.wizard_creator_telegram_user_id or "").strip()
    else:
        tenant = "default"
        worker = "default"
        owner = ""
    try:
        from duckclaw.ops.manager import _load_merged_gateway_apps  # noqa: PLC0415

        pm2_name = (env.get("DUCKCLAW_PM2_PROCESS_NAME") or "DuckClaw-Gateway").strip()
        for app in _load_merged_gateway_apps(str(repo_root)):
            if isinstance(app, dict) and (app.get("name") or "").strip() == pm2_name:
                p = int(app.get("port") or 0)
                if p > 0:
                    port = p
                break
    except Exception:
        pass
    base = (
        os.environ.get("DUCKCLAW_GATEWAY_URL")
        or env.get("DUCKCLAW_GATEWAY_URL")
        or f"http://127.0.0.1:{port}"
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
        worker = (draft.default_worker_id or worker).strip() or "default"
        owner = owner or (draft.wizard_creator_telegram_user_id or "").strip()
    tenant = (env.get("DUCKCLAW_GATEWAY_TENANT_ID") or env.get("DUCKCLAW_TELEGRAM_DEFAULT_TENANT") or tenant).strip()
    worker = (env.get("DUCKCLAW_DEFAULT_WORKER_ID") or worker).strip() or "default"
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
            "chat_id": "sovereign-tui-chat",
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
        "Comandos: /workers · /worker <id> · /quit\n"
        "Escribe un mensaje para hablar con el agente seleccionado."
    )


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

    picks = list_worker_picks(repo_root)
    worker_id = cfg.default_worker_id
    port_match = re.search(r":(\d+)$", cfg.base_url)
    gw_port = int(port_match.group(1)) if port_match else 8282
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

    render_chat_intro(
        console,
        base_url=cfg.base_url,
        tenant_id=cfg.tenant_id,
        repo_root=repo_root,
        draft=shell_draft,
        worker_id=worker_id,
    )

    client = PlaygroundChatClient(cfg)
    session = PromptSession()

    while True:
        try:
            raw = session.prompt("[magenta]*[/] ", default="")
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
        if low == "/workers":
            if not picks:
                console.print("[yellow]No hay plantillas en forge/templates.[/]")
                continue
            for p in picks:
                mark = " ← activo" if p.worker_id == worker_id else ""
                console.print(f"  [bold]{p.worker_id}[/] — {p.label}{mark}")
            continue
        if low.startswith("/worker"):
            parts = line.split(maxsplit=1)
            if len(parts) < 2 or not parts[1].strip():
                console.print("[yellow]Uso: /worker <id>[/]")
                continue
            worker_id = parts[1].strip()
            cfg = GatewayChatConfig(
                base_url=cfg.base_url,
                admin_key=cfg.admin_key,
                tenant_id=cfg.tenant_id,
                telegram_user_id=cfg.telegram_user_id,
                default_worker_id=worker_id,
            )
            client = PlaygroundChatClient(cfg)
            console.print(f"[green]Worker activo:[/] {worker_id}")
            continue

        console.print(Panel(line, title="Tú", border_style="dim", padding=(0, 1)))
        try:
            result = client.post_chat(line, worker_id=worker_id, stream=use_stream)
        except httpx.HTTPStatusError as exc:
            detail = ""
            try:
                detail = exc.response.json().get("detail", "")
            except Exception:
                detail = exc.response.text[:200] if exc.response else ""
            console.print(f"[red]HTTP {exc.response.status_code}[/] {detail}".strip())
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
        assigned = result.get("assigned_worker_id")
        title = f"Agente ({worker_id})"
        if assigned and assigned != worker_id:
            title += f" → {assigned}"
        console.print(
            Panel(
                reply or "[dim](sin respuesta)[/]",
                title=title,
                border_style=DUCK_ACCENT,
                padding=(0, 1),
            )
        )
        shell.note(f"Chat · {worker_id}")
