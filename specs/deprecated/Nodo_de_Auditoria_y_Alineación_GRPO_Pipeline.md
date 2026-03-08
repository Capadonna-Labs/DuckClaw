# Nodo de Auditoría y Alineación (GRPO Pipeline)

## 1. Objetivo Arquitectónico
Implementar un sistema de **Aprendizaje por Refuerzo con Optimización de Política Relativa de Grupo (GRPO)**. Este nodo evalúa las trazas de ejecución en LangSmith, clasifica el éxito/fracaso de las consultas SQL y el código generado en el Sandbox, y genera un dataset de entrenamiento para ajustar el modelo local (Llama-3.2-3B) mediante **Unsloth**.

## 2. Especificación de Skill: `GRPO_Evaluator`

Este nodo actúa como un "Juez" que corre en background tras cada interacción.

*   **Entrada:** `trace_id` (LangSmith), `execution_result` (Strix/DuckDB), `user_feedback` (opcional).
*   **Lógica de Evaluación (Reward Model):**
    1.  **Validación de Ejecución:** ¿El código terminó con `exit_code 0`?
    2.  **Validación de Datos:** ¿El resultado de la consulta SQL está vacío o contiene errores de sintaxis?
    3.  **Validación de Alucinación:** ¿El LLM inventó columnas o tablas que no existen en el esquema de DuckDB?
    4.  **Asignación de Recompensa (Reward):**
        *   `+1.0`: Ejecución exitosa, resultado coherente, sin errores.
        *   `-1.0`: Error de sintaxis SQL, error de ejecución en Sandbox.
        *   `-0.5`: Alucinación (el agente intentó acceder a datos inexistentes).
*   **Salida:** `RewardScore` + `TrainingSample` (Prompt, Código/SQL, Resultado).

## 3. Pipeline de Re-entrenamiento (Unsloth + GRPO)

El sistema no solo observa, sino que **auto-mejora**.

1.  **Data Collection:** El `GRPO_Evaluator` guarda las trazas exitosas en `data/training/success_traces.jsonl`.
2.  **Fine-Tuning (Background Job):**
    *   Cuando el dataset alcanza 100 muestras exitosas, se dispara un job de `pm2` que ejecuta el script de entrenamiento.
    *   **Tecnología:** `Unsloth` (para fine-tuning 2x más rápido y 70% menos memoria).
    *   **Algoritmo:** `GRPO` (optimiza el razonamiento lógico del modelo para que aprenda a generar código SQL/Python que siempre pase el `SQLValidator` y el `StrixSandbox`).
3.  **Hot-Swap:** Una vez finalizado el entrenamiento, el script exporta el modelo en formato `GGUF` y lo reemplaza en el directorio de modelos de `llama.cpp` sin detener el bot.

## 4. Contrato de Integración (LangSmith + GRPO)

Para que esto funcione, cada nodo en tu grafo debe emitir eventos de telemetría estructurados:

```python
# Ejemplo de evento para el Evaluador
{
    "trace_id": "uuid-123",
    "worker_role": "finanz",
    "input": "Calcula el gasto promedio en café",
    "generated_sql": "SELECT AVG(amount) FROM transactions WHERE category = 'cafe'",
    "execution_status": "success",
    "reward": 1.0
}
```

## 5. Ventajas para el Cumplimiento (Habeas Data)
*   **Privacidad en el Entrenamiento:** El fine-tuning ocurre **localmente en tu VPS**. Los datos financieros del usuario nunca salen de tu infraestructura para ser entrenados en servidores de terceros (como OpenAI o Anthropic).
*   **Alineación Específica:** El modelo aprende la "jerga" y la estructura de tus datos financieros específicos, reduciendo drásticamente las alucinaciones y mejorando la precisión del agente con el tiempo.