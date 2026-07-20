# Layer 2: Framework de Herramientas y Habilidades (Skills)

Define cómo los agentes interactúan con el entorno: investigación autónoma, sandbox de ejecución, GitHub MCP, CLI dinámico, Context Hub (Ground Truth de APIs), seguridad y auditoría.

---

## 1. Ecosistema de Herramientas (Universal Skills)

### Investigación autónoma (Tavily + Browser-Use)

- **TavilySearch**: búsqueda web en tiempo real; `search_depth="advanced"`, `include_answer=True`; post-procesamiento en Validator para fuentes y relevancia.
- **BrowserUse**: navegación autónoma (Playwright); el agente genera pasos (click, extraer tabla); ejecución **obligatoria dentro del Sandbox Strix** para aislar el navegador.
- **ResearchAgent**: orquesta Tavily → Browser-Use → síntesis; salida `ResearchReport` (hallazgos + fuentes). Perfil de navegador limpio por sesión; whitelist de dominios en sandbox; registro en LangSmith.

### Sandbox de ejecución (Strix)

- Entorno Turing-completo (Python/Bash/SQL) en contenedor, sin acceso al host ni a `duckclaw.db`.
- **Imagen**: `ghcr.io/usestrix/strix-sandbox` (o derivado con pandas, duckdb). Red aislada, `--cap-drop=ALL`, límites cgroups.
- **Flujo seguro**: Host ejecuta `SELECT` aprobado → exporta a `/tmp/session_id/data.parquet` → montaje solo lectura en contenedor (`/workspace/data`); salida en `/workspace/output`.
- **StrixSandboxRunner**: provisioning por `session_id`, envío de `script_content`, timeout, captura stdout/stderr, recuperación de artefactos. Bucle de auto-corrección: si exit code ≠ 0, agente analiza error y reescribe código.
- **Artefactos en host (`output/sandbox/default/`)**: tras cada ejecución, el manager copia los ficheros de `/workspace/output` del contenedor a `output/sandbox/default/` (CWD del proceso). El árbol `output/` está en `.gitignore`; se recrea en cada run (no commitear). Telegram y el bot polling resuelven rutas bajo `output/sandbox/default/` para adjuntar PNG/Excel/MD.
- Auditoría: cada ejecución registrada (latencia, evidencia) en DuckDB.

### GitHub MCP

