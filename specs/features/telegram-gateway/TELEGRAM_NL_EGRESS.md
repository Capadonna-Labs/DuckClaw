# Worker: lenguaje natural en salida Telegram (síntesis LLM)

## Objetivo

Los mensajes visibles al usuario en Telegram (y trazas alineadas) deben ser **lenguaje natural**, con Markdown ligero (compatible con la conversión a HTML del gateway), **sin** JSON, SQL ni bloques de código crudos como respuesta principal, salvo opt-out explícito.

## Comportamiento por defecto

- Todo worker construido con **`build_worker_graph`** que tenga **LLM** (`llm is not None`) aplica, en **`set_reply`**, una **pasada de síntesis** con el mismo modelo **sin herramientas** cuando el texto candidato es **JSON parseable** (objeto o array) tras `strip`.
- Turnos **`[SYSTEM_DIRECTIVE: SUMMARIZE_NEW_CONTEXT]`** o **`SUMMARIZE_STORED_CONTEXT`** (Telegram `/context`): si la respuesta del agente es **trivial** (p. ej. solo «Listo.», sin viñetas útiles), **`rescind_trivial_context_summary_reply`** intenta **primero** una segunda pasada **LLM** (sin herramientas) con el volcado como evidencia, en **lenguaje natural** (prosa y/o viñetas). Si esa síntesis falla, está vacía o no supera el umbral de sustancia (`context_summary_synthesis_acceptable`), se usa **fallback determinístico** parseando `--- registro N ---` a viñetas, para no dejar al usuario sin resumen útil. Sin LLM o con `egress_natural_language_synthesis` / env global desactivados, se omite la segunda pasada LLM y se aplica solo el fallback determinístico cuando aplique.
- **Omisión de clave en `manifest.yaml`** implica **activado** (`egress_natural_language_synthesis` efectivo `true`).

## Opt-out

| Mecanismo | Efecto |
|-----------|--------|
| `egress_natural_language_synthesis: false` en `manifest.yaml` del worker | Desactiva la síntesis para ese template. |
| `DUCKCLAW_DISABLE_NL_REPLY_SYNTHESIS=1` (u otros truthy habituales) en el entorno del proceso | Desactiva la síntesis en **todos** los workers (ops / OOM / diagnóstico). |

## Implementación (referencia de código)

- Detección y prompt: `packages/agents/src/duckclaw/forge/atoms/user_reply_nl_synthesis.py`
- Integración: `packages/agents/src/duckclaw/workers/factory.py` → `set_reply`
- Campo en spec: `packages/agents/src/duckclaw/workers/manifest.py` → `WorkerSpec.egress_natural_language_synthesis`

## Límites

- La evidencia enviada al modelo de síntesis se **trunca** (p. ej. ~12k caracteres) para contener contexto MLX/memoria.
- `max_tokens` moderado en la invocación de síntesis para respuestas breves por defecto.

## Reintentos de inferencia (fallos transitorios)

Ante errores típicos de **conexión** al backend OpenAI-compatible (p. ej. MLX en `127.0.0.1` reiniciando, `connection refused`, timeouts cortos), el gateway puede **reintentar** el `invoke` del modelo con un **backoff** breve, tanto en el **nodo agente** del worker (`build_worker_graph` → `agent_node`) como en la **síntesis NL** de esta spec.

| Variable | Rol |
|----------|-----|
| `DUCKCLAW_LLM_INVOKE_MAX_ATTEMPTS` | Máximo de intentos por invocación (default `3`, tope interno `10`). |
| `DUCKCLAW_LLM_INVOKE_RETRY_DELAY_SEC` | Pausa entre intentos en segundos (default `0.4`). |

No reemplaza tener **MLX-Inference** (u otro servidor) estable en PM2; solo amortigua ventanas cortas de indisponibilidad.

Implementación: `packages/shared/src/duckclaw/integrations/llm_providers.py` (`invoke_chat_model_with_transient_retries`, `is_transient_inference_connection_error`).

## Plantillas nuevas

Los autores de templates **no** deben añadir pasos manuales: el default del manifest cubre el criterio. Solo documenten `egress_natural_language_synthesis: false` si necesitan entregar JSON crudo al usuario (casos excepcionales).

## Validadores posteriores (Finanz y otros)

Tras la síntesis, los validadores existentes (p. ej. auditoría quant/visual en Finanz, Job-Hunter) operan sobre el **texto ya parafraseado**, cuando el flujo los ejecuta.

## Corrección determinista Finanz + IBKR (`snapshot_unavailable`)

Si el último `ToolMessage` de `get_ibkr_portfolio` incluye `snapshot_unavailable` y el borrador de respuesta contiene frases engañosas del tipo «gateway desconectado» / «no logueado» / «necesitas conectar el IB Gateway», **`finanz_repair_ibkr_snapshot_disconnect_paraphrase`** (`user_reply_nl_synthesis.py`) sustituye la sección que empieza en `Cuenta IBKR:` por el texto devuelto por la herramienta. Se invoca desde `set_reply` en `factory.py` **después** de `maybe_synthesize_reply` (y en la ruta de tools embebidas). Objetivo: el Telegram no contradiga el diagnóstico real (API HTTP OK sin snapshot en el servicio portfolio del VPS).
