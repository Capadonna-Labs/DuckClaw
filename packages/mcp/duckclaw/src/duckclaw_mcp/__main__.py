"""
Punto de entrada: MCP streamable HTTP en el puerto local (p. ej. 8001) → URL ``http://127.0.0.1:8001/mcp``.

Producción: expón este puerto con **Tailscale Funnel** (o túnel TLS) y usa la URL HTTPS
pública + ``/mcp`` en ``mcp_connections.duckclaw.url``.

  uv run python -m duckclaw_mcp --host 0.0.0.0 --port 8001
"""

from __future__ import annotations

import argparse
import os


def main() -> None:
    import uvicorn

    from duckclaw_mcp.server import build_streamable_http_asgi

    default_port = int((os.environ.get("DUCKCLAW_MCP_PORT") or "8001").strip() or "8001")
    parser = argparse.ArgumentParser(description="DuckClaw MCP (LangGraph tools, streamable HTTP)")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host (use 0.0.0.0 behind Funnel)")
    parser.add_argument("--port", type=int, default=default_port, help="TCP port (default 8001 or DUCKCLAW_MCP_PORT)")
    args = parser.parse_args()

    app = build_streamable_http_asgi()
    print(
        f"duckclaw-mcp streamable HTTP → http://{args.host}:{args.port}/mcp "
        "(configure cliente MCP with this URL over HTTPS when using Funnel)",
        flush=True,
    )
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
