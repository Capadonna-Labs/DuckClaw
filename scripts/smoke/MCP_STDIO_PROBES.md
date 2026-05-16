# Smoke probes (MCP stdio)

Ejecución manual desde la raíz del monorepo:

```bash
uv run python scripts/smoke/smoke_github_mcp_stdio.py
uv run python scripts/smoke/smoke_telegram_mcp_stdio.py [chat_id]
```

Requieren variables en `.env` (tokens, Docker para GitHub MCP).
