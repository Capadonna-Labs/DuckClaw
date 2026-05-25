# Reddit MCP — Social Sentiment (QuantClaw / Finanz)

**Objetivo**  
Permitir al worker **Finanz** (cuant / QuantClaw) consultar Reddit vía **Model Context Protocol (stdio)** para señales de sentimiento social: búsqueda por ticker o tema, posts en subreddits, hilos de comentarios. El cómputo de un **Social Score** (p. ej. VADER) se hace en **Strix Sandbox** (`run_sandbox`), no en el proceso del gateway.

**Fuente del servidor MCP**  
No existe `src/reddit` en el repositorio oficial [modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers) en la rama actual. DuckClaw usa el paquete npm **`mcp-reddit`** (`npx --quiet -y mcp-reddit`), alineado con el patrón de [packages/agents/src/duckclaw/forge/skills/github_bridge.py](packages/agents/src/duckclaw/forge/skills/github_bridge.py).

**Herramientas expuestas por `mcp-reddit` (nombres reales)**  

| Uso típico QuantClaw | Tool MCP |
|---------------------|----------|
| Búsqueda global o en subreddit | `search_reddit` |
| Listar posts de un subreddit | `get_subreddit_posts` |
| Metadatos del subreddit | `get_subreddit_info` |
| Detalle de un post | `get_post` |
| Comentarios de un post | `get_post_comments` |
| Perfil / historial usuario | `get_user_info`, `get_user_posts`, `get_user_comments` |

**Paquete npm `mcp-reddit` ≥1.1:** las mismas herramientas se listan con prefijo `reddit_` (p. ej. `reddit_get_post`, `reddit_search_reddit`). El bridge en `reddit_bridge.py` admite **ambos** esquemas de nombres.

**Enlaces de compartir `/r/<sub>/s/<slug>`:** el slug **no** es el `post_id` de la API. El gateway **sigue redirecciones HTTP** hasta `.../comments/<id>/...` y, si la URL final **no** trae parámetros típicos de compartición (`share_id`, `utm_source=share`, `utm_medium=android_app`/app móvil), **sobrescribe** `reddit_get_post` (`subreddit`/`post_id`) con lo parseado; el LLM a veces pone el slug como `post_id`. Si el 301 incluye esos parámetros de tracking, **no** se considera canónica fiable (evidencia producción: mismo `/s/…` puede 301 a otro submission vía servidor Reddit) y `agent_node` **fuerza** `reddit_get_post` en el primer turno y reescribe la llamada a **`reddit_search_reddit`** con query **`r/<sub> shortlink <slug>`** (no la URL cruda — `reddit_search_reddit(query=<url>)` falla en MCP con errores tipo `reading 'children'`). Opt-in legado: **`DUCKCLAW_REDDIT_TRUST_SHARE_TRACKING_REDIRECT=1`** vuelve a confiar en ese 301. Preferir pegar URL `/comments/<id>/…` sin acortador.

**Quant-Trader, sólo línea URL Reddit:** en `packages/agents/src/duckclaw/workers/factory.py`, si el usuario envía **una sola línea** que es HTTP(S) y contiene enlace Reddit (mismo detector que lone-URL para mercenario Quant), `agent_node` **fuerza** la primera llamada Reddit (análogo a la ruta ya existente para `SUMMARIZE_NEW_CONTEXT`), salvo `[SYSTEM_DIRECTIVE: SUMMARIZE_STORED_CONTEXT]` y salvo fuerzos de herramienta de mayor prioridad (schema/read_sql/portfolio, etc.). Así no se sintetiza un “post plausible” desde el chat sin ejecutar `reddit_*`.

**Anti-bucle acortador /s/:** si ya hay **dos** `ToolMessage` de `reddit_search_reddit` para el mismo enlace `/r/…/s/…` y sigue sin resolverse el hilo (caso frecuente: resultados irrelevantes tipo r/all), `agent_node` inyecta `[DIRECTIVA_REDDIT_SHARE_AGOTADO]` y enlaza el LLM **sin** herramientas `reddit_*` en ese turno (solo cuando el invoke sería el genérico `llm_with_tools`), para evitar reintentos infinitos vistos en runtime. El segundo intento de búsqueda usa query alternativa `<subreddit> <slug>` (primer intento: `r/<sub> shortlink <slug>`).

**Contexto LLM (`tools_node` en `factory.py`):** las herramientas cuyo nombre comienza por `reddit_` pasan su salida por [`duckclaw.utils.formatters`](packages/shared/src/duckclaw/utils/formatters.py) (`format_reddit_mcp_reply_if_applicable`) **antes** de añadir el `ToolMessage` al historial, para evitar JSON masivo en contexto/KV cache (Markdown compacto: cabecera `## r/… (Top N posts)`, score, enlace, extracto truncado).

