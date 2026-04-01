# Google Trends MCP — Macro Interest (Finanz / QuantClaw)

**Objetivo**  
Exponer al worker **Finanz** datos de **Google Trends** (índice de interés de búsqueda relativo 0–100 y consultas relacionadas) vía **Model Context Protocol (stdio)** para análisis macro y lecturas de divergencia frente al precio (OHLCV en `quant_core`).

**Sin servidor oficial**  
Google no publica un MCP oficial. DuckClaw usa por defecto el paquete PyPI **`google-trends-mcp`** ([PyPI](https://pypi.org/project/google-trends-mcp/)), que envuelve **pytrends** (acceso no oficial a Trends). Consecuencias: posibles **rate limits**, errores intermitentes o cambios del lado de Google; no hay API key obligatoria.

**Herramientas MCP (google-trends-mcp 1.x, nombres reales)**  
Las más usadas en Finanz:

| Necesidad del agente | Tool MCP |
|---------------------|----------|
| Serie de interés en el tiempo | `interest_over_time` |
| Consultas relacionadas a un término | `related_queries` |
| Opcional: comparar varios keywords | `compare_keywords` |

El manifest puede limitar las tools expuestas con `tool_allowlist` para reducir ruido y superficie.

**Backend y arranque**  
- Default: ejecutable **`google-trends-mcp`** en el mismo entorno que el gateway (p. ej. `PATH` del venv tras `uv sync --extra google-trends`), equivalente a la consola definida en el paquete (`server:main` → `mcp.run(transport="stdio")`).  
- Override opcional en manifest: `command` y `args` para `StdioServerParameters`.  
- Alternativa documentada: `uvx google-trends-mcp` si está en PATH.

**Variables de entorno**  
Para **pytrends** no se requieren claves. Una integración futura **SerpApi** u otros MCP comerciales sí las tendrían (`SERPAPI_API_KEY`, etc.); quedan fuera de esta entrega salvo spec aparte.

**Uso en Finanz (divergencias)**  
- Obtener interés con `interest_over_time` / términos relacionados con `related_queries` para el activo o nombre coloquial (NVDA, Bitcoin, etc.).  
- **Cruzar** con precios reales vía `fetch_market_data` y/o `read_sql` sobre `quant_core.ohlcv_data`.  
- Una **subida de precio con caída de interés de búsqueda** puede describirse como hipótesis de “agotamiento de interés retail” o similar — **no** es una señal mecánica ni asesoramiento; el modelo debe ser explícito sobre incertidumbre y límites de los datos.

**Implementación en repo**  
- Bridge: [packages/agents/src/duckclaw/forge/skills/google_trends_bridge.py](packages/agents/src/duckclaw/forge/skills/google_trends_bridge.py)  
- Manifest: `google_trends_config` en [packages/agents/src/duckclaw/workers/manifest.py](packages/agents/src/duckclaw/workers/manifest.py)  
- Grafo: [packages/agents/src/duckclaw/workers/factory.py](packages/agents/src/duckclaw/workers/factory.py)  
- Template: [packages/agents/src/duckclaw/forge/templates/finanz/manifest.yaml](packages/agents/src/duckclaw/forge/templates/finanz/manifest.yaml) y [system_prompt.md](packages/agents/src/duckclaw/forge/templates/finanz/system_prompt.md)

**Alternativas comunitarias (no implementadas aquí)**  
- Servidores npm basados en RapidAPI / SerpApi (p. ej. `@andrewlwn77/google-trends-mcp`) con coste y claves propias.

**Fase 2 (opcional)**  
Persistir snapshots de Trends en DuckDB (`quant_core` o similar) vía db-writer y spec dedicada.
