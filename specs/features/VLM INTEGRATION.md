**VLM INTEGRATION**

### Objetivo
Habilitar el procesamiento de payloads visuales (`photo`, `document`) en el Gateway de Telegram/Discord, utilizando inferencia local soberana (MLX) como motor principal y APIs externas (Gemini/OpenAI) como fallback, garantizando que los datos extraídos no violen la *Regla de Evidencia Única*.

### Contexto
El usuario envía capturas de pantalla de mercados (ej. Google Finance, VIX) o fragmentos de código al War Room. Actualmente, el Gateway ignora estos mime-types o falla al no encontrar texto. Se requiere un pipeline de pre-procesamiento visual que traduzca los píxeles a contexto semántico inyectable en el *Manager Graph*, respetando el *Mention Gate* (Anti-Context Bloat).

### Esquema de datos
**Telegram Webhook Payload (Extendido):**
```json
{
  "message_id": 842,
  "sender_id": "12345678",
  "chat_id": "wr_-100123456789",
  "photo_id": "AgACAgEAAx0...",
  "caption": "@Finanz evalúa el impacto de esta volatilidad en mi portafolio",
  "mime_type": "image/jpeg"
}
```

**StateDelta (Redis Queue):**
```json
{
  "tenant_id": "wr_-100123456789",
  "delta_type": "VLM_CONTEXT_EXTRACTED",
  "mutation": {
    "image_hash": "sha256...",
    "vlm_summary": "Captura de pantalla de Google Finance mostrando el índice VIX con un valor de 24.55 (-2.77%).",
    "confidence_score": 0.89
  }
}
```

### Flujo Cognitivo
1. **Ingesta y Filtro (Gateway):** El webhook recibe el mensaje con la imagen. Se aplica el *Zero-Trust Check* (¿El usuario está en `wr_members`?).
2. **Mention Gate Visual:** Si la imagen **no** tiene un `caption` con una mención explícita (ej. `@Finanz`) o un comando, se hace *Drop Silencioso*. No procesamos imágenes huérfanas para proteger los recursos del Mac mini.
3. **Descarga Efímera:** La imagen se descarga a un buffer en memoria o a `/tmp/duckclaw_vlm/` (montado en RAM disk).
4. **Inferencia Soberana (MLX-VLM):** 
   * Se invoca un modelo cuantizado en Apple Silicon vía **`mlx_vlm` en proceso** (misma familia que Gemma 4 multimodal en disco o HF; sobreescribible con `DUCKCLAW_VLM_MLX_VLM_MODEL`). El cargador pasa `pathlib.Path` al processor/tokenizer (requerido por `mlx_vlm`; evita fallos al unir rutas).
   * **HTTP** (`DUCKCLAW_VLM_MLX_BASE_URL` / `VLM_MLX_BASE_URL`): solo si hay un servidor **OpenAI-compatible con visión** escuchando (p. ej. `mlx_lm.server` suele ser **texto**; si no hay proceso en el puerto, falla con *connection refused*). Para Gemma 4 **imagen**, lo habitual es **local `mlx_vlm`** con los pesos locales o HF, no solo el puerto de texto.
   * **Prompt del sistema VLM:** *"Describe los datos financieros, texto o código presentes en esta imagen de forma concisa. No inventes datos."*
   * **Fallback:** Si MLX (local o HTTP OpenAI-compatible) falla, el Gateway intenta **Gemini Flash** vía API REST y, si sigue fallando o no hay clave, **OpenAI Vision** cuando exista `OPENAI_API_KEY`.

### Variables de entorno (Gateway — visión)

