# Admin Identity, RBAC y Gateway Hub

Versión: 1.0 · Fecha: 2026-05-31

## Objetivo

Definir cómo DuckClaw Admin autentica usuarios, dónde se persisten roles/permisos y cómo se relacionan usuarios, tenants, canales y agentes runtime con el hub DuckDB del Gateway.

Relacionado:

- `specs/features/platform/ADMIN_CONSOLE_AUTH.md`
- `specs/features/platform/ADMIN_ACCESS_MANAGEMENT.md`
- `specs/features/platform/ADMIN_USER_AGENT_WORKSPACES.md`

## Conceptos

### Gateway Hub

El hub del Gateway es el archivo DuckDB activo resuelto por `duckclaw.gateway_db.get_gateway_db_path()`.

No es una “tabla padre” como tal. Es más parecido a una base de datos central o hub relacional donde viven tablas de control:

- Usuarios de consola.
- Perfiles operativos por usuario.
- Agentes runtime por tenant.
- Whitelist Telegram.
- Grants a bases compartidas.
- Configuración por chat/agente.

La ruta se resuelve en orden desde variables como:

1. `DUCKCLAW_WAR_ROOM_ACL_DB_PATH`
2. `DUCKCLAW_FINANZ_DB_PATH`
3. `DUCKCLAW_JOB_HUNTER_DB_PATH`
4. `DUCKCLAW_SIATA_DB_PATH`
5. `DUCKCLAW_QUANT_TRADER_DB_PATH`
6. `DUCKCLAW_PQRSD_ASSISTANT_DB_PATH`
7. `DUCKCLAW_AXIS_DB_PATH`
8. `DUCKDB_PATH`

### Identidad de Consola

La tabla `main.admin_console_users` es la fuente de verdad del login web:

- `email`: identificador del usuario.
- `rol`: `admin` o `user`.
- `password_hash`: hash Argon2id o PBKDF2 legacy.
- `hash_algo` y `hash_params`: metadata del algoritmo.
- `failed_login_count` y `last_failed_at`: seguridad de login.
- `active`: permite desactivar usuarios sin borrarlos.

No hay registro público en la pantalla de login. Los usuarios se crean por seed inicial o por un admin desde la API/vista de acceso.

### Perfil Operativo

La tabla `main.admin_user_profiles` conecta el usuario de consola con su contexto operativo:

- `email`: referencia lógica a `admin_console_users.email`.
- `tenant_id`: tenant único del usuario.
- `telegram_user_id`: identidad Telegram opcional.
- `channels_json`: canales configurados.
- `default_worker_id`: agente default del usuario.

### Agentes Runtime

La tabla `main.admin_user_agents` indexa agentes creados por usuarios:

- `tenant_id`: tenant dueño.
- `owner_email`: usuario dueño.
- `worker_id`: identificador del agente.
- `display_name`: nombre visible.
- `source_template_id`: template base usado como semilla.
- `manifest_path`: manifiesto runtime fuera de templates globales.
- `active`: permite ocultar/desactivar.

Los agentes de usuario no deben escribirse en `packages/agents/src/duckclaw/forge/templates`. Ese árbol queda como catálogo base del producto.

### Catálogo DB-First de Workers

El catálogo nuevo usa DuckDB como control plane de visibilidad y ownership:

- `main.admin_worker_catalog`: identidad actual del worker/agente. No guarda snapshots grandes.
- `main.admin_worker_versions`: snapshots importados de `manifest.yaml` y archivos relevantes.
- `main.admin_worker_contexts`: N contextos `.md` por worker, ordenables y activables.
- `main.admin_skills` / `main.admin_worker_skills`: skills reutilizables N:N.
- `main.admin_capabilities` / `main.admin_worker_capabilities`: capabilities reutilizables N:N.
- `main.admin_projects` / `main.admin_project_agents`: N agentes por proyecto.

Reglas:

- `default` es el único template global visible por defecto.
- Templates en disco distintos de `default` no se listan ni se ejecutan por la consola salvo que estén importados/asignados en BD.
- Importar un template es una copia lógica hacia DuckDB; no borra, mueve ni renombra carpetas.
- Los templates se pueden importar de forma selectiva por prefijo o nombre exacto para el owner/admin actual.
- Templates de otros devs quedan intactos y ocultos salvo import explícito.
- La autorización se resuelve por sesión, tenant, owner/asignación y catálogo DB, no por existencia de una carpeta.

## Modelo Entidad-Relación

