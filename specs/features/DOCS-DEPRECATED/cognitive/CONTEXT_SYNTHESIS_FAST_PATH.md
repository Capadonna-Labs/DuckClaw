# Context synthesis fast path (tool surface)

## Objetivo

Reducir latencia en turnos provocados por el gateway con directivas:

- `[SYSTEM_DIRECTIVE: SUMMARIZE_STORED_CONTEXT]` (`/context --summary`)
- `[SYSTEM_DIRECTIVE: SUMMARIZE_NEW_CONTEXT]` (resumen tras `/context --add`)

En esos turnos el contenido a sintetizar **ya va en el mensaje**; se evita levantar MCP stdio pesados (GitHub, Google Trends) que añaden cold start. **Reddit** se mantiene registrado cuando el manifest lo declara, porque `/context --add` con URL `/r/.../s/...` debe poder usar la API Reddit (ver [`FINANZ_CONTEXT_INJECTION_TELEGRAM.md`](../finanz/FINANZ_CONTEXT_INJECTION_TELEGRAM.md)).

## Comportamiento

1. **Manager `plan_node`**: si el `incoming` contiene una de las directivas anteriores, el plan (título y tareas) se obtiene solo con `_llm_plan` heurístico; **no** se invoca el planner LLM (`_llm_plan_from_model`).

2. **Manager `invoke_worker_node`**: si `planned_task` o `incoming` contienen la misma directiva:
   - La clave de caché del grafo del worker incluye el sufijo `::ctx_syn`.
   - Si la directiva es exactamente `SUMMARIZE_NEW_CONTEXT` o `SUMMARIZE_STORED_CONTEXT`, la caché también lleva `::sum_vault_ro` y `build_worker_graph` recibe `open_vault_read_only=True`: la bóveda se abre en **solo lectura** para no competir por bloqueo exclusivo con **db-writer** (inyección de contexto en cola). DuckDB permite conexiones RO concurrentes con un proceso en RW.

   **Follow-up a memoria indexada (sin directiva):** mensajes que parecen preguntar por notas ya en VSS (p. ej. «¿hay algo sobre X en el contexto?», «qué hay anotado sobre…») usan la **misma** superficie `context_synthesis` y sufijo `::ctx_syn` vía heurística en código (`_incoming_looks_like_semantic_context_followup`). No afecta al fast path del planner LLM salvo los turnos con directiva `SUMMARIZE_*`.

3. **`build_worker_graph`**: con `tool_surface=context_synthesis`, **no** se registran `register_github_skill` ni `register_google_trends_skill`. **`register_reddit_skill` sí** si el manifest tiene `reddit:` (coherente con síntesis de enlaces Reddit en `SUMMARIZE_NEW_CONTEXT`).

   El resto de herramientas del manifest (SQL, Tavily, sandbox, IBKR, etc.) se mantiene; el system prompt del worker ya indica no usar búsqueda semántica innecesaria en esos turnos.

4. **Quant Trader · OHLCV vs ventana MOC:** la ingesta `fetch_market_data` / `fetch_ib_gateway_ohlcv` **no** está limitada por la ventana MOC de auto-execución (~14:40–14:59 COT). En turnos `SUMMARIZE_*` el gateway puede inyectar la directiva `[DIRECTIVA_OHLCV_FUERA_VENTANA_MOC]` para que el modelo combine Reddit/Tavily con velas cuando haya tickers. Opt-in para **forzar** la primera tool de ingesta igual que en chat normal: `DUCKCLAW_QUANT_OHLCV_ON_CONTEXT_SUMMARY=1` y texto del usuario con palabras clave OHLCV + símbolo (misma heurística que `force_fetch_market_data` en `workers/factory.py`).

## Default

`tool_surface=full` (comportamiento anterior) para invocaciones que no son síntesis de contexto vía directiva, p. ej. `AgentAssembler` / `WorkerFactory.create`.
