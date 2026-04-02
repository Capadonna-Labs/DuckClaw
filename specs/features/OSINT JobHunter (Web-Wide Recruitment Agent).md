### OSINT JobHunter (Web-Wide Recruitment Agent)

**Objetivo:** Desplegar un pipeline de descubrimiento de empleo en dos fases (Búsqueda Amplia + Extracción Profunda) utilizando navegación agentiva, garantizando que el KV Cache del Mac mini no colapse por el HTML basura de la web.

#### Fase 1: Discovery (Búsqueda Amplia)

En lugar de navegar a ciegas, el agente primero usa un motor de búsqueda para obtener URLs candidatas.

- **Herramienta:** Un MCP de búsqueda (ej. `google-search-mcp`, `tavily-mcp`, `brave-search`).
- **Técnica (Google Dorks):** El agente genera queries precisas.
  - *Ejemplo:* `"Data Engineer" AND ("Remote" OR "Colombia") (site:greenhouse.io OR site:jobs.lever.co OR site:linkedin.com/jobs)`
- **Salida:** Una lista de 10-15 URLs limpias.

**Entrega al usuario (contrato UX):** ante una petición de ofertas para postular, el agente debe priorizar **hasta 3 vacantes** con descripción breve (snippet Tavily o texto extraído en sandbox) y **un enlace literal verificado** por herramienta (`tavily_search` / Playwright en `run_browser_sandbox`); sin inventar URLs para rellenar. Detalle operativo: `packages/agents/src/duckclaw/forge/templates/Job-Hunter/system_prompt.md`.

**Flujo cognitivo (garantía de ejecución):** (1) **`tavily_search` siempre primero** — no anticipar fallo del sandbox antes del resultado de Tavily; (2) intentar **`run_browser_sandbox`** solo después; (3) si el sandbox falla, **egress inmediato** con datos crudos de Tavily (sin simular otra discovery).

**Contrato skill `tavily_search` (manifest):** `include_raw_content: false` (evitar hinchado de contexto con HTML crudo), `max_results: 15` (margen para filtrar manualmente las mejores URLs).

**Edge case — 0 resultados:** el agente debe reformular la query (sinónimos de rol, otra geografía, otro `site:`) y volver a llamar Tavily antes de rendirse (~2 reintentos razonables).

**Validación de egress:** si el mensaje contiene URLs plantilla (`example.com` / `example.org` / `example.net`), `pid=123456`, `localhost` o `127.0.0.1`, el runtime **rechaza** la respuesta y sustituye un aviso (implementación: `job_hunter_output_validator` + `set_reply` en worker).

#### Fase 2: Deep Extraction (Strix Browser Sandbox)

El script en el contenedor usa **Playwright** (`playwright.async_api`). Debe **validar** la página antes de extraer: comprobar selectores críticos (p. ej. `.job-view-layout` en LinkedIn, o `h1` con texto relevante según portal), rechazar **404**, mensajes tipo **“No se ha podido cargar”** u otros errores visibles, y en ese caso devolver **error explícito** sin inventar filas en Parquet. Detalle: `Job-Hunter/system_prompt.md` (Fase 2).

- **El Contrato del Sandbox:** El agente inyecta las URLs en un script de Python que corre en el contenedor efímero.
- **Código Generado por el Agente (Ejemplo para Cursor):**
  ```python
  import asyncio
  import pandas as pd
  from browser_use import Agent
  from pydantic import BaseModel
  from langchain_openai import ChatOpenAI

  # Forzamos un esquema estricto para evitar alucinaciones
  class JobExtraction(BaseModel):
      title: str
      company: str
      location: str
      salary_range: str | None
      requirements: list[str]
      apply_url: str

  urls =["https://jobs.lever.co/ejemplo/123", "https://linkedin.com/jobs/view/456"]
  extracted_jobs =[]

  async def extract_job(url):
      agent = Agent(
          task=f"Ve a {url}. Extrae los detalles del trabajo siguiendo estrictamente el esquema JSON. Si la página no es una oferta de trabajo, devuelve campos vacíos.",
          llm=ChatOpenAI(model="gpt-4o-mini"),
          extract_schema=JobExtraction
      )
      result = await agent.run()
      return result.extracted_data

  async def main():
      # Procesamiento concurrente controlado (max 3 a la vez)
      for url in urls:
          try:
              data = await extract_job(url)
              if data and data.get('title'):
                  extracted_jobs.append(data)
          except Exception as e:
              print(f"Fallo en {url}: {e}")
      
      # Persistencia Soberana (Anti-OOM)
      df = pd.DataFrame(extracted_jobs)
      df.to_parquet('/workspace/output/osint_jobs.parquet')
      print(f"✅ {len(df)} vacantes extraídas y guardadas en Parquet.")

  asyncio.run(main())
  ```

