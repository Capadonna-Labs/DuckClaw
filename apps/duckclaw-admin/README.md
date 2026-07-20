# DuckClaw Admin UI

Consola web de operación para DuckClaw: agentes (catálogo DB-first), playground, runtime DuckDB, skills/MCP, Telegram y observabilidad. Construida con **Next.js 14** (App Router) y **pnpm**.

| Documento | Contenido |
|-----------|-----------|
| [docs/README.md](docs/README.md) | Índice de toda la documentación |
| [docs/architecture.md](docs/architecture.md) | BFF, seguridad, fuentes de verdad |
| [docs/environment.md](docs/environment.md) | Variables de entorno |
| [docs/development.md](docs/development.md) | Desarrollo, build, pruebas |
| [docs/voice-realtime.md](docs/voice-realtime.md) | Voz en vivo (Pipecat / playground) |
| [UIUX patterns](../../docs/architecture/UIUX-PATTERNS.md) | Patrones UI del monorepo |

---

## Qué es (y qué no es)

**Sí:** panel de administración del monorepo DuckClaw — edita agentes en catálogo DuckDB (`admin_worker_catalog`), variables `.env` del gateway (enmascaradas), whitelist Telegram, `agent_config` por bóveda, playground con delegación al manager, historial Redis.

**No:** no ejecuta el grafo LangGraph ni escribe DuckDB directamente; todo pasa por el **API Gateway** y el **db-writer**.

---

## Arquitectura (resumen)

```
Navegador → Next.js (puerto 3001 por defecto)
              └─ /api/admin/*  (BFF, solo servidor)
                    └─ API Gateway :8000 /api/v1/admin/*
                          ├─ DuckDB (catálogo workers, skills, MCP, políticas)
                          ├─ disco (forge/seed/default, .env)
                          ├─ Redis (sesiones, historial chat)
                          └─ cola → db-writer → DuckDB (escrituras)
```

La UI **nunca** llama al gateway con la API key desde el browser; el BFF en `src/app/api/admin/[...path]/route.ts` inyecta `X-Admin-Key` y valida CSRF en mutaciones.

### Fuentes de verdad relevantes para agentes

| Dato | Origen |
|------|--------|
| Lista y ficheros del agente | DuckDB `admin_worker_versions` (snapshot) |
| Categorías de skills en el picker | DuckDB `admin_skill_categories` + seed `framework_skill_categories_v1` |
| Skills custom del tenant | DuckDB `admin_skills` / `admin_worker_skills` |
| Runtime efectivo (tools) | Gateway al construir el grafo (`manifest_snapshot.skills` + env) |

El worker **filesystem** `forge/seed/default` sigue existiendo como plantilla base; agentes creados en Admin viven en catálogo DB.

---

## Requisitos previos

| Componente | Versión | Obligatorio |
|------------|---------|-------------|
| Node.js | ≥ 20 | Sí |
| pnpm | ≥ 9 | Sí |
| Redis | — | Sí |
| DuckClaw-Gateway | PM2 o `uvicorn` | Sí |
| DuckClaw-DB-Writer | PM2 | Sí (escrituras runtime) |
| Docker | — | Solo si usas GitHub MCP, sandbox Strix o browser sandbox |

---

## Inicio rápido

### 1. Backend DuckClaw

Desde la **raíz del monorepo**:

```bash
# .env raíz: DUCKCLAW_ADMIN_API_KEY, REDIS_URL, GITHUB_TOKEN (opcional), etc.
uv run duckops serve --pm2 --gateway
pm2 start config/ecosystem.db-writer.config.cjs
pm2 restart DuckClaw-Gateway --update-env
```

Comprobar gateway:

```bash
curl -sS -H "X-Admin-Key: TU_CLAVE" http://127.0.0.1:8000/api/v1/admin/health
```

### 2. Admin UI

```bash
cp apps/duckclaw-admin/.env.example apps/duckclaw-admin/.env.local
# Editar DUCKCLAW_GATEWAY_URL, DUCKCLAW_ADMIN_API_KEY, DUCKCLAW_ADMIN_EMAIL/PASSWORD

pnpm admin:install    # desde raíz
pnpm admin:dev        # http://localhost:3001
```

O dentro de la app:

```bash
cd apps/duckclaw-admin
pnpm install
pnpm dev
```

### 3. Login

Credenciales iniciales vía seed en hub DuckDB (`.env.local`: `DUCKCLAW_ADMIN_EMAIL` / `DUCKCLAW_ADMIN_PASSWORD`). En desarrollo, hints opcionales en `/login` (`SHOW_DEV_HINT=true`).

Tras cambiar usuarios en el hub, no hace falta reiniciar Next; sí reiniciar gateway si cambias políticas de auth.

---

## Pantallas principales

Navegación definida en `src/config/adminNav.ts` (grupos **Trabajo · Estudio · Plataforma** para admin).

| Ruta | Descripción |
|------|-------------|
| `/overview` | Health gateway, workers, flags |
| `/playground` | Chat admin (manager + workers, vault, LLM, voz) |
| `/sandbox` | Artefactos y sesiones sandbox |
| `/kanban` | Tablero operativo |
| `/templates` | **Agentes** — lista y editor por worker |
| `/templates/[workerId]` | Manifest YAML, contextos, capabilities, herramientas |
| `/projects` | Proyectos y asignación de agentes |
| `/knowledge` | Fuentes RAG por proyecto |
| `/reports` | Reportes HTML publicados |
| `/skills` | Catálogo global de skills custom |
| `/mcp` | Conectores MCP (DB-first) |
| `/gen/image` | Generación de imágenes (ComfyUI) |
| `/duckdb` | Bóvedas DuckDB |
| `/runtime` | `agent_config` por vault |
| `/policies` | Instrucciones / políticas de prompt |
| `/integrations/*` | Edge devices, sensory node |
| `/telegram` | Webhooks + whitelist |
| `/admin/access` | Usuarios autorizados |
| `/audit` | Registro de cambios admin |
| `/settings` | Perfil, tema, ajustes |

