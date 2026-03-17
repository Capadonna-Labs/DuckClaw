# TimeContextSkill (Time-Awareness)

## 1. Objetivo Arquitectónico
Proveer al agente de una fuente de verdad temporal sincronizada con el host (Mac Mini). Esta skill no solo devuelve la hora, sino que inyecta el contexto temporal en el `System Prompt` de cada sesión, permitiendo al agente realizar aritmética de fechas (ej. "hace 3 días") sin alucinar.

## 2. Especificación de Skill: `TimeContextSkill`
*   **Ubicación:** `packages/agents/src/duckclaw/forge/skills/time_context.py`
*   **Lógica:**
    1.  Utilizar `zoneinfo` para manejar la zona horaria `America/Bogota`.
    2.  Retornar un objeto JSON con: `iso_8601`, `day_of_week`, `date`, `time`.
*   **Contrato (Python):**
```python
from datetime import datetime
from zoneinfo import ZoneInfo
from langchain_core.tools import tool

@tool
def get_current_time() -> str:
    """
    Retorna la fecha y hora actual en Colombia (COT).
    Úsala para calcular vencimientos, rangos de fechas o responder preguntas temporales.
    """
    tz = ZoneInfo("America/Bogota")
    now = datetime.now(tz)
    return json.dumps({
        "iso_8601": now.isoformat(),
        "day_of_week": now.strftime("%A"),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S")
    })
```

## 3. Inyección Automática en el `AgentAssembler`
El `AgentAssembler` (en `packages/agents/src/duckclaw/forge/assembler.py`) debe inyectar este contexto al compilar el grafo, asegurando que el agente siempre sepa "dónde está en el tiempo".

*   **Lógica de Inyección:**
    ```python
    def get_system_prompt_with_time(base_prompt: str) -> str:
        tz = ZoneInfo("America/Bogota")
        now = datetime.now(tz)
        time_context = f"\n[CONTEXTO TEMPORAL]: Hoy es {now.strftime('%A %d de %B de %Y, %H:%M %Z')}.\n"
        return base_prompt + time_context
    ```

## 4. Auditoría y Registro (Habeas Data)
Para cumplir con la trazabilidad, cada vez que el agente invoque `get_current_time`, el `TaskAuditLog` debe registrar la consulta.

*   **Lógica:** En el nodo `Executor` de LangGraph, si la herramienta ejecutada es `get_current_time`, el `TaskAuditLog` debe registrar:
    *   `task_id`: UUID
    *   `worker_id`: (ej. `finanz`)
    *   `query_prefix`: "Consulta de contexto temporal"
    *   `status`: "SUCCESS"
    *   `duration_ms`: (latencia de la llamada)

## 5. Validación de Escenarios (Tests)
El equipo de QA debe validar los siguientes escenarios en `tests/test_time_context.py`:

1.  **Precisión:** Verificar que la hora devuelta coincida con `America/Bogota` (no UTC).
2.  **Inyección:** Verificar que el `AgentAssembler` inyecta el bloque `[CONTEXTO TEMPORAL]` en el prompt compilado.
3.  **Razonamiento:**
    *   *Input:* "¿Qué día es hoy?" -> *Output esperado:* Debe coincidir con el `day_of_week` del sistema.
    *   *Input:* "¿Cuándo vence la cotización de hace 3 días?" -> *Output esperado:* El agente debe calcular `fecha_actual - 3 días`.

## 6. Consideraciones de Seguridad
*   **Host-Only:** La herramienta debe ejecutarse en el proceso del agente (Mac Mini), nunca en el `Strix Sandbox`. Esto es necesario porque el sandbox no tiene acceso al reloj del sistema host por razones de seguridad.
*   **Inmutabilidad:** El agente no puede cambiar la hora del sistema; la herramienta es estrictamente de lectura.