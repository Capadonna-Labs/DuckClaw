# Worker tool orchestration (manifest-driven)

## Objetivo

Declarar en `manifest.yaml` cuándo forzar herramientas, encadenar tools (p. ej. `get_current_time` → `read_sql`), confirmar acciones pendientes ("Procede") y reintentar planes del manager — **sin** heurísticas hardcodeadas por worker en `factory.py` / `manager_graph.py`.

Workers empaquetados fuera del monorepo importan `duckclaw` y aportan solo YAML, prompts y guardrails en su `worker_dir`.

## Bloque manifest: `tool_orchestration`

Opcional. Si está presente, el runtime en [`tool_orchestration.py`](../../../packages/agents/src/duckclaw/workers/tool_orchestration.py) tiene prioridad sobre heurísticas legacy del mismo dominio (p. ej. finanz deudas/cuentas).

### `clock_anchor`

Ancla temporal antes de intents de ledger:

```yaml
clock_anchor:
  tool: get_current_time
  before_intents: [ledger_read, ledger_write]
```

### `intents`

Mapa `intent_id → { patterns: [regex], force_first_tool: read_sql|admin_sql|... }`.

Los patrones son regex Python (case-insensitive recomendado con `(?i)`).

### `tool_chains`

Encadena la siguiente tool cuando el turno ya ejecutó tools listadas:

```yaml
tool_chains:
  - after_tools: [get_current_time]
    when_intent: ledger_read   # string o lista
    force_next: read_sql
```

Fix principal: tras `get_current_time` forzado, el segundo paso del agente **debe** forzar `read_sql` aunque `already_has_tool_result` sea true.

### `affirm_followup`

Mensajes cortos de confirmación anclados al último assistant con acciones pendientes:

```yaml
affirm_followup:
  short_affirm_patterns: ['(?i)^\\s*procede\\s*\\.?$']
  pending_action_patterns: ['acciones que voy', 'admin_sql']
  planned_task_guardrail: guardrails/ledger_affirm_planned.md
```

`planned_task_guardrail` es relativo a `worker_dir` (template externo).

### `replan`

Reglas post-invoke del manager:

```yaml
replan:
  rules:
    - when_intent: ledger_write
      require_tool: admin_sql
      unless_tools: [admin_sql]
```

Si el intent del mensaje original coincide y `require_tool` no apareció en tools usadas → replan (hasta `DUCKCLAW_AGENT_MAX_PLAN_ATTEMPTS`).

## Integración runtime

| Componente | Uso |
|------------|-----|
| `WorkerSpec.tool_orchestration_config` | Dict crudo desde manifest |
| `factory.agent_node` | `resolve_forced_tool()` → force flags o early return gct |
| `manager_graph.plan` | `try_manifest_affirm_followup()` antes de fast-paths Quant |
| `manager_graph.invoke_worker` | `replan_rule_triggered()` |

## Compatibilidad legacy

Workers **sin** `tool_orchestration` siguen usando heurísticas existentes (`is_finanz`, etc.). Migración gradual; no eliminar legacy en la misma entrega que introduce el bloque.

## Referencias

- [FINANZ_ADMIN_SQL_DB_WRITER.md](../finanz/FINANZ_ADMIN_SQL_DB_WRITER.md) — escrituras vía `admin_sql`
- [AGENT_MANAGER_REPLAN_RESILIENCE.md](../cognitive/AGENT_MANAGER_REPLAN_RESILIENCE.md) — reintentos de plan
- [TIME_CONTEXT_SKILL.md](../cognitive/TIME_CONTEXT_SKILL.md) — `get_current_time`

## Criterios de aceptación

1. Finanz con manifest de orquestación: "Dame un resumen de mis deudas" ejecuta `get_current_time` y luego `read_sql` en el mismo turno.
2. "Agrega 50k deuda mamá" fuerza `admin_sql` (o replan si solo hubo `read_sql`).
3. "Procede" tras assistant con plan de ajustes inyecta TAREA desde guardrail del worker, no plan genérico.
4. Motor testeable sin importar `is_finanz()` — fixture `load_manifest("finanz")`.
