# INFRA_BOOTSTRAP_VERTICAL_PURGE_SDD

Hito 1 — Purge Quant/Trading/Finanz del core DuckClaw. Producto vertical vive en **Capadonna-Driller** (repo externo) vía extension root + DB-first; el core ya **no** incluye `capadonna_plugin`.

## Objetivo

El monorepo DuckClaw arranca y pasa tests **sin** `CAPADONNA_DRILLER_ROOT` / `DUCKCLAW_EXTENSION_ROOT` para flujos genéricos. Cero imports `duckclaw.quant.*` / `duckclaw.finance.*` en `packages/agents` y `services/api-gateway`.

## Alcance IN (estado actual)

- Eliminados paquetes `quant/`, `finance/`, bridges verticales y `capadonna_plugin.py` del monorepo.
- **HITL transversal** en `duckclaw.hitl.*` + tablas `main.code_decisions` / `main.agent_uncertainty_log` + comandos tipados `UpdateCodeDecisionStatusCommand` / `ResolveUncertaintyEventCommand`. Fly commands `/approve-code`, `/reject-code`, `/uncertainty`, `/resolve-uncertainty` y rutas admin `/code/*`, `/uncertainty/*` en `admin_domains/hitl_admin.py` usan el framework, no Driller ni `capadonna_plugin`.
- Quitar colas `quant_state_delta` del loop transversal db-writer; `state_delta_enqueue` solo enruta deltas transversales (`CONTEXT_INJECTION`, `SEMANTIC_MEMORY_UPSERT`, etc.).
- Admin + tests + docs: fixtures genéricos (`platform-orchestrator`, `ui-designer`).
- `test_forge_legacy_cleanup`: allowlist Capadonna vacía; AST prohíbe `duckclaw.capadonna_plugin` en core.

## Alcance OUT

- Wheel PyPI / merge setuptools (Hito 2 Infra Bootstrap).
- Reorganizar `services/api-gateway` → `app/`.
- Refactor completo `vaults.py`.

## Orden de ejecución (histórico)

1. Capadonna-Driller: libs en `workers/duckclaw/lib/` + pytest.
2. DuckClaw: delete packages + HITL transversal + db-writer handler purge.
3. DuckClaw: admin + tests + docs.
4. Verificación: `rg` acotado + pytest ambos repos.
5. Dos PRs (Driller primero, DuckClaw segundo).

## Criterios de aceptación

- Core arranca sin `DUCKCLAW_EXTENSION_ROOT` / `CAPADONNA_DRILLER_ROOT` para flujos genéricos.
- Comandos verticales de producto (quant/trading) no existen en core; extensiones viven fuera.
- `test_forge_legacy_cleanup` sin allowlist permanente para módulos borrados ni `capadonna_plugin.py`.
- Marcadores `capadonna`/`driller` confinados a docs/scripts ops (no runtime core).

## Destino Capadonna-Driller (producto externo)

| Módulo duckclaw (eliminado del core) | Destino Driller |
|--------------------------------------|-----------------|
| `quant/` + `finance/runtime_policy.py` | `workers/duckclaw/lib/runtime_policy.py`, `finance_runtime_policy.py` |
| `code_decision_service.py` (vertical) | sustituido por `duckclaw.hitl.code_decision_service` en core; Driller puede extender vía checkout |
| `quant_state_delta` | `workers/duckclaw/lib/quant_state_delta.py` |

## Extension root (config, no import runtime)

- `DUCKCLAW_EXTENSION_ROOT` (canónico) con fallback `CAPADONNA_DRILLER_ROOT` en `vaults.db_root()` y admin UI preview.
- Scripts ops en `scripts/README-CAPADONNA-OPS.md` apuntan al repo externo; no son parte del runtime core.

## Verificación

```bash
rg -i '\bquant\b|quant[-_]|trading|ibkr|finanz' --glob '!**/.agents/**' packages/agents services apps tests
uv run pytest tests/test_forge_legacy_cleanup.py -q
uv run pytest -q
```

---

# Hito 2 — Infra Bootstrap

**Estado:** implementado en core (`duckclaw.gateway.settings`, `verify_schema_integrity`, `duckclaw-migrate`, `duckclaw-healthcheck`, lifespan fail-fast).

**Docs:** [`docs/architecture/infra-bootstrap.md`](../../../architecture/infra-bootstrap.md)

## Criterios de aceptación Hito 2

- Gateway no arranca sin Redis + schema migrada + secretos prod (salvo `DUCKCLAW_DEV_MODE=1`).
- `duckclaw-migrate` y `duckclaw-healthcheck` operativos (entry points en `duckclaw-shared`).
- Cero `redis.config_set` / `docker` administrativo en lifespan gateway.
- Wheel unificado (Fase A3) **diferido** — solo entry points + shared importable.