`viewer` recibe **403** en escrituras vía BFF; rutas `adminOnly` requieren rol `admin`.

---

## Herramientas del agente (manifest)

En `/templates/[workerId]`, el panel **Capabilities** incluye el dropdown **Herramientas**:

- Categorías desde gateway `GET /api/v1/admin/catalog/skill-categories` (DuckDB; fallback local si el gateway no responde).
- Cada skill opcional tiene **checkbox** para activar/desactivar en `manifest.yaml`.
- El baseline (perfil `general` / `minimal` / `rag_only`) aparece con checkbox deshabilitado — lo controla `tool_profile` en el manifest.
- Cambios en memoria hasta pulsar **Guardar**; el gateway persiste en `admin_worker_versions` vía db-writer.

Código clave:

| Módulo | Rol |
|--------|-----|
| `src/components/templates/WorkerToolsDropdown.tsx` | UI picker por categorías |
| `src/lib/manifestSkillsEdit.ts` | Parse/apply skills en YAML |
| `src/lib/skillCategories.ts` | Agrupación baseline + plataforma + custom |
| `src/components/skills/useSkillCategoriesCatalog.ts` | Fetch catálogo desde gateway |

Skills de plataforma (web, reportes HTML, MCP/GitHub, infra, etc.) se declaran en el manifest; no se mezclan con skills custom de `admin_skills` salvo sync explícito al guardar.

### GitHub MCP desde Admin

1. Activar **MCP → GitHub** en Herramientas y guardar manifest (bloque `github:` con `token_env`, `mcp_read_only`, etc.).
2. En el **host del gateway** (mismo usuario que PM2):
   - `GITHUB_TOKEN` en `.env` raíz
   - `docker` en PATH del proceso PM2
   - Usuario en grupo `docker` (`docker info` sin *permission denied*)
   - Imagen: `docker pull ghcr.io/github/github-mcp-server`
3. `pm2 restart DuckClaw-Gateway`

Éxito en logs: `GitHub MCP registered N tools`. En **Capabilities**, `tools_runtime` debe listar tools del servidor MCP (`get_file_contents`, `list_issues`, …), no un skill llamado `github`.

---

## Scripts npm (raíz del monorepo)

| Script | Acción |
|--------|--------|
| `pnpm admin:dev` | `next dev -p 3001` |
| `pnpm admin:build` | Build producción |
| `pnpm admin:start` | Servir build |
| `pnpm admin:lint` | ESLint |
| `pnpm admin:install` | `pnpm install` en `apps/duckclaw-admin` |

---

## Estructura del código

```
apps/duckclaw-admin/
├── src/app/
│   ├── (admin)/              # Rutas protegidas (layout + sidebar)
│   ├── (auth)/login/         # Login
│   └── api/admin/            # BFF → gateway (+ proxies playground/voice)
├── src/components/
│   ├── templates/            # WorkerCapabilitiesCard, WorkerToolsDropdown, …
│   ├── playground/           # Chat studio, vault, sandbox chips
│   ├── chat/                 # AdminChatPanel, streaming SSE
│   └── skills/               # Catálogo skills + hooks
├── src/services/adminService.ts
├── src/lib/                    # manifestSkillsEdit, skillCategories, …
├── src/config/adminNav.ts
└── docs/                       # Guías detalladas
```

---

## Producción

```bash
pnpm admin:build
pnpm admin:start   # PORT en .env.local (p. ej. 3001)
```

- Sirve detrás de reverse proxy (Tailscale Serve, nginx) con HTTPS.
- `DUCKCLAW_ADMIN_API_KEY` solo en servidor (`.env.local` o secretos del host).
- Auth con sesión en Redis; planificar SSO/JWT para entornos multi-tenant estrictos (spec § fase posterior).

Tailscale admin: ver [docs/environment.md](docs/environment.md#admin-en-el-celular-tailscale-serve).

---

## Solución de problemas

| Síntoma | Causa habitual | Acción |
|---------|----------------|--------|
| `503 DUCKCLAW_GATEWAY_URL no configurada` | Falta `.env.local` | Copiar `.env.example` → `.env.local` |
| `401 Admin key inválida` | Clave distinta entre gateway y Next | Igualar `DUCKCLAW_ADMIN_API_KEY` en raíz y `.env.local` |
| Overview en rojo | Gateway o Redis caídos | `pm2 status`, `curl …/admin/health` |
| Catálogo skills vacío / fallback | Migraciones DuckDB pendientes | Reiniciar gateway (aplica M028+); `GET …/catalog/skill-categories` |
| Agente dice que no tiene GitHub | Skill no guardada en manifest | Activar checkbox + **Guardar** manifest |
| `FileNotFoundError: 'docker'` | PM2 sin `docker` en PATH | Añadir PATH en `.env` o `ecosystem.api.config.cjs` |
| `permission denied … docker.sock` | Usuario PM2 fuera del grupo `docker` | `sudo usermod -aG docker $USER`, re-login, `pm2 restart` |
| GitHub MCP `Connection closed` | Docker/PAT/imagen | `docker info`, `GITHUB_TOKEN`, pull imagen MCP |
| Capabilities: Docker no disponible | Host sin Docker o sin permisos | Arreglar Docker antes de sandbox o GitHub MCP |
| Viewer no puede guardar | Esperado | Usar rol `admin` |

Más detalle: [docs/development.md](docs/development.md#troubleshooting).
