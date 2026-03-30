

# SPEC: Migración de Orquestación n8n a Integración Nativa Telegram (DuckClaw)

## 1. Objetivo
Eliminar la dependencia de n8n para reducir la latencia, evitar errores de protocolo SSL (`EPROTO`) y centralizar la lógica de negocio en el backend de Python (FastAPI).

## 2. Arquitectura de Referencia (n8n vs. Nativo)

*   **Actual:** `Telegram` ⮕ `n8n (Webhook)` ⮕ `DuckClaw (API)` ⮕ `n8n (Response)` ⮕ `Telegram`.
*   **Propuesta:** `Telegram` ⮕ `DuckClaw (FastAPI Webhook)` ⮕ `DeepSeek/LLM` ⮕ `DuckClaw (Direct Push)` ⮕ `Telegram`.

---

## 3. Componentes a Implementar

### A. Endpoint de Recepción (Webhook)
Se debe crear un router en FastAPI que reciba el objeto `Update` de Telegram.
*   **Ruta:** `/api/v1/telegram/webhook`
*   **Método:** `POST`
*   **Seguridad:** Validar un `X-Telegram-Bot-Api-Secret-Token` o filtrar por IPs de Telegram (opcional si usas Tailscale).

### B. Cliente de Salida (Telegram Bot Client)
Implementar una clase `TelegramService` utilizando `httpx` para enviar respuestas de forma asíncrona.

### C. Lógica de Mapeo (Análisis del JSON previo)
El backend debe extraer manualmente lo que n8n hacía en los nodos:
1.  `chat_id`: Extraer de `message.chat.id`.
2.  `text`: Extraer de `message.text`.
3.  `username`: Extraer de `message.from.username`.

---

## 4. Cambios en el Repositorio (Implementación — monorepo DuckClaw)

### 1. Variables de Entorno (`.env`)
```env
TELEGRAM_BOT_TOKEN=tu_token_aqui
DUCKCLAW_API_BASE_URL=https://tu-maquina.ts.net
# En producción: misma cadena que secret_token en setWebhook de Telegram
TELEGRAM_WEBHOOK_SECRET=un_password_seguro_y_largo
# Opcional (webhook): worker y tenant por defecto
DUCKCLAW_TELEGRAM_DEFAULT_WORKER=finanz
DUCKCLAW_TELEGRAM_DEFAULT_TENANT=default
# Partes 2..N de la respuesta por Bot API si no usas cola n8n
DUCKCLAW_TELEGRAM_NATIVE_SEND=true
```

### 2. Paquete compartido — carpeta explícita `integrations/telegram/`

Ubicación: `packages/shared/src/duckclaw/integrations/telegram/`

| Archivo | Rol |
|--------|-----|
| `telegram_long_polling_bot_base.py` | Base del bot por long polling (`TelegramBotBase`). |
| `telegram_bot_api_async_client.py` | Cliente httpx async (`sendMessage`, troceo MarkdownV2). |
| `telegram_webhook_secret_header.py` | Valida `X-Telegram-Bot-Api-Secret-Token` vs `TELEGRAM_WEBHOOK_SECRET`. |

### 3. API Gateway

| Módulo | Rol |
|--------|-----|
| `services/api-gateway/routers/telegram_inbound_webhook.py` | `POST /api/v1/telegram/webhook`: dedupe Redis por `update_id`, `_invoke_chat`, envío de respuesta por Bot API. |
| `services/api-gateway/core/telegram_multipart_tail_dispatch_async.py` | Cola de texto largo: nativo o `N8N_OUTBOUND_WEBHOOK_URL`. |

El pipeline del agente coincide con `POST /api/v1/agent/{worker_id}/chat` (mismos guards, fly commands, grafo).

*(Referencia histórica: los ejemplos con prefijo `app/` de un layout genérico FastAPI no aplican a este monorepo.)*

---

## 5. Pasos para el "Switch-Off" de n8n

1.  **Configurar Webhook:** Telegram no sabe dónde enviar los mensajes hasta que tú le digas. Ejecuta este comando una sola vez (recomendado: `secret_token` igual a `TELEGRAM_WEBHOOK_SECRET`):
    ```bash
    curl -X POST https://api.telegram.org/bot<TOKEN>/setWebhook \
         -H "Content-Type: application/json" \
         -d '{"url": "https://tu-dominio.ts.net/api/v1/telegram/webhook", "secret_token": "<TELEGRAM_WEBHOOK_SECRET>"}'
    ```
2.  **Eliminar n8n del `docker-compose.yml`:**
    *   Remover servicio `n8n`.
    *   Remover servicio `n8n-db`.
    *   Eliminar carpetas `./n8n_data` y `./db_data`.
3.  **Actualizar DuckClaw:** Desplegar el nuevo router de FastAPI.

---

## 6. Ventajas del Cambio (Análisis de Rendimiento)

1.  **Eliminación del error `EPROTO`:** Al no haber un intermediario local (n8n) intentando forzar HTTPS en un puerto interno HTTP (8000), la comunicación es directa y limpia.
2.  **Memoria RAM:** n8n + Postgres consumen aprox **800MB - 1.2GB** de RAM. Al eliminarlos, ese recurso queda libre para que tu **Mac Mini de AI** corra modelos locales o maneje más concurrencia.
3.  **Debugging:** Los logs de error ahora aparecerán directamente en tu consola de Python/Uvicorn, no tendrás que saltar entre los logs de n8n y los de tu API.

