# Empezar con DuckClaw

Entrada mínima para un dev nuevo. Detalle normativo: [`docs/specs/features/platform/PLUG_AND_PLAY_ONBOARDING.md`](specs/features/platform/PLUG_AND_PLAY_ONBOARDING.md).

## Requisitos

- Python 3.11+ y [uv](https://docs.astral.sh/uv/)
- Node 20+ (solo si usas la consola admin)
- Redis local o Docker (el wizard puede levantar Redis)
- PM2 (`npm i -g pm2`) para stack local recomendado

## Camino rápido

```bash
git clone <repo> duckclaw && cd duckclaw
uv sync
uv run duckops doctor          # diagnóstico sin tocar el sistema
uv run duckops init            # Sovereign Wizard v2 (TUI); --classic para wizard Rich
uv run duckclaw-migrate        # idempotente tras init o pull
uv run duckops serve --gateway --pm2   # gateway + db-writer (--stack por defecto)
uv run duckops doctor --smoke  # probe GET /health tras arrancar stack
```

Consola admin:

```bash
cd apps/duckclaw-admin
# .env.local se sincroniza en duckops init; si falta: cp .env.example .env.local
npm install && npm run dev
```

Abre `http://127.0.0.1:3001` y entra con `DUCKCLAW_ADMIN_EMAIL` / `DUCKCLAW_ADMIN_PASSWORD` del `.env` raíz.

## Siguiente lectura

1. [`docs/README.md`](README.md) — mapa de documentación
2. [`docs/specs/features/platform/DB_FIRST_CORE_REFACTOR.md`](specs/features/platform/DB_FIRST_CORE_REFACTOR.md) — arquitectura
3. [`docs/COMANDOS.md`](COMANDOS.md) — operación diaria

## Comandos útiles

| Comando | Uso |
|---------|-----|
| `uv run duckops doctor` | Redis, schema, admin key, puerto |
| `uv run duckops doctor --smoke` | Lo anterior + GET `/health` |
| `uv run duckops smoke` | Alias de `doctor --smoke` |
| `uv run duckclaw-healthcheck` | Infra Redis (+ probe gateway opcional) |
| `uv run duckclaw-migrate --verify-only` | Solo verificar migraciones |
| `uv run duckops stack status` | Estado PM2 gateway / db-writer |
