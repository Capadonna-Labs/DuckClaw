
# Template — BI Analyst

## 1. Objetivo
Implementar un agente de Inteligencia de Negocios (BI) de nivel Senior capaz de realizar análisis exploratorio de datos (EDA), ejecutar consultas SQL complejas en DuckDB, generar visualizaciones profesionales en el **Strix Sandbox** y entregar recomendaciones estratégicas. Este worker es la herramienta principal para pruebas técnicas de Data Science y monitoreo de infraestructura.

## 2. Contexto y Topología
- **Host:** Mac mini M4.
- **Runtime:** LangGraph (Grafo de estado cíclico).
- **Aislamiento:** Código Python ejecutado en contenedores efímeros (Strix Sandbox).
- **Memoria:** Acceso de lectura a la base de datos soberana del tenant.

## 3. Esquema de Datos (`analytics_core`)
El agente operará sobre un esquema dedicado para evitar colisiones con datos operativos.

### Tablas:
- **`sales`**: Registro histórico de transacciones.
  - `id` (UUID), `fecha` (TIMESTAMP), `producto` (VARCHAR), `categoria` (VARCHAR), `cantidad` (INT), `precio_unit` (FLOAT), `total` (FLOAT), `vendedor` (VARCHAR), `region` (VARCHAR), `canal` (VARCHAR).
- **`system_metrics`**: Registro de performance del arnés (ideal para demos técnicas).
  - `id` (UUID), `timestamp` (TIMESTAMP), `worker_id` (VARCHAR), `latency_ms` (FLOAT), `tokens_used` (INT), `status` (VARCHAR), `error_type` (VARCHAR).

### Seed Data (Requisito de Demo):
- **Ventas:** 1,000 filas sintéticas cubriendo los últimos 12 meses. Debe incluir estacionalidad, una caída de ventas en un mes específico y un vendedor estrella.
- **Métricas:** 200 filas con variaciones de latencia y picos de uso de tokens.

## 4. Flujo Cognitivo (Analytical Pipeline)
El agente NO tiene permitido improvisar respuestas. Debe seguir este protocolo en cada turno:

1.  **Paso 1: INTROSPECCIÓN:** Llamar a `get_schema_info()` para validar tablas y tipos de datos reales.
2.  **Paso 2: PLANIFICACIÓN:** Declarar explícitamente qué métricas va a calcular y por qué (ej. "Calcularé el MoM growth para identificar la caída mencionada").
3.  **Paso 3: EXTRACCIÓN:** Ejecutar SQL analítico usando **CTEs** para consultas con más de 2 joins o cuando varias métricas compartan el mismo contexto (una sola query con varias CTEs).
4.  **Paso 4: VISUALIZACIÓN:** Si el usuario pide gráficos, generar código Python para el Sandbox; los datos para el gráfico deben leerse desde la DuckDB montada bajo `/workspace/repo_db/...` (solo lectura), nunca desde arrays hardcodeados.
5.  **Paso 5: SÍNTESIS:** Entregar la respuesta estructurada en tres secciones:
    - **INSIGHT:** ¿Qué pasó? (El dato duro).
    - **CAUSA:** ¿Por qué pasó? (La correlación encontrada).
    - **RECOMENDACIÓN:** ¿Qué hacer? (Acción de negocio).

### 4.1 Concurrencia SQL (`read_sql`)
- Preferir **una** sentencia con **varias CTEs** cuando se pidan varias agregaciones en el mismo turno y compartan tablas o filtros.
- Si las consultas son **independientes**, permitido **varias** llamadas a `read_sql` en el mismo turno (paralelismo cuando el runtime lo permita).

### 4.2 Strix / `run_sandbox`: datos solo desde DuckDB montada
- **Prohibido** incrustar listas, dicts o `DataFrame` manuales con valores de negocio.
- El sandbox expone `db/` del repo en **`/workspace/repo_db`** (RO). Abrir el `.duckdb` con `duckdb.connect("/workspace/repo_db/<ruta-relativa-bajo-db/>/<archivo>.duckdb", read_only=True)` y usar `pandas.read_sql(...)`.
- No usar rutas inventadas fuera de ese montaje (p. ej. `/mnt/data/shared/analytics.duckdb`) salvo que existan en la `security_policy` del template.

## 5. Contratos de Herramientas (Skills)

- **`get_schema_info()`**: Retorna el DDL exacto de `analytics_core`.
- **`run_sql(query: str)`**: Ejecuta consultas en DuckDB. 
  - **Restricción:** Conexión forzada a `read_only=True`. Bloquea cualquier mutación.
  - **Error Handling:** Retorna el error de DuckDB al LLM para auto-corrección (máximo 2 reintentos).
