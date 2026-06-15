# DB-First Core Refactor

## Objetivo Del Estado Final

DuckClaw debe quedar como un core generico de orquestacion LangGraph/LangChain, con runtime DB-first y sin verticales hardcodeadas en Python. El core decide con datos: catalogo de workers, capabilities, runtime policies, prompt policies, proyectos, contextos, equipos, permisos y comandos tipados.

El estado objetivo no es "borrar todos los dominios del repo" de una vez. El objetivo es que el core no tenga conocimiento especial de dominios. Un dominio puede existir solo como configuracion DB-first creada por el usuario, como plantilla de catalogo, o como paquete/extension vertical fuera del core generico.

## Regla De Separacion Vertical

Estas verticales no pertenecen al core:

- Quant Trader.
- Finanz, Finance o IBKR.
- PQRSD o PQRS.
- Leila.
- War Room o WR.
- Job Hunter.

Regla obligatoria: esas verticales no deben aparecer como defaults, rutas especiales, prompts especiales, worker ids especiales, tablas especiales, env vars especiales o branches de decision dentro de `duckclaw.manager.*`, runtime gateway generico, bootstrap compartido, schema migrations core o comandos transversales. Solo pueden existir si el usuario las crea/configura via DB-first, o si viven como paquete/extension vertical fuera del core.

Si un futuro corte necesita comportamiento especifico de una vertical, debe modelarlo como capability, runtime policy, prompt policy, tool policy, plantilla de worker, grant o comando DB-first. No debe meter otro `if worker_id == "Quant-Trader"` ni otro alias de dominio en Python core.

## Decisiones Arquitectonicas Vigentes

- DuckDB es el source of truth del control plane: workers, capabilities, prompt policies, runtime settings, proyectos, contextos, knowledge sources, shared grants y team access.
- El indice vectorial y otros artefactos derivados son reconstruibles. La verdad operacional vive en tablas y comandos idempotentes.
- El gateway y los agentes deben operar en read-only salvo allowlists explicitamente justificadas. Las mutaciones deben pasar por DB-writer o por comandos tipados autorizados.
- Markdown runtime no se reintroduce como politica cargada por agentes. Markdown sigue permitido para specs y docs de ingenieria como este archivo.
- El manager es un orquestador generico. Routing, fast plans y clasificacion de tareas se basan en capacidades/policies, no en nombres de dominios.
- Los wrappers legacy pueden mantenerse solo como compatibilidad temporal si delegan en el owner nuevo y tienen tests que protejan la direccion del cambio.

## Lo Movido O Limpiado Hasta Ahora

### Manager Y Routing

- `duckclaw.manager.graph` es el owner de `build_manager_graph`; `duckclaw.graphs.manager_graph` queda como fachada de compatibilidad.
- `duckclaw.manager.routing` concentra helpers genericos de worker id, normalizacion y cache routing.
- `duckclaw.manager.task_classification` concentra clasificacion generica de contexto/memoria y superficie MCP ligera. Los tests prohiben frases verticales en este modulo.
- `duckclaw.manager.fast_plans` reemplaza fast plans hardcodeados por policies DB-first de capability `fast_plan`.
- `duckclaw.manager.fast_replies`, `duckclaw.manager.planning`, `duckclaw.manager.invocation`, `duckclaw.manager.worker_reply_formatting` extraen responsabilidades del grafo grande.

### Egress Y Evidencia

- `duckclaw.egress.evidence_validator` es el owner transversal de auditoria de evidencia/citas, incluyendo `bracket_citation_audit`.
- `duckclaw.egress.tool_response_repair` reemplaza el repair de respuestas de tool acoplado a mercado. Repara JSON crudo, respuestas vacias y ecos de tools sin mencionar verticales.
- `duckclaw.egress.user_reply_nl_synthesis` conserva sintesis NL de salida, pero los nuevos helpers transversales deben vivir fuera de verticales.
- `duckclaw.egress.market_worker_tool_repair` fue removido como owner canonico.
- `duckclaw.egress.job_hunter_output_validator` fue removido. La validacion laboral no pertenece al egress core; si Job Hunter vuelve, debe ser extension/config vertical fuera del core.

### Comandos Y DB-Writer

