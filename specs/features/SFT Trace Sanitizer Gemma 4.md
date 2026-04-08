# SFT Trace Sanitizer Gemma 4

## Objetivo

Preparar trazas de producción (ChatML en JSONL) para fine-tuning supervisado (SFT) con **mlx_lm.lora** y Gemma 4, sin entrenar con razonamiento interno de modelos tipo R1 ni con cifras sin evidencia de herramienta.

## Fuentes y salida

| Concepto | Ruta |
|----------|------|
| Entrada (datalake) | `packages/agents/train/conversation_traces/YYYY/MM/DD/traces.jsonl` |
| Salida (espejo sanado) | `packages/agents/train/gemma4/YYYY/MM/DD/traces.jsonl` |

La jerarquía `YYYY/MM/DD/traces.jsonl` se conserva; solo cambia el directorio raíz (`conversation_traces` → `gemma4`).

## Script

- **Ubicación**: `scripts/sanitize_traces_for_gemma.py`
- **Ejecución**: Python 3.9+ (Apple Silicon compatible), UTF-8.

### CLI

| Flag | Descripción |
|------|-------------|
| `--input-root` | Raíz del datalake de trazas (default: `packages/agents/train/conversation_traces` relativo al repo). |
| `--output-root` | Raíz de salida (default: `packages/agents/train/gemma4`). |
| `--input-glob` | Opcional; patrón glob adicional bajo `input-root` (default: `**/traces.jsonl`). |
| `--dry-run` | No escribe archivos; imprime conteos y tasa de descarte. |
| `--verbose` | Log DEBUG. |

### Invariantes

1. **Ablación CoT**: Se eliminan bloques `<redacted_thinking>...</redacted_thinking>` del texto antes de validar y templar.
2. **Regla de evidencia única**: Si un turno `assistant` (contenido ya limpio) contiene términos CFD reservados (`Temperatura`, `Densidad`, `Masa`, `Presión`, `viscosidad`, case-insensitive) **o** un patrón monetario `$` con dígitos, el mensaje **inmediatamente anterior** en la lista debe ser `role: tool` cuyo contenido indique ejecución exitosa (JSON sin error fatal, `status: ok`, `exit_code: 0` en sandbox, lista de filas `read_sql`, etc.). Si no se cumple, **toda la línea de traza se descarta** (no se escribe en `gemma4/`).
3. **Alcance**: La regla se aplica al **contenido del assistant**, no al system prompt.

### Formato de cada línea de salida (JSONL)

Un objeto JSON por línea, UTF-8:

- `text` (string, obligatorio): conversación en formato de turnos Gemma 4 (`<start_of_turn>user` / `<start_of_turn>model` / `<end_of_turn>`), incluyendo system fusionado al primer turno user cuando aplique.
- `session_id`, `timestamp`, `status`, `worker_id`: copiados de la traza origen si existen.

Herramientas OpenAI-style se serializan como bloques XML:

```xml
<tool_call>
{"name": "...", "arguments": {...}}
</tool_call>
```

Resultados de tool se representan en turnos `user` con prefijo identificable del nombre de herramienta.

### Auditoría

- Con `--dry-run`, si la tasa de descarte global supera el **30 %**, se emite un warning: revisar alucinaciones en producción o relajar el validador.

### DuckDB

`task_audit_log` en el gateway **no** almacena mensajes completos; el sanitizer opera sobre archivos JSONL. DuckDB puede usarse de forma opcional para ingestión masiva (`read_json_auto`) en evoluciones futuras; el script prioriza lectura línea a línea en Python.

## Privacidad y Git

Los directorios `conversation_traces/` y `gemma4/` pueden contener datos sensibles; suelen ignorarse en `.gitignore` en entornos locales.
