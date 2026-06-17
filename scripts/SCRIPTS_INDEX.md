# Índice de scripts (`scripts/SCRIPTS_INDEX.md`)

Utilidades **puntuales** del monorepo. Runtime de producción: `services/` + `duckops`. Normativa: `docs/specs/`.

## Uso habitual

| Comando preferido | Script compatible | Cuándo |
|-------------------|-------------------|--------|
| `uv run python scripts/doctor.py` | [`doctor.py`](doctor.py) | Diagnóstico local (Redis, DuckDB, PAT, MLX) |
| `uv run duckops db bootstrap` | [`bootstrap_dbs.py`](bootstrap_dbs.py) | Crear/esquemas DB iniciales (`--core-only` perfil Spawn) |
| `uv run duckops deploy spawn-install` | [`deploy/spawn-install.sh`](deploy/spawn-install.sh) | Instalación desatendida VM (Spawn) |
| `uv run python scripts/bootstrap_team_admin.py` | [`bootstrap_team_admin.py`](bootstrap_team_admin.py) | Alta admin en whitelist (`user_id` por argumento) |
| `uv run duckops ingress telegram-register-webhooks` | [`register_webhooks.py`](register_webhooks.py) | Registrar webhooks Telegram |
| `uv run duckops init` | [`duckclaw_setup_wizard.py`](duckclaw_setup_wizard.py) | Wizard legacy con `duckops init --classic` |
| `uv run python scripts/sanitize_traces_for_gemma.py` | [`sanitize_traces_for_gemma.py`](sanitize_traces_for_gemma.py) | Curar JSONL SFT |
| `uv run duckops db authorized-users` | [`check_authorized_users.py`](check_authorized_users.py) | Listar whitelist en DuckDB hub |

## Por carpeta

| Carpeta | Contenido |
|---------|-----------|
| [`smoke/`](smoke/) | Probes MCP stdio (GitHub, Telegram) |
| [`experimental/`](experimental/) | Laboratorio local (vacío por defecto) |
| [`telegram/`](telegram/) | Reservado; utilidades en `duckops ingress` |

## CLI sueltos

```bash
uv run duckops ingress serve-admin
uv run duckops mcp prefetch reddit
uv run duckops comfyui start --dry-run
uv run python scripts/smoke/smoke_github_mcp_stdio.py
```

## No versionar

- Secretos → `.env` (ver `.env.example`)
- Artefactos → `db/`, `logs/`, `packages/agents/train/gemma4/`
