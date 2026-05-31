# Admin Console — Login y autenticación segura

Versión: 1.0 · Fecha: 2026-05-30

## Objetivo

Autenticación segura para `apps/duckclaw-admin`: sesiones server-side (Redis), cookies HttpOnly, Argon2id con migración desde PBKDF2, rate limiting, CSRF y RBAC derivado de sesión en el BFF.

Relacionado: [`ADMIN_ACCESS_MANAGEMENT.md`](ADMIN_ACCESS_MANAGEMENT.md), [`API_GATEWAY_HARDENING.md`](API_GATEWAY_HARDENING.md).

## Arquitectura

```
Browser → Next.js BFF (/api/admin/auth/*) → Gateway (/api/v1/admin/auth/*) → DuckDB + Redis
```

- **Gateway**: verifica credenciales, emite cookies `session` + `csrf_token`, almacena sesión en Redis.
- **BFF**: proxy simple en login; deriva rol desde `/auth/me` (no confía en headers del cliente); valida CSRF en mutaciones.
- **Frontend**: Zustand sin persist; hydrate vía `/api/admin/auth/me`; `credentials: 'include'`.

## Persistencia

Tabla `main.admin_console_users` en hub DuckDB (`get_gateway_db_path()`).

Columnas de auth (migración `002_admin_auth_columns`):

| Columna | Tipo | Notas |
|---------|------|-------|
| `password_hash` | VARCHAR | Argon2id o PBKDF2 legacy |
| `hash_algo` | TEXT | `argon2id` \| `pbkdf2_sha256` |
| `hash_params` | JSON | DuckDB JSON (no JSONB) |
| `failed_login_count` | INTEGER | Fallos acumulados |
| `last_failed_at` | TIMESTAMP | Para delay progresivo |

### Hashing

- **Nuevo**: Argon2id (`argon2-cffi`), params vía env (`ARGON2_TIME`, `ARGON2_MEMORY_KB`, `ARGON2_PARALLELISM`).
- **Legacy**: `pbkdf2_sha256$<iter>$<salt_b64>$<hash_b64>` (260k iter default).
- **Migración**: rehash-on-login silencioso PBKDF2 → Argon2id.

## Sesiones (Redis)

- Key: `sess:{session_id}` → JSON `{user_id, email, rol, created_at, last_activity}`
- TTL: `SESSION_TTL_SECONDS` (default 43200)
- Cookie `session`: HttpOnly, Secure (prod), SameSite=Lax
- Cookie `csrf_token`: readable por JS (double-submit)
- `/auth/me` **refresca TTL** en cada request

## Rate limiting y delay

- IP: `rl:login:ip:{ip}` — max 100/min → 429
- Email: contador fallos Redis + DuckDB; **delay progresivo** (no lock total):
  - `calculate_login_delay(n) = min(2^(n-5), 3600)` para n ≥ 5
  - Sleep cap 5s en handler

## CSRF

Double-submit: header `X-CSRF-Token` debe coincer con cookie `csrf_token` en POST/PUT/PATCH/DELETE del BFF.

## Endpoints

| Método | Ruta | Auth |
|--------|------|------|
| POST | `/api/v1/admin/auth/login` | Público |
| GET | `/api/v1/admin/auth/me` | Cookie session |
| POST | `/api/v1/admin/auth/logout` | Cookie session |

Errores login: siempre genérico `Invalid credentials` (401). Sin enumeración de emails.

## Cabeceras (Next.js)

- CSP con nonce dinámico (`middleware.ts`)
- X-Frame-Options, nosniff, Referrer-Policy
- HSTS solo si `ENV=production`

## Variables de entorno

```
SESSION_TTL_SECONDS=43200
COOKIE_DOMAIN=
ENV=development
ARGON2_TIME=2
ARGON2_MEMORY_KB=65536
ARGON2_PARALLELISM=4
PBKDF2_ITERATIONS=260000
GATEWAY_INTERNAL_URL=http://127.0.0.1:8000
SHOW_DEV_HINT=false
DUCKCLAW_ADMIN_EMAIL=
DUCKCLAW_ADMIN_PASSWORD=
```

## Dev hints

Solo en `NODE_ENV=development` **y** `SHOW_DEV_HINT=true`. Email opcional vía `NEXT_PUBLIC_DEV_HINT_EMAIL`. **Nunca** passwords en código ni `NEXT_PUBLIC_*`.

## Criterios de aceptación

- Login establece cookies HttpOnly + CSRF
- Argon2id para nuevos hashes; PBKDF2 migra en login
- `/me` renueva TTL Redis
- BFF no confía en `x-duckclaw-role` del cliente
- CSRF en mutaciones BFF
- Sin credenciales en repo ni localStorage
- Tests unit + integration pasan en CI
