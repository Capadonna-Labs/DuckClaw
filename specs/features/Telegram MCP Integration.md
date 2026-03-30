
# Telegram MCP Integration (Egress Gateway)

**Objetivo**
Reemplazar la dependencia externa de n8n para el envío de mensajes a Telegram mediante la implementación de un servidor MCP (Model Context Protocol) local. DuckClaw actuará como un *MCP Client*, consumiendo las herramientas de Telegram de forma estandarizada, síncrona y tipada, resolviendo definitivamente los problemas de formato multimedia (imágenes/documentos).

**Contexto**
Actualmente, el flujo de salida (Egress) depende de webhooks HTTP hacia n8n, lo que añade latencia de red, fragmenta la lógica de negocio fuera del repositorio y dificulta el manejo de errores (ej. el bug `IMAGE_PROCESS_FAILED` del BI Analyst). Al integrar un `telegram-mcp-server` ejecutado localmente vía `stdio`, LangGraph puede invocar la API de Telegram como una herramienta nativa, manteniendo el control total del ciclo de vida del mensaje y los reintentos dentro del ecosistema Python/MLX.

**Esquema de datos (Configuración MCP)**
El servidor MCP vive en el monorepo en **`packages/mcp/telegram/`** (paquete `duckclaw-telegram-mcp`, módulo `duckclaw_telegram_mcp`). La configuración del arnés está en la raíz del repo: **`config/mcp_servers.yaml`** (no en `packages/core`, que es duckclaw-core).

```yaml
# config/mcp_servers.yaml — por defecto el gateway arranca el hijo con el mismo Python que uvicorn
# (evita con PM2 el error uv "Package duckclaw-telegram-mcp not found in workspace").
mcp_servers:
  telegram:
    enabled: false  # o true / DUCKCLAW_TELEGRAM_MCP_ENABLED=1
    env: {}
```

Instalación: `uv sync` en la raíz (Python **3.10+** trae `mcp` y `duckclaw-telegram-mcp`). Gateway: `DUCKCLAW_TELEGRAM_MCP_ENABLED=1` y `TELEGRAM_BOT_TOKEN`; ver `docs/COMANDOS.md`.

* **Wizard (`duckops init` → `scripts/duckclaw_setup_wizard.py`):** al completar la configuración con canal Telegram, al guardar/salir del flujo del API Gateway, o al editar el Brain (PM2/systemd) con canal Telegram, el asistente escribe por defecto `DUCKCLAW_TELEGRAM_MCP_ENABLED=1` y pone `enabled: true` bajo `mcp_servers.telegram` en `config/mcp_servers.yaml` (primer integrador MCP del stack; otros se podrán añadir con la misma convención). Reiniciar el gateway para aplicar.

**Flujo**
1. **Ingress (Sin cambios):** Telegram envía el webhook -> Cloudflare Tunnel -> FastAPI (DuckClaw Gateway) -> Redis Queue.
2. **Inicialización MCP:** Al arrancar el gateway (FastAPI), un `MCPClient` opcional se conecta por `stdio` al proceso **`python -m duckclaw_telegram_mcp`** definido en `config/mcp_servers.yaml` (paquete en `packages/mcp/telegram/`).
3. **Ejecución (Egress):** Cuando el agente (ej. Leila o BI Analyst) decide responder, LangGraph intercepta la salida y llama a la tool expuesta por el servidor MCP (`telegram_send_message` o `telegram_send_photo`).
4. **Transmisión:** El servidor MCP recibe la llamada JSON-RPC localmente, formatea el `multipart/form-data` correcto (incluyendo `Content-Type: image/png` para gráficos) y hace el POST a la API de Telegram.
5. **Confirmación:** El servidor MCP devuelve el `message_id` de Telegram a LangGraph para confirmar la entrega.

**Contratos (Tools expuestas por el MCP Server)**

El servidor MCP expondrá automáticamente estas herramientas al cliente DuckClaw:

```json
// Tool: telegram_send_message
{
  "name": "telegram_send_message",
  "description": "Envía un mensaje de texto a un chat de Telegram.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "chat_id": { "type": "string" },
      "text": { "type": "string" },
      "parse_mode": { "type": "string", "enum":["MarkdownV2", "HTML"], "default": "MarkdownV2" }
    },
    "required":["chat_id", "text"]
  }
}

// Tool: telegram_send_photo
{
  "name": "telegram_send_photo",
  "description": "Envía una imagen generada en el Sandbox a Telegram.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "chat_id": { "type": "string" },
      "photo_base64": { "type": "string", "description": "Buffer de la imagen en Base64" },
      "filename": { "type": "string", "default": "chart.png" },
      "caption": { "type": "string" }
    },
    "required": ["chat_id", "photo_base64"]
  }
}
```

**Validaciones**
1. **Aislamiento de Proceso:** El servidor MCP debe ejecutarse como un subproceso (`stdio`) gestionado por el ciclo de vida de FastAPI. Si FastAPI muere, el proceso MCP debe terminar (evitar procesos zombies).
2. **Validación de Payload Multimedia:** El servidor MCP debe decodificar el `photo_base64` y empaquetarlo estrictamente con el MIME type `image/png` antes de enviarlo a Telegram, rechazando payloads malformados antes de tocar la red.
3. **Rate Limiting:** El servidor MCP debe respetar los límites de la API de Telegram (ej. máximo 30 mensajes por segundo), implementando un backoff interno si recibe un HTTP 429 (Too Many Requests).

**Edge cases**
1. **Caída de Red (Telegram API Down):** Si la API de Telegram no responde (Timeout), el servidor MCP devolverá un error JSON-RPC. El nodo de LangGraph debe capturar este error y encolar el mensaje en Redis para un reintento diferido (Dead Letter Queue), evitando que el agente asuma que el usuario leyó el mensaje.
2. **Archivos Demasiado Grandes:** Si el BI Analyst genera un gráfico que excede los 10MB (límite de Telegram para fotos), el servidor MCP debe hacer un fallback automático interno a `sendDocument` sin que LangGraph tenga que gestionar esa lógica.