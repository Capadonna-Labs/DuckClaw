# Telegram multiplex: outbound token, A2A y tool routing

## Objetivo

1. Los DMs de **chat heartbeat** (delegación, progreso por tool, handoff A2A visible) deben enviarse con el **mismo bot** que recibió el mensaje en webhooks multiplex (Finanz vs Job Hunter), no con el token por defecto del proceso.
2. Los handoffs **Finanz → Job Hunter** por marcadores en la respuesta del modelo **solo** aplican si **Finanz** está en el equipo del chat (`available_templates`).
3. Los workers pueden usar **elección de herramienta por LLM** (sin forzar `inspect_schema` / `read_sql` / `tavily` / etc. en el primer turno) mediante variable de entorno o manifest.

## Outbound token por request

- El gateway conoce el `reply_token` correcto por ruta de webhook (`/telegram/finanz`, `/telegram/trabajo`, etc.).
- Ese token se pasa al grafo como `outbound_telegram_bot_token` en el estado inicial del manager.
- `schedule_chat_heartbeat_dm` acepta `outbound_bot_token` opcional y lo pasa al hilo de envío; el hilo **no** depende de `ContextVar` (los hilos nuevos no heredan el override de `telegram_bot_token_override`).
- Orden de resolución del token en envío nativo: argumento explícito no vacío → `effective_telegram_bot_token_outbound()` → env global.

## A2A y Finanz en equipo

- `active_mission` tipo crisis + Job Hunter ya se crea solo si Finanz está en el equipo (lógica existente en `plan_node`).
- Las ramas del router posteriores a `invoke_worker` que interpretan marcadores en la respuesta de Finanz (`handoff_job_track`, `handoff_to_target`) **exigen** que Finanz figure en `available_templates`.

## Tool choice LLM-first

- **`DUCKCLAW_WORKER_HEURISTIC_FIRST_TOOL`**: por defecto `true` (comportamiento histórico). Si `false`/`0`/`off`, el nodo `agent_node` no fuerza la primera herramienta por heurísticas (`force_schema`, `force_read_sql`, `force_tavily`, `force_reddit`, `force_portfolio`); el modelo usa `tool_choice` automático con las tools enlazadas.
- **Manifest** (`manifest.yaml`): clave opcional `agent_node.heuristic_first_tool` (bool). Si está definida, **tiene prioridad** sobre la variable de entorno.
- Se mantienen: directivas de contexto (`SUMMARIZE_*`), respuestas rápidas de capacidades/saludo Job Hunter, y el error explícito si Job Hunter pide búsqueda web sin Tavily configurado.
- En modo LLM-first se antepone una instrucción breve al contexto enviado al modelo para elegir herramienta según plan y mensaje, sin inventar datos si falta una tool.

## Seguridad

- `outbound_telegram_bot_token` solo circula en memoria del proceso gateway/agents; no se persiste en DuckDB ni en logs de contenido del token.
