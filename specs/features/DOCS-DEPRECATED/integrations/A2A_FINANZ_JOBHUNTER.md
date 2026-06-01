# A2A Integration — Finanz ↔ JobHunter

**Objetivo:** Implementar un flujo de colaboración directa donde `Finanz` detecta crisis de liquidez y orquesta a `JobHunter` para encontrar "Inyecciones de Masa" (empleos) de forma autónoma, entregando al usuario una solución financiera integral.

## 1. Arquitectura de Comunicación (A2A Chaining)

Modificaremos el `ManagerGraph` para permitir **Delegación Encadenada**. El estado de LangGraph (`AgentState`) llevará un objeto `handoff_context` que permite transferir variables críticas entre subyacentes.

*   **Flujo:** `Usuario` → `Manager` → `Finanz` (Detecta iliquidez) → `JobHunter` (Busca ingresos) → `Finanz` (Sintetiza reporte) → `Usuario`.

## 2. Contrato de Interfaz (The A2A Payload)

Para que `JobHunter` sepa qué buscar, `Finanz` debe emitir un contrato de necesidad:

```json
{
  "source_worker": "finanz",
  "target_worker": "job_hunter",
  "mission": "INCOME_INJECTION",
  "required_amount_cop": 2500000,
  "urgency": "high",
  "user_profile_ref": "vss_resume_id_001"
}
```

## 3. Ajustes en Workers (ADF)

### A. Finanz: El Sensor de Presión (`system_prompt.md`)
Añadiremos la capacidad de **Handoff Proactivo**:
> "🚨 **PROTOCOLO DE ALIVIO DE CAJA (A2A):**
> Si al ejecutar `read_sql` detectas que el saldo total es < `liquidity_buffer` O el usuario expresa preocupación por falta de dinero:
> 1. No te limites a dar consejos de ahorro.
> 2. Invoca la capacidad de `Job-Hunter` enviando un mensaje interno: 'Necesitamos inyectar masa. Busca 3 vacantes de [Perfil del Usuario] con contratación rápida'.
> 3. Espera el resultado de `Job-Hunter` para integrarlo en tu síntesis final."

### B. Job-Hunter: El Proveedor de Flujo (`system_prompt.md`)
Ajuste para recibir misiones financieras:
> "Si recibes una petición de `Finanz`, tu prioridad cambia a **Quick Hits**:
> 1. Filtra vacantes por 'Tiempo de contratación corto' o 'Freelance/Project-based'.
> 2. El enlace DEBE ser verificado en el Sandbox (Stealth Protocol).
> 3. Devuelve el resultado a `Finanz` en formato estructurado, no al usuario directamente."

## 4. Implementación en el Grafo (`manager_graph.py`)

Implementaremos un nodo de **Router A2A** que intercepte la salida de un worker antes de volver al usuario.

```python
def a2a_router(state: AgentState):
    last_message = state["messages"][-1]
    # Si Finanz pide ayuda a JobHunter
    if "invocar a Job-Hunter" in last_message.content:
        return "Job-Hunter"
    return "end"
```

## 5. Flujo Cognitivo de Alquimia Unificada

1.  **Trigger:** Usuario: *"No me va a alcanzar para la renta este mes, ¿qué hago?"*
2.  **Finanz (Análisis):** Consulta DuckDB. Ve que el reservorio local está en $84k COP. Detecta déficit de $1.5M COP.
3.  **Handoff A2A:** `Finanz` envía a `Job-Hunter`: *"Déficit detectado. Busca ingresos extra de $1.5M+ para este mes."*
4.  **Job-Hunter (Ejecución):** 
    *   `tavily_search` (Fase 1).
    *   `run_browser_sandbox` (Fase 2 - Verificación de links).
    *   Retorna 3 proyectos freelance de Python/Data.
5.  **Finanz (Síntesis Final):**
    > 🧪 **ALQUIMIA DE EMERGENCIA**
    > 
    > **Estado del Reservorio:** Crítico ($84,100 COP).
    > **Acción de Mitigación:** He coordinado con Job-Hunter para buscar inyecciones de flujo.
    > 
    > 💼 **OPORTUNIDADES DE MASA INMEDIATA:**
    > 1. [Link Verificado] - Freelance Data Analyst ($2M COP)
    > 2. [Link Verificado] - Consultoría Express SQL ($800k COP)
    > 
    > **RECOMENDACIÓN:** Aplica a la opción 1 hoy mismo. He reservado $20k para transporte/datos en tu cuenta de Efectivo.