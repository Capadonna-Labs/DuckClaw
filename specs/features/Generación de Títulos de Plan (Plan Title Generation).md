# Generación de Títulos de Plan (Plan Title Generation)

## 1. Objetivo Arquitectónico
Dotar al nodo `Planner` del grafo `Manager` de la capacidad de sintetizar la intención del usuario en un **Título de Plan (Plan Title)** semántico. Esto mejora la observabilidad del sistema, permitiendo que los logs y el comando `/history` muestren la intención estratégica del usuario en lugar de la consulta literal, facilitando la auditoría y el debugging.

## 2. Especificación del Nodo `Planner` (Manager Graph)

El nodo `Planner` debe evolucionar de retornar una lista de tareas a retornar un objeto estructurado que contenga el título y el plan.

*   **System Prompt (Actualización):**
    > "Eres el Manager de Agentes. Antes de planificar las tareas, analiza la intención del usuario y genera un 'plan_title' (máximo 5 palabras) que resuma la estrategia. Luego, genera la lista de 'tasks' (todos) necesarias para cumplir esa intención."

*   **Contrato de Salida (JSON Schema):**
    ```json
    {
      "plan_title": "string",
      "tasks": ["string"]
    }
    ```

## 3. Especificación de Estado (`ManagerAgentState`)

Actualizar el `TypedDict` del grafo `Manager` para persistir el título del plan durante el ciclo de vida de la tarea.

```python
class ManagerAgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    chat_id: str
    assigned_worker_id: str | None
    plan_title: str | None  # Nuevo campo para persistencia
    tasks: list[str] | None
```

## 4. Integración en el Gateway y Auditoría

### A. Logging (services/api-gateway/main.py)
El Gateway debe capturar el `plan_title` del estado del grafo tras la ejecución del `Planner` y registrarlo en los logs.

*   **Log Format:** `manager plan: [{plan_title}] | tasks: [{tasks_list}]`

### B. Persistencia (DuckDB Audit Log)
Actualizar la función `append_task_audit` para incluir el `plan_title`.

*   **Query SQL:**
    ```sql
    INSERT INTO task_audit_log (task_id, worker_id, plan_title, status, duration_ms)
    VALUES (?, ?, ?, ?, ?);
    ```

## 5. Protocolo de Visualización (`/history`)

El comando `/history` debe ser refactorizado para leer el nuevo campo `plan_title`.

*   **Lógica de Salida:**
    *   *Antes:* `1. [finanz] ¿Cuánto dinero tengo?`
    *   *Ahora:* `1. [finanz] [Consulta de Saldo Total] · ⏱️ 1.2s`

## 6. Roadmap de Implementación

1.  **Prompt Engineering:** Actualizar el `system_prompt.md` del `Manager` con la instrucción de generación de títulos.
2.  **State Update:** Modificar `ManagerAgentState` en `packages/agents/src/duckclaw/forge/atoms/state.py`.
3.  **Planner Logic:** Ajustar el nodo `Planner` para que fuerce la salida JSON con el nuevo esquema.
4.  **Audit Log:** Actualizar la función `append_task_audit` en `packages/agents/src/duckclaw/agents/activity.py` para incluir `plan_title`.
5.  **History Command:** Actualizar la query SQL en `on_the_fly_commands.py` para mostrar el `plan_title` en la respuesta de Telegram.