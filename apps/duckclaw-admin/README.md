# DuckClaw Admin UI

Consola web de operación para DuckClaw: plantillas Forge, runtime DuckDB, Telegram, fly commands y observabilidad. Construida con **Next.js 14** (App Router) y **pnpm**.

| Documento | Contenido |
|-----------|-----------|
| [docs/README.md](docs/README.md) | Índice de toda la documentación |
| [docs/architecture.md](docs/architecture.md) | BFF, seguridad, fuentes de verdad |
| [docs/environment.md](docs/environment.md) | Variables de entorno |
| [docs/development.md](docs/development.md) | Desarrollo, build, pruebas |
| [docs/legacy-crm-module.md](docs/legacy-crm-module.md) | Código CRM PQRSD heredado (no expuesto en rutas actuales) |
| [specs/features/platform/DUCKCLAW_ADMIN_UI.md](../../specs/features/platform/DUCKCLAW_ADMIN_UI.md) | Spec normativa (SDD) |

---

## Qué es (y qué no es)

**Sí:** panel de administración del monorepo DuckClaw — edita workers en `packages/agents/src/duckclaw/forge/templates/`, variables `.env` del gateway (enmascaradas), whitelist Telegram, `agent_config` por bóveda, historial Redis.

**No:** la bandeja operativa GovTech PQRSD (Kanban, tickets por secretaría) del hackathon. Ese dominio quedó como **módulo legacy** en `src/lib/crm/` y servicios asociados; ver [docs/legacy-crm-module.md](docs/legacy-crm-module.md). El CRM desplegable sigue en el repo histórico [retoPWRSomegahack](https://github.com/ManePeqsiCoda/retoPWRSomegahack) hasta reactivarse aquí.

---

## Arquitectura (resumen)

```
Navegador → Next.js (puerto 3000)
              └─ /api/admin/*  (BFF, solo servidor)
                    └─ API Gateway :8000 /api/v1/admin/*
                          ├─ disco (forge/templates, .env)
                          ├─ Redis (historial chat)
                          └─ cola → db-writer → DuckDB
```

La UI **nunca** llama al gateway con la API key desde el browser; el BFF en `src/app/api/admin/[...path]/route.ts` inyecta `X-Admin-Key`.

---

## Requisitos previos

| Componente | Versión | Obligatorio |
|------------|---------|-------------|
| Node.js | ≥ 20 | Sí |
| pnpm | ≥ 9 | Sí |
| Redis | — | Sí |
| DuckClaw-Gateway | PM2 o `uvicorn` | Sí |
| DuckClaw-DB-Writer | PM2 | Sí (escrituras runtime) |

---

## Inicio rápido

### 1. Backend DuckClaw

Desde la **raíz del monorepo**:

```bash
# .env raíz: define DUCKCLAW_ADMIN_API_KEY (misma clave que usará el admin)
uv run duckops serve --pm2 --gateway
pm2 start config/ecosystem.db-writer.config.cjs
pm2 restart DuckClaw-Gateway --update-env
```

Comprobar gateway + admin:

```bash
curl -sS -H "X-Admin-Key: TU_CLAVE" http://127.0.0.1:8000/api/v1/admin/health
```

### 2. Admin UI

```bash
cp apps/duckclaw-admin/.env.example apps/duckclaw-admin/.env.local
# Editar DUCKCLAW_GATEWAY_URL y DUCKCLAW_ADMIN_API_KEY

pnpm admin:install    # desde raíz
pnpm admin:dev        # http://localhost:3000
```

O dentro de la app:

```bash
cd apps/duckclaw-admin
pnpm install
pnpm dev
```

### 3. Login

Usuarios demo en `src/config/adminUsers.ts` (por defecto):

| Email | Contraseña | Rol |
|-------|------------|-----|
| `admin@duckclaw.local` | `1234` | `admin` — CRUD completo + auditoría |

Tras editar usuarios, reinicia `pnpm dev`. En `/login` hay panel **Usuarios de prueba** con autocompletado.

---

## Pantallas

| Ruta | Descripción | Rol |
|------|-------------|-----|
| `/login` | Autenticación demo | — |
| `/overview` | Health gateway, workers, flags | todos |
| `/templates` | Lista workers Forge | todos (lectura) |
| `/templates/[workerId]` | Editor YAML/MD/SQL/skills | admin escribe |
| `/projects/new` | Wizard clonar plantilla | admin |
| `/runtime` | `agent_config` por vault | admin escribe |
| `/telegram` | Webhooks + whitelist | admin escribe |
| `/commands` | Catálogo fly commands | todos |
| `/duckdb` | Bóvedas y variables DuckDB | todos |
| `/traces` | Historial Redis por sesión | todos |
| `/audit` | Registro de cambios admin | solo `admin` |
| `/settings` | Perfil, tema, hints demo | todos |

`viewer` (si lo añades en `adminUsers.ts`) recibe **403** en PUT/PATCH/POST/DELETE vía BFF.

---

## Scripts npm (raíz del monorepo)

| Script | Acción |
|--------|--------|
| `pnpm admin:dev` | `next dev` en esta app |
| `pnpm admin:build` | Build producción |
| `pnpm admin:start` | Servir build |
| `pnpm admin:lint` | ESLint |
| `pnpm admin:install` | `pnpm install` en `apps/duckclaw-admin` |

---

## Estructura del código

```
apps/duckclaw-admin/
├── src/app/
│   ├── (admin)/          # Rutas protegidas (layout + sidebar)
│   ├── (auth)/login/     # Login
│   └── api/admin/[...path]/  # BFF → gateway
├── src/components/       # UI (admin, layout, shared)
├── src/services/         # adminService + legacy CRM
├── src/lib/crm/          # Legacy GovTech (sin rutas activas)
├── src/config/adminUsers.ts
└── docs/                 # Guías detalladas
```

---

## Producción

```bash
pnpm admin:build
pnpm admin:start   # puerto 3000 por defecto
```

- Sirve detrás de reverse proxy (Tailscale, nginx) con HTTPS.
- `DUCKCLAW_ADMIN_API_KEY` solo en servidor (`.env.local` o secretos del host).
- Auth demo **no** es apta para producción; planificar SSO/JWT (spec § fase posterior).

---

## Solución de problemas

| Síntoma | Causa habitual | Acción |
|---------|----------------|--------|
| `503 DUCKCLAW_GATEWAY_URL no configurada` | Falta `.env.local` | Copiar `.env.example` → `.env.local` |
| `401 Admin key inválida` | Clave distinta entre gateway y Next | Igualar `DUCKCLAW_ADMIN_API_KEY` en raíz y `.env.local` |
| Overview en rojo | Gateway o Redis caídos | `pm2 status`, `curl …/admin/health` |
| Plantillas vacías | `DUCKCLAW_REPO_ROOT` incorrecto | En gateway, ruta al monorepo o dejar default |
| Viewer no puede guardar | Esperado | Usar rol `admin` |

Más detalle: [docs/development.md](docs/development.md#troubleshooting).

---

## Origen del código

Migrado desde el hackathon [retoPWRSomegahack](https://github.com/ManePeqsiCoda/retoPWRSomegahack) (rama `samuel_dev-interfaz`) hacia `apps/duckclaw-admin`. Ver [EXTERNAL_RETO_PWR.md](EXTERNAL_RETO_PWR.md).