- `duckclaw.commands.chat_state` extrae estado chat-scoped antes mezclado en `on_the_fly_commands.py`.
- `duckclaw.commands.team_templates` extrae equipo de chat/tenant y mantiene compatibilidad con imports legacy.
- `duckclaw.commands.team_access` extrae whitelist generica de Telegram Guard y usa comandos tipados para mutaciones de usuarios autorizados y shared grants.
- `duckclaw.commands.vaults` extrae `/vault` y sus helpers de sesion/gateway/template-bound vaults; `on_the_fly_commands.py` queda como fachada de compatibilidad y dispatcher.
- `duckclaw.commands.crons` extrae `/crons`, parseo/listado de intervalos `--delta`, horarios `--timestamp`, ids `--rm` y el mensaje SYSTEM_EVENT proactivo generico; `on_the_fly_commands.py` queda como fachada de compatibilidad y dispatcher.
- `duckclaw.commands.crons` ya no abre bóvedas hermanas con DuckDB read-write directo para limpiar schedules. Las limpiezas remotas de `agent_config` se encolan como `UpsertAgentConfigEntriesCommand` y las aplica el DB-writer/inline writer transaccional.
- `duckclaw.commands.goals` extrae `/goals`, helpers legacy de `agent_config` goals, listado/persistencia del manifiesto homeostasis y normalizacion de belief keys; `on_the_fly_commands.py` queda como fachada de compatibilidad y dispatcher mediante callbacks explicitos para resolver LLM/vault user sin ciclos.
- `duckclaw.commands.goals` ya no resuelve el registry de beliefs desde `workers/manifests`, `load_manifest`, `list_workers` ni carpetas `templates/workers`. Mientras no exista un owner DB-first tipado para un registry administrable de beliefs, `/goals` opera solo con el manifiesto homeostasis persistido, estado chat/config valido y conversión genérica/NL sin defaults verticales.
- `duckclaw.commands.sensors` extrae `/sensors`, helpers de diagnostico SSH/Tailscale, formato de lineas sensor y resumen de browser sandbox; `on_the_fly_commands.py` queda como fachada/dispatcher compatible y configura explicitamente el adaptador graph-local de sandbox para evitar ciclos.
- `duckclaw.commands.audit` extrae `/audit` y `save_last_audit` como estado chat-scoped de la ultima ejecucion; `on_the_fly_commands.py` queda como fachada/dispatcher compatible.
- `duckclaw.commands.history` extrae `/history`, `append_task_audit`, `get_history_limit_for_chat` y helpers de `task_audit_log`; `on_the_fly_commands.py` queda como fachada/dispatcher compatible. El append historico usa `AppendTaskAuditCommand` y `enqueue_typed_command` para handles read-only, evitando SQL crudo en la cola DB-writer.
- `duckclaw.commands.model_setup` extrae `/model`, `/models`, `/setup`, `/prompt`, resolucion efectiva de tripleta LLM y `get_effective_system_prompt`; `on_the_fly_commands.py` queda como fachada/dispatcher compatible y configura callbacks explicitos para listar templates y cargar solo el fallback de prompt del worker `default`.
- `duckclaw.commands.model_setup` no importa `workers.factory`, `workers.manifest`, `workers.loader` ni `graphs.on_the_fly_commands`. Sus mutaciones siguen usando `agent_config` heredado para overrides chat-scoped (`llm_*`) y prompt global/por worker (`system_prompt*`). Esta deuda es aceptable en este corte como compatibilidad de comandos, pero el destino DB-first estable es migrar defaults globales a `admin_runtime_settings`/`prompt_policy_registry` y enrutar writes persistentes por comandos tipados/DB-writer.
- `duckclaw.commands.health` extrae `/health` y `/heartbeat`; `on_the_fly_commands.py` queda como fachada/dispatcher compatible e inyecta explicitamente un adaptador graph-local hacia `chat_heartbeat` para evitar ciclos. `/health` solo lee `SELECT 1` y sondea inferencia; `/heartbeat` no escribe DuckDB ni `agent_config`, pero conserva deuda separada de estado Redis en el backend heartbeat existente.
- `duckclaw.commands.runtime_toggles` extrae `/sandbox`, `/internet` y aliases estrechos (`/sandox`, `/red`, `/network`); `on_the_fly_commands.py` queda como fachada/dispatcher compatible e inyecta explicitamente el cleanup graph-local de sesiones sandbox para evitar ciclos. Los toggles siguen siendo estado chat-scoped heredado en `agent_config`: `/sandbox` usa `set_chat_state` y `/internet` usa `UpsertAgentConfigEntriesCommand` via DB-writer cuando el handle es read-only. La deuda DB-first estable es migrar estos flags a runtime settings/policies chat-scoped tipadas cuando exista tabla owner para overrides de sesion.
- `packages/agents/src/duckclaw/graphs/on_the_fly_commands.py` ya no debe exponer alias `Trabajo -> Job Hunter`, mensajes de red sandbox que recomienden `Job-Hunter`, ni textos laborales como default de comandos transversales.
- `packages/agents/src/duckclaw/graphs/on_the_fly_commands.py` ya no conserva ramas, prompts ni comandos core de Quant/Finanz/Finance/IBKR/Trader. `/audit`, `/sensors`, `/crons`, `/goals` y `/vault` delegan en `duckclaw.commands.*`; `/lake` queda como diagnostico generico local que reutiliza el helper canonico de sensors. Comandos verticales de sesion, senales y broker ya no son propiedad del core command graph.
- `duckclaw.write_commands` define comandos Pydantic idempotentes para workers, worker capabilities, proyectos, runtime settings, team access, shared grants, Kanban, knowledge/RAG y prompt policies.
- `duckclaw.write_command_handlers` despacha esos comandos dentro de una transaccion administrada por el caller.
- `UpsertWorkerCapabilityCommand` registra/otorga capabilities DB-first a workers existentes por `worker_id` + `tenant_id`. La proteccion `bounded_select_star_read` de `read_pool` debe asignarse con este comando o con el catalogo admin a los workers que realmente deban bloquear `SELECT *` sin `LIMIT`; no se siembra como default vertical ni se hardcodea en Python.
- `services/api-gateway/routers/admin_domains/access_management.py` ya no escribe access mutators directamente; console users, Telegram whitelist y shared grants delegan en comandos tipados via DB-writer.
- `services/db-writer/main.py` ya no carga un loop de `quant_state_delta`; mantiene loops transversales/contextuales como context injection, visual, meditate y reports.
- `duckclaw.forge.team_env.default_tenant_id_from_env` ya no infiere tenants desde nombres PM2 ni rutas DuckDB y queda como compatibilidad env-only.
- El owner DB-first canonico del tenant default administrado es `main.admin_runtime_settings` con `tenant_id='global'`, `actor_email=''`, `domain='gateway'`, `key='default_tenant_id'`. Gateway, Telegram inbound, Telegram compact routes legacy y `/vault` resuelven con `duckclaw.forge.team_env.default_tenant_id_from_runtime`: env explicito administrado (`DUCKCLAW_GATEWAY_TENANT_ID` / `DUCKCLAW_TELEGRAM_DEFAULT_TENANT`) → lookup read-only del setting global → fallback seguro `default`. La configuracion debe persistirse via runtime settings/comando tipado; no por escritura directa desde gateway ni por heuristicas de proceso/path.

