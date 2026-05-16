# Mapa del monorepo DuckClaw

Markdown en el repo; **sin sitio HTML**. Normativa en `specs/`; guías operativas en `docs/`.

## Capas (de afuera hacia adentro)

```
duckclaw/
├── specs/              ← SDD: qué debe hacer el sistema (leer antes de codificar)
├── docs/               ← Runbooks: instalar, PM2, troubleshooting (no duplicar specs)
├── services/           ← Procesos desplegables (I/O, colas, escritura)
├── packages/           ← Librerías Python/C++ importables por los servicios
├── config/             ← Plantillas PM2, MCP (secretos locales en .env, gitignored)
├── tests/              ← Pytest
└── scripts/            ← ver scripts/README.md (doctor, quant, smoke, experimental)
```

## `services/` — procesos (uno por carpeta)

| Servicio | Rol | Escribe DuckDB |
|----------|-----|----------------|
| `api-gateway/` | FastAPI, Telegram webhook, chat, encola mutaciones | No (encola) |
| `db-writer/` | Consumidor Redis → transacciones DuckDB | **Sí (único)** |
| `heartbeat/` | Proactividad / homeostasis (opcional) | No |
| `ibkr-ohlcv-api/` | OHLCV HTTP auxiliar | No |

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

1. [`specs/README.md`](specs/README.md) y `specs/core/`
2. [`docs/index.md`](docs/index.md) para operación
3. [`docs/COMANDOS.md`](docs/COMANDOS.md) para PM2 y variables
