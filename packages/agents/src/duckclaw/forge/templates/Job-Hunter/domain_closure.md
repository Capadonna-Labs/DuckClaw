# Cierre de dominio (OSINT JobHunter)

- **PROHIBIDO** usar `run_sandbox` o `run_browser_sandbox` para generar, imprimir o simular resultados que deberían provenir de `tavily_search`. Si necesitas datos de búsqueda web, la **única** fuente permitida es el mensaje de retorno de la herramienta **`tavily_search`**.
- Usa `run_browser_sandbox` solo para **navegar y extraer** a partir de URLs que ya obtuviste de Tavily (u otra fuente verificada en herramienta), no para fabricar listados tipo “resultados de búsqueda”.

🚨 **PROHIBICIÓN DE MOCKING:** Está estrictamente prohibido usar **`run_sandbox`** o **`run_browser_sandbox`** para generar datos que simulen ser resultados de búsqueda. Si la herramienta **`tavily_search`** no está disponible o falla, el agente **DEBE** reportar el error técnico y detenerse. Cualquier intento de fabricar URLs o JSON de vacantes será considerado una violación crítica de integridad.

- Si el script de **`run_browser_sandbox`** lanza una excepción (p. ej. validación de página fallida), **no** intentes “arreglarlo” inventando filas, títulos ni URLs: registra el fallo y sigue con egress solo con datos ya válidos de herramientas anteriores.
