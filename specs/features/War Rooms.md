# War Rooms

### Objetivo
Diseñar e implementar el paradigma de **War Rooms** (Salas de Guerra): entornos de ejecución multi-agente y multi-humano sobre integraciones de mensajería grupal (Telegram/Discord MCP), garantizando aislamiento de tenant, Zero-Trust mediante RBAC estricto, y consistencia transaccional vía Singleton Writer.

### Contexto
Actualmente, el arnés opera bajo un modelo 1:1 donde el `chat_id` mapea directamente a un tenant en DuckDB (`db/private/<chat_id>/`). La introducción de grupos (N:M) rompe este paradigma. Un War Room requiere que múltiples humanos (desarrolladores/operadores) y múltiples workers (Finanz, JobHunter, GitClaw) coexistan en un mismo canal. Esto introduce riesgos de *Context Bloat* (ruido humano), violaciones de seguridad (usuarios no autorizados en el grupo) y *Race Conditions* en la mutación de estado. La solución exige un Gateway determinista y un modelo de invocación explícita.

### Esquema de datos
El War Room opera como un tenant soberano (`db/private/wr_<group_id>/`).

**DuckDB (SQL - Esquema `war_room_core`):**
```sql
CREATE TABLE wr_members (
    user_id VARCHAR PRIMARY KEY, -- Telegram/Discord ID
    username VARCHAR,
    clearance_level ENUM('admin', 'operator', 'observer'),
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE wr_audit_log (
    event_id UUID PRIMARY KEY,
    sender_id VARCHAR, -- Puede ser humano o agent_id
    target_agent VARCHAR, -- NULL si es broadcast
    payload TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Redis Queue (StateDelta Payload Update):**
```json
{
  "tenant_id": "wr_-100123456789",
  "delta_type": "WR_MESSAGE_PROCESSED",
  "mutation": {
    "sender": "12345678",
    "agent_invoked": "Finanz",
    "action": "propose_trade"
  },
  "signature": "sha256_hash"
}
```

### Flujo Cognitivo
1. **Ingesta (Gateway MCP):** El webhook de Telegram/Discord recibe un mensaje de un `group` o `supergroup`.
2. **Filtro Zero-Trust (Determinista):** El Gateway consulta `wr_members` en DuckDB (vía read-pool efímero). Si el `sender_id` no existe, el mensaje se dropea silenciosamente (DROP). Si el bot es añadido a un grupo no autorizado, hace `leave_chat` automáticamente.
3. **Invocación Explícita (Anti-Context Bloat):** El Gateway solo enruta el mensaje al *Manager Graph* si contiene una mención explícita (ej. `@DuckClaw`, `@Finanz`, `@GitClaw`). El ruido humano sin mención se ignora y no consume tokens.
4. **Orquestación (Manager Graph):** 
   * Extrae la intención y el *target worker*.
   * Recupera el contexto comprimido del War Room (últimas 5 interacciones relevantes vía VSS).
   * Despacha el payload al worker específico.
5. **Ejecución y A2A Visible:** El worker ejecuta su pipeline. Si requiere ayuda de otro agente (ej. Finanz necesita a JobHunter), emite un `[A2A_REQUEST]` que el Gateway renderiza en el grupo como una mención visible: *"@JobHunter, requiero escaneo de vacantes para inyección de liquidez"*.
6. **Egress:** El worker responde en el grupo citando el mensaje original del humano o agente que lo invocó.

### Contratos (Skills)
*   `register_wr_member(user_id: str, clearance: str) -> dict`: Solo ejecutable por un `admin` existente. Emite *StateDelta* para añadir un humano al War Room.
*   `get_wr_context(timeframe_minutes: int) -> str`: Recupera un resumen de las decisiones tomadas en el War Room en el tiempo especificado, consultando `wr_audit_log`.
*   `broadcast_alert(level: str, message: str) -> None`: Permite a un worker (ej. SIATA Analyst detecta PM2.5 crítico) enviar un mensaje proactivo al grupo sin invocación previa, sujeto a políticas de rate-limit.

### Validaciones
*   **Regla de Invocación Estricta:** Los workers tienen prohibido procesar mensajes que no los mencionen directamente o que no provengan del *Manager Graph*.
*   **HITL Distribuido:** Si un worker genera una operación de alto riesgo (ej. `propose_trade`), **cualquier** humano en el War Room con `clearance_level = 'admin'` puede emitir `/execute_signal <signal_id>`. El Singleton Writer validará el `clearance_level` antes de mutar el estado.
*   **Aislamiento de Sandbox:** Los scripts ejecutados en el Strix Sandbox por orden de un War Room se etiquetan con el `tenant_id` del grupo. Los outputs (`.parquet`) se guardan en `/workspace/output/wr_<group_id>/`.

### Edge cases
*   **Menciones Múltiples (`@Finanz y @BI_Analyst analicen X`):** El Gateway divide el payload. El *Manager Graph* orquesta una ejecución paralela (Fan-out) y consolida las respuestas antes del Egress, o permite que cada worker responda asíncronamente citando el mensaje original.
*   **Revocación de Acceso en Vuelo:** Si un humano es eliminado de `wr_members` mientras un worker procesa su petición, el nodo de *Egress* validará nuevamente el clearance antes de responder. Si falla, aborta con "Clearance Revoked".
*   **Ceguera Sensorial por Spam:** Si humanos autorizados spamean comandos, el Gateway aplica un *Token Bucket Rate Limiter* por `user_id`. Exceder el límite resulta en un *cooldown* de 5 minutos impuesto a nivel de Redis, protegiendo el KV Cache de MLX.