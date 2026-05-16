# COMANDOS · DuckClaw

## Arranque

```bash
uv run duckops serve --pm2 --gateway
pm2 start config/ecosystem.db-writer.config.cjs
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
pm2 delete DuckClaw-DB-Writer
pm2 status 
pm2 flush                                        # Limpia la consola
pm2 logs DuckClaw-Gateway
pm2 logs BI-Analyst-Gateway                      # Ej. multi-gateway
pm2 logs JobHunter-Gateway
pm2 logs DuckClaw-DB-Writer
pm2 restart DuckClaw-Gateway --update-env        # Tras .env
pm2 restart all --update-env                      # Reinicia todos los servicios 
```

## TELEGRAM

```bash
/team                         # Verifica usuarios actuales
/team --add id_telegram admin # Agrega un usuairo con permiso 'admin' 
/team --add id_telegram       # Agrega usuario con permiso ' user ' 
/team --rm  id_telegram       # eliminar usuario

/workers                             # Muestra plantillas de trabajadores virtuales
Equipo: 
- cobranzas
- research_worker
- BI-Analyst
- LeilaAssistant
- gymbro
- powerseal
- PQRSD-Assistant
- SIATA-Analyst
- Quant-Trader
- finanz
- support
- AXIS
- TheMindCrupier
- gitclaw
- Job-Hunter

/workers --add cobranzas
/workers --rm  cobranzas

/vault                        # Muestra la ruta del storage

/heartbeat on                 # Muestra el uso de tools 
/heartbeat off                # oculta el uso de tools

/context on
/context off
/context --summary 
/context --add Documentacion especifica 
```

## Admin UI (pnpm)

```bash
# Gateway con DUCKCLAW_ADMIN_API_KEY en .env raíz
pm2 restart DuckClaw-Gateway --update-env

cd apps/duckclaw-admin && pnpm install && pnpm dev
# o desde raíz: pnpm admin:dev
```

Variables en `apps/duckclaw-admin/.env.local`: `DUCKCLAW_GATEWAY_URL`, `DUCKCLAW_ADMIN_API_KEY` (misma clave que el gateway).

