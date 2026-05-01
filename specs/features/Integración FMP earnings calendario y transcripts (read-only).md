# Integración FMP — calendario de earnings y transcripts (solo lectura)

## Objetivo

Extender el uso de [Financial Modeling Prep](https://financialmodelingprep.com) como **sistema de alerta temprana** datos-driven para **Quant Trader** y el radar CFD: JSON estructurado desde FMP frente a scraping frágil, alineado con la filosofía de soberanía computacional DuckClaw (procesamiento pesado fuera del contexto principal del LLM cuando sea posible).

**Alcance de esta spec:** contrato funcional y flujos; la implementación vive en el mismo puente Python que dividendos (`fmp_bridge.py`), reutilizando `_fmp_api_key`, `_fmp_base_url` y el cliente HTTP `_fmp_get_json` (timeouts, errores sin filtrar `apikey`). Ver spec hermana: [Integración FMP dividendos (read-only).md](./Integración%20FMP%20dividendos%20(read-only).md).

## Variables de entorno

Mismas que dividendos:

| Variable | Obligatoria | Descripción |
|----------|-------------|-------------|
| `FMP_API_KEY` | Sí | Clave API. Configurar en `.env` del host/gateway; no registrar en logs ni trazas. |
| `FMP_API_BASE` | No | Origen HTTP (default `https://financialmodelingprep.com`). |

## Herramientas LangGraph (diseño)

Registrar **dos** herramientas adicionales cuando el bloque `fmp` del manifest esté habilitado (mismo criterio `enabled: false` que dividendos), con nombres orientados al resto del worker:

1. **`get_fmp_earnings_calendar`** (o nombre equivalente acordado en PR, coherente con `get_fmp_*`)
   - **Parámetros:** `from_date`, `to_date` (ISO `YYYY-MM-DD`); validación de rango acotado (p. ej. máximo 90 días, mismo espíritu que calendario de dividendos).
   - **Datos:** filas típicas con `symbol`, `date`, `eps`, `epsEstimated`, `time` (nombre de zona o banda del día según payload FMP).
   - **HTTP de referencia (FMP v3):** `GET …/api/v3/earning_calendar?from={from}&to={to}&apikey=***`. Si FMP expone ruta **`stable/`** equivalente documentada oficialmente, preferir **`stable/`** para consistencia con dividendos (`_fmp_get_json("stable/…", {...})`).
   - **Salida:** texto/tabular compacto para el modelo (lista truncada por `limit`), mensajes claros si lista vacía o error HTTP.

2. **`get_fmp_earnings_transcript`**
   - **Parámetros:** `ticker` (normalizado mayúsculas); `year` (`int`); `quarter` (`int`, 1–4).
   - **HTTP (implementado):** `GET {FMP_API_BASE}/stable/earning-call-transcript?symbol={TICKER}&year={year}&quarter={quarter}&apikey=***`.
   - **Salida:** cuerpo de transcripción (**contenido largo**): devolver texto plano concatenado desde el campo `content` del primer elemento de la lista JSON, o string vacío con mensaje explícito si `[]`. Documentar en la descripción de la tool que el consumidor **no** debe pegar el transcript completo al usuario por defecto; el flujo recomendado es el reactor sandbox (abajo).

**Seguridad:** no loguear URL con `apikey`; mismas reglas que spec dividendos.

## Manifest y red

- **Quant Trader:** hoy declara `fmp: {}` junto a dividendos; esta spec asume que **las nuevas tools se enganchan al mismo registro FMP** (ampliación de `register_fmp_skill` o factoría equivalente), no un segundo bloque duplicado.
- **Salida a Internet:** el host del worker debe poder resolver HTTPS hacia `financialmodelingprep.com` cuando FMP esté activo (`network_access`/ops del despliegue). Si el manifest fija red deshabilitada, documentar la excepción operativa necesaria sólo donde las tools se ejecutan (gateway vs worker), sin ensanchar alcance más allá de dominios acordados.

## Reglas de contexto (operativo)

Antes de un **rebalanceo HRP** (sandbox o ciclo guiado donde el objetivo implique sizing vs mandato jerárquico), el agente debe **consultar el calendario de earnings** FMP para los **tickers del universo o posiciones vigentes del turno** en una ventana razonable (p. ej. ±7 u ±14 días respecto al día de revisión según playbook ops), para no ignorar catalizadores corporativos estructuralmente visibles.

Esta regla es complementaria al mandato CFD/MOC ([Core-Satellite HRP Weekly + MOC CFD.md](./Core-Satellite%20HRP%20Weekly%20+%20MOC%20CFD.md)): FMP aporta **calendario y narrativa de management**; no sustituye evidencia OHLCV ni el job `moc_pipeline.py`.

## Flujo cognitivo: reactor de sentimiento (sandbox Strix)

Objetivo: **no** alimentar al LLM con decenas de páginas de transcript en cada turno (tokens y latencia).

1. **Ingesta:** el worker obtiene transcript vía `get_fmp_earnings_transcript` (solo cuando el ticker/fecha tiene sentido; p. ej. tras hit en calendario o decisión deliberada).
2. **Aislamiento:** enviar texto al **Strix Sandbox** (`execute_sandbox_script`): sin montar DuckDB vault; script recibe texto por argumentos o artefacto mínimo inyectado según práctica actual del sandbox.
3. **Procesamiento local:** script en Python usando **NLTK**, **TextBlob** u otro método **ligero instalable en la imagen** del sandbox; segmentación heurística (p. ej. bloques tipo “opening/CEO remarks” vs “Q&A”) y **métricas de densidad/emoción por sección** (no modelo generativo SaaS dentro del sandbox salvo nueva spec).
4. **Veredicto:** el sandbox devuelve **JSON corto** hacia el host, por ejemplo forma orientativa:

   ```json
   {
     "sentiment_score": -0.8,
     "key_topics": ["AI CapEx", "guidance"],
     "key_risks": ["supply chain", "guidance cut"]
   }
   ```

   Esquema y claves pueden afinarse en implementación siempre que sigan siendo compactos (<2 KB típico).

5. **Acción:** el agente cruza veredicto con **Radar CFD** (`quant_core.fluid_state`). Semántica ejemplificativa para producto:

   - sentimiento muy negativo + fase **`PLASMA`** (definiciones en specs CFD vigentes): priorizar comunicación explícita al usuario sobre riesgo y **no trivializar** recomendaciones SELL/reducción (`propose_trade_signal` / HITL existente).

No se auto-asigna ejecutión real sin comandos Telegram/HITL ya definidos por spec principal de trading.

## Caso práctico (ejemplo META, ilustrativo)

1. ~14:00 COT — calendario FMP marca reporte de META en la ventana de interés intradía.
2. Post-publicación (~16:xx según TZ del exchange) — transcript disponible estructurado vía endpoint FMP.
3. Sandbox — aumento relativizado de menciones monetizadas tipo “CapEx IA” vs benchmark de llamadas previas; tono CFO medido con polaridad más baja en Q&A.
4. Radar CFD muestra masa/contracción conforme modelo de fluidos.
5. El agente notifica algo del estilo “alerta de fase”: sentimiento FMP adversus + CFD en tensión + **pregunta única HITL** (volumenes ilustrativos), sin ejecución autónoma.

## Fuera de alcance (aquí)

- Cron dedicado ingestando todos los transcripts del mercado.
- Persistencia nueva en DuckDB para cada línea del calendario (si se necesita historia, nueva spec ACID/db-writer).
- Script concreto del sandbox: artefacto de implementación; si se añade, enlazar desde snippets o `templates/Quant-Trader` con versión etiquetada de dependencias (NLTK data, corpus).

## Relación con otras specs

- Dividendos FMP siguen aisladamente en la spec dividendos; esta spec amplía endpoints **earnings**.
- Mantener lineamiento **read-only**: FMP solo consulta datos; órdenes siguen canal IBKR/tooling existentes.

## Código (referencia en repo)

- Tools: [`packages/agents/src/duckclaw/forge/skills/fmp_bridge.py`](../../packages/agents/src/duckclaw/forge/skills/fmp_bridge.py) — `get_fmp_earnings_calendar`, `get_fmp_earnings_transcript`, registradas junto a dividendos en `register_fmp_skill`.
- Snippet sandbox (sentimiento): [`packages/agents/src/duckclaw/forge/templates/Quant-Trader/snippets/earnings_transcript_sentiment_sandbox.py`](../../packages/agents/src/duckclaw/forge/templates/Quant-Trader/snippets/earnings_transcript_sentiment_sandbox.py).
