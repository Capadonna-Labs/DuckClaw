# Índice de features (`specs/features/FEATURES_INDEX.md`)

Specs de **producto** referenciadas por código, manifests y runbooks. Principios transversales consolidados: [`specs/core/`](../core/). Planes de formato: [`specs/meta/PLAN_FORMAT_STANDARD.md`](../meta/PLAN_FORMAT_STANDARD.md). Histórico: [`specs/archive/`](../archive/ARCHIVE_INDEX.md).

## Cómo usar

| Necesitas | Ve a |
|-----------|------|
| Norma global (infra, memoria, writer) | `specs/core/00`–`04` + [`SDD_INDEX.md`](../SDD_INDEX.md) |
| Feature concreta (Finanz, Quant, Telegram…) | Tablas abajo |
| Operación (PM2, env, troubleshooting) | [`docs/operations/`](../../docs/operations/index.md) — enlazado desde specs con runbook |

Estado: **implemented** = hay código/manifest; **partial** = diseño parcial; **planned** = sin implementación clara en repo.

---

## `finanz/`

| Spec | Estado |
|------|--------|
| [FINANZ_ADMIN_SQL_DB_WRITER.md](finanz/FINANZ_ADMIN_SQL_DB_WRITER.md) | implemented |
| [FINANZ_REQUIRED_DUCKDB_TOOLS.md](finanz/FINANZ_REQUIRED_DUCKDB_TOOLS.md) | implemented |
| [FINANZ_IBKR_ACCOUNT_SUMMARY.md](finanz/FINANZ_IBKR_ACCOUNT_SUMMARY.md) | implemented |
| [FINANZ_BUDGET_TELEGRAM.md](finanz/FINANZ_BUDGET_TELEGRAM.md) | implemented |
| [FINANZ_FIELD_REFLECTION_AGENT_BELIEFS.md](finanz/FINANZ_FIELD_REFLECTION_AGENT_BELIEFS.md) | implemented |
| [FINANZ_CONTEXT_INJECTION_TELEGRAM.md](finanz/FINANZ_CONTEXT_INJECTION_TELEGRAM.md) | implemented |
| [FINANZ_CFD_CYBER_FLUID.md](finanz/FINANZ_CFD_CYBER_FLUID.md) | implemented |
| [CRM_EXECUTIVE_SUMMARY_GATEWAY.md](finanz/CRM_EXECUTIVE_SUMMARY_GATEWAY.md) | implemented |
| [CRM_PQRSD_DUCKDB_PERSISTENCE.md](finanz/CRM_PQRSD_DUCKDB_PERSISTENCE.md) | implemented |
| [FMP_DIVIDENDS_READONLY.md](finanz/FMP_DIVIDENDS_READONLY.md) | implemented |
| [FMP_EARNINGS_TRANSCRIPTS_READONLY.md](finanz/FMP_EARNINGS_TRANSCRIPTS_READONLY.md) | implemented |
| [FINANZ_MQL5_STEALTH_READER.md](finanz/FINANZ_MQL5_STEALTH_READER.md) | partial |

## `quant/`

| Spec | Estado |
|------|--------|
| [QUANTITATIVE_TRADING_WORKER.md](quant/QUANTITATIVE_TRADING_WORKER.md) | implemented (base Finanz / `quant_core`) |
| [QUANT_TRADER_WORKER.md](quant/QUANT_TRADER_WORKER.md) | implemented |
| [QUANT_TRADING_SESSION_HOMEOSTASIS.md](quant/QUANT_TRADING_SESSION_HOMEOSTASIS.md) | implemented |
| [QUANT_CORE_SATELLITE_HRP_MOC.md](quant/QUANT_CORE_SATELLITE_HRP_MOC.md) | implemented |
| [QUANT_CAPADONNA_OHLC_IBKR.md](quant/QUANT_CAPADONNA_OHLC_IBKR.md) | implemented |
| [QUANT_MOC_MACRO_PGQ_VSS.md](quant/QUANT_MOC_MACRO_PGQ_VSS.md) | implemented |
| [QUANT_REDDIT_MCP_SENTIMENT.md](quant/QUANT_REDDIT_MCP_SENTIMENT.md) | implemented |
| [QUANT_GOOGLE_TRENDS_MCP.md](quant/QUANT_GOOGLE_TRENDS_MCP.md) | implemented |
| [QUANT_CAGED_BEAST_MERCENARY.md](quant/QUANT_CAGED_BEAST_MERCENARY.md) | implemented |

## `telegram-gateway/`

| Spec | Estado |
|------|--------|
| [TELEGRAM_WEBHOOK_ONE_PORT.md](telegram-gateway/TELEGRAM_WEBHOOK_ONE_PORT.md) | implemented (recomendado) |
| [TELEGRAM_WEBHOOK_MULTIPLEX.md](telegram-gateway/TELEGRAM_WEBHOOK_MULTIPLEX.md) | implemented (alternativa) |
| [TELEGRAM_MULTIPLEX_OUTBOUND_ROUTING.md](telegram-gateway/TELEGRAM_MULTIPLEX_OUTBOUND_ROUTING.md) | implemented |
| [TELEGRAM_MCP_INTEGRATION.md](telegram-gateway/TELEGRAM_MCP_INTEGRATION.md) | implemented |
| [TELEGRAM_AUTH_WHITELIST.md](telegram-gateway/TELEGRAM_AUTH_WHITELIST.md) | implemented |
| [TELEGRAM_SANDBOX_MULTI_ATTACH.md](telegram-gateway/TELEGRAM_SANDBOX_MULTI_ATTACH.md) | implemented |
| [TELEGRAM_NL_EGRESS.md](telegram-gateway/TELEGRAM_NL_EGRESS.md) | implemented |
| [GATEWAY_AGNOSTIC_CHANNELS.md](telegram-gateway/GATEWAY_AGNOSTIC_CHANNELS.md) | partial |

