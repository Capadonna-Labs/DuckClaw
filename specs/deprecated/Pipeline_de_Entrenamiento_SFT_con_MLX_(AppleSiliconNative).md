# Pipeline de Entrenamiento SFT con MLX (Apple Silicon Native)

## 1. Objetivo Arquitectónico
Migrar el pipeline de entrenamiento de `Unsloth` (basado en PyTorch/CUDA) a **`mlx-lm` (Apple Silicon Native)**. Al ejecutar el entrenamiento directamente en el motor de Apple, eliminamos la capa de abstracción de CUDA/PyTorch, aprovechando al máximo el *Unified Memory Architecture* de tu Mac M4. Esto permite un entrenamiento SFT más rápido, con menor consumo de energía y una integración nativa con tu stack de inferencia actual.

## 2. Arquitectura del Pipeline MLX-SFT

```mermaid
graph LR
    A[LangSmith: Trazas Exitosas] --> B[DataCollector: MLX-SFT Format]
    B --> C[mlx-lm: Fine-Tuning SFT]
    C --> D[MLX-GGUF Converter]
    D --> E[Hot-Swap: Recarga en mlx_lm.server]
```

## 3. Especificación de Skills del Worker (MLX-SFT)

### Skill: `MLX_DataCollector`
*   **Entrada:** Trazas de LangSmith (`reward == 1.0`).
*   **Lógica:**
    1.  Convertir trazas a formato `jsonl` compatible con `mlx-lm`.
    2.  Estructura requerida: `{"text": "<s>[INST] Prompt [/INST] Código </s>"}`.
*   **Salida:** `dataset_mlx.jsonl`.

### Skill: `MLX_Trainer`
*   **Entrada:** `dataset_mlx.jsonl`, Modelo Base (`Llama-3.2-3B-Instruct` en formato MLX).
*   **Lógica:**
    1.  Cargar modelo con `mlx_lm.load`.
    2.  Configurar `LoRA` (Low-Rank Adaptation):
        *   `rank`: 8 (suficiente para tareas de código).
        *   `alpha`: 16.
        *   `target_modules`: `q_proj`, `v_proj`.
    3.  Ejecutar entrenamiento usando `mlx.optimizers.AdamW`.
*   **Salida:** Adaptador LoRA (`adapters.npz`).

### Skill: `MLX_Converter`
*   **Entrada:** Adaptador LoRA + Modelo Base.
*   **Lógica:**
    1.  Fusionar pesos (`fuse_lora`).
    2.  Convertir a formato `GGUF` (usando `mlx_lm.convert` con `--quantize 4`).
*   **Salida:** `model_finetuned.gguf`.

## 4. Configuración del Worker en PM2 (`ecosystem.config.cjs`)

```javascript
{
  name: "DuckClaw-Trainer-MLX",
  script: "scripts/train_mlx.py",
  cron: "0 4 * * *",
  autorestart: false,
  env: {
    "MODEL_PATH": "mlx-community/Llama-3.2-3B-Instruct-4bit",
    "DATASET_PATH": "./data/training/dataset_mlx.jsonl",
    "LORA_RANK": "8"
  }
}
```

## 5. Protocolo de Hot-Swap (MLX Native)
Dado que tu inferencia corre sobre `mlx_lm.server` (o un wrapper similar), el reemplazo es directo:

1.  El script de entrenamiento guarda el nuevo `model_finetuned.gguf`.
2.  El script envía una señal `SIGTERM` al proceso `DuckClaw-Inference`.
3.  El proceso se reinicia automáticamente (vía PM2) cargando el nuevo archivo `.gguf` desde el disco.
4.  **Zero-Downtime:** Si tienes dos instancias de inferencia, puedes implementar un *Blue-Green Deployment* manual: levantas la nueva instancia con el modelo nuevo, esperas a que cargue, y luego apagas la vieja.

## 6. Ventajas de MLX sobre Unsloth en tu VPS (Mac M4)
1.  **Unified Memory:** MLX no necesita copiar datos entre CPU y GPU. El entrenamiento accede directamente a la RAM del sistema, permitiendo entrenar modelos más grandes sin errores de memoria.
2.  **Eficiencia Energética:** El entrenamiento MLX es significativamente más eficiente en el M4, evitando el *thermal throttling* que suele ocurrir con procesos intensivos de PyTorch/CUDA.
3.  **Stack Unificado:** Tu inferencia ya usa MLX. Usar MLX para el entrenamiento significa que no necesitas instalar `torch`, `bitsandbytes` ni `transformers`, reduciendo el tamaño de tu entorno virtual y la complejidad de dependencias.