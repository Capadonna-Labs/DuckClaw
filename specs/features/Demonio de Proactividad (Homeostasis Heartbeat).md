# Demonio de Proactividad (Homeostasis Heartbeat)

## 1. Objetivo Arquitectónico
Desplegar un microservicio independiente (`services/heartbeat`) que se despierte periódicamente, evalúe las métricas de homeostasis en DuckDB y, si detecta una anomalía, inyecte un "Pensamiento Interno" en el API Gateway. El agente procesará este pensamiento y decidirá si debe usar la herramienta de salida (n8n Outbound) para alertar al usuario, respetando los límites de spam en Redis.

## 2. Topología del Flujo Proactivo

```mermaid
graph TD
    A[Heartbeat Daemon] -->|1. Cron (ej. cada 1h)| B[(DuckDB: Evaluar Homeostasis)]
    B -->|2. Sorpresa Alta detectada| C[Redis: Check Cooldown]
    C -->|3. Permitido| D[FastAPI Gateway: POST /chat]
    D -->|4. Inyecta Pensamiento| E[LangGraph: Agente]
    E -->|5. Decide Alertar| F[Tool: send_proactive_message]
    F -->|6. Webhook| G[n8n: Outbound Flow]
    G -->|7. Mensaje| H[Usuario Telegram/WPP]
```

## 3. Especificación del Microservicio: `services/heartbeat/main.py`

Este script correrá en un bucle infinito gestionado por PM2.

```python
import asyncio
import httpx
import logging
import redis.asyncio as redis
from duckclaw.forge.homeostasis.manager import HomeostasisManager

logger = logging.getLogger("heartbeat")
REDIS_URL = "redis://localhost:6379/0"
GATEWAY_URL = "http://localhost:8000/api/v1/agent/chat"

async def check_cooldown(r: redis.Redis, tenant_id: str, alert_type: str) -> bool:
    """Verifica si ya enviamos esta alerta recientemente (Anti-Spam)."""
    key = f"cooldown:{tenant_id}:{alert_type}"
    if await r.exists(key):
        return False
    # Bloquear futuras alertas de este tipo por 24 horas (86400 segundos)
    await r.setex(key, 86400, "locked")
    return True

async def run_heartbeat():
    r = redis.from_url(REDIS_URL)
    hm = HomeostasisManager() # Tu manager actual que lee DuckDB
    
    while True:
        logger.info("Iniciando ciclo de evaluación de Homeostasis...")
        
        # 1. Evaluar todos los tenants/workers
        anomalies = hm.evaluate_all_systems() 
        
        for anomaly in anomalies:
            tenant_id = anomaly["tenant_id"]
            alert_type = anomaly["belief_key"] # ej. "presupuesto_mensual"
            
            # 2. Control de Spam (Redis)
            if await check_cooldown(r, tenant_id, alert_type):
                logger.info(f"Anomalía detectada en {tenant_id}. Inyectando pensamiento...")
                
                # 3. Inyección de Pensamiento Interno al Gateway
                payload = {
                    "message": f"[SYSTEM_EVENT: Anomalía detectada en {alert_type}. Valor actual: {anomaly['observed_value']}. Evalúa la situación y notifica al usuario si es crítico.]",
                    "chat_id": anomaly["admin_chat_id"], # A quién avisar
                    "is_system_prompt": True # Flag para que el Gateway sepa que no es un humano
                }
                
                async with httpx.AsyncClient() as client:
                    await client.post(
                        f"{GATEWAY_URL}?tenant_id={tenant_id}&worker_id=finanz", 
                        json=payload,
                        headers={"X-Tailscale-Auth-Key": "tu_secreto"}
                    )
        
        # Dormir por 1 hora antes del siguiente chequeo
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(run_heartbeat())
```

## 4. Especificación de Skill: `send_proactive_message`

El agente necesita una herramienta para "hablar" hacia afuera, ya que este flujo no fue iniciado por un mensaje de Telegram que n8n esté esperando responder síncronamente.

*   **Ubicación:** `packages/agents/src/duckclaw/forge/skills/outbound_messaging.py`
*   **Contrato:**
    ```python
    from langchain_core.tools import tool
    import httpx
    import os

    @tool
    def send_proactive_message(chat_id: str, message: str) -> str:
        """
        Usa esta herramienta para enviar un mensaje proactivo o una alerta al usuario.
        Solo úsala cuando un [SYSTEM_EVENT] te lo solicite.
        """
        # Llama al Flujo 2 (Outbound) de n8n que configuramos antes
        webhook_url = os.getenv("N8N_OUTBOUND_WEBHOOK_URL")
        
        response = httpx.post(
            webhook_url,
            json={"chat_id": chat_id, "text": message},
            headers={"X-DuckClaw-Secret": os.getenv("N8N_AUTH_KEY")}
        )
        
        # Auditoría: Registrar en DuckDB que el agente inició la conversación
        # append_task_audit(..., status="PROACTIVE_MESSAGE_SENT")
        
        return "Mensaje enviado exitosamente al usuario."
    ```

## 5. Integración en PM2 (`ecosystem.config.cjs`)

Añade el nuevo microservicio a tu orquestador para que arranque junto con el Gateway y el DB-Writer.

```javascript
{
  name: "DuckClaw-Heartbeat",
  script: "uv",
  args: "run --project services/heartbeat python main.py",
  env: {
    "REDIS_URL": "redis://localhost:6379/0"
  }
}
```