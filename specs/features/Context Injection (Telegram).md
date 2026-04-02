# Context Injection (Telegram `/context --add`)

## Objetivo

Permitir que un **admin** inyecte texto largo en **memoria semántica** (`main.semantic_memory`) del DuckDB del tenant, sin bloquear el API Gateway en el Singleton Writer, y disparar en segundo plano un resumen vía Manager Graph.

## DuckDB: bóveda única y conexiones efímeras

- **Una bóveda por tenant** (un archivo `.duckdb` por usuario/tenant según resolución de ruta); no se usa un fichero sidecar separado para `semantic_memory`.
- El **API Gateway** no mantiene un `duckdb.connect` persistente al archivo del gateway ni al vault durante el tiempo entre peticiones. Cada turno del Manager Graph abre el DuckDB del gateway en **solo lectura**, compila el grafo con ese handle, ejecuta `invoke` y **cierra** la conexión en `finally` (y vacía la caché de subgrafos de worker que referencian ese handle).
- **`/context --summary`** y lecturas auxiliares usan conexiones **RO efímeras** a la ruta de bóveda resuelta (abrir → leer → cerrar), sin reutilizar un handle global del grafo.
- El **db-writer** abre el vault en **escritura** solo mientras procesa un mensaje de la cola `CONTEXT_INJECTION` y cierra al terminar (sin pool persistente al mismo archivo).

## RBAC

- Solo usuarios con `role = 'admin'` en `main.authorized_users` (misma convención que Telegram Guard).
- En War Rooms (`tenant_id` prefijo `wr_`), alternativa: `clearance_level = 'admin'` en `war_room_core.wr_members`.
- Bypass: `DUCKCLAW_OWNER_ID` / `DUCKCLAW_ADMIN_CHAT_ID` coincide con `user_id`.

## Comando

- `/context --add <texto>` (opcional sufijo de bot: `/context@BotName --add ...`).
- Texto vacío tras `--add`: respuesta determinista de error, **sin LLM**.
- `/context --summary` (alias: `--peek`, `--db`): **solo lectura** de `main.semantic_memory` en la bóveda del usuario; **no** encola Redis ni escribe. Acuse inmediato + `invoke_agent_chat` en segundo plano con `[SYSTEM_DIRECTIVE: SUMMARIZE_STORED_CONTEXT]` y el volcado reciente de filas (mismo RBAC admin que `--add`). Si no hay filas/tabla, mensaje determinista **sin LLM**.

## StateDelta (Redis)

- Cola: `DUCKCLAW_CONTEXT_STATE_DELTA_QUEUE` (default `duckclaw:state_delta:context`).
- Payload JSON (Pydantic en gateway y validación en db-writer):

```json
{
  "tenant_id": "<tenant lógico>",
  "delta_type": "CONTEXT_INJECTION",
  "mutation": {
    "raw_text": "<texto>",
    "source": "telegram_cmd"
  },
  "user_id": "<vault user id>",
  "target_db_path": "<ruta absoluta .duckdb del tenant>"
}
```

- El Gateway hace `LPUSH` en **fire-and-forget** (`asyncio.create_task`); no espera confirmación del Writer para responder al usuario.

## Respuesta al usuario

- Mensaje corto fijo de acuse (p. ej. contexto encolado para indexación).
- En paralelo (sin bloquear al Writer): `invoke_agent_chat` con `is_system_prompt=true` y `skip_session_lock=true`, mensaje:

`[SYSTEM_DIRECTIVE: SUMMARIZE_NEW_CONTEXT] <texto>` + instrucción de sintetizar en bullets técnicos alineados al dominio del worker activo.

### Comportamiento del worker en ese turno

- El **texto crudo** a sintetizar ya va en el mensaje; la ingesta/embed en `main.semantic_memory` puede ser **asíncrona** y aún no devolver filas en búsqueda vectorial.
- En ese mismo turno el worker **no** debe llamar a `search_semantic_context` (ni forzar `inspect_schema` por palabras como “esquemas” en el cuerpo): solo produce el resumen pedido.
- `search_semantic_context` queda para **turnos futuros** en que el usuario pregunte por lo guardado (p. ej. «¿qué sabemos de SpaceX?») sin repetir el texto inyectado.

### `SUMMARIZE_STORED_CONTEXT` (`/context --summary`)

- El Gateway lee `main.semantic_memory` con DuckDB **read-only** en la ruta de bóveda (misma resolución que el delta de inyección), orden descendente por `created_at`, con límite de filas y de caracteres totales en el prompt.
- El worker trata el mensaje como en `SUMMARIZE_NEW_CONTEXT`: **sin** `search_semantic_context` en ese turno (el contenido ya va en el prompt).

## Excepción de arquitectura (embeddings en Writer)

Para `CONTEXT_INJECTION` únicamente, el proceso **db-writer** calcula embeddings en este orden: **HTTP** a `DUCKCLAW_MLX_EMBEDDINGS_URL` (cuerpo estilo OpenAI `/v1/embeddings`, vector 384 dims), si no hay URL o falla, **sentence-transformers** (`all-MiniLM-L6-v2`). Modelo opcional: `DUCKCLAW_MLX_EMBEDDINGS_MODEL`. Otras colas (p. ej. VFS en specs legacy) pueden seguir asumiendo vectores precomputados.

## Tabla `main.semantic_memory`

```sql
CREATE TABLE IF NOT EXISTS main.semantic_memory (
  id VARCHAR PRIMARY KEY,
  content TEXT NOT NULL,
  source VARCHAR DEFAULT 'manual_injection',
  embedding FLOAT[384],
  embedding_status VARCHAR DEFAULT 'PENDING',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

- Chunks > 8000 caracteres: división por párrafos (`\n\n`), luego por líneas si hace falta; una fila por chunk.
- Si la vectorización falla: `embedding NULL`, `embedding_status = 'FAILED'`, y evento `NEEDS_EMBEDDING` en Redis (`DUCKCLAW_NEEDS_EMBEDDING_QUEUE`, default `duckclaw:needs_embedding`).

## Tool Finanz

- `search_semantic_context(query, limit=3)` en `forge/templates/finanz/skills/search_semantic_context.py`, registrada en `manifest.yaml`.
- Usa `embed_text` + `array_cosine_distance` sobre filas con `embedding IS NOT NULL` y estado utilizable (`READY`).
