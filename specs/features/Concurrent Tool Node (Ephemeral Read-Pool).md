# Concurrent Tool Node (Ephemeral Read-Pool)

| Campo | Valor |
|--------|--------|
| Estado | Borrador |
| Versión | 0.2 |
| Relacionado | Singleton Writer, `packages/agents` LangGraph workers, `bind_tools` / `parallel_tool_calls` |

## 1. Resumen ejecutivo

El nodo de herramientas (`tools_node`) de los workers LangGraph debe poder ejecutar **en paralelo** las herramientas de **solo lectura** que consultan DuckDB (p. ej. varias llamadas a `read_sql` en un mismo turno), usando **conexiones efímeras `read_only`** por petición, sin compartir la conexión interna de `DuckClaw` entre hilos. Las herramientas con **efectos secundarios** o **no deterministas** siguen ejecutándose **secuencialmente** y con el mismo contrato actual.

Objetivo medible: reducir la latencia end-to-end cuando el LLM emite N tool calls de lectura (típico N ≤ 5), sin violar el modelo **Singleton Writer** ni la seguridad transaccional de escrituras.

## 2. Contexto

- El proveedor LLM (OpenAI-compatible) puede devolver **varias** entradas en `AIMessage.tool_calls` cuando `parallel_tool_calls=True` en el binding (`duckclaw.integrations.llm_providers.bind_tools_with_parallel_default`).
- Hoy, `tools_node` en `build_worker_graph` itera `tool_calls` en un `for` y llama `tool.invoke()` de forma **secuencial**. La instancia `DuckClaw` encapsula **una** conexión DuckDB; ejecutar consultas en paralelo sobre esa misma conexión desde varios hilos **no** está garantizado como seguro.
- DuckDB permite **varios lectores** sobre el mismo archivo si las conexiones son de lectura y el bloqueo del SO lo permite; durante WAL/checkpoint del proceso escritor, los lectores pueden fallar o esperar.
- Forge hace **ATTACH** de `private` y opcionalmente `shared` sobre la ruta de la bóveda del worker (`_apply_forge_attaches`). Cualquier conexión efímera debe ver el **mismo catálogo** que la sesión principal (mismos ATTACH y rutas escapadas).

## 3. Objetivos

1. **Paralelizar** solo las herramientas incluidas en la allow-list de lectura (sección 6).
2. **Offload** del trabajo bloqueante DuckDB al thread pool (`asyncio.to_thread` o equivalente) cuando el grafo se ejecute en un bucle asyncio, sin asumir que `tool.invoke` es async en todas las rutas legacy.
3. **Preservar** el orden de los `ToolMessage` en la lista `messages`: mismo orden que `tool_calls` en el `AIMessage`, con `tool_call_id` correcto (requisito de APIs de chat con tools).
4. **Limitar** la concurrencia máxima (semáforo) para no agotar FD ni memoria en hosts pequeños (p. ej. Mac mini).
5. **Reintentar** lecturas ante `IOException` / transient lock con backoff acotado.

## 4. Fuera de alcance (Non-goals)

- Paralelizar `admin_sql`, `run_sandbox`, escrituras remotas al `db-writer`, ni herramientas IBKR / Telegram / research que no deben duplicarse sin contrato explícito.
- Sustituir el Singleton Writer por escritura concurrente desde el gateway.
- Cambiar el formato de respuesta del LLM ni el esquema de `WorkerSpec` más allá de flags opcionales descritos en sección 11.

## 5. Clasificación de herramientas

### 5.1 Conjunto concurrente (solo lectura + idempotente en lectura)

Herramientas que **solo** leen estado DuckDB ya consolidado y no disparan efectos externos. Lista inicial (extensible por configuración declarada en manifest):

| Herramienta | Notas |
|-------------|--------|
| `read_sql` | Debe usar pool efímero; mismas validaciones que hoy (allow-list, RO-only, límites de tamaño / `LIMIT` según worker). |
| `inspect_schema` | Lista tablas vía `information_schema`; candidata a ejecución efímera. |
| `get_schema_info` | Si el worker la expone (p. ej. skills de catálogo), misma regla que `inspect_schema` si únicamente consulta metadatos/SQL RO. |