### Heartbeat

- `services/heartbeat/main.py` ya no resuelve sesiones ni bóvedas Quant-Trader, no consulta ni escribe `quant_core.*`, no extrae PnL desde respuestas, no fuerza `worker_id=finanz` en homeostasis y no permite ticks proactivos sin goals por ramas de trading. Conserva scheduler/homeostasis/proactive messaging como flujo transversal basado en `agent_config`, goals, worker_id/tenant_id y mensajes genericos hacia el gateway.
- `tests/test_forge_legacy_cleanup.py::test_heartbeat_base_has_no_quant_finance_trading_residue` protege que heartbeat base no reintroduzca marcadores Quant/Trader/Finance/IBKR/broker/trading.

### Homeostasis Y Goals Alignment

- `duckclaw.homeostasis.goals_alignment` es el owner transversal de alineacion de goals. Ya no lee estado de sesion, broker, schemas verticales ni bridges de dominio para derivar observaciones. La alineacion compara `observed_value`, `target_value`, `threshold` y `comparison` provenientes del manifiesto/registry DB-first.
- `duckclaw.homeostasis.surprise`, `duckclaw.homeostasis.belief_registry` y `duckclaw.homeostasis.manager` son los owners transversales de calculo de sorpresa, registry de creencias y action planning homeostasis.
- `duckclaw.forge.homeostasis.goals_alignment`, `duckclaw.forge.homeostasis.surprise`, `duckclaw.forge.homeostasis.belief_registry`, `duckclaw.forge.homeostasis.manager` y el package `duckclaw.forge.homeostasis` quedan como fachadas legacy temporales, sin logica propia, para callers que aun no deben tocarse en este corte.
- `duckclaw.db_write_queue` es ahora el owner canonico del singleton writer/cola DuckDB, incluyendo los adaptadores legacy `enqueue_write`, `execute_write_direct`, `WriteQueueBridge` y `run_consumer`. `duckclaw.forge.homeostasis.singleton_writer` queda como fachada legacy temporal sin logica propia.
- El nudging proactivo de desalineacion ya no agrega contexto Quant ni recomendaciones por objetivo vertical. Si una vertical necesita enriquecer observaciones, debe hacerlo como capability/policy DB-first o extension fuera del core antes de persistir `observed_value`.
- `tests/test_forge_legacy_cleanup.py::test_homeostasis_goals_alignment_has_no_quant_finance_trading_residue` protege que el owner canonico `duckclaw.homeostasis.goals_alignment` no reintroduzca marcadores Quant/Trader/Finance/IBKR/broker/trading.
- Los fixtures positivos de goals/homeostasis/meditate usan metricas genericas como `latency_ms`, `completion_rate_pct` y `error_rate_pct`; los ejemplos PnL/drawdown/trading quedan fuera del core o como guardrails negativos explicitos.
- `tests/test_forge_legacy_cleanup.py::test_on_the_fly_command_graph_has_no_quant_finance_trading_residue` ahora cubre tambien `pnl` y `drawdown` para evitar que copy/runtime transversal de `/goals` o `/crons` vuelva a usar ejemplos financieros.
- `docs/operations/Homeostasis-Heartbeat.md` y `Meditate-Homeostasis.md` usan ejemplos transversales de tenant/worker y metricas genericas; `tests/test_forge_legacy_cleanup.py::test_homeostasis_operation_docs_use_generic_metrics` evita reintroducir Finanz/Finance/PNL/drawdown/trading como ejemplos positivos.
- `tests/test_package_reorg_contracts.py::test_homeostasis_goals_alignment_implementation_is_owned_by_homeostasis_package` protege que los imports legacy deleguen al owner canonico y que `__module__` no vuelva a `duckclaw.forge.homeostasis`.
- `tests/test_package_reorg_contracts.py::test_homeostasis_runtime_implementations_are_owned_by_homeostasis_package` protege que `surprise`, `belief_registry` y `manager` deleguen desde Forge hacia `duckclaw.homeostasis`.
- `tests/test_forge_legacy_cleanup.py::test_canonical_homeostasis_package_does_not_depend_on_forge_homeostasis` protege que el paquete canonico `duckclaw.homeostasis` no importe de vuelta desde Forge.

### War Room

- `services/api-gateway/core/war_rooms.py` fue removido.
- `schema_migrations.py` y `scripts/bootstrap_dbs.py` ya no deben registrar ni crear `war_room_core`, `wr_members` ni `wr_audit_log`.
- `duckclaw.commands.team_access` no exporta comandos War Room. War Room solo puede volver como extension vertical externa o como configuracion DB-first creada por el usuario.

### Package Reorg Y Training

