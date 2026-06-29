# COMANDOS · DuckClaw

Runbook operativo canónico. Arquitectura: [`docs/specs/features/platform/DB_FIRST_CORE_REFACTOR.md`](specs/features/platform/DB_FIRST_CORE_REFACTOR.md).

## Spawn / VM genérica

```bash
export OPENROUTER_API_KEY=sk-or-...
export DUCKCLAW_ADMIN_API_KEY=...
export DUCKDB_PATH=db/private/default/duckclaw.duckdb
bash scripts/deploy/spawn-install.sh

# o manualmente:
uv run python scripts/bootstrap_dbs.py --core-only --only db/private/default/duckclaw.duckdb
pm2 start config/ecosystem.spawn.config.cjs
pm2 save
```

Plantilla: `config/.env.spawn.example`. Spec: [`SPAWN_GENERIC_DEPLOY.md`](specs/features/platform/SPAWN_GENERIC_DEPLOY.md).

---

## Stack local (PM2 / dev)

```bash
uv run duckops init
uv run duckops serve --gateway              # dev sin PM2
uv run duckops serve --pm2 --gateway        # regenera ecosystem + PM2
uv run python scripts/doctor.py

pm2 start config/ecosystem.db-writer.config.cjs
pm2 start config/ecosystem.api.config.cjs --only DuckClaw-Gateway
pm2 start config/ecosystem.mcp.config.cjs
pm2 save
pm2 restart DuckClaw-Gateway --update-env   # tras cambiar .env

# MLX texto local (opcional; alias: config/ecosystem.config.cjs)
pm2 start config/ecosystem.mlx.config.cjs
```

---

## Telegram

Spec: [`specs/features/telegram-gateway/TELEGRAM.md`](specs/features/telegram-gateway/TELEGRAM.md).

```bash
tailscale up
tailscale funnel --bg 8000                  # mismo puerto que DUCKCLAW_GATEWAY_PORT
uv run duckops ingress telegram-check
uv run duckops ingress telegram-register-webhooks
```

Comandos fly: `/team`, `/workers`, `/vault`, `/heartbeat on|off`, `/context on|off`.

---

## Admin UI

```bash
pm2 restart DuckClaw-Gateway --update-env
pnpm admin:dev    # o: cd apps/duckclaw-admin && pnpm dev
```

Variables en `apps/duckclaw-admin/.env.local`: `DUCKCLAW_GATEWAY_URL`, `DUCKCLAW_ADMIN_API_KEY` (misma clave que gateway).

Servicios: Redis + DuckClaw-DB-Writer + DuckClaw-Gateway.

### Context monitor (compactación LLM del hilo)

Por defecto activo en el gateway. Variables en `.env` (ver `.env.example`):

```bash
DUCKCLAW_CONTEXT_PRUNE_ENABLED=1
DUCKCLAW_CONTEXT_PRUNE_MAX_TOKENS_M=4
DUCKCLAW_CONTEXT_FOLD_PERSIST=1
pm2 restart DuckClaw-Gateway --update-env
```

El resumen compactado se persiste en la bóveda DuckDB conectada por conversación (`agent_config`, clave `context_fold_summary`). Opt-out global: `DUCKCLAW_CONTEXT_PRUNE_ENABLED=0`. Opt-out por worker: `context_pruning: { enabled: false }` en manifest.

**Compactación manual:** `/summarize` en playground, Telegram o cualquier canal con fly commands. Usa el historial Redis (gateway) o `api_conversation`/`telegram_conversation` en la bóveda, ejecuta el fold LLM y guarda el resumen sin esperar al umbral automático.

---

## ComfyUI (opcional)

```bash
pm2 start config/ecosystem.comfyui.config.cjs --update-env
```

En `.env`: `COMFYUI_API_URL=http://127.0.0.1:8188`, `DUCKCLAW_COMFYUI_INBOUND_EDIT=1` (edición foto+caption en Telegram).

Implementación: `packages/agents/src/duckclaw/forge/skills/comfyui_bridge.py` y admin **Gen → Image**.

---

## Train / trazas SFT (CLI, sin admin /train)

```bash
uv run duckops train -c config/lora_config.yaml
# Trazas JSONL: packages/agents/train/conversation_traces/
```

Ver [`packages/agents/train/`](../packages/agents/train/) (`train_sft.py`, `config/lora_config.yaml`).

---

## GitHub MCP (smoke)

```bash
uv run python scripts/smoke/smoke_github_mcp_stdio.py
```

Variable: `GITHUB_TOKEN` en `.env`. Diagnóstico: `uv run python scripts/doctor.py`.