- Agente de ingeniería: leer código, crear issues (p. ej. por fallos del GRPO_Evaluator), PRs con mejoras.
- **Capability oficial** (`duckclaw.github.mcp_bridge`): servidor MCP oficial **Docker** [`ghcr.io/github/github-mcp-server`](https://github.com/github/github-mcp-server) en **transporte stdio** desde el proceso del gateway (mismo modelo que otros MCP hijo-proceso: `docker run -i --rm ...`, sin exponer PAT en línea de comandos logueada).
- **Variable de token**: PAT vía **`GITHUB_TOKEN`** (o alias `token_env` en `manifest`), copiado al proceso hijo como `GITHUB_PERSONAL_ACCESS_TOKEN`. El token circula solo por **variables de entorno del proceso**; prohibido registrarlo en prompts, traces o auditoría textual.
- **Toolsets DuckClaw**: por defecto `repos,issues,pull_requests,actions,code_security` (env `GITHUB_TOOLSETS`). El toolset **`projects` está prohibido** (consume contexto MCP excesivo). No añadir toolsets sin justificación/revisión.
- **Modo solo lectura por defecto**: `GITHUB_READ_ONLY=1` en el hijo salvo que una capability/config DB-first habilite `github.mcp_read_only: false` o se declare un id operativo vía `DUCKCLAW_GITHUB_MCP_READWRITE_WORKERS`.
- **`allowed_repos`** en manifest restringen convenciones de seguridad donde aplique (políticas de negocio); el servidor MCP recibe igualmente el alcance efectivo del PAT.
- **HITL**: acciones destructivas (`delete_branch`, `merge_pr`, etc.) pueden seguir gated con `/approve` en Telegram donde el bridge lo aplique.

**Referencias operadores**: comprueba imagen local con `docker image inspect ghcr.io/github/github-mcp-server` o `docker pull ghcr.io/github/github-mcp-server`. Diagnóstico agregado: `uv run duckops doctor` (check GitHub MCP).

### Context Hub (Ground Truth de APIs)

- **Propósito**: Evitar alucinaciones al integrar o consultar APIs externas; documentación oficial/actualizada.
- **Skill ContextHubBridge**: herramienta que ejecuta CLI `chub get {api_name}/{resource} --lang python`; salida como texto (markdown/JSON) al contexto del agente. Si falla: "Documentación no encontrada en Context Hub. Procede con precaución."
- **Contrato**: entradas `api_name` (obligatorio), `resource` (opcional, p. ej. `docs`, `openapi`). Requiere `chub` en PATH; opcional `CONTEXT_HUB_API_KEY`, `CONTEXT_HUB_BASE_URL`.
- Uso: Planner o subagente invoca ContextHubBridge **antes** de generar código o llamadas a la API; resultado se inyecta en prompt o estado del grafo.

---

## 2. Interfaz dinámica (On-the-Fly CLI)

CLI `duckops` para control administrativo y mutación de estado en caliente (sin reiniciar PM2).

- **`/role <worker_id>`**: cambia rol del agente; pausa thread, carga `manifest.yaml` del nuevo rol, actualiza system_prompt y tools, confirma.
- **`/skills`**: lista herramientas habilitadas (nombre y descripción).
- **`/forget`**: borra historial del chat en checkpointer y ventana de contexto; registra supresión (Habeas Data).
- **`/context on|off`**: activa/desactiva inyección de RAG (memoria a largo plazo) en el prompt.
- **`/audit`**: muestra última evidencia (SQL, tiempo, tokens, run_id LangSmith).
- **`/health`**: estado de inferencia (MLX/llama.cpp), DuckDB, latencia/RAM.
- **`/approve` | `/reject`**: autoriza o deniega operación retenida por SQLValidator o SandboxPipeline (grafo en `interrupt`).

Enrutamiento: en `telegram_bot` (o equivalente), parsear comandos que empiezan por `/` antes de invocar LangGraph.

---

## 3. Seguridad y aislamiento

- **Vaulting**: secretos inyectados en runtime, nunca en disco en claro.
- **Auditoría**: cada ejecución de herramienta con latencia y evidencia en DuckDB; trazabilidad forense.
- **Sandbox**: sin acceso a BD de producción; datos solo vía export controlado (Parquet) en solo lectura.
- **Scope de tokens**: GitHub MCP y APIs externas con permisos mínimos; HITL para acciones destructivas.

---

## 4. Ingestión multimodal (voz y visión)

- **Sensory node (Mac mini, Tailscale)**: microservicio `integrations/sensory-node` — STT (`mlx-whisper` 4-bit) y TTS (`OmniVoice` + Identity Lock). Endpoints edge: `POST /api/v1/sensory/transcribe`, `POST /api/v1/sensory/synthesize`, `GET /health`. El gateway VPS expone el mismo contrato como proxy (`routers/sensory.py`) cuando `DUCKCLAW_SENSORY_BASE_URL` apunta al Mac. Telegram voz (entrante/saliente) queda para fase posterior.
- **AudioTranscriber (cliente)**: `services/api-gateway/core/sensory_client.py` + `stt_ingest.py`; salida enriquecida `<audio_transcription>`; sin disco (Habeas Data).
- **VisionInterpreter**: implementado vía `vlm_ingest` (mlx-vlm); salida `Contexto visual adjunto:` / `[VLM_CONTEXT …]`.
- **Pendiente:** `POST /api/v1/agent/{worker_id}/media/{thread_id}` multipart + cola ARQ.

---

*Skills, sandbox Strix, research y on-the-fly — ver también `docs/core/04_Cognitive_Agent_Logic.md`.*