- Se retiraron paquetes legacy de Forge: `duckclaw.forge.industries`, `duckclaw.forge.crm`, `duckclaw.forge.quotes`, `duckclaw.forge.sft`, `duckclaw.forge.models` y `duckclaw.forge.atoms`.
- `duckclaw.forge.skills.github_bridge` fue removido. La integracion util de GitHub vive como capability generica en `duckclaw.github.mcp_bridge`, read-only por defecto y sin registro default desde factory.
- `duckclaw.github.workflow` fue removido. No debe existir workflow determinista de PR en core, ni manifests/heuristicas verticales acopladas a Quant, Job Hunter u otra vertical.
- `duckclaw.workers.identity` expone predicados genericos, no constantes `WORKER_*` ni sets de dominios.
- `duckclaw.workers.discovery` es el owner canonico de `list_workers`: combina solo el layout filesystem `default` con ids del catalogo DB-first y deja `duckclaw.workers.factory` como fachada compatible.
- `duckclaw.workers.visual_evidence_policy` es el owner canonico del limite de reintentos de evidencia visual en el grafo de worker; `workers.factory` conserva una fachada legacy compatible para callers existentes.
- `duckclaw.workers.tool_output_truncation` es el owner canonico del truncado puro de `ToolMessage` para contexto LLM: limita tool outputs largos, compacta outputs de sandbox removiendo `figure_base64` y aplica la compactacion existente de tools `reddit_*` sin convertir Reddit en vertical core. `workers.factory` conserva fachadas legacy compatibles para callers existentes.
- `duckclaw.workers.provider_input_budget` es el owner canonico del presupuesto de entrada por proveedor y helpers puros de poda de historial: normaliza `context_pruning_config`, estima tokens por mensajes, aplica limites Groq/MLX y divide historial preservando pares AI/tool. Depende de `duckclaw.workers.tool_output_truncation` para compactar `ToolMessage`; no decide routing ni ensamblaje de tools. `workers.factory` conserva fachadas legacy compatibles para callers existentes.
- `duckclaw.workers.context_monitor` es el owner canonico de la compresion/resumen de contexto del worker: serializa mensajes antiguos, compone el prompt generico de resumen, resuelve el LLM opcional de resumen y construye el nodo `context_monitor` a partir de `context_pruning_config`. No decide routing ni binding de tools; `workers.factory` solo lo conecta cuando la policy DB-first lo habilita y conserva fachadas legacy compatibles para helpers de resumen.
- `duckclaw.workers.tool_binding` es el owner canonico de helpers puros de superficie de tools para binding LLM: filtra tools de sandbox cuando el sandbox esta deshabilitado, reduce la superficie Groq generica removiendo `reddit_*`, construye `tool_choice` OpenAI-compatible y detecta tool calls recientes sin cambiar las rutas forzadas Reddit. No registra tools, no decide capabilities y no abre workers por filesystem; `workers.factory` conserva fachadas legacy compatibles para callers existentes.
- `duckclaw.runtime_session_settings` es el owner DB-first de flags runtime por chat/sesion. Usa `main.admin_runtime_settings` con dominio `runtime.session`, actor `chat:<chat_id>` y tenant explicito. Los flags `sandbox_enabled`, `sandbox_network_enabled` y overrides chat-scoped `llm_provider`/`llm_model`/`llm_base_url` ya no se leen/escriben desde `agent_config`; `/sandbox`, `/internet`, `/model`, `/setup`, el admin sandbox/playground, `workers.factory`, `graph_server` y `forge.schema` consumen este owner. La policy de red por chat acepta `tenant_id` explicito para evitar leer siempre el scope `default` en tenants no-default.
- `duckclaw.commands.model_setup` ya no escribe prompts de sistema en `agent_config` (`system_prompt` / `system_prompt_<worker>`). `/prompt <worker> --change ...` y `/setup system_prompt=...` hacen upsert de `main.prompt_policy_registry` con `policy_type='system_prompt'` y `policy_name=<worker_id>` mediante `UpsertPromptPolicyCommand`; `get_effective_system_prompt` resuelve desde `PromptPolicyResolver`.
- `duckclaw.workers.read_pool` ya no contiene special-cases por worker BI. Las restricciones de `SELECT *` sin `LIMIT` se modelan con la capability DB-first generica `bounded_select_star_read`; las restricciones de JSON remoto siguen bajo `bounded_json_read`.
- `duckclaw.workers.factory` ya no registra ni orquesta GitHub/Job Hunter como ramas especiales del core; esas integraciones solo pueden volver como capability/policy DB-first o extension externa.
- Los guardrails Markdown `capabilities/job_hunter.md` y `manager_tasks/job_*` fueron removidos del core. El runtime generico no debe cargar politicas de busqueda laboral desde archivos versionados como defaults.
- `packages/agents/src/duckclaw/graphs/sandbox.py` ya no debe inferir salidas desde texto de vacantes, usar `osint_jobs.parquet` como default laboral ni mencionar OSINT JobHunter en la descripcion de la tool. La salida tabular del browser sandbox es generica (`rows_extracted` + Parquet bajo `/workspace/output/`).
- El layout de entrenamiento vive bajo `packages/agents/train/` con separacion de scripts de data, scripts de serve, datasets y outputs.
- El training puede tener prompts o datasets de dominio, pero no debe ser fuente de defaults runtime del core.

### Admin Y Playground

- Admin sigue el patron BFF/Gateway y debe leer/escribir DuckDB como control plane.
- Project detail y Playground respetan proyectos, equipos y conversaciones DB-first.
- `platform-orchestrator` ya no existe como worker hardcodeado, seed por actor ni plantilla protegida. El flujo conceptual se llama `managed workspace draft` / borrador administrado de workspace: el draft puede usar el layout permitido `default` y la confirmacion crea workers explicitos en `admin_worker_catalog` con `source_template_id='default'`.
- `/workspace/orchestrator/*` queda solo como alias de compatibilidad API para clientes existentes. Los DTOs, helpers, sesion interna, auditoria y copy UI deben usar naming `WorkspaceManagedDraft` / borrador administrado, no "orchestrator wizard" ni "Platform Orchestrator".
- Las instrucciones, fallback local, naming de borrador y metadatos de confirmacion del flujo administrado se resuelven desde `main.prompt_policy_registry` con la policy activa `manager_task/admin_workspace_managed_draft`, sembrada por migracion. Si la policy falta o es invalida, el endpoint debe fallar como configuracion administrable faltante; no debe reconstruir un prompt o identidad de dominio en Python.
- Playground ya no admite un worker especial para guiar proyectos. Con `project_id`, `default` se resuelve al primer agente asignado al proyecto; cualquier worker no-default debe venir del catalogo DB y pertenecer al proyecto.
- La config de Playground expone estado de voz como `voice.configured`, `voice.available` y `voice.tts_loaded`; la disponibilidad depende de `DUCKCLAW_SENSORY_BASE_URL` y health de Sensory TTS.

