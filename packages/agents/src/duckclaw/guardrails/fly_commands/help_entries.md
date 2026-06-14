# cmd|descripción
/team|Whitelist + grants bases compartidas (--shared-*)
/vault|Bóvedas privadas: ver/listar/crear/cambiar/eliminar
/workers|Equipo (templates): ver o definir workers para este chat
/roles|Ver todos los trabajadores virtuales (templates)
/tasks|Estado actual: BUSY/IDLE, subagente, tarea
/history|Historial de tareas (quién hizo qué)
/goals|Manifiesto homeostasis: metas de dominio + umbrales infra (--set, --rm, --migrate, --reset)
/crons|Solo programación proactiva: --delta / --timestamp; --rm delta|wall (metas en /goals)
/meditate|Infra: --delta 4h|10m|off (contrasta /goals). Quant-Trader: --self|--now pasa al agente (auto-mejora)
/prompt <worker_id>|Ver prompt; --change <texto> para cambiar
/model|Ver o cambiar LLM (provider/model; openrouter, or, deepseek, mlx, …)
/models|Listar modelos disponibles de un provider (ej. gemini)
/skills <worker_id>|Herramientas del template
/forget|Borrar historial de la conversación
/context|on|off (historial); en Telegram: --add / --summary (memoria semántica)
/comfyui|Proveedor visual: --provider local|fal (ComfyUI Mac vs Fal.ai cloud)
/sandbox|Toggle ejecución de código (true|false) para esta sesión
/sandox|(Alias) /sandbox para tolerar errores de escritura.
/ibkr|Portfolio IBKR por chat: on --mode paper|live (obligatorio) | off
/heartbeat|Activa mensajes en tiempo real mientras el agente trabaja
/audit|Última auditoría de ejecución
/health|Estado del servicio
/sensors|DuckDB, IBKR, Lake, Tavily, Reddit, Trends, browser sandbox
/setup|Config key=value
/approve|Aprobar última acción
/reject|Rechazar última acción
/execute-signal <uuid>|HITL: confirma ejecución (Quant Trader: execute_approved_signal); alias /execute_signal
/approve-code <uuid>|HITL: aprueba code_decision y crea PR (backend soberano); alias /approve_code
/reject-code <uuid> [razón]|Rechaza code_decision propuesta por Quant Trader
/execute_all_moc <session_uid>|HITL Quant: ejecuta todas las señales moc_hrp_cfd pendientes de esa sesión MOC
/cancel_signal <uuid> [--force]|HITL: cancela señal pendiente o fallida (PENDING_HITL/AWAITING_HITL/PENDING/FAILED); --force limpia otros estados excepto EXECUTED
/trading-session --mode paper|live [--tickers A,B] [--objective maximize_pnl|rebalance_hrp|overnight_gap_squeeze] [--confirm] [--status] [--stop]|Quant: sesión activa + session_goal + auto delta de /crons (live requiere --confirm)
/quant_cycle [--tickers A,B] [--timeframe 1h] [--lookback_days 20] [--objective maximize_pnl|rebalance_hrp|overnight_gap_squeeze] [--execute auto|off]|Quant: pipeline determinista (fetch -> portfolio -> evaluate -> señal) con salida estructurada
/profile|Quant: muestra perfil de inversión inferido desde VSS (semantic_memory)
/macro --update REGIMEN_* [confidence=0.8] [evidence="…"]|Quant admin: registra régimen macro manual para el pipeline MOC (singleton writer)
/lake|Estado del túnel SSH Capadonna (env + prueba rápida)
