# Context synthesis fast path (tool surface)

## Objetivo

Reducir latencia en turnos provocados por el gateway con directivas:

- `[SYSTEM_DIRECTIVE: SUMMARIZE_STORED_CONTEXT]` (`/context --summary`)
- `[SYSTEM_DIRECTIVE: SUMMARIZE_NEW_CONTEXT]` (resumen tras `/context --add`)

En esos turnos el contenido a sintetizar **ya va en el mensaje**; se evita levantar MCP stdio pesados (GitHub, Google Trends) que añaden cold start. **Reddit** se mantiene registrado cuando el manifest lo declara, porque `/context --add` con URL `/r/.../s/...` debe poder usar la API Reddit (ver *Context Injection (Telegram)*).

## Comportamiento

1. **Manager `plan_node`**: si el `incoming` contiene una de las directivas anteriores, el plan (título y tareas) se obtiene solo con `_llm_plan` heurístico; **no** se invoca el planner LLM (`_llm_plan_from_model`).

2. **Manager `invoke_worker_node`**: si `planned_task` o `incoming` contienen la misma directiva:
   - La clave de caché del grafo del worker incluye el sufijo `::ctx_syn`.
   - Se construye el worker con `tool_surface=context_synthesis` en `build_worker_graph`.

   **Follow-up a memoria indexada (sin directiva):** mensajes que parecen preguntar por notas ya en VSS (p. ej. «¿hay algo sobre X en el contexto?», «qué hay anotado sobre…») usan la **misma** superficie `context_synthesis` y sufijo `::ctx_syn` vía heurística en código (`_incoming_looks_like_semantic_context_followup`). No afecta al fast path del planner LLM salvo los turnos con directiva `SUMMARIZE_*`.

3. **`build_worker_graph`**: con `tool_surface=context_synthesis`, **no** se registran `register_github_skill` ni `register_google_trends_skill`. **`register_reddit_skill` sí** si el manifest tiene `reddit:` (coherente con síntesis de enlaces Reddit en `SUMMARIZE_NEW_CONTEXT`).

   El resto de herramientas del manifest (SQL, Tavily, sandbox, IBKR, etc.) se mantiene; el system prompt del worker ya indica no usar búsqueda semántica innecesaria en esos turnos.

## Default

`tool_surface=full` (comportamiento anterior) para invocaciones que no son síntesis de contexto vía directiva, p. ej. `AgentAssembler` / `WorkerFactory.create`.