- **`strix_sandbox_runner(code: str)`**: Ejecuta código DS en contenedor aislado.
  - **Librerías:** pandas, numpy, matplotlib, seaborn, scipy.
  - **Output:** Retorna `{"stdout": str, "figure_base64": str | None}`.
- **`explain_sql(query: str)`**: Traduce la lógica de la query a lenguaje natural para el usuario.

## 6. Personalidad y Políticas (Soul & Domain Closure)

### Soul (`soul.md`):
- **Identidad:** Analista Senior, escéptico, basado en evidencia.
- **Tono:** Profesional, directo, sin "relleno" conversacional.
- **Formato:** Moneda en COP ($), fechas en formato estándar colombiano.

### Domain Closure (`domain_closure.md`):
- **Prohibido:** Acceder a tablas fuera de `analytics_core`.
- **Prohibido:** Inventar datos o tendencias si la consulta SQL devuelve vacío.
- **Prohibido:** Sugerir comandos internos (`/help`, `/prompt`) al usuario final.

## 7. Manifiesto (`manifest.yaml`)

```yaml
name: bi_analyst
version: 1.3.0
type: sovereign_worker
cognition:
  soul: ./soul.md
  system_prompt: ./system_prompt.md
  domain_closure: ./domain_closure.md
execution:
  engine: langgraph
  entrypoint: analytical_pipeline_flow
  policies:
    timeout_ms: 60000
    retry_max: 2
memory:
  sql:
    required_schemas: [analytics_core]
    seed_data: ./seed_data.sql
observability:
  tracing: true
  trace_namespace: "{tenant}:bi_analyst"
```

## 8. Casos de Prueba (Edge Cases)
- **Query Ineficiente:** Si el LLM intenta un `SELECT *` en una tabla masiva, la tool debe forzar un `LIMIT` o pedir agregación.
- **Gráfico Fallido:** Si el código de Matplotlib falla, el agente debe leer el error del Sandbox e intentar corregir el script una vez.

## 9. Optimización de runtime (LangGraph)

- **`context_pruning` en `manifest.yaml`:** habilita el nodo `context_monitor` (tras `prepare` y tras `tools`) con umbrales `max_messages`, `max_estimated_tokens`, `keep_last_messages`, truncado de `ToolMessage` (`tool_content_max_chars`) y resumen vía LLM dedicado opcional.
- **LLM de resumen:** variables `DUCKCLAW_SUMMARY_LLM_PROVIDER`, `DUCKCLAW_SUMMARY_LLM_MODEL`, `DUCKCLAW_SUMMARY_LLM_BASE_URL`; si se omiten, se reutiliza el LLM principal del proceso.
- **SQL:** el modelo solo expone `read_sql` (no `run_sql`) para DuckDB en solo lectura.
- **Sandbox:** imagen `duckclaw/sandbox:latest` con pandas, matplotlib, **seaborn**, scipy, etc.; cabecera inyectada en Python con `matplotlib` Agg, `rcParams` (fondo blanco, `savefig.dpi`/`figure.dpi` 100) y comentario con `plt.savefig(..., dpi=100, facecolor='white', edgecolor='none')` para compatibilidad con Telegram `sendPhoto`; mensaje de error estandarizado al LLM si falla la ejecución.
- **Telegram (gateway):** envío del PNG con `sendPhoto` usando `Content-Type: image/png` y `filename=chart.png`; si la API responde error (p. ej. `IMAGE_PROCESS_FAILED`), log detallado (`error_code`, `description`) solo en servidor y fallback a `sendDocument` (adjunto). La respuesta JSON al cliente incluye `sandbox_chart_delivered` sin texto de error de Telegram. **Token del bot:** si varias gateways comparten `.env` con un solo `TELEGRAM_BOT_TOKEN` (p. ej. Finanz), el proceso `BI-Analyst-Gateway` debe usar el bot de BI: define `TELEGRAM_BOT_TOKEN_BI_ANALYST` en `.env` (o `TELEGRAM_BOT_TOKEN` dentro del bloque `env` de esa app en `config/api_gateways_pm2.json`). Prioridad: token en JSON del bloque PM2; si no viene, se usa `TELEGRAM_BOT_TOKEN_BI_ANALYST`; si no existe, cae en `TELEGRAM_BOT_TOKEN` del `.env`.
- **Heartbeat Telegram:** si `sandbox_heartbeat` es true y existe `N8N_OUTBOUND_WEBHOOK_URL`, antes de `run_sandbox` se notifica al usuario; desactivar con `DUCKCLAW_SANDBOX_HEARTBEAT=false`.