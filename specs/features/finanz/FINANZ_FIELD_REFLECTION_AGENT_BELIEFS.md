# Finanz: Field Reflection y `agent_beliefs`

## Objetivo

Evolutar al worker Finanz persistiendo lecciones cuando fallan herramientas, recuperándolas como **Experiencia de Campo** en el prompt del turno, sin romper homeostasis numérica ni creencias del lake.

## Tabla `finance_worker.agent_beliefs`

- **`belief_kind`**: `numeric` (homeostasis, `lake_*`, semillas YAML) o `field_lesson` (narrativa).
- **Filas numéricas**: `target_value`, `threshold`, `observed_value` como hoy; `lesson_text` y `context_trigger` NULL; `confidence_score` NULL.
- **Filas `field_lesson`**: `lesson_text` (lección), `context_trigger` (frase clave para matching con el mensaje del usuario), `confidence_score` (≥ 0, típicamente ≤ 10 o normalizado; solo puede **aumentar** en reencuentros).
- **Dummy numérico** en lecciones: `target_value = 0`, `threshold = 0`, `observed_value` NULL para satisfacer NOT NULL histórico en columnas legacy.

## Regla de oro

- **Prohibido** `DELETE` sobre `agent_beliefs` desde el Reflector o la lógica de experiencia de campo.
- En conflicto por `belief_key` (misma lección deduplicada por hash estable): solo `UPDATE` de `confidence_score` con `GREATEST(actual, propuesto)` y `last_updated`; **no** sobrescribir `lesson_text` con texto nuevo de un reencuentro (la primera redacción se conserva).

## Nodo Reflector (LangGraph, solo Finanz)

- Se ejecuta **solo** si `field_reflection.enabled` (manifest, default true) y el **último batch** de respuestas a `tool_calls` contiene al menos un error.
- Heurística de error (alineada al gateway):
  - Contenido de `ToolMessage` que empiece por `Error:`.
  - JSON con clave `"error"` presente (p. ej. `LAKE_EMPTY_BARS`).
  - JSON de sandbox con `exit_code` distinto de `0`.
  - Mensajes tipo herramienta desconocida / sandbox deshabilitado cuando el texto lo indica claramente.
- El Reflector invoca al LLM con el contexto del fallo y persiste una fila `field_lesson` (o sube `confidence_score` si la clave ya existe). No añade ruido obligatorio al hilo visible salvo decisión de producto; el efecto principal es escritura en DuckDB.

## Experiencia de Campo (inyección en `prepare`)

- Antes de componer el mensaje de sistema del turno, se consultan hasta **200** filas `field_lesson` recientes y se rankean por solapamiento léxico entre el mensaje entrante del usuario y `context_trigger` / `lesson_text`, ponderando `confidence_score`.
- Se inyectan las **5** mejores en un bloque `## Experiencia de Campo` **después** del cuerpo del system prompt estático y **antes** del bloque de tarea/conciencia de tarea, luego el cierre de dominio (`append_domain_closure_block`).

## Alcance

- Worker lógico `finanz` únicamente. Otros workers no cargan Reflector ni inyección.
