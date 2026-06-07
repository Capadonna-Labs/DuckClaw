# DuckClaw - Agent Instructions

## First reads
- `.cursorrules` — philosophy, SOLID, SDD workflow. Read before any code change.
- `specs/SDD_INDEX.md` — find relevant specs. No feature code without an approved spec.

## Monorepo layout
```
services/       # Long-running processes (FastAPI)
  api-gateway/  # FastAPI front door (main.py)
  db-writer/    # Singleton DuckDB writer (only process with write access)
  heartbeat/    # Proactive messaging
  ibkr-ohlcv-api/
packages/       # Libraries (editable via pyproject.toml [tool.uv.sources])
  agents/       # LangGraph agent logic, templates, skills
  core/         # C++/Python core bindings
  duckops/      # CLI wizard (`uv run duckops ...`)
  shared/       # Shared utilities
  mcp/          # MCP servers (telegram, duckclaw)
apps/
  duckclaw-admin/  # Next.js admin UI (pnpm)
config/           # PM2 ecosystem files, MCP config, lora config
specs/            # Source of truth — read before implementing
docs/             # Runbooks, COMANDOS cheat sheet
tests/            # 160+ pytest tests
scripts/          # Utility scripts, doctor, migrations
```

## Commands

```bash
uv sync                    # Install Python deps
pnpm install               # Install admin UI deps (apps/duckclaw-admin)
uv run duckops init        # Interactive setup wizard
uv run duckops serve --gateway  # Dev server (no PM2)
uv run duckops serve --pm2 --gateway  # PM2 gateway
pnpm admin:dev             # Admin UI dev server
pnpm stack:up              # duckops stack up shorthand
```

## Testing

```bash
uv run pytest tests/ -v -m "not integration"  # Unit tests (CI default)
uv run pytest tests/run_singleton_writer_pipeline.py -v -m integration  # Integration (needs Redis)
uv run duckops init --smoke  # Quick smoke test
```

- Markers: `integration` (Redis needed), `slow` (DuckDB extensions/seed), `requires_docker` (Strix sandbox)
- `conftest.py` auto-sets `REDIS_URL=redis://127.0.0.1:6379/0` and `DUCKCLAW_TEST_DUCKDB_HOME`
- Tests isolate env from `.env` via `env_isolation.py` (autouse fixture)
- Single test: `uv run pytest tests/test_foo.py -v -k "test_name"`

## Architecture must-knows

- **Singleton Writer**: Only `services/db-writer` writes to DuckDB (`read_only=False`). Everything else reads (`read_only=True`). Writes go via Redis queue → db-writer applies.
- **DuckDB** is the analytical state store (SQL + PGQ + VSS triple memory).
- **Redis** chains: gateway → Redis → db-writer.
- **MCP** for tools: GitHub MCP (Docker), Reddit MCP (npx), Telegram MCP.
- **Cold start**: Reddit MCP can take 2-5 min on first invoke (npx). Prefetch: `bash scripts/prefetch_mcp_reddit.sh`.
- **MLX local inference**: needs separate venv (Python≥3.10). Vision needs Python≥3.11<3.13. See `.env.example` for VLM config.
- **Admin UI BFF**: browser never calls gateway directly — all admin API routes go through `apps/duckclaw-admin/src/app/api/admin/*` which injects `X-Admin-Key`.
- **Traffic**: internal Mac↔VPS only via Tailscale (zero-trust).

## Developer conventions

- `Async-First` all Python. No blocking libs.
- `Pydantic v2` strict validation on all API inputs and configs.
- `FastAPI Depends` for DI (Redis, DB, config).
- `RFC 7807` Problem Details for API errors.
- `pyproject.toml` is the workspace root — `uv` resolves editable packages from `[tool.uv.sources]`.
- `mypy` is configured in `config/mypy.ini` (python 3.9 target, lenient).
- `pytest` markers and env setup in `pyproject.toml [tool.pytest.ini_options]`.

## CI (GitHub Actions)
- Python 3.12, uv, cmake
- Runs: `uv run pytest tests/ -v -m "not integration" --ignore=tests/run_singleton_writer_pipeline.py --ignore=tests/deprecated`
- Integration: `REDIS_URL`, `RUN_SINGLETON_PIPELINE_INTEGRATION=1` on `tests/run_singleton_writer_pipeline.py`
- Redis 7-alpine service container

## Spec-driven development
- Read `specs/SDD_INDEX.md` first. Core specs (00-04) cover infrastructure, memory, skills, cognition.
- Feature specs in `specs/features/`. Index: `specs/features/FEATURES_INDEX.md`.
- No substantial feature without an approved spec.