### Sensory TTS

- `integrations/sensory-node` ya no hardcodea voces Leila/Finanz/Quant Trader como defaults en el modelo Pydantic, el manifiesto versionado ni los scripts operativos principales de preparacion/regeneracion.
- `TTSRequest.voice_id` valida un slug generico; la aprobacion runtime sigue en el manifiesto cargado por `TTSEngine.has_voice`, no en una allowlist Python de dominios.
- `integrations/sensory-node/voices/manifest.json` queda intencionalmente vacio en core. Las voces se agregan por flujo offline administrado y no deben commitearse como defaults verticales.

### Meditate Harness

- `harness_core.states.meditate_state` y `harness_core.skills.emit_correction_delta` ya no usan fuentes stale de dominio como default. El default transversal para `PURGE_STALE_TASKS` es `main.task_audit_log`, alineado con `services/db-writer/models/meditate_state_delta.py`.
- `harness_core.skills.fetch_system_telemetry` trata `task_audit_log` como fuente DB-first de tareas stale usando `task_id` y `created_at` cuando no existe `updated_at`, sin crear migraciones nuevas ni rutas write directas.
- `tests/test_forge_legacy_cleanup.py::test_meditate_harness_uses_transversal_stale_task_source_table` protege que el harness de meditate no vuelva a depender de tablas Quant como default.

## Patrones Nuevos A Usar

### Modulos Canonicos

- `duckclaw.manager.*`: ownership de manager graph, routing, planning, invocation, fast plans, fast replies, task classification y formatting.
- `duckclaw.commands.*`: ownership de comandos chat/team/whitelist antes incrustados en `graphs/on_the_fly_commands.py`.
- `duckclaw.homeostasis.*`: ownership de helpers transversales de homeostasis/goals alignment que no pertenecen a legacy Forge.
- `duckclaw.egress.evidence_validator`: validacion transversal de evidencia y citas.
- `duckclaw.egress.tool_response_repair`: reparacion transversal de respuestas crudas de tools.
- `duckclaw.db_write_queue`, `duckclaw.write_commands` y `duckclaw.write_command_handlers`: cola singleton, confirmacion de task status y contrato de mutacion DB-first.
- `duckclaw.shared_db_grants`: grants compartidos como control plane, no como bypass de filesystem.
- `duckclaw.workers.discovery`: discovery/listado DB-first de workers, con filesystem limitado a `default` y fachada legacy desde `duckclaw.workers.factory`.
- `duckclaw.workers.visual_evidence_policy`: politicas puras de retry visual del grafo de worker, sin defaults de dominio ni fallback filesystem.
- `duckclaw.workers.tool_output_truncation`: truncado y compactacion pura de salidas de tools antes de alimentar contexto LLM; no decide provider budgets ni routing de tools.
- `duckclaw.workers.provider_input_budget`: presupuesto de entrada por proveedor y poda pura de historial, apoyado en `tool_output_truncation`; no decide routing, tool binding ni policies DB-first.
- `duckclaw.workers.context_monitor`: compresion generica de contexto y nodo LangGraph derivado de `context_pruning_config`; no debe contener prompts ni compuertas por worker vertical.
- `duckclaw.workers.tool_binding`: filtros puros de superficie de tools, helpers `tool_choice` y deteccion de tool calls para binding LLM; no registra bridges, no resuelve workers y no decide policies DB-first.
- `duckclaw.runtime_session_settings`: flags runtime chat-scoped en `admin_runtime_settings` (`runtime.session.*`), con `commands.runtime_toggles` y `commands.model_setup` como owners de writes desde chat/admin.

### Regla Para Runtime Policies

Las runtime policies se agregan como filas/capabilities/policies DB-first. No se agregan como defaults de dominio en Python. Si una policy necesita keywords, regex, prompt, tools o permisos, se versiona en DB y se prueba con migraciones/fixtures.

### Regla Para Agentes De Filesystem

El unico worker/agente que puede existir como layout versionado en filesystem es `default`. Cualquier otro `worker_id` debe resolverse desde `admin_worker_catalog`/catalogo DB-first o desde una extension externa, no desde carpetas `templates/workers`, `forge/seed`, manifests verticales ni alias de layout. Si no hay fila de catalogo para un agente no-default, el runtime debe fallar en vez de hacer fallback a filesystem.

### Regla Para Compatibilidad Legacy

Una fachada legacy es aceptable solo si:

- Delegar al owner canonico es trivial y testeado.
- No reintroduce conocimiento vertical.
- Tiene una razon temporal clara.
- No se convierte en el nuevo punto de extension.

## Guardrails Y Tests Relevantes

Ejecutar o actualizar estos tests cuando un corte toque el area correspondiente:

