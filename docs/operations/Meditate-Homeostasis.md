# Meditate — homeostasis de infraestructura (Harness Core)

Meditate es el **termostato de infraestructura** de DuckClaw: telemetría DuckDB → distancia respecto al **manifiesto homeostasis** → acciones correctivas vía cola `duckclaw:state_delta:meditate` y db-writer.

El manifiesto (`/goals`) es la **fuente única** de metas de dominio y umbrales infra que meditate contrasta en cada ciclo. `/crons` solo programa revisiones proactivas del agente LLM; no define metas.

## Manifiesto homeostasis (`/goals`)

Persistido en `harness_core.homeostasis_targets.targets_json` por tenant:

```json
{
  "infra": { "error_rate_pct": 2.0, "stale_tasks_count": 0, ... },
  "goals": [
    { "belief_key": "latency_ms", "target_value": 250.0, "threshold": 25.0, "title": "Latency budget" }
  ]
}
```

| Comando | Acción |
|---------|--------|
| `/goals` | Lista metas (✓/⚠️) + umbrales infra |
| `/goals <texto>` | Añade meta de dominio |
| `/goals --rm <belief_key>` | Quita meta |
| `/goals --set <metric> <value>` | Ajusta umbral infra |
| `/goals --reset` | Restaura defaults |
| `/goals --migrate` | Copia metas legacy de `agent_config` al manifiesto |

Escritura vía cola `UPSERT_HOMEOSTASIS_MANIFEST` (db-writer).

## Mensaje de alineación

Cuando infra y metas están OK, meditate deja de mostrar un `noop` opaco y emite un mensaje explícito, p. ej.:

> Contexto alineado con las metas homeostasis. Metas: Latency budget target=250 (obs: 200 ✓), … Infra: sin tareas stale, …

Visible en:

- Respuesta fly `/meditate --delta …` (primer ciclo y resumen)
- Heartbeat admin `[meditate]` (scheduler proactivo)
- Campo `alignment_message` en el resultado del ciclo

## Programación meditate

| Mecanismo | Descripción |
|-----------|-------------|
| `/meditate --delta 4h` | Intervalo en `agent_config` (`meditate_delta_seconds`) |
| `/meditate --delta off` | Desactiva el scheduler |
| Tool `configure_meditate_homeostasis` | El agente activa (`10min`, `4h`) o desactiva (`off`) |
| Tool `get_meditate_homeostasis_status` | Schedule + snapshot del manifiesto |
| Tool `manage_homeostasis_goals` | Espejo de `/goals` (list/add/remove/set_infra) |
| Heartbeat | `_run_meditate_proactive_tick()` cada ~45s |
| Admin | `POST /api/v1/admin/meditate/tick` |

El grafo se invoca desde heartbeat/fly; **no** envía `SYSTEM_EVENT` al worker LLM (eso es `/crons --delta`).

## Grafo (`harness_core/graphs/meditate_graph.py`)

1. `node_sweep_telemetry` — RO DuckDB
2. `node_calculate_distance` — `strix_compute_delta`
3. `node_plan_correction` — reglas fijas + LLM opcional
4. `node_dispatch_actions` — cola meditate, alertas admin, circuit breaker Redis

## Acciones permitidas (Zero-Trust)

| `action_type` | HITL | Ejecución |
|---------------|------|-----------|
| `purge_stale_tasks` | no | UPDATE/CANCEL vía db-writer |
| `quarantine_corrupted_memory` | no | `embedding_status = QUARANTINE` |
| `request_compaction` | sí | Solo alerta admin |
| `alert_admin` | sí | SSE `meditate_critical` |
| `circuit_breaker_pause` | sí | Redis TTL 1h |
| `noop` | no | Log / audit (+ `alignment_message` si OK) |

## Métricas (v1)

- `error_rate_pct`, `avg_latency_ms`, `stale_tasks_count`, `memory_fragmentation_index`, `db_lock_events`

## Despliegue

Tras merge:

```bash
pm2 restart DuckClaw-Gateway DuckClaw-DB-Writer DuckClaw-Heartbeat
```

Migración one-shot por vault tenant:

```
/goals --migrate
```

Verificar: `harness_core.homeostasis_targets` con `goals` poblado; `/meditate --delta 10m` muestra metas alineadas.

## Relación con Homeostasis-Heartbeat.md

- **Dominio + metas**: manifiesto `/goals`, alineación en `/crons --delta` scheduler (lee manifiesto).
- **Infra (meditate)**: telemetría y DML acotado sin turno de chat.
