Soy **OSINT JobHunter** (empleo / OSINT). Puedo:
• **Discovery:** búsqueda amplia con Tavily (consultas tipo Google Dork; URLs limpias, sin HTML en el chat).
• **Extracción:** navegación pesada en sandbox de navegador (Playwright en contenedor) y resultado en Parquet.
• **Ingesta:** cargar ofertas en DuckDB (`finance_worker.job_opportunities`) con SQL.
• **Resumen:** hasta **3 vacantes** con descripción breve y **enlace verificado** para postular (Tavily + opcional Playwright en sandbox).

Ejemplos: «Busca data scientist remoto Colombia y LinkedIn», «Ofertas de backend en Lever/Greenhouse, Europa». Imagen Docker: `docker build -t duckclaw/browser-env:latest docker/browser-env/`. `/sandbox on` para ejecutar código en contenedor.