- `tests/test_manager_core_vertical_guardrail.py`: prohibe verticales en `packages/agents/src/duckclaw/manager/graph.py`, `routing.py` y `fast_plans.py`.
- `tests/test_manager_task_classification.py`: protege clasificacion generica y evita special-cases de Job/Finance/Quant/PQRS/Leila/War Room.
- `tests/test_manager_fast_plans.py`: valida fast replies y fast plans DB-first via prompt/capability policies.
- `tests/test_manager_worker_reply_formatting.py`: asegura que formatting de respuestas de subagentes viva en `duckclaw.manager.worker_reply_formatting`.
- `tests/test_forge_legacy_cleanup.py`: protege removal de paquetes Forge legacy, shims `WORKER_*`, env vars DB path de dominio, War Room core, CREATE TABLE fuera de allowlists y read-write DuckDB fuera de allowlists.
- `tests/test_package_reorg_contracts.py`: protege facades publicas compartidas y ownership de `duckclaw.manager.graph`.
- `tests/test_worker_factory_modular_boundaries.py`: protege que `template_registry`, `load_manifest` y `workers.discovery.list_workers` expongan desde filesystem solo `default`; `workers.factory.list_workers` queda como fachada compatible y agentes extra deben venir de DB/catalogo.
- `tests/test_worker_factory_modular_boundaries.py::test_tool_output_truncation_owns_helpers_with_factory_facade` y `tests/test_tool_output_truncation.py`: protegen que el truncado de `ToolMessage`, sandbox outputs y sanitizacion de tools `reddit_*` vivan en `duckclaw.workers.tool_output_truncation`, con fachada legacy desde `workers.factory`.
- `tests/test_worker_factory_modular_boundaries.py::test_provider_input_budget_owns_helpers_with_factory_facade` y `tests/test_provider_input_budget.py`: protegen que presupuesto de entrada por proveedor, estimacion de tokens y poda pura de historial vivan en `duckclaw.workers.provider_input_budget`, con fachada legacy desde `workers.factory`.
- `tests/test_worker_factory_modular_boundaries.py::test_context_monitor_owns_summary_helpers_with_factory_facade` y `tests/test_context_monitor.py`: protegen que resumen/compresion de contexto y el builder del nodo `context_monitor` vivan en `duckclaw.workers.context_monitor`, con fachada legacy desde `workers.factory` y sin hardcodes BI en la policy de compresion.
- `tests/test_worker_factory_modular_boundaries.py::test_tool_binding_owns_tool_surface_helpers_with_factory_facade` y `tests/test_worker_tool_binding.py`: protegen que filtros puros de binding, helpers `tool_choice` y deteccion de tool calls vivan en `duckclaw.workers.tool_binding`, con fachada legacy desde `workers.factory`.
- `tests/test_read_pool.py`: protege que `workers.read_pool` no reintroduzca hardcodes BI y que los bloqueos de `SELECT *` sin `LIMIT` dependan de capability DB-first generica, no de ids de worker.
- `tests/test_worker_factory_modular_boundaries.py::test_core_admin_runtime_does_not_hardcode_non_default_platform_worker`: prohibe que admin catalog/runtime/router vuelvan a fijar `platform-orchestrator` como worker no-default de sistema.
- `tests/test_admin_workspace_catalog.py::test_orchestrator_draft_uses_db_first_prompt_policy_for_prompt_and_naming`: protege compatibilidad de la ruta legacy y que el flujo administrado use la policy DB-first para prompt y naming.
- `tests/test_admin_projects_ui_static.py::test_managed_workspace_draft_copy_and_symbols_avoid_orchestrator_product_naming`: prohibe reintroducir "Platform Orchestrator", "orchestrator wizard" o helpers `Orchestrator*` como naming interno/copy fuera del alias `/workspace/orchestrator/*` y topologias genericas.
- `tests/test_prompt_policies.py::test_managed_workspace_draft_policy_is_seeded_by_migrations`: protege que la policy generica del flujo administrado exista como fila de migracion, no como Markdown/runtime Python.
- `tests/test_commands_chat_state_contract.py`: protege ownership de `duckclaw.commands.chat_state`.
- `tests/test_commands_team_templates_contract.py`: protege ownership de `duckclaw.commands.team_templates`.
- `tests/test_commands_team_access_contract.py`: protege ownership de whitelist, comandos typed DB-writer y ausencia de War Room en team access.
- `tests/test_commands_vaults_contract.py`: protege ownership de `/vault` y evita que sus helpers vuelvan a `graphs/on_the_fly_commands.py`.
- `tests/test_commands_crons_contract.py`: protege ownership de `/crons`, helpers de schedule proactivo y compatibilidad de imports legacy desde `graphs/on_the_fly_commands.py`.
- `tests/test_commands_goals_contract.py`: protege ownership de `/goals`, helpers del manifiesto homeostasis y compatibilidad de imports legacy desde `graphs/on_the_fly_commands.py`.
- `tests/test_commands_sensors_contract.py`: protege ownership de `/sensors`, compatibilidad de imports legacy desde `graphs/on_the_fly_commands.py` y ausencia de defaults verticales en el modulo canonico.
- `tests/test_commands_audit_contract.py`: protege ownership de `/audit` y `save_last_audit`, compatibilidad de imports legacy desde `graphs/on_the_fly_commands.py`, ausencia de defaults verticales y ausencia de conexiones DuckDB RW directas en el modulo canonico.
- `tests/test_commands_history_contract.py`: protege ownership de `/history`, `append_task_audit`, helpers de `task_audit_log`, compatibilidad de imports legacy desde `graphs/on_the_fly_commands.py`, ausencia de defaults verticales y uso de comando tipado para la cola DB-writer.
- `tests/test_commands_model_setup_contract.py`: protege ownership de `/model`, `/models`, `/setup`, `/prompt`, resolvers LLM y `get_effective_system_prompt`, compatibilidad de imports legacy desde `graphs/on_the_fly_commands.py`, ausencia de defaults verticales y ausencia de fallback a workers por filesystem en el modulo canonico.
- `tests/test_commands_health_contract.py`: protege ownership de `/health` y `/heartbeat`, compatibilidad de imports legacy desde `graphs/on_the_fly_commands.py`, ausencia de defaults verticales, ausencia de writes DuckDB y ausencia de imports desde `duckclaw.graphs` en el owner canonico.
- `tests/test_commands_runtime_toggles_contract.py`: protege ownership de `/sandbox`, `/internet`, aliases `/red`/`/network` en dispatcher, compatibilidad de imports legacy desde `graphs/on_the_fly_commands.py`, ausencia de defaults verticales, ausencia de imports desde `duckclaw.graphs` en el owner canonico y uso de callback explicito para cleanup sandbox.
- `tests/test_sandbox_network_policy.py`: protege que la policy efectiva de red por chat lea `runtime.session.sandbox_network_enabled` desde `admin_runtime_settings`, no desde `agent_config` ni desde `graphs.on_the_fly_commands`.
- `tests/test_api_gateway.py` y `tests/test_forge_legacy_cleanup.py::test_team_env_does_not_infer_tenant_from_vertical_process_or_path_names`: protegen que el tenant default del gateway no vuelva a inferirse desde PM2/rutas ni desde nombres verticales en `team_env.py`.
- `tests/test_telegram_compact_webhook_routes.py::test_parse_legacy_path_uses_db_first_default_tenant` y `tests/test_multi_vault_system.py::test_vault_default_tenant_label_uses_db_first_runtime_setting`: protegen que Telegram compact legacy y `/vault` usen el owner DB-first de tenant default.
- `tests/test_tool_response_repair.py`: protege repair transversal y ausencia de marcadores verticales en `tool_response_repair.py`.
- `tests/test_answer_evidence_validator.py`: protege auditoria transversal de evidencia/citas.
- `tests/test_write_commands.py`: protege serializacion y handlers de comandos tipados.
- `tests/test_admin_router.py`: cubre contrato de Playground, incluyendo estado de voz.
- `integrations/sensory-node/tests/test_models.py`: protege que Sensory no vuelva a hardcodear voces Leila/Finanz/Quant Trader como defaults versionados y que `voice_id` sea manifiesto-owned en vez de una allowlist Python vertical.
- `tests/test_forge_legacy_cleanup.py::test_labor_vertical_residues_are_absent_from_core_config_and_telegram_tests`: prohibe residuos Job Hunter/laborales en `on_the_fly_commands.py`, `sandbox.py`, `.env.example`, `config/` y tests Telegram/PM2 que deben usar workers genericos.
- `tests/test_forge_legacy_cleanup.py::test_meditate_harness_uses_transversal_stale_task_source_table`: prohibe que `meditate_state.py` o `emit_correction_delta.py` vuelvan a usar fuentes stale Quant como default.
- `tests/test_forge_legacy_cleanup.py::test_homeostasis_operation_docs_use_generic_metrics`: prohibe que las docs operativas de Homeostasis usen ejemplos financieros/verticales como runtime positivo.