| Variable | Descripción |
|----------|-------------|
| `DUCKCLAW_VLM_MLX_VLM_MODEL` | Repo HF o ruta local de pesos **mlx_vlm** (override). Si no se define, el default sigue al stack Gemma 4 (`MLX_GEMMA4_MODEL_PATH` → `MLX_MODEL_*` con `gemma` → `mlx-community/gemma-4-e4b-it-4bit`). |
| `MLX_VLM_MODEL` | Alias alternativo del anterior. |
| `MLX_GEMMA4_MODEL_PATH` | Misma semántica que texto MLX: si está definido, VLM local usa ese id/ruta sin duplicar config. |
| `DUCKCLAW_VLM_DISABLE_LOCAL_MLX_VLM` | `1` / `true`: no cargar **mlx_vlm** en proceso (solo HTTP u otros backends). |
| `VLM_MLX_DISABLE_LOCAL` | Alias del anterior (misma semántica). |
| `DUCKCLAW_VLM_MLX_BASE_URL` | Base OpenAI-compatible para VLM (p. ej. `http://127.0.0.1:8080/v1`). |
| `VLM_MLX_BASE_URL` | Alias del anterior. Si ninguna está definida, se usa `http://127.0.0.1:{MLX_PORT|8081}/v1`. |
| (cliente HTTP) | Para URLs loopback, el gateway usa `httpx` con `trust_env=False` para que `HTTP_PROXY` no rompa la conexión a MLX local. |
| `DUCKCLAW_VLM_MLX_VLM_PROCESSOR_REPO` | Repo HF para `AutoProcessor` cuando los pesos mlx-community no traen preprocessor válido. |
| `DUCKCLAW_VLM_GEMINI_API_KEY` | Clave Google AI para VLM (prioridad sobre las demás). |
| `GEMINI_API_KEY` | Alternativa estándar de Gemini. |
| `GOOGLE_API_KEY` | Clave de Google AI si no se fijan las anteriores. |
| `DUCKCLAW_VLM_GEMINI_MODEL` | Modelo `generateContent` (default: `gemini-2.5-flash`). |
| `DUCKCLAW_VLM_GEMINI_HTTP_TIMEOUT` | Timeout HTTP en segundos (default acotado ~90s). |

**Orden HTTP:** por defecto `mlx` → `gemini` (si hay clave) → `openai` (si hay clave). Con `DUCKCLAW_VLM_PRIMARY=openai` y `OPENAI_API_KEY`: `openai` → `mlx` → `gemini` (si hay clave).
5. **Inyección de Contexto:** El texto resultante del VLM se concatena con el `caption` original del usuario y se envía al *Manager Graph* como un mensaje de texto estándar.
6. **Ejecución del Worker (Degradación Epistémica):** Finanz recibe: *"Usuario dice: '@Finanz evalúa el impacto...'. Contexto visual adjunto: 'Imagen muestra VIX a 24.55'"*. Finanz **debe** ejecutar `fetch_market_data(symbol="VIX")` para validar el valor real en el ledger antes de calcular la *Temperatura* en su modelo CFD.

### Contratos (Skills)
*   `process_visual_payload(file_id: str, caption: str) -> str`: Función interna del Gateway que orquesta la descarga y la inferencia VLM. Retorna el string descriptivo.
*   `verify_visual_claim(symbol: str, claimed_value: float) -> dict`: Skill determinista para Finanz que cruza el valor extraído por el VLM con el valor real del mercado (IBKR/Lake Capadonna).

### Validaciones
*   **Regla de Evidencia Única (Enforced):** El *Validator Node* de Finanz rechazará cualquier `propose_trade` o cálculo de riesgo que cite el valor "24.55" si no existe un tool call exitoso a una fuente de datos autorizada en el mismo turno. La imagen es una hipótesis; el tool call es la evidencia.
*   **Protección de Memoria (Mac mini):** El proceso de MLX-VLM debe correr en un subproceso con límite de memoria estricto. Si el KV Cache del LLM principal (texto) y el VLM compiten por la memoria unificada y exceden el 85% de la RAM, el VLM hace *fail-fast* hacia la API remota.
*   **Purga de Archivos:** Toda imagen descargada se elimina criptográficamente (`os.remove` + sobrescritura si es disco físico) inmediatamente después de la inferencia. No se guardan imágenes en DuckDB, solo el `image_hash` y el `vlm_summary`.

### Edge cases
*   **Imágenes Múltiples (Álbumes en Telegram):** Telegram envía los álbumes como mensajes separados. El Gateway debe agruparlos por `media_group_id` y procesarlos como un solo batch hacia el VLM para no perder contexto, aplicando un límite estricto de max 3 imágenes por request.
*   **Imágenes sin texto/irrelevantes:** Si el usuario envía un meme al War Room con la mención `@Finanz`, el VLM retornará "Imagen de un gato". Finanz responderá: *"Estímulo visual irrelevante para operaciones de Cyber-Fluid Dynamics. Especifique parámetros financieros."*
*   **Archivos maliciosos (Steganography/Zip bombs):** La validación del `mime_type` debe ser estricta (`image/jpeg`, `image/png`, `image/webp`). Se prohíbe el procesamiento de SVG o PDFs complejos en esta fase inicial para evitar vectores de ataque en la librería de procesamiento de imágenes.