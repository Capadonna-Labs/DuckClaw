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

### 2.1 Role flattening para Gemma / `mlx_lm` (dataset entrenable)

Los tokenizers de **Gemma** no usan roles `system` ni `tool` en el mismo esquema que OpenAI. El collector SFT (`duckclaw.forge.sft.collect_traces_to_sft`) transforma las trazas crudas antes de escribir **`train/gemma4/dataset_sft.jsonl`**:

1. **System → primer `user`:** el texto de `system` se concatena al inicio del primer mensaje `user` (separador `\n\n`).
2. **`assistant` con `tool_calls`:** las invocaciones se serializan como un bloque JSON de texto dentro de `content`, precedido por la marca `[TOOL_CALLS_JSON]` (el modelo aprende el patrón en texto plano).
3. **`tool` → `user`:** cada resultado de herramienta pasa a `{"role":"user","content":"[RESULTADO DE HERRAMIENTA {name}]: {content}"}`.
4. **Alternancia:** la lista final solo contiene `user` y `assistant`, fusionando turnos consecutivos del mismo rol con `\n\n` y garantizando alternancia (si hace falta, se antepone un `user` vacío).

La salida sigue siendo un JSONL con `{"messages":[...]}` por línea, pero **sin** roles `system` ni `tool` en `messages`. Política de escritura: **sobrescritura** del archivo de salida al regenerar el dataset.

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

## 5. Entorno: `mlx-lm` y Gemma 4 (SFT / LoRA)

Los checkpoints MLX con `"model_type": "gemma4"` (p. ej. `deadbydawn101/gemma-4-E4B-mlx-4bit` o una carpeta local convertida) **requieren** que el paquete `mlx-lm` incluya el módulo `mlx_lm.models.gemma4`.

| Situación | Acción |
|-----------|--------|
| `ValueError: Model type gemma4 not supported` o `No module named 'mlx_lm.models.gemma4'` | Actualizar: **`pip install -U "mlx-lm>=0.31.2"`** (Gemma 4 entró en [v0.31.2](https://github.com/ml-explore/mlx-lm/releases), p. ej. PR [#1093](https://github.com/ml-explore/mlx-lm/pull/1093)). |
| Re-descarga desde Hugging Face pese a tener el modelo en disco | En `config/lora_config.yaml`, `model` debe ser la **ruta absoluta** a la carpeta local con `config.json` y `model*.safetensors`; un id `org/repo` siempre pasa por el Hub si esa ruta no existe como directorio. |
| `Loading Hugging Face dataset packages/.../sft_data_dir` + `FileNotFoundError` | La ruta `data:` **no existía como directorio**; `mlx_lm` asumió un id de dataset HF. Crea `packages/agents/train/gemma4/sft_data_dir/` con `train.jsonl` (p. ej. copia de `dataset_sft.jsonl`) y `test.jsonl`, o ejecuta `python packages/agents/train/train_sft.py`. |
| `[METAL] Insufficient Memory` / `kIOGPUCommandBufferCallbackErrorOutOfMemory` | Memoria unificada insuficiente en Apple Silicon. En `config/lora_config.yaml`: `grad_checkpoint: true`, bajar `max_seq_length` (p. ej. 1024), `batch_size: 1`, opcionalmente menos `num_layers` o `lora_parameters.rank`; cerrar apps y procesos que usen GPU. |

**Comprobación rápida:** `pip show mlx-lm | grep -i version` debe mostrar **0.31.2 o superior**. (Un `import mlx_lm.models.gemma4` solo es válido en un entorno con Metal/MLX funcional; en CI headless puede fallar por inicialización de GPU.)

Opcional en el monorepo: instalar el extra de entrenamiento del paquete agents, p. ej. `uv pip install -e packages/agents[train]` (ver `pyproject.toml` de `duckclaw-agents`).

### 5.1 Holdout de validación (`valid.jsonl`)

`mlx_lm.lora` carga desde el directorio `data` los archivos `train.jsonl`, `valid.jsonl` y `test.jsonl`. Si `valid.jsonl` falta o está vacío, no hay **Val loss** durante el entrenamiento.

- **`packages/agents/train/train_sft.py`** parte el dataset principal en **train + valid** (por defecto **10 %** a validación, semilla fija). Variables: `SFT_VALID_FRACTION`, `SFT_VALID_SEED`. Con `SFT_SKIP_MLX=1` solo escribe los JSONL sin lanzar MLX.
- En **`config/lora_config.yaml`**: `steps_per_eval` (cada cuántas iteraciones se calcula Val loss) y `val_batches: -1` (toda la validación) o un número fijo de batches.

### 5.2 Inferencia con adapters (Telegram / Gateway)

El chat de Telegram usa el mismo pipeline que el API Gateway: **ChatOpenAI-compatible → `mlx_lm.server`**. Para servir el **mismo base Gemma 4 + LoRA** que entrenaste:

1. **Base MLX** (`model` del YAML de entrenamiento) debe coincidir con **`MLX_MODEL_PATH`** / **`MLX_MODEL_ID`** del proceso que arranca el servidor (misma carpeta local o mismo id HF que al entrenar).
2. **Adapters:** define **`MLX_ADAPTER_PATH`** apuntando al directorio que contiene `adapters.safetensors` y `adapter_config.json` (p. ej. `adapter_path` del `lora_config.yaml`, típicamente `packages/agents/train/gemma4/adapters_lora_yaml` relativo a la raíz del repo).
3. **`packages/agents/train/scripts/start_mlx.sh`** arranca **`run_mlx_lm_server.py`** (delega en `mlx_lm server` de Apple) y pasa `--adapter-path` cuando `MLX_ADAPTER_PATH` existe; incluye una capa fina de **reparación de JSON** en tool calls Gemma 4 cuando la salida del modelo no es JSON estricto. Rutas relativas se resuelven contra la raíz del monorepo.
4. **Gateway / PM2:** en el `.env` del proceso API Gateway (mismo que documenta `docs/COMANDOS.md`): `DUCKCLAW_LLM_PROVIDER=mlx`, `DUCKCLAW_LLM_BASE_URL=http://127.0.0.1:<MLX_PORT>/v1`, `DUCKCLAW_LLM_MODEL` igual que el id que expone `/v1/models` (o alias `gemma4` si aplica según `mlx_openai_compatible_model_name`).
5. Reiniciar **`MLX-Inference`** (o el proceso que ejecuta `start_mlx.sh`) y el **gateway** que atiende el webhook de Telegram.

Sin `MLX_ADAPTER_PATH`, el servidor MLX usa solo el modelo base (sin fine-tuning).

## 6. Contrato de Implementación (Python)

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