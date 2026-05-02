#!/usr/bin/env python3
"""
Smoke test: GitHub MCP oficial en Docker con el mismo handshake stdio que el gateway.

Corrige la confusión de un único::

  echo '{"method":"tools/list",...}' | docker run ...

Eso falla con ``method invalid during initialization`` porque MCP exige antes
``initialize`` y la notificación ``notifications/initialized``; el cliente
``mcp`` (como usa ``mcp_stdio_list_tools``) lo hace en orden correcto.

Uso (desde la raíz del repo, con ``GITHUB_TOKEN`` en ``.env`` o en el shell)::

    uv run python scripts/smoke_github_mcp_stdio.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _prep_sys_path(repo: Path) -> None:
    agents_src = repo / "packages" / "agents" / "src"
    shared_src = repo / "packages" / "shared" / "src"
    for p in (shared_src, agents_src):
        s = str(p)
        if s not in sys.path:
            sys.path.insert(0, s)


def main() -> int:
    repo = _repo_root()
    _prep_sys_path(repo)

    try:
        from dotenv import load_dotenv
    except ImportError:
        pass
    else:
        load_dotenv(repo / ".env")

    token = (os.environ.get("GITHUB_TOKEN") or "").strip()
    if not token:
        sys.stderr.write("GITHUB_TOKEN ausente. Define en .env o exporta antes de ejecutar.\n")
        return 2

    async def _run() -> int:
        from duckclaw.forge.skills.github_bridge import compose_github_stdio_server_params
        from duckclaw.forge.skills.mcp_stdio_util import mcp_stdio_list_tools

        params = compose_github_stdio_server_params(token, read_only=True)
        try:
            tools = await mcp_stdio_list_tools(params)
        except Exception as exc:
            sys.stderr.write(f"mcp_stdio_list_tools falló: {exc}\n")
            return 1

        names = sorted({getattr(t, "name", None) or str(t) for t in tools})

        print(json.dumps({"ok": True, "tool_count": len(tools)}, ensure_ascii=False))
        if names:
            print(f"{len(names)} tools (primeras 15):")
            for name in names[:15]:
                print(" ", name)
            if len(names) > 15:
                print("  ...")

        return 0

    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
