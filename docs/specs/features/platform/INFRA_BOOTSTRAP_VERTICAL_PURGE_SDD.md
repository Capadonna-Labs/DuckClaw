# INFRA_BOOTSTRAP_VERTICAL_PURGE_SDD

Hito 1 — Purge Quant/Trading/Finanz del core DuckClaw. Producto vertical vive en **Capadonna-Driller** vía `capadonna_plugin` + DB-first.

## Objetivo

El monorepo DuckClaw arranca y pasa tests **sin** `CAPADONNA_DRILLER_ROOT` para flujos genéricos. Cero imports `duckclaw.quant.*` / `duckclaw.finance.*` en `packages/agents` y `services/api-gateway`.

## Alcance IN

- Eliminar paquetes `quant/`, `finance/`, `code_decision_service.py`, `quant_investor_profile.py`.
- `/approve-code`, `/reject-code` → `dispatch_capadonna_fly_command`; mensaje explícito si plugin ausente.
- Quitar colas `quant_state_delta` del loop transversal db-writer.
- Admin + tests + docs: fixtures `platform-orchestrator`, `ui-designer`.
- `test_forge_legacy_cleanup`: allowlist vacía salvo `capadonna_plugin.py`.

## Alcance OUT

- Wheel PyPI / merge setuptools (Hito 2 Infra Bootstrap).
- Reorganizar `services/api-gateway` → `app/`.
- Refactor completo `vaults.py`.

## Orden de ejecución

1. Capadonna-Driller: libs en `workers/duckclaw/lib/` + pytest.
2. DuckClaw: delete packages + plugin dispatch + db-writer handler.
3. DuckClaw: admin + tests + docs.
4. Verificación: `rg` acotado + pytest ambos repos.
5. Dos PRs (Driller primero, DuckClaw segundo).

## Criterios de aceptación

- Core arranca sin `CAPADONNA_DRILLER_ROOT`.
- Comandos verticales: mensaje Capadonna-Driller no configurada, no stacktrace.
- `test_forge_legacy_cleanup` sin allowlist permanente para módulos borrados.
- Marcadores verticales confinados a `capadonna_plugin.py` (facade de extensión).

## Destino Capadonna-Driller

| Módulo duckclaw (eliminado) | Destino Driller |
|-----------------------------|-----------------|
| `quant/` + `finance/runtime_policy.py` | `workers/duckclaw/lib/runtime_policy.py`, `finance_runtime_policy.py` |
| `code_decision_service.py` | `workers/duckclaw/lib/code_decision_service.py` |
| `quant_state_delta` | `workers/duckclaw/lib/quant_state_delta.py` |

## Facade core

`packages/agents/src/duckclaw/capadonna_plugin.py`:

- `load_capadonna_lib`, `dispatch_capadonna_fly_command`
- `push_capadonna_state_delta_sync` (dreamer / extensión)
- `approve_capadonna_code_decision`, `reject_capadonna_code_decision`
- Helpers de contexto visual: `capadonna_tool_*`, `set_capadonna_tool_context`

## Verificación

```bash
rg -i '\bquant\b|quant[-_]|trading|ibkr|finanz' --glob '!**/.agents/**' packages/agents services apps tests
uv run pytest tests/test_forge_legacy_cleanup.py -q
uv run pytest -q
cd ~/Desktop/Capadonna-Driller/workers/duckclaw && pytest -q
```