```mermaid
erDiagram
  ADMIN_CONSOLE_USERS ||--|| ADMIN_USER_PROFILES : owns_profile
  ADMIN_USER_PROFILES ||--o{ ADMIN_USER_AGENTS : owns_agents
  ADMIN_USER_PROFILES ||--o{ ADMIN_WORKER_CATALOG : owns_workers
  ADMIN_WORKER_CATALOG ||--o{ ADMIN_WORKER_VERSIONS : has_versions
  ADMIN_WORKER_CATALOG ||--o{ ADMIN_WORKER_CONTEXTS : has_contexts
  ADMIN_WORKER_CATALOG ||--o{ ADMIN_WORKER_SKILLS : has_skills
  ADMIN_SKILLS ||--o{ ADMIN_WORKER_SKILLS : reused_by
  ADMIN_WORKER_CATALOG ||--o{ ADMIN_WORKER_CAPABILITIES : has_capabilities
  ADMIN_CAPABILITIES ||--o{ ADMIN_WORKER_CAPABILITIES : reused_by
  ADMIN_USER_PROFILES ||--o{ ADMIN_PROJECTS : owns_projects
  ADMIN_PROJECTS ||--o{ ADMIN_PROJECT_AGENTS : contains_agents
  ADMIN_WORKER_CATALOG ||--o{ ADMIN_PROJECT_AGENTS : works_in
  ADMIN_USER_PROFILES ||--o{ AUTHORIZED_USERS : maps_optional_telegram
  ADMIN_USER_PROFILES ||--o{ USER_SHARED_DB_ACCESS : receives_grants
  ADMIN_USER_PROFILES ||--o{ AGENT_CONFIG : scopes_chat_config

  ADMIN_CONSOLE_USERS {
    string email PK
    string nombre
    string rol
    string password_hash
    string hash_algo
    json hash_params
    int failed_login_count
    timestamp last_failed_at
    boolean active
    timestamp created_at
    timestamp updated_at
  }

  ADMIN_USER_PROFILES {
    string email PK
    string tenant_id UK
    string telegram_user_id
    string channels_json
    string default_worker_id
    timestamp created_at
    timestamp updated_at
  }

  ADMIN_USER_AGENTS {
    string tenant_id PK
    string worker_id PK
    string owner_email
    string display_name
    string source_template_id
    string manifest_path
    boolean active
    timestamp created_at
    timestamp updated_at
  }

  ADMIN_WORKER_CATALOG {
    string worker_uid PK
    string tenant_id
    string owner_email
    string worker_id
    string display_name
    string source_kind
    string source_template_id
    string visibility
    string status
    boolean active
  }

  ADMIN_WORKER_VERSIONS {
    string worker_uid PK
    int version PK
    string manifest_snapshot_json
    string files_snapshot_json
    string created_by
    string change_note
  }

  ADMIN_WORKER_CONTEXTS {
    string context_id PK
    string worker_uid
    string title
    string content_md
    int sort_order
    boolean active
  }

  ADMIN_SKILLS {
    string skill_id PK
    string name
    string skill_type
    string implementation_ref
    string visibility
    boolean active
  }

  ADMIN_CAPABILITIES {
    string capability_id PK
    string name
    string kind
    string provider
    string risk_level
    boolean requires_secret
    boolean requires_network
  }

  ADMIN_PROJECTS {
    string project_id PK
    string tenant_id
    string owner_email
    string name
    string status
    string visibility
  }

  AUTHORIZED_USERS {
    string tenant_id PK
    string user_id PK
    string username
    string role
    timestamp added_at
  }

  USER_SHARED_DB_ACCESS {
    string tenant_id
    string user_id
    string resource_key
    timestamp created_at
  }

  AGENT_CONFIG {
    string key PK
    string value
    timestamp updated_at
  }
```

## RBAC Recomendado

### `admin`

Puede:

- Crear y desactivar usuarios de consola.
- Cambiar roles.
- Ver auditoría y operaciones.
- Administrar grants y whitelist Telegram.
- Crear proyectos/global templates si se habilita explícitamente.

### `user`

Puede:

- Iniciar sesión.
- Usar Playground.
- Crear agentes runtime propios.
- Configurar su perfil operativo y canales.
- Ver solo sus agentes/tenant.

No debe:

- Administrar otros usuarios.
- Ejecutar ops PM2.
- Modificar `.env`.
- Modificar templates globales del repo.

## Alta de Usuarios

### Primer Admin

El primer admin se crea desde `.env` solo si `main.admin_console_users` está vacía:

```bash
DUCKCLAW_ADMIN_EMAIL=admin@example.com
DUCKCLAW_ADMIN_PASSWORD=change-me-min-8
```

Si la tabla ya tiene usuarios, cambiar `.env` no actualiza contraseñas ni crea nuevos usuarios. En ese caso se debe usar un comando de bootstrap/upsert controlado o la vista de gestión de acceso.

### Usuarios Delegados

Un admin debe poder crear usuarios con:

- email
- nombre
- rol (`admin` o `user`)
- contraseña temporal o flujo de invitación
- estado `active`

Al crear el usuario, el sistema debe asegurar también `main.admin_user_profiles` con tenant único.

## Flujo de Login

```mermaid
sequenceDiagram
  participant Browser
  participant BFF as Next_BFF
  participant Gateway
  participant DuckDB as Gateway_Hub_DuckDB
  participant Redis

  Browser->>BFF: POST /api/admin/auth/login
  BFF->>Gateway: POST /api/v1/admin/auth/login
  Gateway->>DuckDB: lookup admin_console_users
  Gateway->>DuckDB: verify hash and ensure admin_user_profiles
  Gateway->>Redis: create sess:{id}
  Gateway-->>BFF: Set-Cookie session and csrf_token
  BFF-->>Browser: user payload with profile
```

## Buenas Prácticas de Seguridad

- No exponer registro público sin invitación o control de admin.
- No guardar passwords en frontend ni `NEXT_PUBLIC_*`.
- Usar Argon2id para hashes nuevos.
- Mantener `session` como HttpOnly.
- Mantener CSRF double-submit para mutaciones BFF.
- Derivar rol/actor/tenant desde sesión server-side, no desde headers del browser.
- No usar contraseñas débiles ni compartidas.
- Rotar credenciales seed después del primer login.