Comandos sugeridos por corte:

```bash
uv run pytest tests/test_manager_core_vertical_guardrail.py tests/test_manager_task_classification.py tests/test_forge_legacy_cleanup.py -q
```

```bash
uv run pytest tests/test_package_reorg_contracts.py tests/test_commands_chat_state_contract.py tests/test_commands_team_templates_contract.py tests/test_commands_team_access_contract.py -q
```

```bash
uv run pytest tests/test_tool_response_repair.py tests/test_answer_evidence_validator.py tests/test_manager_fast_plans.py tests/test_write_commands.py -q
```

## Allowlists Y Residuos Conocidos

Estos residuos existen en el repo actual y no deben confundirse con patrones a copiar:

- `packages/agents/src/duckclaw/workers/factory.py`: sigue siendo una superficie grande de ensamblaje de tools/runtime. Los cortes recientes retiraron orquestacion determinista Quant/IBKR/Finance y Job Hunter/GitHub hardcodeado; el pendiente ya no debe resolverse con ramas por dominio, sino con capabilities/tools DB-first o extensiones.
- `packages/agents/src/duckclaw/graphs/on_the_fly_commands.py`: ya salio de la allowlist de residuos verticales del core command graph y delega `/vault`, `/crons`, `/goals`, `/sensors`, `/audit`, `/history`, `/model`, `/models`, `/setup`, `/prompt`, `/health`, `/heartbeat`, `/sandbox` y `/internet`. Sigue siendo una fachada grande con ownership residual de comandos genericos; el pendiente es seguir extrayendo otros helpers transversales hacia `duckclaw.commands.*`, no reintroducir dominios.
- `packages/agents/src/duckclaw/graphs/sandbox.py`: el prompt y summary del browser sandbox ya son genericos respecto a busqueda laboral; los pendientes restantes son cleanup de ejemplos/heuristicas de navegacion no laborales.
- `packages/agents/src/duckclaw/finance/*` y `packages/agents/src/duckclaw/quant/*`: paquetes verticales pendientes de remover o sacar del core despues del corte de factory.
- `services/db-writer/quant_state_delta_handler.py` y `services/db-writer/models/quant_state_delta.py`: handlers/DTOs verticales residuales; el loop no esta activo en `services/db-writer/main.py`, pero los archivos siguen presentes.
- `services/api-gateway/routers/admin.py` y `services/api-gateway/routers/admin_domains/visual_assets.py`: estan en allowlists por diagnosticos/admin context pendientes de genericizar.
- `services/api-gateway/routers/admin_domains/access_management.py`: los mutadores admin de access management delegan en comandos tipados/DB-writer y el modulo salio de la allowlist de conexiones DuckDB read-write directas.
- `scripts/deployment/patch_tts_production_env.py`, `scripts/deployment/test_sensory_tts.py`, `scripts/deployment/test_tts_duration_remote.py`, `scripts/deployment/debug_tts_mac.py` e `integrations/sensory-node/scripts/check_tts_amplitude.py`: smoke/debug/patch scripts de TTS aun nombran voces legacy. No deben copiarse como defaults; el siguiente corte Sensory debe moverlos a ids genericos o resolver voz desde `DUCKCLAW_TTS_VOICE_MAP`/manifest.
- `packages/duckops/duckops/sovereign/materialize.py`: contiene comentarios/operaciones con nombres legacy; no es runtime manager core.

