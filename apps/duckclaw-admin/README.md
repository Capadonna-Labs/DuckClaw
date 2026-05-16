# DuckClaw Admin UI

Consola web (Next.js 14 + **pnpm**). Spec: `specs/features/DuckClaw_Admin_UI.md`.

## Qué debes tener levantado

La UI **no** es un servicio aparte de DuckClaw: es un frontend que habla con el **API Gateway** vía BFF.

| Proceso | Obligatorio | Rol |
|---------|-------------|-----|
| **Redis** | Sí | Cola `duckdb_write_queue`, historial chat |
| **DuckClaw-DB-Writer** | Sí | Escrituras ACID DuckDB |
| **DuckClaw-Gateway** | Sí | `/api/v1/admin/*`, agentes, Telegram |
| **MLX / LLM** | No para admin CRUD | Solo si pruebas chat desde otros clientes |

```bash
# Desde la raíz del monorepo
uv run duckops serve --pm2 --gateway
pm2 start config/ecosystem.db-writer.config.cjs
pm2 restart DuckClaw-Gateway --update-env
```

Comprueba: `curl -s -H "X-Admin-Key: TU_CLAVE" http://127.0.0.1:8000/api/v1/admin/health`

## Variables

**Raíz `.env`** (gateway):

```env
DUCKCLAW_ADMIN_API_KEY=tu-clave-secreta
REDIS_URL=redis://localhost:6379/0
```

**`apps/duckclaw-admin/.env.local`** (solo servidor Next):

```env
DUCKCLAW_GATEWAY_URL=http://127.0.0.1:8000
DUCKCLAW_ADMIN_API_KEY=tu-clave-secreta
```

Usa **localhost** para desarrollo. Si `DUCKCLAW_TAILSCALE_AUTH_KEY` está en el gateway, las rutas `/api/v1/admin/*` están **exentas** de esa cabecera (auth = `X-Admin-Key`).

## pnpm

```bash
cd apps/duckclaw-admin
pnpm install
pnpm dev
```

Desde raíz: `pnpm admin:dev`

## Login (usuarios de prueba)

| Email | Contraseña | Rol |
|-------|------------|-----|
| `admin@duckclaw.local` | `DuckAdmin2026!` | admin (CRUD) |
| `viewer@duckclaw.local` | `DuckView2026!` | viewer (solo lectura) |

Configuración: edita `src/config/adminUsers.ts` y reinicia `pnpm dev`. En la pantalla de login hay un panel **Usuarios de prueba** con botón **Usar** para autocompletar.

## Logout

Botón **Cerrar sesión** en sidebar (pie) y **Salir** en topbar.

## Pantallas

| Ruta | Función |
|------|---------|
| `/overview` | Health gateway + workers |
| `/templates` | CRUD plantillas `forge/templates` |
| `/projects/new` | Wizard clonar worker |
| `/runtime` | `agent_config` por vault (cola db-writer) |
| `/telegram` | Webhooks, token `.env`, whitelist `authorized_users` |
| `/commands` | Catálogo fly commands (`/help`) |
| `/duckdb` | Bóvedas y vars DuckDB |
| `/traces` | Historial Redis por sesión |
| `/audit` | Registro de cambios (solo rol **admin**) |
| `/settings` | Perfil, usuarios demo, tema |

**Auth real (JWT/BD):** fase posterior; hoy rol `admin`/`viewer` solo en BFF demo.
