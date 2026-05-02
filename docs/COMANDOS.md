# COMANDOS — Despliegue rápido DuckClaw
## Comandos del día a día

```bash
uv run duckops serve --pm2 --gateway
pm2 start ecosystem.db-writer.config.cjs
pm2 save
uv run python scripts/doctor.py
uv run duckops init                         # Reconfigurar / instalar
uv run python scripts/doctor.py             # Diagnóstico local (§5)
uv run duckops serve --gateway              # Gateway en dev (sin PM2)
uv run duckops serve --pm2 --gateway        # Genera ecosystem + PM2 DuckClaw-Gateway (§5)
pm2 start config/ecosystem.api.config.cjs --only DuckClaw-Gateway  # Si el ecosystem ya existe
pm2 status                                  # Si usas PM2 tras el wizard
pm2 logs DuckClaw-Gateway                   # Gateway único por defecto (duckops --pm2 --gateway)
pm2 logs BI-Analyst-Gateway                 # Ej.: traza Telegram + subagentes (multi-gateway)
pm2 logs JobHunter-Gateway                  # Job-Hunter + resúmenes /context
pm2 logs DuckClaw-DB-Writer                 # Escrituras + CONTEXT_INJECTION
pm2 flush                                   # Vaciar logs PM2
pm2 restart DuckClaw-Gateway --update-env   # Tras cambiar .env en setup de un solo gateway
pm2 restart BI-Analyst-Gateway --update-env # Nombre según config/
```

