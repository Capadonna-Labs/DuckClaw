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
pnpm dev
```

Desde raíz: `pnpm admin:dev`.

Abre http://localhost:3001 → redirige a `/overview` si hay sesión, si no a `/login`.

## Añadir una pantalla admin

1. Crear `src/app/(admin)/mi-pantalla/page.tsx` (hereda layout con sidebar).
2. Añadir entrada en `src/components/layout/Sidebar.tsx` (`NAV_CORE` o `NAV_ADMIN`).
3. Si necesita API nueva en gateway: implementar en `services/api-gateway/routers/admin.py` y spec en `specs/features/platform/DUCKCLAW_ADMIN_UI.md`.
4. Consumir desde `src/services/adminService.ts` vía `adminFetch('/mi-recurso')`.

El BFF ya reenvía cualquier subruta: no hace falta nuevo `route.ts` si el path existe en `/api/v1/admin/`.

## Roles y permisos en UI

- Sesión: cookie HttpOnly `session` + `csrf_token` (ver [`specs/features/platform/ADMIN_CONSOLE_AUTH.md`](../../../specs/features/platform/ADMIN_CONSOLE_AUTH.md))
- Store: `src/store/authStore.ts` — estado en memoria; hidrata vía `/api/admin/auth/me`
- BFF deriva el rol desde la sesión en gateway (no confía en headers del cliente)
- Mutaciones: `adminService` envía `X-CSRF-Token` desde la cookie `csrf_token`

Para probar solo lectura, crea un usuario con `rol: 'user'` en `/admin/access`.

## Estilos y UX

- Tailwind + tokens GovTech en `src/app/globals.css` y `tailwind.config.ts`
- Patrones del monorepo: `UIUX-PATTERNS.md` en la raíz
- Componentes compartidos: `src/components/shared/`, shell: `src/components/admin/PageShell.tsx`

## Calidad

```bash
pnpm lint          # en apps/duckclaw-admin
pnpm build         # debe pasar antes de PR
```

Tests del gateway admin (Python): `tests/test_admin_router.py` en la raíz del monorepo.

## Build y despliegue

```bash
pnpm admin:build
pnpm admin:start   # NODE_ENV=production
```

Variables en el host de producción equivalentes a `.env.local`. Reverse proxy recomendado (no exponer `:3000` sin TLS).

## Troubleshooting

### BFF devuelve 503

- Revisar `DUCKCLAW_GATEWAY_URL` y `DUCKCLAW_ADMIN_API_KEY` en `.env.local`.
- Reiniciar `pnpm dev` tras cambiar env.

### 401 en todas las llamadas admin

- Clave distinta entre gateway y Next.
- Gateway sin `DUCKCLAW_ADMIN_API_KEY` → el router responde 503/401 según caso.

### Plantilla no guarda / 400 path

- El gateway valida path relativo y extensión (`.yaml`, `.md`, `.sql`, `.py`, …).
- No uses `..` en rutas.

### Runtime config no persiste

- Comprobar **db-writer** y Redis: `pm2 logs DuckClaw-DB-Writer`.
- Escrituras van por cola, no son síncronas instantáneas en disco.

### Puerto 3000 ocupado

```bash
pnpm dev -- -p 3001
```

### Cambios en `adminUsers.ts` no aplican

- Reiniciar servidor Next (no hot-reload fiable para ese módulo en todos los casos).

## Relación con el monorepo

| Cambio en | Acción en admin |
|-----------|-----------------|
| Nuevo worker Forge | Aparece en `/templates` tras refresh (lee disco vía gateway) |
| Nueva variable `.env` permitida | Actualizar allow-list en `admin.py` + spec |
| Nuevo endpoint admin | Router Python + opcional método en `adminService` |

No editar plantillas solo en la UI sin commitear: el gateway escribe en `packages/agents/.../forge/templates/` del repo.
