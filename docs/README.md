# Documentación DuckClaw — empieza aquí

Mapa canónico de `docs/`. Las **specs normativas** viven bajo **`docs/specs/`** (no existe `specs/` en la raíz del repo).

---

## Lectura recomendada (nuevo dev)

1. **[`README.md`](../README.md)** — layout del monorepo, `uv sync`, `duckops init`, `duckops serve --gateway`.
2. **Este archivo** — qué leer según tu tarea.
3. **[`docs/specs/features/platform/DB_FIRST_CORE_REFACTOR.md`](specs/features/platform/DB_FIRST_CORE_REFACTOR.md)** — **fuente de verdad de arquitectura** (DB-first, qué es core, qué está limpio, roadmap).
4. **[`docs/architecture/system_overview.md`](architecture/system_overview.md)** — diagrama y componentes.
5. **[`docs/COMANDOS.md`](COMANDOS.md)** — PM2, Redis, Telegram, variables, cheat sheet operativo.
6. **[`docs/specs/features/platform/README.md`](specs/features/platform/README.md)** — tabla por spec: canonical / operational / stale / archived.
7. **Tu feature** — spec concreta de la tabla anterior + runbook en [`docs/operations/`](operations/) si aplica.

---

## Mapa: specs vs operations vs archive

| Carpeta | Rol | Cuándo leer |
|---------|-----|-------------|
| [`docs/specs/`](specs/) | **Normativa (SDD)** — leer antes de implementar | Cambias comportamiento del producto o contratos API |
| [`docs/operations/`](operations/) | **Runbooks** — cómo operar en prod/dev | Despliegue, heartbeat, multi-vault, observabilidad |
| [`docs/architecture/`](architecture/) | Narrativa técnica estable | Singleton writer, memoria tri-cameral, Tailscale, infra-bootstrap |
| [`docs/core/`](core/) | Capas del sistema (skills, memoria, agentes) | Profundizar en tooling y sandbox |
| [`docs/api/`](api/) | Contratos HTTP gateway / db-writer | Integrar clientes o BFF |
| [`docs/archive/`](archive/) | **Histórico** — cortes cerrados, diseños no vigentes | Contexto de PRs antiguos, no para nuevas features |
| [`apps/duckclaw-admin/docs/`](../../apps/duckclaw-admin/docs/) | Docs de la consola admin | Solo frontend admin |

---

## Notas que evitan confusiones

### `harness_core/` es core activo

El directorio [`harness_core/`](../harness_core/) en la raíz **no es legacy**. Es el runtime de **Meditate** (homeostasis de infraestructura): grafos, políticas y skills del termostato. Comando fly `/meditate`, runbook [`docs/operations/Meditate-Homeostasis.md`](operations/Meditate-Homeostasis.md).

### Train: sin API admin `/train`

Las rutas **`/api/v1/admin/train/*`** y la pestaña **`/train`** del admin **fueron retiradas** del gateway (404). Pipeline SFT/GRPO:

- Código y datasets: [`packages/agents/train/`](../packages/agents/train/)
- CLI: `uv run duckops train` (ver `packages/duckops/duckops/commands/train.py`)
- Trazas: [`docs/agents/sft_conversation_traces.md`](agents/sft_conversation_traces.md)

La spec [`ADMIN_TRAIN_UI.md`](specs/features/platform/ADMIN_TRAIN_UI.md) está **obsoleta** (marcada STALE).

### Specs obsoletas pero conservadas

Ver banner `⚠️ STALE` en [`ADMIN_TRAIN_UI.md`](specs/features/platform/ADMIN_TRAIN_UI.md), [`VLM_INTEGRATION.md`](specs/features/platform/VLM_INTEGRATION.md), [`API_GATEWAY_HARDENING.md`](specs/features/platform/API_GATEWAY_HARDENING.md).

---

## Enlaces rápidos

- Índice plataforma: [`docs/specs/features/platform/README.md`](specs/features/platform/README.md)
- Admin UI (spec): [`DUCKCLAW_ADMIN_UI.md`](specs/features/platform/DUCKCLAW_ADMIN_UI.md)
- Telegram: [`docs/specs/features/telegram-gateway/`](specs/features/telegram-gateway/)
- Tests de guardrail docs: `tests/test_db_first_guardrails_static.py`, `tests/test_forge_legacy_cleanup.py`
