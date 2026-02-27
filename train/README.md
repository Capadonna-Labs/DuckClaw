# Trazas para entrenamiento GRPO

Este directorio almacena trazas en formato JSONL listas para **GRPO** (Group Relative Policy Optimization).

## Formato

Cada línea es un objeto JSON:

```json
{
  "prompt": "¿Quiénes son los mejores vendedores?",
  "completion": "<thought>...</thought>\n<tool_call>...</tool_call>\n<answer>...</answer>",
  "messages": [
    {"role": "user", "content": "¿Quiénes son los mejores vendedores?"},
    {"role": "assistant", "content": "<thought>...</thought>..."}
  ],
  "metadata": {"timestamp": "...", "provider": "groq", "source": "ask_bi"}
}
```

- **prompt**: pregunta del usuario.
- **completion**: respuesta del modelo en formato XML estructurado (thought, tool_call, answer).
- **messages**: formato chat para entrenamiento.
- **metadata**: timestamp, provider (groq/mlx), source.

## Uso

### Guardar trazas desde ask_bi

```python
from duckclaw.bi import ask_bi, load_olist_data
import duckclaw

db = duckclaw.DuckClaw("olist_bi.duckdb")
load_olist_data(db, "data")

respuesta = ask_bi(db, "¿Mejores vendedores?", provider="groq", save_traces=True)

# Enviar también a LangSmith (requiere LANGCHAIN_API_KEY)
respuesta = ask_bi(db, "¿Mejores vendedores?", provider="groq", save_traces=True, send_to_langsmith=True)
```

### API directa

```python
from duckclaw.bi.grpo_traces import save_grpo_trace, load_grpo_traces, trace_stats

save_grpo_trace("¿Cuál es el tiempo de entrega?", "<thought>...</thought>...", provider="mlx")
save_grpo_trace("...", "...", provider="groq", send_to_langsmith=True)  # También a LangSmith
traces = load_grpo_traces(limit=100)  # Por defecto carga grpo_olist_rewarded.jsonl (con rewards)
print(trace_stats())  # Stats del archivo rewarded por defecto
```

### LangSmith

Para enviar trazas a [LangSmith](https://smith.langchain.com/):

1. Crea `.env` en la raíz del repo con:
   - `LANGCHAIN_API_KEY=lsv2_pt_...` (o `LANGSMITH_API_KEY`)
   - `LANGCHAIN_PROJECT=Olist` (debe coincidir con el proyecto en smith.langchain.com)
2. `save_traces=True, send_to_langsmith=True` en `ask_bi` o `save_grpo_trace(..., send_to_langsmith=True)`
3. El módulo carga `.env` automáticamente y usa `tracing_context(enabled=True)` para forzar el envío

## Clasificación de recompensas (GRPO)

Para clasificar rewards y generar el dataset listo para entrenar:

```python
from duckclaw.rl import classify_traces, load_rewarded_traces, compute_reward

# Clasificar todas las trazas y escribir train/grpo_olist_rewarded.jsonl
rewarded, stats = classify_traces()
print("Stats:", stats)

# Cargar trazas clasificadas (con reward)
traces = load_rewarded_traces(min_reward=0.3)
```

Criterios de reward:

- Formato: `<thought>`, `<tool_call>`, `<answer>` en orden (+0.25)
- JSON válido en tool_call (+0.25)
- Tools válidas (+0.25)
- Sin artefactos `<|eot_id|>` (+0.1)
- Coherencia prompt→herramienta (+0.15)
- Penalización por incoherencia o exceso de tools

## Formato GRPO para Unsloth (grupos)

GRPO requiere **múltiples completions por prompt** para calcular ventajas. Si solo hay una respuesta por prompt, el gradiente se anula (Training Loss 0.0).

Convierte `grpo_olist_rewarded.jsonl` al formato de grupos:

```python
from duckclaw.rl import convert_to_grpo_groups

groups, stats = convert_to_grpo_groups()
print("Stats:", stats)  # groups_output, groups_skipped, etc.
```

Salida en `train/grpo_olist_groups.jsonl`:

```json
{"prompt": "¿Cuántas tablas hay?", "completions":[{"text": "<thought>...</thought>...", "reward": 1.0}, {"text": "...", "reward": -0.2}]}
```

Solo se incluyen prompts con ≥2 completions (configurable con `min_completions_per_prompt`). Para tener grupos, repite preguntas con distintos modelos o temperaturas. Si tienes `rewarded.jsonl` en formato flat antiguo, ejecuta `migrate_rewarded_to_groups_format()`.

## Archivos

- `grpo_olist_traces.jsonl`: trazas crudas (append). Entrada de `classify_traces()`.
- `grpo_olist_rewarded.jsonl`: **formato grupos** `{"prompt": "...", "completions": [{"text": "...", "reward": 1.0}]}`. Nuevas trazas se fusionan por prompt. `save_grpo_trace` y `classify_traces` escriben en este formato.
- `grpo_olist_groups.jsonl`: filtrado para Unsloth (solo prompts con ≥2 completions). **Usar para entrenar.**
