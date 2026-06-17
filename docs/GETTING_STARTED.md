# Empezar con DuckClaw

Entrada mínima para un dev nuevo. Detalle normativo: [`docs/specs/features/platform/PLUG_AND_PLAY_ONBOARDING.md`](specs/features/platform/PLUG_AND_PLAY_ONBOARDING.md).

## Requisitos automáticos (macOS / Linux)

No necesitas memorizar la lista: el CLI instala lo que falte.

| Herramienta | Para qué |
|-------------|----------|
| **uv** | Dependencias Python del monorepo |
| **Redis** | Colas y sesiones |
| **Node + npm** | Consola admin |
| **PM2** | Gateway y db-writer en segundo plano |

Soportado: **macOS** (Homebrew) y **Linux** (apt). Windows nativo: usa WSL2.

## Camino plug & play (un comando)

```bash
git clone <repo> duckclaw && cd duckclaw

# Si no tienes uv aún: curl -LsSf https://astral.sh/uv/install.sh | sh
uv run duckops up
```

`duckops up` hace en orden:

1. Instala **uv**, **Redis**, **Node**, **pnpm**, **PM2** si faltan (macOS/Linux) + `uv sync`
2. Abre el **wizard TUI** la primera vez (admin + `.env` + PM2)
3. `duckclaw-migrate`
4. Gateway + DB-Writer en PM2
5. Smoke `/health`
6. **Menú persistente:** chat TUI, consola web o salir — puedes alternar sin bajar PM2

Tras login web → **Playground** (chat).

En el chat TUI: `/web` abre la consola sin salir del terminal.

### Smoke `/health` (paso 5)

Comprueba que el **API Gateway** responde en `http://localhost:8000/health` con HTTP 200. No prueba login ni Playground; solo confirma que el backend está vivo tras PM2.

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
2. [`docs/specs/features/platform/DB_FIRST_CORE_REFACTOR.md`](specs/features/platform/DB_FIRST_CORE_REFACTOR.md) — arquitectura
3. [`docs/COMANDOS.md`](COMANDOS.md) — operación diaria

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
