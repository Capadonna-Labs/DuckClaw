"""
Cliente MCP stdio hacia duckclaw_telegram_mcp (egress Telegram).

Lee config/mcp_servers.yaml bajo la raíz del repo (DUCKCLAW_REPO_ROOT o inferido).
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

_log = logging.getLogger("duckclaw.telegram_mcp")

if TYPE_CHECKING:
    from mcp import ClientSession


def run_async(coro: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


_run_async_from_sync = run_async  # compat github_bridge


def infer_repo_root() -> Path:
    env = (os.environ.get("DUCKCLAW_REPO_ROOT") or "").strip()
    if env:
        return Path(env).resolve()
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        marker = parent / "pyproject.toml"
        if marker.is_file():
            try:
                head = marker.read_text(encoding="utf-8")[:400]
            except OSError:
                continue
            if "name = \"duckclaw\"" in head or "name = 'duckclaw'" in head:
                return parent
    return here.parents[6]


def load_mcp_servers_yaml(repo: Path) -> dict[str, Any]:
    path = repo / "config" / "mcp_servers.yaml"
    if not path.is_file():
        return {}
    try:
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception as exc:  # noqa: BLE001
        _log.warning("telegram MCP: no se pudo leer %s: %s", path, exc)
        return {}


def telegram_mcp_feature_enabled(cfg: dict[str, Any]) -> bool:
    env = (os.environ.get("DUCKCLAW_TELEGRAM_MCP_ENABLED") or "").strip().lower()
    if env in ("0", "false", "no", "off"):
        return False
    if env in ("1", "true", "yes", "on"):
        return True
    tg = (cfg.get("mcp_servers") or {}).get("telegram")
    if not isinstance(tg, dict):
        return False
    return bool(tg.get("enabled"))


def _expand_stdio_params(repo: Path, tg: dict[str, Any]) -> Any:
    from mcp.client.stdio import StdioServerParameters

    # Mismo intérprete/venv que el gateway: con ``uv run --package`` el hijo a menudo falla con
    # "Package duckclaw-telegram-mcp not found in workspace" (PM2, cwd, discovery de uv).
    use_parent_python = tg.get("use_parent_python", True)
    env_force_uv = (os.environ.get("DUCKCLAW_TELEGRAM_MCP_SPAWN_WITH_UV") or "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    if use_parent_python is not False and not env_force_uv:
        cmd = sys.executable
        args = ["-m", "duckclaw_telegram_mcp"]
        _log.info("telegram MCP: hijo vía intérprete del gateway (%s -m duckclaw_telegram_mcp)", cmd)
    else:
        cmd = (tg.get("command") or "uv").strip()
        args = tg.get("args") or []
        if isinstance(args, str):
            args = [args]
        args = [str(x) for x in args]

        if cmd == "uv" and not shutil.which("uv"):
            _log.info("telegram MCP: uv no está en PATH; usando sys.executable -m duckclaw_telegram_mcp")
            cmd = sys.executable
            args = ["-m", "duckclaw_telegram_mcp"]

    env_cfg = tg.get("env")
    child_env = os.environ.copy()
    if isinstance(env_cfg, dict):
        for k, v in env_cfg.items():
            if v is None:
                continue
            s = str(v).strip()
            if s.startswith("${") and s.endswith("}"):
                var = s[2:-1].strip()
                if var and os.environ.get(var):
                    child_env[var] = os.environ[var]
            elif s:
                child_env[str(k)] = s

    tok = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    if tok:
        child_env["TELEGRAM_BOT_TOKEN"] = tok

    cwd_raw = tg.get("cwd")
    cwd: str | Path | None
    if cwd_raw:
        cwd = Path(cwd_raw).expanduser()
        if not cwd.is_absolute():
            cwd = (repo / cwd).resolve()
        cwd = str(cwd)
    else:
        cwd = str(repo.resolve())

    return StdioServerParameters(command=cmd, args=args, env=child_env, cwd=cwd)


def tool_result_first_json(result: Any) -> dict[str, Any]:
    parts: list[str] = []
    for block in getattr(result, "content", None) or []:
        t = getattr(block, "text", None)
        if t:
            parts.append(t)
    raw = "\n".join(parts) if parts else str(result)
    try:
        out = json.loads(raw)
        return out if isinstance(out, dict) else {"ok": False, "error": raw[:800]}
    except json.JSONDecodeError:
        return {"ok": False, "error": raw[:800]}


class _McpOwnerState:
    """Estado compartido entre la tarea dueña del stdio y el arranque del gateway."""

    __slots__ = ("ready", "stop", "session", "error")

    def __init__(self) -> None:
        self.ready = asyncio.Event()
        self.stop = asyncio.Event()
        self.session: Any = None
        self.error: BaseException | None = None


class TelegramMcpGatewayHolder:
    """
    El stdio_client de MCP/AnyIO exige entrar y salir de los cancel scopes en la **misma** tarea.
    Uvicorn puede cerrar el lifespan en otra tarea que la del arranque; por eso una única
    tarea de fondo posee los ``async with`` de punta a punta.
    """

    __slots__ = ("_state", "_task")

    def __init__(self, state: _McpOwnerState, task: asyncio.Task) -> None:
        self._state = state
        self._task = task

    @property
    def session(self) -> Any:
        return self._state.session

    async def aclose(self) -> None:
        self._state.stop.set()
        try:
            await asyncio.wait_for(self._task, timeout=45.0)
        except asyncio.TimeoutError:
            _log.warning("telegram MCP: timeout al cerrar tarea dueña; cancelando")
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        except Exception as exc:  # noqa: BLE001
            _log.warning("telegram MCP: error esperando tarea dueña: %s", exc)


async def _telegram_mcp_owner_loop(state: _McpOwnerState, params: Any) -> None:
    """Una sola tarea: async with stdio + ClientSession; call_tool desde otras tareas usa la misma sesión."""
    try:
        from mcp import ClientSession
        from mcp.client.stdio import stdio_client
    except ImportError:
        state.error = RuntimeError("paquete mcp no instalado")
        state.ready.set()
        return

    try:
        async with stdio_client(params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as client_session:
                await client_session.initialize()
                listed = await client_session.list_tools()
                names = [t.name for t in (listed.tools or [])]
                _log.info("telegram MCP: conectado tools=%s", names)
                if "telegram_send_message" not in names:
                    state.error = RuntimeError("servidor MCP sin telegram_send_message")
                    state.ready.set()
                    return
                state.session = client_session
                state.ready.set()
                await state.stop.wait()
    except Exception as exc:  # noqa: BLE001
        state.error = exc
        if not state.ready.is_set():
            state.ready.set()
        else:
            _log.warning("telegram MCP: error en tarea dueña tras arranque: %s", exc, exc_info=True)


async def start_telegram_mcp_gateway_session(
    repo: Path | None = None,
) -> TelegramMcpGatewayHolder | None:
    """Arranca tarea dueña con stdio + ClientSession; None si deshabilitado o error."""
    root = repo or infer_repo_root()
    cfg = load_mcp_servers_yaml(root)
    if not telegram_mcp_feature_enabled(cfg):
        _log.info("telegram MCP: deshabilitado (DUCKCLAW_TELEGRAM_MCP_ENABLED / config/mcp_servers.yaml)")
        return None
    if not (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip():
        _log.warning("telegram MCP: habilitado pero falta TELEGRAM_BOT_TOKEN; no se inicia el hijo MCP")
        return None
    tg = (cfg.get("mcp_servers") or {}).get("telegram")
    if not isinstance(tg, dict):
        _log.warning("telegram MCP: bloque mcp_servers.telegram ausente en YAML")
        return None
    try:
        import mcp  # noqa: F401
    except ImportError:
        _log.warning("telegram MCP: paquete mcp no instalado (Python 3.10+ y uv sync)")
        return None

    params = _expand_stdio_params(root, tg)
    _log.info(
        "telegram MCP: iniciando stdio command=%s args=%s cwd=%s",
        params.command,
        params.args,
        params.cwd,
    )
    state = _McpOwnerState()
    task = asyncio.create_task(_telegram_mcp_owner_loop(state, params))
    await state.ready.wait()
    if state.session is None:
        err = state.error
        _log.warning(
            "telegram MCP: no se pudo iniciar sesión%s",
            f": {err}" if err else "",
            exc_info=err is not None,
        )
        if not task.done():
            state.stop.set()
            try:
                await task
            except Exception:  # noqa: BLE001
                pass
        return None
    return TelegramMcpGatewayHolder(state, task)


async def call_telegram_send_message_via_mcp(
    session: ClientSession,
    *,
    chat_id: str,
    text: str,
    parse_mode: str = "HTML",
) -> dict[str, Any]:
    result = await session.call_tool(
        "telegram_send_message",
        {"chat_id": chat_id, "text": text, "parse_mode": parse_mode},
    )
    return tool_result_first_json(result)


async def send_long_plain_via_mcp_chunks(
    session: ClientSession,
    *,
    chat_id: str,
    plain_text: str,
    max_plain_chunk: int = 3600,
) -> bool:
    """Trocea texto y envía HTML vía MCP (markdown del modelo → HTML Telegram). True si todos los trozos ok."""
    from duckclaw.utils.telegram_markdown_v2 import plain_subchunks_for_telegram_html

    raw = (plain_text or "").strip()
    if not raw:
        return True
    chunks = plain_subchunks_for_telegram_html(raw)
    if not chunks:
        chunks = [raw]
    total = len(chunks)
    for idx, part in enumerate(chunks):
        prefix = f"[{idx + 1}/{total}]\n" if total > 1 else ""
        payload_text = prefix + part
        out = await call_telegram_send_message_via_mcp(
            session,
            chat_id=chat_id,
            text=payload_text,
            parse_mode="HTML",
        )
        if not out.get("ok"):
            _log.warning(
                "telegram MCP: send_message chunk falló [%s/%s] chat_id=%s err=%s",
                idx + 1,
                total,
                chat_id,
                str(out.get("error", out))[:400],
            )
            return False
    _log.info("telegram MCP: cola de texto enviada (%s partes) chat_id=%s", total, chat_id)
    return True


async def send_sandbox_photo_via_mcp(
    session: ClientSession,
    *,
    chat_id: str,
    image_bytes: bytes,
    filename: str = "chart.png",
    caption: str = "",
) -> dict[str, Any]:
    b64 = base64.standard_b64encode(image_bytes).decode("ascii")
    result = await session.call_tool(
        "telegram_send_photo",
        {
            "chat_id": chat_id,
            "photo_base64": b64,
            "filename": filename,
            "caption": caption or "",
        },
    )
    return tool_result_first_json(result)
