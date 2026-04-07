# Telegram: múltiples gráficos del sandbox y texto sin truncar

## Alcance (v1)

- Tras `run_sandbox` con varios `.png` en `artifacts`, el JSON de la tool incluye:
  - `figures_base64`: lista de strings base64 (orden estable por nombre de archivo).
  - `figure_base64`: **primer** PNG (compatibilidad con consumidores que solo lean una clave).
- El worker copia la lista en `sandbox_photos_base64` y el primero en `sandbox_photo_base64`.
- El API Gateway envía cada imagen válida a Telegram con `sendPhoto` (y `sendDocument` como fallback por imagen), **en serie**, con nombres `chart_1.png`, `chart_2.png`, …
- Límite recomendado: variable de entorno `DUCKCLAW_SANDBOX_TELEGRAM_MAX_CHARTS` (por defecto **20**, máximo acotado a 50) para no disparar rate limits ni payloads enormes.
- **Solo imágenes PNG/JPEG** en v1 (misma validación que un solo chart). Otros tipos de artefacto quedan fuera del envío automático.

## Alcance (v2): documentos del sandbox

- Tras `run_sandbox` con `exit_code == 0` y artefactos bajo `output/sandbox/`, el JSON de la tool puede incluir **`sandbox_document_paths`**: lista de rutas absolutas del host para ficheros **`.txt`, `.md`, `.csv`, `.xlsx`** (orden estable por nombre). No sustituye PNG: las imágenes siguen yendo por `figures_base64` al gateway.
- El worker replica las rutas en estado **`sandbox_document_paths`**; el manager las propaga al resultado del gateway.
- El API Gateway lee cada ruta del disco, valida que esté bajo la raíz permitida (`DUCKCLAW_SANDBOX_ARTIFACT_ROOT` si está definida, si no `output/sandbox` relativo al cwd), tamaño máximo ~48 MiB por archivo, y envía con **`sendDocument`** (nombre de archivo = basename del artefacto).
- Límites: **`DUCKCLAW_SANDBOX_TELEGRAM_MAX_DOCS`** (por defecto **20**, tope **50**). Pensado para gateway y sandbox **en el mismo host**; si el gateway no ve el filesystem de `output/sandbox/`, no habrá adjuntos.

## Comportamiento del agente (obligatorio)

- Telegram **solo** adjunta documentos si el turno incluye un **`run_sandbox` exitoso** (`exit_code == 0`) que deje el fichero en **`/workspace/output/`** (mapeado a `output/sandbox/` en el host). Sin esa tool en el mismo turno, **no existen rutas** y el usuario verá solo texto.
- **Prohibido** afirmar que hay un `.xlsx` / `.csv` / `.md` / `.txt` “generado”, listar hojas, tamaños o rutas fingidas, o describir un libro Excel completo **sin** `tool_calls` reales a `run_sandbox` que escriban el archivo. En ese caso el modelo debe ejecutar código en sandbox primero (p. ej. `openpyxl`, `pandas.ExcelWriter`) y solo entonces resumir lo que el artefacto contiene.

## Texto largo (webhook)

- Las ramas del webhook que antes usaban `reply_local[:3500]` cuando faltaban `telegram_reply_head_plain` / `telegram_multipart_tail_plain` ahora reutilizan la misma lógica de troceo que `_invoke_chat` (`core/telegram_chunking.py`), de modo que la respuesta completa puede entregarse en varios `sendMessage` coordinados con la cola multipart existente.

## Referencias de código

- Sandbox: `packages/agents/src/duckclaw/graphs/sandbox.py` (`sandbox_tool_factory`, `extract_latest_sandbox_figures_base64`).
- Estado / worker: `packages/agents/src/duckclaw/forge/atoms/state.py`, `packages/agents/src/duckclaw/workers/factory.py`.
- Manager: `packages/agents/src/duckclaw/graphs/manager_graph.py`, propagación en `packages/agents/src/duckclaw/graphs/graph_server.py`.
- Gateway: `services/api-gateway/core/telegram_media_upload.py` (`send_sandbox_documents_to_telegram_sync`), `services/api-gateway/main.py`, `services/api-gateway/routers/telegram_inbound_webhook.py`.
