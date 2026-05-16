# API Gateway (`services/api-gateway`)

Proceso FastAPI: chat de agentes, webhooks Telegram/Discord, encolado de escrituras DuckDB (no escribe DB directamente), VLM, health.

```bash
uv run duckops serve --gateway
# o PM2 según config/api_gateways_pm2.json.example
```

- Código: `main.py`, `core/`, `routers/`
- Runbooks: [`docs/COMANDOS.md`](../../docs/COMANDOS.md), [`docs/api/api_gateway.md`](../../docs/api/api_gateway.md)
