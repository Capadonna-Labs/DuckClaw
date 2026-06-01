# Dotenv — única fuente de secretos (v1.0.0)

## Regla

- **Secretos** (`*_API_KEY`, `*_TOKEN`, `*_SECRET`, `DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES`, etc.) → **solo** `.env` en la raíz del repo.
- **No** commitear valores reales en `config/ecosystem.api.config.cjs` ni `config/api_gateways_pm2.json`.

## Runtime

1. PM2: `env_file: ".env"` en cada app del ecosystem API.
2. Gateway (`services/api-gateway/main.py`): tras cargar `.env`, `DOTENV_OVERRIDE_KEYS` **sustituyen** env heredado de PM2 (evita drift de claves viejas y URLs IBKR/Capadonna).

## Regenerar ecosystem (sin secretos)

```bash
uv run duckops serve --pm2 --gateway
pm2 restart DuckClaw-Gateway --update-env
```

`duckclaw.env_secrets.strip_secrets_from_env` filtra al escribir JSON/CJS.

## Código

| Módulo | Rol |
|--------|-----|
| `packages/shared/src/duckclaw/env_secrets.py` | Lista secretos + strip + override |
| `packages/shared/src/duckclaw/ops/manager.py` | `_render_gateway_ecosystem_cjs` + `env_file` |
| `services/api-gateway/main.py` | Override `.env` > PM2 |