**Regla:** Si una herramienta nueva solo ejecuta `SELECT` / metadatos contra el mismo archivo(s) que la bóveda del worker, puede añadirse al conjunto concurrente **solo** tras revisión en spec + manifest (`concurrent_read_tools: [...]`).

### 5.2 Conjunto secuencial (default)

Todo lo no listado en 5.1, incluyendo de forma no exhaustiva:

- `run_sandbox`, `admin_sql`, `manage_memory`, skills con red, colas, o efectos en terceros.
- Cualquier tool que use la conexión única de `DuckClaw` para **escritura** o estado mutable en proceso.

Orden de ejecución propuesto: **primero** el lote concurrente de lecturas (manteniendo orden de aparición dentro del lote según `tool_calls`); **después** el resto en el orden original del array `tool_calls`. Alternativa aceptable: ejecutar en orden global pero “saltando” las concurrentes ya resueltas; la implementación debe documentar cuál estrategia adopta si hay intercalación lectura/escritura en un mismo turno.

Recomendación de producto: si en un turno hay mezcla RO + side-effect, ejecutar **todo secuencialmente** en orden (más simple y predecible) **o** RO paralelo primero y luego secuenciales; no paralelizar side-effects.

## 6. Contrato: conexión efímera (Read-Pool)

### 6.1 Apertura

- `duckdb.connect(primary_db_path, read_only=True)` en un hilo dedicado (vía `asyncio.to_thread`).
- Repetir los **mismos** `ATTACH` que aplica `_apply_forge_attaches` para ese worker (rutas `private` y `shared` resueltas, mismo escaping de comillas que la implementación actual). Sin ATTACH, consultas a `shared.*` o `private.*` **fallarán** en el pool.

### 6.2 Alineación con validaciones existentes

- Reutilizar la lógica de validación SQL RO (`allow`-list de tablas, mensajes de error) **antes** de ejecutar en el hilo pool, o centralizar en una función compartida para no duplicar reglas.
- Respetar `DUCKCLAW_READ_SQL_MAX_RESPONSE_CHARS` (o equivalente) en el truncado del resultado para el LLM.

### 6.3 Timeouts

- Establecer `PRAGMA statement_timeout` acorde al entorno (p. ej. 10s por defecto; configurable). Documentar interacción con consultas legítimas largas (analytics).

### 6.4 Errores y reintentos

- Ante `duckdb.IOException` u errores de archivo bloqueado / busy: hasta **3** reintentos con backoff exponencial (p. ej. 50ms, 200ms, 800ms), jitter opcional.
- Tras agotar reintentos: devolver `ToolMessage` con error serializado coherente con el formato actual (`json.dumps({"error": ...})` donde aplique).

### 6.5 Límite de concurrencia

- Semáforo global por proceso o por worker: **máximo 5** lecturas concurrentes por defecto (`DUCKCLAW_TOOL_READ_POOL_CONCURRENCY`, default `5`).
- Si N tool calls RO supera el límite, el resto espera al semáforo (cola FIFO dentro del turno).

## 7. Integración con LangGraph / async

- Si el `tools_node` sigue siendo **sincrono**, la primera iteración puede usar `concurrent.futures.ThreadPoolExecutor` con el mismo contrato de conexión efímera y semáforo, siempre ordenando resultados al final.
- Si el proyecto migra el nodo a **async**, preferir `asyncio.to_thread` + `asyncio.gather` con semáforo, sin bloquear el event loop del gateway.
- No introducir dependencias bloqueantes nuevas en rutas FastAPI críticas sin executor.

## 8. Seguridad e integridad

- **Escrituras:** solo el flujo existente hacia Singleton Writer / `admin_sql` según política del worker; el pool efímero **nunca** abre `read_only=False` para estas herramientas.
- **Multi-tenant:** usar siempre la ruta de bóveda resuelta para el tenant/instancia actual (mismo `path` que `DuckClaw(path)` en `build_worker_graph`). No mezclar rutas entre tenants.
- **PII:** el truncado y masking previos a LangSmith/frontend no cambian; el pool no debe loguear SQL completo en producción salvo modo diagnóstico explícito.

