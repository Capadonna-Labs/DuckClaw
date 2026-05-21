# Índice de scripts (`scripts/SCRIPTS_INDEX.md`)

Utilidades **puntuales** del monorepo. Runtime de producción: `services/` + `duckops`. Normativa: `specs/`.

## Uso habitual

| Script | Cuándo |
|--------|--------|
| [`doctor.py`](doctor.py) | Diagnóstico local (Redis, DuckDB, PAT, MLX) |
| [`bootstrap_dbs.py`](bootstrap_dbs.py) | Crear/esquemas DB iniciales |
| [`bootstrap_team_admin.py`](bootstrap_team_admin.py) | Alta admin en whitelist (`user_id` por argumento) |
| [`register_webhooks.py`](register_webhooks.py) | Registrar webhooks Telegram |
| [`duckclaw_setup_wizard.py`](duckclaw_setup_wizard.py) | Wizard legacy (preferir `duckops init`) |
| [`verify_pqrsd_telegram_pipeline.py`](verify_pqrsd_telegram_pipeline.py) | Smoke pipeline PQRSD |
| [`sanitize_traces_for_gemma.py`](sanitize_traces_for_gemma.py) | Curar JSONL SFT |
| [`check_authorized_users.py`](check_authorized_users.py) | Listar whitelist en DuckDB hub |

## Por carpeta

| Carpeta | Contenido |
|---------|-----------|
| [`quant/`](quant/) | Jobs MOC, ML4T batch, HRP (`moc_pipeline.py`, cron VPS) |
| [`capadonna/`](capadonna/) | Ops VPS Quant/IBKR (señales, OHLCV, hooks deploy) |
| [`data_fetch/`](data_fetch/) + [`data_prep/`](data_prep/) + [`plots/`](plots/) | Pipeline PM2.5 salud — ver [`README_pm25_health_pipeline.md`](README_pm25_health_pipeline.md) |
| [`smoke/`](smoke/) | Probes MCP stdio (GitHub, Telegram) |
| [`experimental/`](experimental/) | One-offs locales (no CI) |
| [`telegram/`](telegram/) | Utilidades Telegram puntuales |

## CLI sueltos

```bash
uv run python scripts/openweather_city.py "Bogotá"
uv run python scripts/crm_origin_check.py
uv run python scripts/smoke/smoke_github_mcp_stdio.py
```

## No versionar

- Secretos → `.env` (ver `.env.example`)
- Bundle Leila Store → `/Leila/` (`.gitignore`; extracción a repo propio)
- Artefactos → `db/`, `logs/`, `packages/agents/train/gemma4/`
