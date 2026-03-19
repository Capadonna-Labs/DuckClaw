# Formateo de Datasets (SFT & GRPO)

## 1. Objetivo Arquitectónico
Construir un transformador de datos (`TraceFormatter`) que convierta los logs operativos (auditoría) en formatos estándar de la industria (`ChatML` / `OpenAI Format`) compatibles nativamente con `mlx_lm.lora` (para SFT) y librerías de RL como `TRL/Unsloth` (para GRPO).

## 2. Especificación de Formato: `_sft` (Supervised Fine-Tuning)

Para SFT, el modelo necesita ver la conversación completa, **incluyendo el uso de herramientas**. `mlx_lm` espera un JSONL donde cada línea tiene una clave `"messages"`.

*   **Estructura requerida (`dataset_sft.jsonl`):**
```json
{
  "messages":[
    {
      "role": "system",
      "content": "Eres Finanz. Tienes acceso a la herramienta read_sql..."
    },
    {
      "role": "user",
      "content": "¿Cuánto dinero tengo en Bancolombia?"
    },
    {
      "role": "assistant",
      "tool_calls":[{"name": "read_sql", "arguments": {"query": "SELECT balance FROM cuentas WHERE name='Bancolombia'"}}]
    },
    {
      "role": "tool",
      "name": "read_sql",
      "content": "[{\"balance\": 5000000}]"
    },
    {
      "role": "assistant",
      "content": "Tienes $5,000,000 en tu cuenta de Bancolombia."
    }
  ]
}
```
*   *Nota Arquitectónica:* Si la interacción fue un simple saludo (como en tu ejemplo), el array solo tendrá `system`, `user` y `assistant`.

## 3. Especificación de Formato: `_grpo` (Group Relative Policy Optimization)

Para GRPO (Aprendizaje por Refuerzo), el formato es diferente. No le das la respuesta final al modelo; le das el **Prompt** y dejas que el modelo genere múltiples respuestas durante el entrenamiento, las cuales son evaluadas por tu `Reward Function` (ej. el `SQLValidator`).

*   **Estructura requerida (`dataset_grpo.jsonl`):**
```json
{
  "prompt":[
    {
      "role": "system",
      "content": "Eres Finanz. Tienes acceso a la herramienta read_sql..."
    },
    {
      "role": "user",
      "content": "¿Cuánto dinero tengo en Bancolombia?"
    }
  ],
  "reward_metadata": {
    "expected_sql_tables": ["cuentas"],
    "worker_id": "finanz"
  }
}
```
*   *Nota Arquitectónica:* La clave `reward_metadata` no la lee el modelo, la lee tu script de entrenamiento (`train_grpo.py`) para saber cómo calcular la recompensa (ej. verificar que el modelo intentó usar la tabla `cuentas`).

## 4. Especificación de Skill: `TraceFormatter`

Debes crear un script que lea tu base de datos de auditoría (o LangSmith) y genere estos archivos `.jsonl`.

*   **Ubicación:** `packages/agents/src/duckclaw/train/formatter.py`
*   **Lógica Interna:**
    1.  **Extracción:** Leer `task_audit_log` donde `status == 'SUCCESS'`.
    2.  **Reconstrucción de Contexto:** Buscar en la tabla `telegram_messages` (o en el Checkpointer de LangGraph) el historial completo de esa `session_id` para recuperar el `system_prompt` y las `tool_calls`.
    3.  **Data Masking:** Aplicar regex para enmascarar PII (Habeas Data).
    4.  **Exportación:**
        *   Si el flag es `--mode sft`, exportar con la estructura de `messages`.
        *   Si el flag es `--mode grpo`, exportar con la estructura de `prompt`.

## 5. Contrato de Implementación (Python)

```python
import json

def format_for_sft(raw_trace: dict, system_prompt: str, tool_calls: list = None) -> str:
    """Convierte una traza cruda al formato ChatML para MLX SFT."""
    messages = [{"role": "system", "content": system_prompt}]
    messages.append({"role": "user", "content": raw_trace["user_message"]})
    
    if tool_calls:
        # Inyectar el razonamiento intermedio
        messages.extend(tool_calls)
        
    messages.append({"role": "assistant", "content": raw_trace["assistant_reply"]})
    
    return json.dumps({"messages": messages})
```