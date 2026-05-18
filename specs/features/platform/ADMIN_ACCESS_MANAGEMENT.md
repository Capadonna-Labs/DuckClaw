# Admin UI — Gestión de acceso (usuarios, roles, permisos)

## Objetivo

Vista unificada en la consola web para administrar:

1. **Usuarios consola** (login duckclaw-admin): roles `admin` | `viewer`
2. **Usuarios Telegram** (`authorized_users`): roles `admin` | `user`
3. **Permisos sobre bases DuckDB compartidas** (`user_shared_db_access`)

Fuente de verdad DuckDB: hub del gateway (`get_gateway_db_path()`). Escrituras vía gateway admin API (DuckClaw RW en hub, mismo patrón que whitelist Telegram).

## Persistencia

### `main.admin_console_users`

```sql
CREATE TABLE IF NOT EXISTS main.admin_console_users (
    email VARCHAR PRIMARY KEY,
    nombre VARCHAR NOT NULL,
    rol VARCHAR NOT NULL DEFAULT 'viewer',
    password_hash VARCHAR NOT NULL,
    initials VARCHAR,
    active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Hash de contraseña:** PBKDF2-HMAC-SHA256 (stdlib). Formato almacenado:

`pbkdf2_sha256$<iterations>$<salt_b64>$<hash_b64>`

- `iterations`: default 260000
- `salt_b64`: 16 bytes aleatorios, base64
- `hash_b64`: 32 bytes derivados, base64

### Telegram y shared (existentes)

Ver [`TELEGRAM_AUTH_WHITELIST.md`](../telegram-gateway/TELEGRAM_AUTH_WHITELIST.md) — `authorized_users`, `user_shared_db_access`.

## Matriz de capacidades (consola web)

| Capacidad | admin | viewer |
|-----------|-------|--------|
| Login | sí | sí |
| Lectura general (templates, duckdb, historial, playground) | sí | sí |
| Escritura env / workers / runtime | sí | no |
| Gestión usuarios (esta vista) | sí | no |
| Ops / auditoría | sí | no |

## API Gateway (`/api/v1/admin`)

| Método | Ruta | Auth |
|--------|------|------|
| `POST` | `/auth/login` | Sin `X-Admin-Key` (público para BFF login) |
| `GET` | `/access/overview` | `X-Admin-Key` |
| `GET/POST/PATCH/DELETE` | `/console-users` | `X-Admin-Key` + escritura solo vía BFF con rol admin |
| `GET` | `/access/shared-grants` | `X-Admin-Key` |
| `POST` | `/access/shared-grants` | `X-Admin-Key` |
| `DELETE` | `/access/shared-grants` | `X-Admin-Key` |

Endpoints legacy `/telegram/whitelist` se mantienen; la UI unificada puede usar ambos.

## Bootstrap

`scripts/bootstrap_dbs.py` crea `admin_console_users` y, si la tabla está vacía, inserta el usuario seed desde `ADMIN_USERS` (o variables `DUCKCLAW_ADMIN_EMAIL` / `DUCKCLAW_ADMIN_PASSWORD`).

## Frontend

- Ruta: `/admin/access` (solo rol consola `admin`)
- Tabs: Consola | Telegram | Bases compartidas
- Nav: sección `admin`, ítem «Acceso»

## Fuera de alcance v1

- War Room (`wr_members`)
- SSO/OIDC
- Permisos granulares por ruta más allá de admin/viewer
- Invitaciones por email
