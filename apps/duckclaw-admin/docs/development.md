# Desarrollo — DuckClaw Admin UI

## Entorno local

```bash
# Terminal 1 — monorepo raíz
uv run duckops serve --pm2 --gateway
pm2 start config/ecosystem.db-writer.config.cjs

# Terminal 2 — admin UI
cd apps/duckclaw-admin
cp .env.example .env.local   # primera vez
pnpm install
pnpm dev                     # http://localhost:3001
```

Desde raíz: `pnpm admin:dev`.

Abre http://localhost:3001 → redirige a `/playground` o `/overview` si hay sesión; si no, `/login`.

## Añadir una pantalla admin

1. Crear `src/app/(admin)/mi-pantalla/page.tsx` (hereda layout con sidebar).
2. Añadir entrada en `src/config/adminNav.ts` (grupo `WORK_NAV_GROUP`, `STUDIO_NAV_GROUP` o `PLATFORM_NAV_GROUP`).
3. Si necesita API nueva en gateway: implementar en `services/api-gateway/routers/admin_domains/` + comando tipado en `packages/shared` si muta DuckDB.
4. Consumir desde `src/services/adminService.ts` vía `adminFetch('/mi-recurso')`.

El BFF ya reenvía cualquier subruta bajo `/api/admin/`: no hace falta nuevo `route.ts` salvo proxies especiales (playground SSE, voz, timeouts largos).

Excepciones con `route.ts` propio: `src/app/api/admin/playground/chat/`, `playground/voice/`, etc.

## Extender el picker de herramientas (manifest)

Flujo DB-first:

1. **Seed** — añadir skill/categoría en `packages/shared/src/duckclaw/seeds/framework_skill_categories_v1.json`.
2. **Migración** — si hace falta upsert en DBs ya migradas, hook en `schema_migrations.py` (ver M029 como ejemplo).
3. **Runtime** — registrar tools en factory (`factory_tool_builder.py`, `skill_tool_registry.py` o bridge dedicado).
4. **Admin UI** — opcional: `DEFAULT_*_CONFIG` en `src/lib/manifestSkillsEdit.ts`; fallback en `src/lib/skillCategories.ts` si el gateway no responde.

Tests útiles:

```bash
# raíz monorepo
uv run pytest tests/test_skill_catalog.py tests/test_github_skill_factory.py -q

# admin
cd apps/duckclaw-admin && npx tsx src/lib/manifestSkillsEdit.test.ts
```

## Roles y permisos en UI

- Sesión: cookie HttpOnly `session` + `csrf_token` (ver [`specs/features/platform/ADMIN_CONSOLE_AUTH.md`](../../../specs/features/platform/ADMIN_CONSOLE_AUTH.md))
- Store: `src/store/authStore.ts` — hidrata vía `/api/admin/auth/me`
- BFF deriva el rol desde la sesión en gateway (no confía en headers del cliente)
- Mutaciones: `adminService` envía `X-CSRF-Token` desde la cookie `csrf_token`

Para probar solo lectura, crea un usuario con rol `user` en `/admin/access`.

## Estilos y UX

- Tailwind + tokens GovTech en `src/app/globals.css` y `tailwind.config.ts`
- Patrones del monorepo: `UIUX-PATTERNS.md` en la raíz
- Componentes compartidos: `src/components/shared/`, shell: `src/components/admin/PageShell.tsx`

## Calidad

```bash
pnpm lint          # en apps/duckclaw-admin
pnpm build         # debe pasar antes de PR
```

Tests del gateway admin (Python): `tests/test_admin_router.py`, `tests/test_worker_capabilities.py` en la raíz del monorepo.

## Build y despliegue

```bash
pnpm admin:build
pnpm admin:start   # NODE_ENV=production; PORT en .env.local (3001 dev, 3000 en spawn PM2)
```

Variables en el host de producción equivalentes a `.env.local`. Reverse proxy recomendado (TLS).

## Troubleshooting

### BFF devuelve 503

- Revisar `DUCKCLAW_GATEWAY_URL` y `DUCKCLAW_ADMIN_API_KEY` en `.env.local`.
- Reiniciar `pnpm dev` tras cambiar env.

### 401 en todas las llamadas admin

- Clave distinta entre gateway y Next.
- Gateway sin `DUCKCLAW_ADMIN_API_KEY` → el router responde 503/401 según caso.

### Agente / manifest no guarda / 400 path

- El gateway valida path relativo y extensión (`.yaml`, `.md`, `.sql`, `.py`, …).
- No uses `..` en rutas.
- Escrituras van por **db-writer**: `pm2 logs DuckClaw-DB-Writer`.

### Runtime config no persiste

- Comprobar **db-writer** y Redis.
- Las mutaciones no son síncronas instantáneas en DuckDB.

### Catálogo skills vacío o sin MCP/GitHub

- Gateway debe aplicar migraciones M028+ (`pm2 restart DuckClaw-Gateway`).
- Probar: `curl -H "X-Admin-Key: …" http://127.0.0.1:8000/api/v1/admin/catalog/skill-categories`

### GitHub MCP activo en UI pero agente sin tools

| Log / UI | Acción |
|----------|--------|
| `FileNotFoundError: 'docker'` | Añadir `docker` al PATH de PM2 (`.env` o `ecosystem.api.config.cjs`) |
| `permission denied … docker.sock` | `sudo usermod -aG docker $USER`, re-login, `pm2 restart` |
| `GitHub MCP disabled: PAT missing` | `GITHUB_TOKEN` en `.env` raíz |
| Capabilities: Docker no disponible | `docker info` como usuario PM2 |
| Sin log `GitHub MCP registered` | Guardar manifest con bloque `github:` y reiniciar gateway |

### Puerto ocupado

Por defecto la app usa **3001** (`package.json`). Si 3001 está ocupado:

```bash
PORT=3002 pnpm dev
```

### Cambios en credenciales de login

Usuarios viven en hub DuckDB (`DUCKCLAW_ADMIN_EMAIL` / `DUCKCLAW_ADMIN_PASSWORD` en seed). Tras cambios en gateway, no hace falta reiniciar Next salvo caché de sesión.

## Relación con el monorepo

| Cambio en | Acción en admin |
|-----------|-----------------|
| Nuevo worker en catálogo DB | Aparece en `/templates` tras refresh |
| Nueva skill en seed framework | Migración + restart gateway; picker vía `/catalog/skill-categories` |
| Nueva variable `.env` permitida | Allow-list en `admin.py` + spec |
| Nuevo endpoint admin | `admin_domains/` + método en `adminService` |

Los agentes creados en Admin **no** se editan solo en `forge/templates/` del disco: el canónico es el snapshot en DuckDB. El filesystem `forge/seed/default` queda para la plantilla base del framework.
