#!/usr/bin/env python3
"""
Prueba extremo a extremo: cliente MCP (stdio) -> duckclaw_telegram_mcp -> Telegram sendMessage.

Ejecutar desde la raíz del repositorio (``uv sync`` instala ``duckclaw-telegram-mcp`` en Python 3.10+):

  uv sync
  export TELEGRAM_BOT_TOKEN=...
  export TELEGRAM_MCP_TEST_CHAT_ID=123456789   # opcional si pasas el chat como argv
  uv run python scripts/smoke_telegram_mcp_stdio.py [chat_id]

Salida esperada: lista de tools MCP y JSON de resultado (ok/message_id o error).
El gateway PM2 no interviene; esto valida solo el servidor MCP y el token.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path


def _load_dotenv_setdefault(repo_root: Path) -> None:
    env_file = repo_root / ".env"
    if not env_file.is_file():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        if not key:
            continue
        val = val.strip().strip("'\"")
        os.environ.setdefault(key, val)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


async def _run(chat_id: str) -> int:
    repo = _repo_root()
    _load_dotenv_setdefault(repo)
    token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        print("Falta TELEGRAM_BOT_TOKEN (export o .env en la raíz del repo)", file=sys.stderr)
        return 2

    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    env = {**os.environ, "TELEGRAM_BOT_TOKEN": token}
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "duckclaw_telegram_mcp"],
        env=env,
        cwd=str(repo),
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            names = [t.name for t in (listed.tools or [])]
            print("tools MCP:", names)
            if "telegram_send_message" not in names:
                print("telegram_send_message no listada", file=sys.stderr)
                return 3

            result = await session.call_tool(
                "telegram_send_message",
                {
                    "chat_id": chat_id,
                    "text": "Smoke test MCP stdio — DuckClaw",
                    "parse_mode": "MarkdownV2",
                },
            )
            parts: list[str] = []
            for block in getattr(result, "content", None) or []:
                text = getattr(block, "text", None)
                if text:
                    parts.append(text)
            out = "\n".join(parts) if parts else str(result)
            print("call_tool telegram_send_message:")
            try:
                print(json.dumps(json.loads(out), ensure_ascii=False, indent=2))
            except json.JSONDecodeError:
                print(out)

            try:
                data = json.loads(out)
                return 0 if isinstance(data, dict) and data.get("ok") is True else 4
            except json.JSONDecodeError:
                return 4


def main() -> None:
    chat = (os.environ.get("TELEGRAM_MCP_TEST_CHAT_ID") or "").strip()
    if not chat and len(sys.argv) > 1:
        chat = (sys.argv[1] or "").strip()
    if not chat:
        print(
            "Pasa el chat_id como primer argumento o define TELEGRAM_MCP_TEST_CHAT_ID",
            file=sys.stderr,
        )
        sys.exit(2)
    raise SystemExit(asyncio.run(_run(chat)))


if __name__ == "__main__":
    main()
