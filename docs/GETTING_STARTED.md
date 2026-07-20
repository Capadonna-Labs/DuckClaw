# Empezar con DuckClaw

Entrada mínima para un dev nuevo. Arquitectura: [`architecture/system_overview.md`](architecture/system_overview.md) y [`architecture/DB_FIRST_CORE_REFACTOR.md`](architecture/DB_FIRST_CORE_REFACTOR.md).

## Requisitos automáticos (macOS / Linux)

No necesitas memorizar la lista: el CLI instala lo que falte.

| Herramienta | Para qué |
|-------------|----------|
| **uv** | Dependencias Python del monorepo |
| **Redis** | Colas y sesiones |
| **Node + npm** | Consola admin |
| **PM2** | Gateway y db-writer en segundo plano |

Soportado: **macOS** (Homebrew), **Linux** (apt) y **Windows** (winget). WSL2 también funciona como Linux.

## Camino plug & play (un comando)

```bash
git clone <repo> duckclaw && cd duckclaw

# Windows: doble clic en install.cmd
# macOS/Linux/WSL: bash scripts/bootstrap/up.sh  (o uv run duckops up)
```

Si ya tienes `uv`:

```bash
uv run duckops up
```

`duckops up` hace en orden:

1. Instala **uv**, **Redis**, **Node**, **pnpm**, **PM2** si faltan (macOS/Linux/Windows) + `uv sync`
2. Abre el **wizard TUI** la primera vez (admin + `.env` + PM2)
3. `duckclaw-migrate`
4. Gateway + DB-Writer en PM2
5. Smoke `/health`
6. **Menú persistente:** chat TUI, consola web o salir — puedes alternar sin bajar PM2

Tras login web → **Playground** (chat).

En el chat TUI: `/web` abre la consola sin salir del terminal.

### Smoke `/health` (paso 5)

Comprueba que el **API Gateway** responde en `http://localhost:8000/health` con HTTP 200. No prueba login ni Playground; solo confirma que el backend está vivo tras PM2.

Tras el smoke, `duckops up` hace un preflight ligero de las **4 policies framework** (capa 0). Si faltan filas en DuckDB pero hay airbag en código, avisa sin abortar; con `--strict` falla si hay keys críticas ausentes.

### Framework policy pack (migración 021)

La migración **021** (`framework_policy_pack_v1`) materializa en DuckDB las cuatro policies mínimas del runtime (`capability/*` + `system_prompt/default`). Se aplica con:

```bash
uv run duckclaw-migrate
uv run duckclaw-migrate --verify-only   # solo comprobar
```

Si el hub quedó sin seed (DB antigua o restore manual), restaura el pack del repo sin tocar prompts de workers:

- **Admin:** `POST /prompt-policies/restore-framework` (consola → Prompt policies)
- **CLI:** `uv run duckops doctor` — filas «Policies framework» y «Policies airbag»

### DB-Writer singleton

Solo el proceso **DB-Writer** (`PM2 DuckClaw-DB-Writer`) abre DuckDB en escritura. Gateway, agentes y admin encolan mutaciones tipadas vía Redis; el resto opera `read_only=True`. Contrato: [`api/DB_WRITER_CONTRACT.md`](api/DB_WRITER_CONTRACT.md).

`uv run duckops doctor` incluye la fila **DB-Writer** (PM2 online, cola Redis, métrica `db_writer:metric:processed`).

### Flags útiles

| Flag | Uso |
|------|-----|
| `--no-yes` | Solo comprueba prerequisitos; no instala brew/apt |
| `--skip-init` | No abrir wizard (falla si falta config) |
| `--skip-admin` | Solo backend; sin Next.js |
| `--no-prompt` | Salir tras el resumen (CI); sin menú interactivo |
| `--ui tui\|web\|none` | Elegir modo sin menú |
| `--no-browser` | Opción web sin abrir URL |
| `--manual` | Wizard con Telegram/Tailscale |
| `--strict` | Fallar si faltan policies framework críticas (degradado solo avisa) |

### Paso a paso (alternativa)

```bash
uv run duckops bootstrap --yes
uv run duckops init
uv run duckclaw-migrate
uv run duckops serve --gateway --pm2
uv run duckops smoke
```

## Siguiente lectura

1. [`docs/README.md`](README.md) — mapa de documentación
2. [`architecture/DB_FIRST_CORE_REFACTOR.md`](architecture/DB_FIRST_CORE_REFACTOR.md) — arquitectura DB-first
3. [`architecture/system_overview.md`](architecture/system_overview.md) — componentes
4. `comandos.txt` (local, no versionado) o `uv run duckops --help` — operación diaria

## Comandos útiles

| Comando | Uso |
|---------|-----|
| `uv run duckops up` | **Día 0 completo** (recomendado) |
| `uv run duckops bootstrap --yes` | Solo prerequisitos + `uv sync` |
| `uv run duckops bootstrap --check` | Solo lista qué falta |
| `uv run duckops doctor --bootstrap --yes` | Bootstrap + diagnóstico |
| `uv run duckops init --no-bootstrap` | Wizard sin tocar el sistema |
| `uv run duckops smoke` | Health check del gateway |
| `uv run duckclaw-migrate --verify-only` | Verificar migraciones |
| `uv run duckops stack status` | Estado PM2 |