Las allowlists vivas estan declaradas en `tests/test_forge_legacy_cleanup.py`. Si un futuro subagente agrega una excepcion, debe agregar tambien una razon explicita y preferiblemente una tarea de follow-up para retirarla.

## Instrucciones Para Subagentes

1. No buscar ni depender de `SDD_INDEX.md`. Este documento es la fuente de contexto para el refactor DB-first/core cleanup.
2. Leer tambien las specs puntuales relacionadas antes de tocar codigo, por ejemplo `docs/specs/features/platform/RAG_TRANSVERSAL_DB_FIRST.md`, `ADMIN_RUNTIME_SETTINGS.md`, `ADMIN_PROJECT_DETAIL_AND_PLAYGROUND_FIXES.md`, `ADMIN_IDENTITY_RBAC_ERD.md` o la spec del area tocada.
3. Trabajar en TDD RED/GREEN para cambios de comportamiento. Primero agrega o ajusta el test guardrail/contrato, verifica que falla por la razon esperada, luego implementa.
4. No agregar defaults de dominio en Python. Si necesitas comportamiento configurable, usa DB-first: capabilities, prompt policies, runtime settings, worker catalog, grants o comandos tipados.
5. No mover verticales al core con otro nombre. Si una funcion contiene conocimiento de Quant, Finance/IBKR, PQRSD, Leila, War Room o Job Hunter, debe vivir como extension vertical o estar alimentada por DB.
6. Antes de tocar `workers/factory.py` u `on_the_fly_commands.py`, identifica la menor extraccion canonica posible y agrega un test de ownership como los existentes.
7. Antes de tocar DuckDB writes, revisa las allowlists en `tests/test_forge_legacy_cleanup.py` y prefiere `duckclaw.write_commands` + DB-writer.
8. Antes de tocar egress, revisa `duckclaw.egress.evidence_validator`, `duckclaw.egress.tool_response_repair` y sus tests. No crear otro repair por vertical.
9. Al terminar, ejecuta el subconjunto de tests del area y al menos el guardrail core/vertical si tocaste manager, runtime, gateway o comandos.

## Pendientes Recomendados

### Inmediato

- Reducir el resto de `on_the_fly_commands.py` por cortes pequeños: comandos transversales residuales como meditate/context/roles/tasks y helpers vecinos. Cada corte debe dejar fachada compatible y test focal.
- Crear un owner DB-first tipado para el registry administrable de beliefs si `/goals` necesita autocompletar metas por worker; no reabrir manifests de workers no-default como fallback.
- Mantener `workers/factory.py` como superficie de alto riesgo: tras extraer discovery/listado, retry visual, truncado de tool outputs, provider input budget, context monitor, helpers puros de tool binding/tool_choice y flags sandbox DB-first, los siguientes cortes deben migrar registro de tools/capabilities y runtime assembly hacia owners pequenos DB-first o extensiones, no a nuevas ramas por dominio.

### Mediano

- Sacar `packages/agents/src/duckclaw/finance/*` y `packages/agents/src/duckclaw/quant/*` hacia extensiones verticales o policies DB-first fuera del core.
- Remover `services/db-writer/quant_state_delta_handler.py` y `services/db-writer/models/quant_state_delta.py` cuando exista migracion/archivo de compatibilidad claro; el loop ya no esta activo, pero los archivos siguen siendo residuo vertical.
- Seguir retirando allowlists de routers admin vecinos (`admin.py`, `admin_domains/visual_assets.py` y flujos relacionados) cuando cada mutacion tenga comando tipado, BFF claro y guardrail focal.
- Revisar imports legacy restantes de harness/homeostasis y `graphs/tools.py` en cortes dedicados; los owners canonicos ya existen, pero aun quedan fachadas e imports historicos.

### Opcional O Bloqueado Por Input Admin

- Genericizar scripts Sensory legacy (`patch_tts_production_env.py`, `test_sensory_tts.py`, `test_tts_duration_remote.py`, `debug_tts_mac.py`, `check_tts_amplitude.py`) para resolver voces desde manifest/env administrado, o moverlos fuera del core si siguen siendo smoke scripts de dominio.
- Extender UI/admin runtime settings para exponer `gateway.default_tenant_id` y otros defaults transversales solo si el admin necesita gestionarlos desde pantalla; el contrato DB-first ya existe.
- Extender el barrido de residuos laborales y verticales fuera del runtime core separando menciones negativas de specs/tests contra ejemplos runtime.
- Mantener tests guardrail cerca del contrato. Cada cleanup que cierre un residuo debe retirar o estrechar su allowlist.
