# Dreamer — computo nocturno (sleep-time)

## Objetivo

Job batch que lee historial reciente (DuckDB **solo lectura**), consolida fragmentos con LLM (**MLX** por defecto, **un** fallback **DeepSeek** si `DEEPSEEK_API_KEY`), y persiste resultados **únicamente** encolando deltas en Redis para el **db-writer** (`push_quant_state_delta_sync` → cola `duckclaw:state_delta:quant`).

## Fases

1. **Light** — `load_raw_history` sobre el DuckDB de lectura (por defecto hub Gateway; override `DUCKCLAW_DREAMER_CONVERSATION_DB`): una conexión `read_only=True`; ventana `LOOKBACK_HOURS` (24 h); `--tenant-id` = **Telegram `chat_id` numérico** → `WHERE chat_id = ?`; `task_audit_log` por `tenant_id` (mapeo Staff: `action` ≈ `query_prefix` / `plan_title`).
2. **REM** — `consolidate_memory`: chunks de `CHUNK_SIZE` (50) líneas `"{role}: {content}\n"`, prompt JSON estricto `insights[]` con `topic`, `insight`, `confidence`; filtro `confidence < 0.5`; dedup por prefijo 80 chars; tope `MAX_INSIGHTS_PER_RUN` (20).
3. **Deep** — `emit_memory_deltas`: un `SEMANTIC_MEMORY_UPSERT` por insight. Fallo **aislado** de LPUSH → log y continuar; Redis caído **al arranque** → `exit(1)`.

## Escrituras permitidas (Quant)

| `delta_type`            | Efecto en DuckDB (writer) |
|-------------------------|----------------------------|
| `SEMANTIC_MEMORY_UPSERT`| UPSERT `main.semantic_memory` (`topic`, `insight`→`content`, `confidence_score`, `source`). |
| `CONVERSATION_COMPACTION` | `DELETE` en `telegram_conversation` con `chat_id` = tenant y `received_at` antes del cutoff (`days`). |

No usar la cola `context` para memoria semántica — debe cumplirse la ruta Quant existente.

## Curación golden (SFT)

`curate_golden_dataset`: append **solo** modo `'a'` en `packages/agents/train/conversation_traces/golden_dataset.jsonl` (override: `DUCKCLAW_DREAMER_GOLDEN_PATH`). Las filas SQL no incluyen `tool_calls` / `status`: la heurística `is_golden_turn` usa rol usuario, longitud mínima y `EXCLUSION_PATTERNS`.

## Compactación opcional

`--compact` encola `CONVERSATION_COMPACTION` **solo si** la fase Deep permite compactar: sin insights **o** al menos un LPUSH de insights exitoso. Si hay insights y **todos** los LPUSH fallan, no se compacta.

## Variables de entorno

| Variable | Uso |
|----------|-----|
| `REDIS_URL` / `DUCKCLAW_REDIS_URL` | Obligatorio (ping al inicio). |
| `DUCKCLAW_DREAMER_TARGET_DB` (etc.) | DuckDB **destino** de deltas (`SEMANTIC_MEMORY_UPSERT`). Si la variable falta en el entorno, el job puede leerla desde `${DUCKCLAW_REPO_ROOT}/.env`. |
| `DUCKCLAW_DREAMER_CONVERSATION_DB` | Opcional. DuckDB donde leer `telegram_conversation` / audit y donde aplicar `CONVERSATION_COMPACTION`. Si no está definida: **hub** `get_gateway_db_path()`; si no hay hub, mismo path que el destino. |
| `DUCKCLAW_DREAMER_USER_ID` | Opcional; default = `--tenant-id` para `user_id` en el delta. |
| `DUCKCLAW_LLM_PROVIDER` | Por defecto MLX en PM2. |
| `DEEPSEEK_API_KEY` | Fallback tras fallo de invoke MLX. |
| `DUCKCLAW_DREAMER_GOLDEN_PATH` | Override ruta golden JSONL. |

## PM2

Ver `ecosystem.config.js` (`duckclaw-dreamer`, cron 02:00, `TZ=America/Bogota`). Ajustar `DUCKCLAW_DREAMER_TARGET_DB` en el entorno del proceso (no va en el ejemplo del repo).
