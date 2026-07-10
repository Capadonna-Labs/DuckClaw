# Loop — auto-mejora cognitiva

`/loop` programa o dispara **auto-mejora cognitiva** del worker asignado al chat: el agente evalúa alineación con el manifiesto `/goals` y planifica correcciones con sus tools.

No ejecuta el grafo Harness de infraestructura (telemetría DuckDB sin LLM). Ese camino queda solo para admin/legacy.

> **Nota:** `/meditate*` es alias deprecated de `/loop*` (compat release N).

## Manifiesto homeostasis (`/goals`)

Persistido en `harness_core.homeostasis_targets.targets_json` por tenant. Metas y umbrales se editan solo con `/goals` o `manage_homeostasis_goals`.

| Comando | Acción |
|---------|--------|
| `/goals` | Lista metas + umbrales |
| `/goals <texto>` | Añade meta de dominio (`goal_kind=task` por defecto) |
| `/goals rm <goal_id>` | Elimina una meta (por `belief_key` o índice del listado) |
| `/goals rm all` | Elimina todas las metas de dominio (conserva umbrales infra) |
| `/goals --set <metric> <value>` | Ajusta umbral |
| `/goals --monitor <goal_id>` | Marca meta como revisión continua (nunca “completada”) |
| `/goals --task <goal_id>` | Vuelve a tratar la meta como tarea discreta |
| `/goals --priority <goal_id> <n>` | Asigna prioridad numérica (1 = atender primero) |

### Prioridad de metas

Cada meta tiene `priority` (entero ≥ 1). **Menor número = mayor prioridad**: P1 se atiende antes que P2. El listado `/goals`, `/loop --status` y los SYSTEM_EVENT de `/loop` ordenan y etiquetan metas así. Nueva meta sin prioridad explícita recibe `max(priority)+1`.

### Tipos de meta (`goal_kind`)

| Tipo | Uso |
|------|-----|
| `task` (default) | Tarea concreta; puede cumplirse y cerrarse vía evidencia + HITL |
| `monitor` | Objetivo persistente (ej. latencia bajo 250 ms, tasa de error); se revisa en cada `/loop`; desalineación bloquea HITL igual que `task`; **nunca** se declara cumplida ni cierra con `/loop-approve` |

## Comandos loop

| Comando | Acción |
|---------|--------|
| `/loop` | Ciclo inmediato one-shot (SYSTEM_EVENT al worker) |
| `/loop on` | **Modo conversación activa por turnos** (agent↔user) hasta approve u off |
| `/loop on --delta 20min` | Turnos + timeout: auto-ciclo si no respondes tras silencio |
| `/loop on 4h` | Legacy: ticks por reloj vía Heartbeat |
| `/loop off` | Detiene modo activo / programación |
| `/loop --self`, `--now` | Alias de `/loop` |
| `/loop --delta 4h` | Auto-ciclo tras silencio desde último mensaje (usuario o agente) |
| `/loop --delta off` | Quita timeout/auto inactividad; conserva `/loop on` si estaba activo |
| `/loop --status` | Alineación /goals + pie próximo ciclo (sin `/summarize`) |
| `/loop-approve [uuid]` | HITL: confirma homeostasis **y apaga** modo activo |
| `/loop-reject [uuid] [razón]` | HITL: rechaza; modo activo **sigue** |

## Modo `/loop --delta` (inactividad)

Heartbeat compara `now - loop_last_activity_epoch` con el intervalo configurado. La ancla se actualiza en cada mensaje usuario **o** agente persistido (Gateway).

| Variante | Comportamiento |
|----------|----------------|
| `/loop --delta 4h` | Auto-ciclo tras ~4h de silencio; no requiere mensaje usuario |
| `/loop on --delta 20min` | Turnos normales; si no respondes tras ~20min desde último mensaje, auto-ciclo |
| `/loop on 4h` | Reloj fijo (`loop_last_fire_epoch`); sin cambios |

`loop_delta_idle=1` distingue inactividad de reloj legacy (`loop_delta_idle=0`).

## Modo activo por turnos (`/loop on`)

No usa intervalo de reloj. Cadencia = mensajes:

1. `/loop on` → ciclo inmediato + `loop_active=1`, `loop_delta_seconds=0`
2. Agente responde en el chat (outbound) y queda `loop_awaiting_user=1`
3. Usuario escribe → wrap SYSTEM_EVENT + siguiente turno agente → vuelve a esperar
4. Si alineado **y sin metas monitor** → `request_homeostasis_validation` + pedir approve
5. Con metas `monitor` en manifiesto: reportar alineación cada ciclo; **no** `request_homeostasis_validation`
6. Stop solo con `/loop off` o `/loop-approve` exitoso (solo aplica si no hay metas monitor)

Así no se solapan turnos: el agente espera respuesta del usuario entre ciclos.

## Flujo cognitivo (cualquier worker)

1. Fly o turno usuario en modo activo envía `[SYSTEM_EVENT: Ciclo de auto-mejora …]` (`[Ciclo loop]`)
2. El worker usa `assess_crons_alignment` / `evaluate_homeostasis` y tools del manifest
3. Si métricas alineadas **y** `hitl_declarable=true` → `request_homeostasis_validation` y detener (metas monitor: solo reportar estado)
4. Usuario responde `/loop-approve` o `/loop-reject`
5. Si desalineado → planifica con tools del worker y pregunta en el chat

Si hay validación HITL pendiente, el SYSTEM_EVENT recuerda el `validation_id`.

Metas solo desde `/goals`. Revisión proactiva ligera: `/crons --delta` (comando separado).

## HITL homeostasis

| Comando | Acción |
|---------|--------|
| `request_homeostasis_validation` (tool) | Agente crea pending con snapshot goals/métricas |
| `/loop-approve [uuid]` | Usuario confirma + clear schedule/modo activo |
| `/loop-reject [uuid] [razón]` | Usuario rechaza; agente no debe declarar equilibrio |

Estado pending en `agent_config` (`loop_hitl_pending` por chat; lectura dual `meditate_hitl_pending`).

## Tools agente

| Tool | Rol |
|------|-----|
| `assess_crons_alignment` | Diagnóstico genérico vs manifiesto |
| `manage_homeostasis_goals` | Espejo de `/goals` |
| `configure_loop_homeostasis` | Programar intervalo legacy desde el agente |
| `get_loop_homeostasis_status` | Estado + snapshot manifiesto |
| `request_homeostasis_validation` | Paso HITL final antes de declarar homeostasis |

## Despliegue

- Gateway: fly `/loop` + finalize footer + wrap turnos en `chat_graph_runner`
- Heartbeat: ticks reloj (`loop_delta_idle=0`) o inactividad (`loop_delta_idle=1`); scan `loop_delta_seconds` + legacy `meditate_delta_seconds`
- Cola Redis: `duckclaw:state_delta:loop` (consumer dual durante migración)
- `pm2 restart DuckClaw-Gateway DuckClaw-DB-Writer DuckClaw-Heartbeat --update-env`