## `agents-axis/`

| Spec | Estado |
|------|--------|
| [AXIS_TEMPLATES_001.md](agents-axis/AXIS_TEMPLATES_001.md) | implemented |
| [AXIS_MAESTRO_ORCHESTRATOR.md](agents-axis/AXIS_MAESTRO_ORCHESTRATOR.md) | implemented |
| [PQRSD_ASSISTANT_MEDELLIN.md](agents-axis/PQRSD_ASSISTANT_MEDELLIN.md) | implemented |
| [PQRSD_SYNTHETIC_TRACES_GEMMA4.md](agents-axis/PQRSD_SYNTHETIC_TRACES_GEMMA4.md) | implemented |
| [BI_ANALYST_TEMPLATE.md](agents-axis/BI_ANALYST_TEMPLATE.md) | implemented |
| [JOBHUNTER_OSINT.md](agents-axis/JOBHUNTER_OSINT.md) | implemented |
| [SIATA_ANALYST.md](agents-axis/SIATA_ANALYST.md) | implemented |
| [GITCLAW_WORKER.md](agents-axis/GITCLAW_WORKER.md) | implemented |

ADF global: [`specs/05_ADF_AGENT_DEFINITION_FRAMEWORK.md`](../05_ADF_AGENT_DEFINITION_FRAMEWORK.md).

## `platform/`

| Spec | Estado |
|------|--------|
| [DUCKCLAW_ADMIN_UI.md](platform/DUCKCLAW_ADMIN_UI.md) | implemented |
| [API_GATEWAY_HARDENING.md](platform/API_GATEWAY_HARDENING.md) | partial |
| [OBSERVABILITY_STRUCTURED_LOGGING.md](platform/OBSERVABILITY_STRUCTURED_LOGGING.md) | implemented |
| [DOTENV_SINGLE_SOURCE.md](platform/DOTENV_SINGLE_SOURCE.md) | implemented |
| [CONCURRENT_TOOL_READ_POOL.md](platform/CONCURRENT_TOOL_READ_POOL.md) | implemented |
| [VLM_INTEGRATION.md](platform/VLM_INTEGRATION.md) | implemented |
| [STRIX_SANDBOX_SECURITY_POLICY.md](platform/STRIX_SANDBOX_SECURITY_POLICY.md) | implemented |
| [STRIX_BROWSER_NOVNC.md](platform/STRIX_BROWSER_NOVNC.md) | implemented |
| [SOVEREIGN_WIZARD_V2.md](platform/SOVEREIGN_WIZARD_V2.md) | implemented |
| [TRIPLE_MEMORY_INDUSTRY_TEMPLATES.md](platform/TRIPLE_MEMORY_INDUSTRY_TEMPLATES.md) | implemented |
| [META_COGNITIVE_PGQ_VSS.md](platform/META_COGNITIVE_PGQ_VSS.md) | partial |
| [MULTI_VAULT_SYSTEM.md](platform/MULTI_VAULT_SYSTEM.md) | implemented |
| [HOMEOSTASIS_HEARTBEAT.md](platform/HOMEOSTASIS_HEARTBEAT.md) | implemented |
| [FLY_COMMANDS_UI.md](platform/FLY_COMMANDS_UI.md) | implemented |
| [UX_CONVERSATIONAL_OPTIMIZATION.md](platform/UX_CONVERSATIONAL_OPTIMIZATION.md) | partial (ver también `UIUX-PATTERNS.md` en raíz) |
| [SFT_DATASET_FORMAT.md](platform/SFT_DATASET_FORMAT.md) | implemented |
| [SFT_TRACE_SANITIZER_GEMMA4.md](platform/SFT_TRACE_SANITIZER_GEMMA4.md) | implemented |

## `cognitive/`

| Spec | Estado |
|------|--------|
| [AGENT_MANAGER_REPLAN_RESILIENCE.md](cognitive/AGENT_MANAGER_REPLAN_RESILIENCE.md) | implemented |
| [CONTEXT_SYNTHESIS_FAST_PATH.md](cognitive/CONTEXT_SYNTHESIS_FAST_PATH.md) | implemented |
| [DREAMER_SLEEP_TIME_COMPUTE.md](cognitive/DREAMER_SLEEP_TIME_COMPUTE.md) | planned |
| [PLAN_TITLE_GENERATION.md](cognitive/PLAN_TITLE_GENERATION.md) | partial |
| [FLY_COMMAND_HISTORY.md](cognitive/FLY_COMMAND_HISTORY.md) | partial |
| [WAR_ROOMS.md](cognitive/WAR_ROOMS.md) | partial |
| [TIME_CONTEXT_SKILL.md](cognitive/TIME_CONTEXT_SKILL.md) | implemented |

## `the-mind/`

Índice: [THE_MIND_INDEX.md](the-mind/THE_MIND_INDEX.md).

## `integrations/`

| Spec | Estado |
|------|--------|
| [TAILSCALE_CONFIGURATION.md](integrations/TAILSCALE_CONFIGURATION.md) | implemented |
| [A2A_FINANZ_JOBHUNTER.md](integrations/A2A_FINANZ_JOBHUNTER.md) | partial |
