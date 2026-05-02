# COMANDOS — Despliegue rápido DuckClaw
## Comandos del día a día

```bash
uv sync                                                         # Dependencias del monorepo
uv run duckops init                                             # Wizard: .env, PM2, Telegram
uv run duckops serve --gateway                                  # Gateway en primer plano (dev)
uv run duckops serve --pm2 --gateway                            # Genera ecosystem API y arranca gateway en PM2
uv run python scripts/doctor.py                                # Diagnóstico local (Redis, puertos, rutas)
uv run python scripts/register_webhooks.py                      # setWebhook Telegram (rutas compactas + DUCKCLAW_PUBLIC_URL)

pm2 start config/ecosystem.db-writer.config.cjs                 # Consumidor Redis → DuckDB
pm2 start config/ecosystem.api.config.cjs --only DuckClaw-Gateway  # Solo gateway si ecosystem ya existe
pm2 status                                                      # Estado de procesos PM2
pm2 logs DuckClaw-Gateway                                       # Logs del gateway por defecto
pm2 logs BI-Analyst-Gateway                                    # Logs gateway BI-Analyst (multi-gateway)
pm2 logs JobHunter-Gateway                                      # Logs gateway Job-Hunter
pm2 logs DuckClaw-DB-Writer                                     # Logs escrituras y cola context
pm2 flush                                                       # Vaciar logs PM2 en memoria
pm2 restart DuckClaw-Gateway --update-env                       # Reinicio gateway con .env actualizado
pm2 restart BI-Analyst-Gateway --update-env                     # Reinicio otro gateway (nombre según config)
pm2 save                                                        # Persistir lista PM2 al reiniciar el SO
```
