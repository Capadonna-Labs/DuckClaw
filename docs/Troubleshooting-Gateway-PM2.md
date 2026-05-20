# Gateway PM2: errores frecuentes

## Alcance

Flujo habitual: `uv run duckops serve --pm2 --gateway` → **`DuckClaw-Gateway`**, `config/ecosystem.api.config.cjs`, puerto **8000** (o `DUCKCLAW_GATEWAY_PORT` en `.env`).

- Reinicio: `pm2 restart DuckClaw-Gateway --update-env`
- Logs: `pm2 logs DuckClaw-Gateway`
- Guía: [COMANDOS §5](COMANDOS.md); diagnóstico: `uv run python scripts/doctor.py`

**Legacy:** despliegues con varios gateways (`Finanz-Gateway`, `TheMind-Gateway`, …) y el mini-juego The Mind están **deprecated**. Ver [THE_MIND_DEPRECATION.md](../specs/features/platform/THE_MIND_DEPRECATION.md).

## `[Errno 48] address already in use` en 8000

Otro proceso ya escucha en el puerto del gateway (uvicorn duplicado, IDE, AirPlay, contenedor, PM2 antiguo).

```bash
lsof -i :8000
# o
sudo lsof -nP -iTCP:8000 -sTCP:LISTEN
```

Cierra el proceso conflictivo o ajusta `DUCKCLAW_GATEWAY_PORT` en `.env` y regenera el ecosystem.

## `Could not set lock on file ... duckdb` (DuckDB)

DuckDB permite **un escritor** por fichero. Si **DuckClaw-DB-Writer**, el gateway y una sesión interactiva abren la misma `.duckdb` en escritura, verás *Conflicting lock*.

- Un `.duckdb` por servicio lógico, o
- `pm2 stop` del proceso que compite antes de scripts de bootstrap, o
- Rutas distintas en `api_gateways_pm2.json` si mantienes varios gateways legacy (no recomendado).

## Comprobar duplicados en la config fusionada

Tras regenerar `config/ecosystem.api.config.cjs`, el CLI puede avisar si hay **el mismo puerto en dos `apps`** o la **misma ruta DuckDB** en varios procesos.

### Asistente (wizard)

```bash
uv run python scripts/duckclaw_setup_wizard.py --resolve-gateways
```

Equivalente: `uv run duckops init` → opción de resolver gateways.

## `403` — «Acceso denegado… interactuar con este agente»

Telegram Guard (`authorized_users` + caché Redis). El endpoint necesita **`user_id`** en el JSON (ID numérico de Telegram en la whitelist). En **privado**, el gateway puede inferir `user_id` desde `chat_id` cuando coinciden. En **grupos**, `user_id` del remitente es obligatorio.

## Referencias

- [DOTENV_SINGLE_SOURCE.md](../specs/features/platform/DOTENV_SINGLE_SOURCE.md)
- [API_GATEWAY_HARDENING.md](../specs/features/platform/API_GATEWAY_HARDENING.md)