## 9. Observabilidad

- Métricas sugeridas: `duckclaw_tool_read_pool_in_flight`, `duckclaw_tool_read_pool_wait_seconds`, contador de reintentos, histograma de latencia por tool.
- Logs: worker_id, tenant_id, nombres de tool (no texto completo de queries en INFO).

## 10. Criterios de aceptación

1. Con un worker que use `read_sql`, un único turno con **tres** `tool_calls` `read_sql` válidas completa en menor tiempo wall-clock que tres veces la mediana de una sola llamada (mismo hardware, mismo archivo, consultas independientes), dentro de un margen razonable de ruido.
2. El orden de `ToolMessage` y los `tool_call_id` coinciden con el `AIMessage` original.
3. Bajo fallo simulado de bloqueo DuckDB, se observan reintentos y luego error útil.
4. `inspect_schema` / `get_schema_info` (si aplica) bajo ATTACH `shared` devuelven el mismo resultado que la sesión principal para una fixture conocida.
5. No regresión: herramientas secuenciales (`run_sandbox`, etc.) comportamiento idéntico al actual.

## 11. Configuración (propuesta)

| Variable | Default | Descripción |
|----------|---------|-------------|
| `DUCKCLAW_TOOL_READ_POOL_ENABLED` | `true` | Feature flag global. |
| `DUCKCLAW_TOOL_READ_POOL_CONCURRENCY` | `5` | Máximo de lecturas efímeras concurrentes. |
| `DUCKCLAW_TOOL_READ_STMT_TIMEOUT_MS` | `10000` | Timeout de sentencia en conexión efímera. |
| `DUCKCLAW_TOOL_READ_POOL_RETRIES` | `3` | Reintentos ante IO/lock. |

Opcional en `WorkerSpec` / YAML: `concurrent_read_tools: [read_sql, inspect_schema, ...]` para ampliar sin redeploy de código (debe intersectarse con allow-list segura).

## 12. Riesgos y mitigaciones

| Riesgo | Mitigación |
|--------|------------|
| Divergencia ATTACH vs sesión principal | Helper único “bootstrap ephemeral connection” generado desde mismas rutas que `_apply_forge_attaches`. |
| Sobrecarga de FD / mmap | Semáforo + límite por defecto 5. |
| Consultas pesadas en paralelo | Timeout + límites existentes en prompts/manifest; opción de desactivar pool por worker. |
| GIL | Lectura DuckDB en threads; no esperar paralelismo CPU puro en Python; objetivo es I/O y lock de lectura. |

## 13. Implementación sugerida (post-aprobación spec)

1. Extraer en `packages/agents` un módulo pequeño (p. ej. `duckclaw/workers/read_pool.py`): `open_ephemeral_reader(primary, private_path, shared_path)`, `run_read_sql_ephemeral(...)`.
2. Refactorizar `tools_node` en `factory.py` (y equivalentes si existen) para clasificar `tool_calls` y despachar.
3. Tests unitarios: orden de mensajes, semáforo, reintentos mockeados, ATTACH fixture mínimo.

---

### Apéndice A: Pseudocódigo de referencia (conexión efímera)

```python
import asyncio
import duckdb

async def read_sql_async(query: str, db_path: str, attach_sql: list[str]) -> str:
    def _execute_read() -> str:
        with duckdb.connect(db_path, read_only=True) as conn:
            for stmt in attach_sql:
                conn.execute(stmt)
            conn.execute("PRAGMA statement_timeout='10s'")
            # ... validación RO / ejecutar query / serializar JSON como hoy ...
            return "[]"

    return await asyncio.to_thread(_execute_read)
```

`attach_sql` debe derivarse de las mismas rutas y reglas de escape que `packages/agents/src/duckclaw/workers/factory.py` (`_apply_forge_attaches`).
