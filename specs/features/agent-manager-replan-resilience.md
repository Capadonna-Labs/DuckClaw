# Manager: replan y resiliencia (plan → invoke worker)

## Objetivo

Tras fallos **recuperables** en la delegación al worker (inferencia caída, respuesta sin tools con indicios de error de backend), el grafo Manager puede **volver al nodo de plan** con un contador de intentos y **reforzar** la heurística de tools en el worker (Finanz: `read_sql` en reintentos).

## Variables de entorno

| Variable | Rol |
|----------|-----|
| `DUCKCLAW_AGENT_MAX_PLAN_ATTEMPTS` | Máximo de ciclos plan → invoke (default `3`, rango 1–10). |
| `DUCKCLAW_AGENT_REPLAN_STRATEGY` | `hybrid` (default) u `off` para desactivar el bucle de replan. |

Independiente de los reintentos **por invocación** del LLM (`DUCKCLAW_LLM_INVOKE_*`).

## Comportamiento

1. Cada mensaje nuevo reinicia el contador en el nodo `router`.
2. Tras `invoke_worker`, si aplica replan, el enrutador vuelve a `plan` con `plan_attempt_index` incrementado y causas acumuladas en `plan_failure_reasons`.
3. Al agotar intentos, la respuesta al usuario usa un mensaje único con causas concretas (`format_exhausted_plan_failure`).

## Implementación

- `packages/agents/src/duckclaw/graphs/agent_resilience.py`
- `packages/agents/src/duckclaw/graphs/manager_graph.py` (arista `invoke_worker` → `plan`)
- Worker: `plan_attempt_index` en estado del worker → `packages/agents/src/duckclaw/workers/factory.py` (escalada Finanz).