**Redundancia anti-regresión:** justo antes de cada `llm.invoke` en `agent_node`, `sanitize_reddit_tool_messages_for_llm` vuelve a compactar cualquier `ToolMessage` `reddit_*` en la lista enviada al modelo. En `context_monitor` / `_truncate_tool_messages` (BI), el contenido `reddit_*` se compacta antes de truncar por tamaño. Las trazas SFT (`conversation_traces._lc_messages_to_chatml`) aplican el mismo formateador al serializar mensajes `tool` con nombre `reddit_*`.

**Egress Telegram:** si el asistente aún devuelve JSON crudo de listado (`subreddit` + `posts`), `set_reply` y el API Gateway aplican el mismo formateador antes de la síntesis NL / envío. La fachada [`reddit_listing_to_nl.py`](packages/agents/src/duckclaw/forge/atoms/reddit_listing_to_nl.py) reexporta las funciones desde shared por compatibilidad.

Herramientas **mutadoras** del paquete (posts, comentarios, borrado, subida de imagen): por defecto **no** se registran si el manifest tiene `reddit.read_only: true`. Con `read_only: false` se exponen pero quedan envueltas en **HITL** (mensaje que pide `/approve`), igual que GitHub destructivo.

**Variables de entorno (proceso del API Gateway)**  
`mcp-reddit` requiere las cinco variables (app tipo *script* en [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps)):

- `REDDIT_CLIENT_ID`
- `REDDIT_CLIENT_SECRET`
- `REDDIT_USER_AGENT` (formato exigido por Reddit, p. ej. `app:version (by /u/username)`)
- `REDDIT_USERNAME`
- `REDDIT_PASSWORD`

Recomendación operativa: cuenta Reddit **dedicada** (no la personal principal); rotar secretos si se filtran; no commitear valores en YAML ni en el repo.

**Requisitos de runtime**  
- Node.js en el `PATH` del gateway (PM2). **Prefetch recomendado:** `bash scripts/prefetch_mcp_reddit.sh` instala `mcp-reddit@1.1.8` en `{repo}/.mcp-cache/reddit/`; `reddit_bridge.reddit_mcp_server_params()` arranca con `node …/dist/server.js` (~3 s) en lugar de `npx -y mcp-reddit` (2–5 min por descarga npm).  
- Fallback: `npx --quiet -y mcp-reddit` si no hay cache ni `mcp-reddit` global.  
- Warm en lifespan del gateway (`warm_reddit_mcp_pool`, hilo daemon). Pool stdio serializa conexiones (`reddit_mcp_pool._connect_lock`).  
- Timeouts: `DUCKCLAW_REDDIT_MCP_WARM_TIMEOUT_S` (default 90), `DUCKCLAW_REDDIT_MCP_REGISTER_TIMEOUT_S` (12 sin cache, 45 con prefetch), `DUCKCLAW_REDDIT_MCP_LIST_TOOLS_TIMEOUT_S` (60 con sesión pool lista).  
- Paquete Python `mcp` ya declarado en el workspace de agentes.

**Configuración en manifest (worker)**  
Bloque opcional en `skills` o clave de nivel superior, p. ej.:

```yaml
reddit:
  read_only: true
  npm_package: mcp-reddit   # default
  hitl_destructive: true    # solo aplica si read_only: false
```

**Rate limits**  
Reddit API: del orden de **~100 consultas por minuto** por cliente OAuth; el agente debe agrupar queries y evitar bucles de herramientas.

**Flujo Social Score (fase 1)**  
1. El agente llama herramientas Reddit (solo lectura) y obtiene texto agregado en el contexto.  
2. Para puntuación de sentimiento, ejecuta código Python en **`run_sandbox`** usando **VADER** (`vaderSentiment`), disponible en la imagen sandbox documentada en [docker/sandbox/Dockerfile](docker/sandbox/Dockerfile).  
3. No inventar títulos, votos ni URLs: citar solo lo devuelto por las tools.  
4. Persistencia histórica en DuckDB (`quant_core.social_*`) queda como **fase 2** opcional (requiere spec y writer ACID aparte).

**Seguridad**  
- Solo lectura por defecto para reducir superficie (sin publicar ni borrar en Reddit desde el agente).  
- Cumplimiento de [términos de la API de Reddit](https://www.reddit.com/wiki/api).

**Implementación en repo**  
- Bridge: [packages/agents/src/duckclaw/forge/skills/reddit_bridge.py](packages/agents/src/duckclaw/forge/skills/reddit_bridge.py)  
- Manifest / WorkerSpec: `reddit_config` en [packages/agents/src/duckclaw/workers/manifest.py](packages/agents/src/duckclaw/workers/manifest.py)  
- Registro en grafo: [packages/agents/src/duckclaw/workers/factory.py](packages/agents/src/duckclaw/workers/factory.py)  
- Template Finanz: [packages/agents/src/duckclaw/forge/templates/finanz/manifest.yaml](packages/agents/src/duckclaw/forge/templates/finanz/manifest.yaml) y [system_prompt.md](packages/agents/src/duckclaw/forge/templates/finanz/system_prompt.md)
