# Finanz — forzar herramientas (DuckDB como fuente de verdad)

## Problema

El modelo a veces lista deudas/gastos desde el hilo del chat, confirma «DB actualizada» sin `read_sql`/`admin_sql`, o el Manager produce un `plan_title` tipo «sin herramientas» cuando el usuario pide explícitamente usar tools.

## Comportamiento esperado

1. **Worker Finanz:** protocolo de evidencia en `system_prompt.md`: listados y totales solo desde tools del turno; escritura + `read_sql` de verificación.
2. **Manager:** `Manager/system_prompt.md` al planner: no titular planes «sin herramientas» ante reclamo de tools.
3. **`_plan_task`:** si el worker asignado es `finanz` y el mensaje coincide con patrones de «usa tools», «no usaste», `insert_deuda`, etc., se sustituye la `planned_task` por una TAREA explícita de cadena lectura → escritura → lectura.
4. **`plan_title`:** `_sanitize_finanz_manager_plan_title` reemplaza títulos prohibidos cuando el planner LLM alucina.
5. **Replan:** `format_replan_task_suffix` y `resilience_escalation_wants_read_sql` incluyen deudas/presupuesto/gastos.
