### MQL5 Stealth Reader (Finanz)

**Objetivo:** Que el agente Finanz lea páginas **mql5.com** vía `run_browser_sandbox` (Playwright) con prácticas de sigilo razonables y reciba en el contexto el **contenido impreso a stdout** del script (`stdout_tail` / `stderr_tail` en el JSON de la tool), para no inferir fallos vacíos cuando `exit_code` es 0.

**Dependencia:** Implementación en `packages/agents/src/duckclaw/graphs/sandbox.py` (`browser_sandbox_tool_factory` → `run_browser_sandbox`). Plantilla de referencia: `packages/agents/src/duckclaw/forge/templates/finanz/snippets/mql5_playwright_stealth.py`. Comportamiento operativo y reintento único: `forge/templates/finanz/system_prompt.md` (PROTOCOLO MQL5) y `domain_closure.md`.

**Límites:** Hardening técnico razonable (UA, headers, `networkidle`/hidratación según plantilla, etc.); **no** bypass legal ni de ToS. El sigilo **no garantiza** eludir Cloudflare u otras defensas. **Auto-Pivote OSINT:** si el sandbox devuelve metadatos (p. ej. título y autor) pero no el código, se permite **un** `tavily_search` acotado en el mismo turno; no sustituye el intento primario ni el archivo `.mq5`. Sin código ni metadatos tras reintento → **muro de seguridad**. El agente puede **proponer** un clon aproximado en Python con `run_sandbox` y `quant_core.ohlcv_data` (LIMIT 5000).

**Contrato de salida:** El script enviado a `run_browser_sandbox` debe terminar con `print(json.dumps(...))` (o texto explícito) para que el modelo lea `stdout_tail` en la respuesta JSON de la tool. Los tails están acotados en caracteres para no saturar el contexto del LLM.
