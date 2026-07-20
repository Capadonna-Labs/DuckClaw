# Infra Bootstrap (Hito 2)

Fail-fast gateway startup, schema integrity verification, and operator CLIs. Product verticals stay in Capadonna-Driller; core only checks transversal infra.

## Components

| Module | Role |
|--------|------|
| `duckclaw.gateway.settings` | Single owner for gateway env (`GatewaySettings`, `DUCKCLAW_DEV_MODE`) |
| `duckclaw.schema_migrations.verify_schema_integrity` | Read-only check: hub DB exists + all migrations applied |
| `duckclaw.cli.migrate` | Entry point `duckclaw-migrate` |
| `duckclaw.cli.healthcheck` | Entry point `duckclaw-healthcheck` (`--fix` may `docker run redis`) |
| `duckclaw.infra.readiness` | Redis + schema checks used by gateway lifespan |

## Operator flow

```bash
# 1. Migrate gateway hub (idempotent)
uv run duckclaw-migrate
# or: uv run python scripts/migrate.py

# 2. Ensure Redis is up
uv run duckclaw-healthcheck
uv run duckclaw-healthcheck --fix   # docker run redis:7-alpine when needed

# 3. Start gateway (fail-fast if Redis/schema/secrets missing in prod)
DUCKCLAW_DEV_MODE=1 uv run uvicorn services.api-gateway.main:app
```

## Production secrets

With `DUCKCLAW_DEV_MODE` unset/false, gateway startup requires at minimum:

- `DUCKCLAW_ADMIN_API_KEY`
- `OPENROUTER_API_KEY` when `DUCKCLAW_LLM_PROVIDER=openrouter`

Set `DUCKCLAW_DEV_MODE=1` for local development without admin/LLM keys.

## Schema strict mode

`DUCKCLAW_SCHEMA_STRICT=1` makes `verify_schema_integrity` fail on checksum drift (migrations edited after apply).

## Lifespan rules

Gateway lifespan:

1. Validates production secrets
2. `assert_gateway_startup_ready` (Redis ping + schema integrity)
3. Connects Redis client
4. Warms optional services in background (Telegram MCP, Reddit pool, goals ticker)

Forbidden in lifespan: `redis.config_set` deploy paths, `docker`, administrative `subprocess`.

## Packaging (Fase A)

`duckclaw-shared` exposes entry points and is importable from external repos (Capadonna-Driller) without monorepo editable paths. Unified mega-wheel (Fase A3) remains deferred.

See also: [`DB_FIRST_CORE_REFACTOR.md`](DB_FIRST_CORE_REFACTOR.md).
