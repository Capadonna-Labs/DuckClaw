# COMANDOS · DuckClaw

## Arranque

```bash
uv run duckops serve --pm2 --gateway
pm2 start ecosystem.db-writer.config.cjs
pm2 save
pm2 list
```

## Utilidad

```bash
uv run duckops init                              # Reconfig / instalar
uv run python scripts/doctor.py                  # Diagnóstico local
uv run duckops serve --gateway                   # Dev sin PM2
uv run duckops serve --pm2 --gateway             # Ecosystem + DuckClaw-Gateway
pm2 start config/ecosystem.api.config.cjs --only DuckClaw-Gateway
pm2 status | pm2 flush
pm2 logs DuckClaw-Gateway
pm2 logs BI-Analyst-Gateway                      # Ej. multi-gateway
pm2 logs JobHunter-Gateway
pm2 logs DuckClaw-DB-Writer
pm2 restart DuckClaw-Gateway --update-env        # Tras .env
```

