# Mapa del monorepo DuckClaw

Markdown en el repo; **sin sitio HTML**. Normativa en `specs/`; guías operativas en `docs/`.

## Capas (de afuera hacia adentro)

```
duckclaw/
├── specs/              ← SDD: `core/` + `features/<dominio>/` — ver specs/SDD_INDEX.md
├── docs/               ← Runbooks: instalar, PM2, troubleshooting (no duplicar specs)
├── services/           ← Procesos desplegables (I/O, colas, escritura)
├── packages/           ← Librerías Python/C++ importables por los servicios
├── config/             ← [`CONFIG_TEMPLATES.md`](config/CONFIG_TEMPLATES.md) (PM2, MCP; secretos en .env)
├── apps/               ← [`duckclaw-admin`](apps/duckclaw-admin/README.md) (Next.js consola admin, pnpm)
├── tests/              ← Pytest
└── scripts/            ← ver scripts/SCRIPTS_INDEX.md (doctor, quant, smoke, experimental)
```

## `services/` — procesos (uno por carpeta)

| Servicio | Doc | Rol | Escribe DuckDB |
|----------|-----|-----|----------------|
| `api-gateway/` | [`API_GATEWAY_SERVICE.md`](services/api-gateway/API_GATEWAY_SERVICE.md) | FastAPI, Telegram webhook, chat, encola mutaciones | No (encola) |
| `db-writer/` | [`DB_WRITER_SERVICE.md`](services/db-writer/DB_WRITER_SERVICE.md) | Consumidor Redis → transacciones DuckDB | **Sí (único)** |
| `heartbeat/` | [`HEARTBEAT_SERVICE.md`](services/heartbeat/HEARTBEAT_SERVICE.md) | Proactividad / homeostasis (opcional) | No |
| `ibkr-ohlcv-api/` | — | OHLCV HTTP auxiliar | No |

## `packages/` — código reutilizable

| Paquete pip | Ruta | Contenido principal |
|-------------|------|---------------------|
| `duckclaw-shared` | `packages/shared/src/duckclaw/` | Utils, Telegram, cola db-write, vaults, env |
| `duckclaw-agents` | `packages/agents/src/duckclaw/` | LangGraph, workers, forge, guardrails |
| `duckclaw-core` | `packages/core/` | Bindings C++, rendimiento |
| `duckops` | `packages/duckops/` | CLI (`duckops init`, `serve`) |
| MCP | `packages/mcp/telegram`, `packages/mcp/duckclaw` | Servidores MCP |

### Por qué dos carpetas `duckclaw/` (`shared` vs `agents`)

Es el patrón **src-layout** de Python: cada paquete publica el namespace `duckclaw`, pero son **distribuciones distintas**.

- `import duckclaw.utils` → **shared**
- `import duckclaw.graphs` → **agents**
- `import duckclaw.workers` → **agents**

`duckclaw-agents` declara dependencia de `duckclaw-shared`. El gateway importa ambos.

### Dentro de `packages/agents/src/duckclaw/`

| Carpeta | Qué es |
|---------|--------|
| `graphs/` | Manager, fly commands, graphs legacy (general/retail) |
| `workers/` | Factory + manifests de workers |
| `forge/` | Templates YAML/SQL (`forge/templates/<WorkerId>/`) |
| `guardrails/` | Textos LLM/directivas en `.md` (no hardcode en `.py`) |
| `adf_validator.py` | Validación plantillas AXIS |

No debe existir `packages/agents/src/duckclaw/agents/` (resto antiguo); el código vive en `graphs/`.

## Qué no subir a git

- `site/`, `__pycache__/`, `.venv/`, `*.duckdb`, `.env`, `logs/`, `packages/agents/train/gemma4/` (artefactos locales)
- Ver `.gitignore` raíz

## Lectura recomendada

1. [`DUCKCLAW.md`](DUCKCLAW.md) — entrada del monorepo
2. [`specs/SDD_INDEX.md`](specs/SDD_INDEX.md) y `specs/core/`
3. [`docs/index.md`](docs/index.md) · [`docs/DOCUMENTATION_MAP.md`](docs/DOCUMENTATION_MAP.md)
4. [`docs/COMANDOS.md`](docs/COMANDOS.md) para PM2 y variables
