# Índice de scripts (`scripts/SCRIPTS_INDEX.md`)

Utilidades **puntuales** del monorepo. Runtime de producción: `services/` + `duckops`. Normativa: `specs/`.

## Uso habitual

| Comando preferido | Script compatible | Cuándo |
|-------------------|-------------------|--------|
| `uv run python scripts/doctor.py` | [`doctor.py`](doctor.py) | Diagnóstico local (Redis, DuckDB, PAT, MLX) |
| `uv run duckops db bootstrap` | [`bootstrap_dbs.py`](bootstrap_dbs.py) | Crear/esquemas DB iniciales (`--core-only` perfil Spawn) |
| `uv run duckops deploy spawn-install` | [`deploy/spawn-install.sh`](deploy/spawn-install.sh) | Instalación desatendida VM (Spawn; shell conservado por bootstrap de sistema) |
| `uv run python scripts/bootstrap_team_admin.py` | [`bootstrap_team_admin.py`](bootstrap_team_admin.py) | Alta admin en whitelist (`user_id` por argumento) |
| `uv run duckops ingress telegram-register-webhooks` | [`register_webhooks.py`](register_webhooks.py) | Registrar webhooks Telegram |
| `uv run duckops init` | [`duckclaw_setup_wizard.py`](duckclaw_setup_wizard.py) | Wizard legacy disponible con `duckops init --classic` |
| `uv run python scripts/verify_pqrsd_telegram_pipeline.py` | [`verify_pqrsd_telegram_pipeline.py`](verify_pqrsd_telegram_pipeline.py) | Smoke pipeline PQRSD |
| `uv run python scripts/sanitize_traces_for_gemma.py` | [`sanitize_traces_for_gemma.py`](sanitize_traces_for_gemma.py) | Curar JSONL SFT |
| `uv run duckops db authorized-users` | [`check_authorized_users.py`](check_authorized_users.py) | Listar whitelist en DuckDB hub |

## Por carpeta

| Carpeta | Contenido |
|---------|-----------|
| [`quant/`](quant/) | Jobs MOC, ML4T batch, HRP (`moc_pipeline.py`, cron VPS) |
| [`capadonna/`](capadonna/) | Ops VPS Quant/IBKR (señales, OHLCV, hooks deploy) |
| [`data_fetch/`](data_fetch/) + [`data_prep/`](data_prep/) + [`plots/`](plots/) | Pipeline PM2.5 salud — ver [`README_pm25_health_pipeline.md`](README_pm25_health_pipeline.md) |
| [`smoke/`](smoke/) | Probes MCP stdio (GitHub, Telegram) |
| [`experimental/`](experimental/) | Reservado para laboratorio local; actualmente sin scripts activos |
| [`telegram/`](telegram/) | Reservado; utilidades operativas nuevas viven en `duckops ingress` |

## CLI sueltos

```bash
uv run duckops ingress serve-admin
uv run duckops mcp prefetch reddit
uv run duckops comfyui start --dry-run
uv run python scripts/smoke/smoke_github_mcp_stdio.py
```

## No versionar

- Secretos → `.env` (ver `.env.example`)
- Bundle Leila Store → `/Leila/` (`.gitignore`; extracción a repo propio)
- Artefactos → `db/`, `logs/`, `packages/agents/train/gemma4/`
