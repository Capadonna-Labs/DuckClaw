# cmd|descripción
/team|Whitelist + grants bases compartidas (--shared-*)
/vault|Bóvedas privadas: ver/listar/crear/cambiar/eliminar
/workers|Equipo (templates): ver o definir workers para este chat
/roles|Ver todos los trabajadores virtuales (templates)
/tasks|Estado actual: BUSY/IDLE, subagente, tarea
/history|Historial de tareas (quién hizo qué)
/goals|Manifiesto homeostasis: metas de dominio + umbrales infra (--set, --rm, --priority, --monitor, --task, --migrate, --reset)
/crons|Solo programación proactiva: --delta / --timestamp; --rm delta|wall (metas en /goals)
/loop|Auto-mejora: bare, on, on --delta, --delta (silencio), --status, on 4h (reloj), off
/loop-approve [uuid]|HITL: confirma homeostasis tras validación de /goals; alias /loop_approve
/loop-reject [uuid] [razón]|HITL: rechaza homeostasis pendiente; alias /loop_reject
/meditate|(Deprecated) alias de /loop
/meditate-approve [uuid]|(Deprecated) alias de /loop-approve
/meditate-reject [uuid] [razón]|(Deprecated) alias de /loop-reject
/prompt <worker_id>|Ver prompt; --change <texto> para cambiar
/model|Ver o cambiar LLM (provider/model; openrouter, or, deepseek, mlx, …)
/models|Listar modelos disponibles de un provider (ej. gemini)
/skills <worker_id>|Herramientas del template
/forget|Borrar historial de la conversación
/summarize|Compactar hilo manualmente (context monitor → bóveda)
/context|on|off (historial); en Telegram: --add / --summary (memoria semántica)
/comfyui|Proveedor visual: --provider local|fal (ComfyUI Mac vs Fal.ai cloud)
/sandbox|Toggle ejecución de código (true|false) para esta sesión
/sandox|(Alias) /sandbox para tolerar errores de escritura.
/heartbeat|Activa mensajes en tiempo real mientras el agente trabaja
/audit|Última auditoría de ejecución
/health|Estado del servicio
/sensors|DuckDB, Lake, Tavily, Reddit, Trends, browser sandbox
/setup|Config key=value
/approve|Aprobar última acción
/reject|Rechazar última acción
/approve-code <uuid>|HITL: aprueba code_decision y crea PR vía GitHub MCP; alias /approve_code
/reject-code <uuid> [razón]|Rechaza code_decision PENDING_HITL en main.code_decisions
/uncertainty --status|Lista eventos PENDING_HITL en main.agent_uncertainty_log
/resolve-uncertainty <uuid>|Resuelve evento de incertidumbre HITL; alias /resolve_uncertainty
/lake|Estado del túnel SSH remoto (env DUCKCLAW_REMOTE_SSH_* + prueba rápida)
