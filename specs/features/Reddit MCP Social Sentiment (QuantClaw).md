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
- Node.js y `npx` en el `PATH` del proceso que ejecuta el gateway (p. ej. PM2), análogo a `@modelcontextprotocol/server-github`.  
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