#### Fase 3: Ingesta y Match Vectorial (DuckDB VSS)

1. El script de Python termina. El agente lee el resultado: `"✅ 8 vacantes extraídas..."`.
2. El agente usa `read_sql` para ingerir el Parquet en la memoria del tenant:
  ```sql
    INSERT INTO finance_worker.job_opportunities 
    SELECT * FROM read_parquet('/workspace/repo_db/output/osint_jobs.parquet');
  ```
3. *(Opcional - Siguiente Nivel):* Si tenemos la extensión VSS de DuckDB activa, el agente puede hacer una búsqueda de similitud semántica entre los `requirements` extraídos y el `resume_embeddings` del usuario para filtrar solo los que tengan >85% de match.

#### Fase 4: Egress (Telegram MCP)

El agente envía un mensaje limpio y accionable:

> 📊 **OSINT JobHunter: Resultados**
> Encontré 8 vacantes remotas de Data Engineer. Las 3 con mayor compatibilidad a tu perfil son:
>
> 1. **MercadoLibre** (Vía LinkedIn) - *Requiere Python, DuckDB, AWS.* [Link]
> 2. **Nubank** (Vía Greenhouse) - *Requiere Spark, Scala.* [Link]
>
> ¿Deseas que redacte una Cover Letter adaptada para la opción 1 en el Sandbox?

---

### Notas de implementación (DuckClaw)

- **Herramienta sandbox browser:** `run_browser_sandbox` en código usa la imagen `duckclaw/browser-env:latest` (sobreescribible con `STRIX_BROWSER_IMAGE`). Build: `docker build -t duckclaw/browser-env:latest docker/browser-env/`.
- **Ruta `read_parquet`:** el ejemplo anterior con `'/workspace/repo_db/output/osint_jobs.parquet'` es solo ilustrativo. Tras `run_browser_sandbox`, usa la ruta **absoluta del host** que aparece en `artifacts` (típicamente bajo `output/sandbox/osint_jobs.parquet` del proceso gateway), no rutas internas del contenedor.
- **Plantilla:** `packages/agents/src/duckclaw/forge/templates/job_hunter/` (`browser_sandbox: true`, Tavily + policy con `max_execution_time_seconds` hasta 300).
- **DDL:** `finance_worker.job_opportunities` en `forge/templates/finanz/schema.sql` (columnas base más `status`, `applied_at`, `notes` para seguimiento; índice único opcional sobre `apply_url` salvo duplicados legacy).
- **Escritura / SRP:** JobHunter mantiene `job_opportunities` en `allowed_tables`. FinanzWorker también puede escribir la misma tabla (misma bóveda) para registros rápidos; alternativa A2A: si Finanz emite **`[a2a_request: job_opportunity_tracking]`**, el manager delega en JobHunter la misión **JOB_OPPORTUNITY_TRACKING** (persistencia sin forzar Tavily). Detalle de grafo: `packages/agents/src/duckclaw/graphs/manager_graph.py`.
- **VSS (siguiente nivel):** si existe extensión VSS en DuckDB y tabla/columna de embeddings del CV (`resume_embeddings` u homónimo), se puede filtrar por similitud coseno sobre el texto agregado de `requirements`; umbral orientativo **> 0.85** según normalización del índice. Si el tenant no tiene VSS, omitir esta fase.

