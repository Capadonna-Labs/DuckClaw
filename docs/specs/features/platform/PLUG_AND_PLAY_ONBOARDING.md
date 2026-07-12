# Plug & Play — Onboarding de desarrollador

Versión: 1.0 (primera slice) · Fecha: 2026-06-17  
Estado: **normativa parcial** — define el camino objetivo; la implementación completa queda en fases posteriores.

Relacionado:

- [`DB_FIRST_CORE_REFACTOR.md`](DB_FIRST_CORE_REFACTOR.md) — arquitectura canónica y roadmap de fachadas
- [`ADMIN_IDENTITY_RBAC_ERD.md`](ADMIN_IDENTITY_RBAC_ERD.md) — identidad consola y hub DuckDB
- [`ADMIN_ACCESS_MANAGEMENT.md`](ADMIN_ACCESS_MANAGEMENT.md) — seed admin y whitelist
- [`docs/architecture/infra-bootstrap.md`](../../../architecture/infra-bootstrap.md) — migrate / healthcheck
- [`docs/GETTING_STARTED.md`](../../../GETTING_STARTED.md) — entrada rápida para nuevos devs

---

## Objetivo

Un clon del monorepo debe llevar a un **stack local funcional** (gateway + DB-writer + Redis + consola admin) con el mínimo de decisiones manuales, sin reescribir el wizard legacy en un solo PR.

**Fuera de alcance de esta slice:** TUI nueva completa, borrado de `on_the_fly_commands.py`, `db_write_compat.py` ni fachadas `forge/homeostasis`.

---

## Flujo recomendado (seguro / probable)

Orden canónico para un dev nuevo en **macOS, Linux o Windows**:

| Paso | Comando | Qué hace |
|------|---------|----------|
| **0** | `./duckops-up.sh` o `.\duckops-up.ps1` | **Todo en uno desde cero** (instala uv + `duckops up`). |
| **0b** | `uv run duckops up` | Igual si `uv` ya está en PATH. |
| 1 | (alternativa) `uv run duckops bootstrap --yes` | Solo prerequisitos + `uv sync`. |
| 2 | `uv run duckops init` | TUI si no usaste `up` o reconfiguras. |
| 3 | `uv run duckops smoke` | Verificar `/health` tras cambios. |

Tras login en consola admin → **Playground** (chat), no Overview.

Alternativas:

- `uv run duckops doctor` — solo diagnóstico (lista uv, Redis, Node, PM2).
- `uv run duckops doctor --bootstrap --yes` — bootstrap + diagnóstico en un comando.
- `uv run duckops bootstrap --check` — lista prerequisitos sin instalar.

**Plataformas:** auto-install en macOS (Homebrew), Linux (apt + sudo) y Windows (winget + instaladores oficiales). WSL2 se trata como Linux.

**Atajo clásico:** `uv run duckops init --classic` → `scripts/duckclaw_setup_wizard.py` (Rich).

### Qué debe crear `init` (objetivo fase 2)

**Estado actual (2026-06-17, slice fase 2):** Sovereign v2 incluye paso **Consola admin** antes de Review (email + password o generación automática + `DUCKCLAW_ADMIN_API_KEY`). Materializa `.env`, sincroniza `apps/duckclaw-admin/.env.local` y hace seed idempotente en hub DuckDB si la tabla está vacía. Wizard clásico (`--classic`) llama `ensure_admin_env_merged` al terminar si faltan claves.

Pendiente: migraciones explícitas post-init si el hub ya existía sin schema admin; upsert de password en re-init cuando ya hay filas en `admin_console_users`.

El seed de login también puede aplicarse vía:

- Variables `DUCKCLAW_ADMIN_EMAIL` / `DUCKCLAW_ADMIN_PASSWORD` en `.env` (y `.env.local` del admin), aplicadas por `duckclaw-migrate` / `bootstrap_dbs.py` / primer login gateway (`UpsertConsoleUserCommand`).

**Propuesta (fase 2):** en Review del Sovereign, paso obligatorio **antes** de mostrar URL admin:

1. Email admin (default `admin@duckclaw.local`).
2. Password ≥ 8 caracteres (o generación automática mostrada una vez).
3. `DUCKCLAW_ADMIN_API_KEY` generada si falta (no placeholder).

Sin al menos (1)+(2) o API key válida, `doctor` debe fallar la fila «Admin login seed» y la consola admin no es usable (BFF devuelve 503 sin key).

---

## Preguntas de producto — respuestas explícitas

### ¿TUI despliega gateway + config UI?

| Superficie | Rol día 1 | Rol ongoing |
|------------|-----------|-------------|
| **TUI (`duckops init`)** | Bootstrap: secretos, `.env`, PM2 ecosystems, Redis local opcional, migración, hints de URL. | Re-ejecutar tras cambio de infra; no sustituye pantallas de configuración rica. |
| **Admin UI** | Configuración operativa: templates, runtime settings, playground, acceso. Requiere gateway + key + usuario admin. | Fuente de verdad UI para prefs DB-first. |
| **`duckops serve` / `stack`** | Orquestación de procesos (gateway, db-writer). | Operación diaria / CI local. |

**Conclusión:** TUI para **bootstrap y secretos**; Admin UI para **config ongoing**. No reemplazar el TUI por UI en el día 1.

### ¿Admin user/password primero?

**Sí** — el bootstrap debe dejar al menos un admin consola antes de considerar el stack «listo para UI».

| Hoy | Propuesto |
|-----|-----------|
| Seed vía env en `.env` + migrate/bootstrap; Sovereign no pide credenciales en TUI. | Sovereign pregunta admin en Review; `doctor` valida email+password o key no-placeholder. |
| Login: BFF → gateway `POST /auth/login` con Argon2/PBKDF2; sesión Redis. | Sin cambio de contrato auth. |
| `DUCKCLAW_ADMIN_API_KEY` en BFF (nunca en browser). | Generada en `init` si ausente. |

Ver [`ADMIN_ACCESS_MANAGEMENT.md`](ADMIN_ACCESS_MANAGEMENT.md) § seed y [`ADMIN_IDENTITY_RBAC_ERD.md`](ADMIN_IDENTITY_RBAC_ERD.md).

### Idempotencia

| Operación | Comportamiento esperado |
|-----------|-------------------------|
| `duckops init` (re-run) | Sovereign: borrador en `~/.config/duckclaw/`; Review reaplica `.env` con merge idempotente (`merge_env_file`). No duplicar filas admin en DuckDB (upsert). |
| `duckclaw-migrate` | Migraciones versionadas; re-run seguro. |
| `duckops serve --pm2` | No crear segundo proceso PM2 con el mismo nombre; `--update-env` si ya existe. |
| `duckops stack up` | `_pm2_start` solo arranca si no `online`; `pm2 save` solo si hubo cambio. |

---

## Roadmap de eliminación de fachadas (orden de PR)

Prioridad: **cero imports prod** → borrar en PR pequeño con test de contrato actualizado.

| PR | Fachada / deuda | Acción | Owner canónico |
|----|-----------------|--------|----------------|
| **P0 (esta slice)** | `graphs/adapters/*` | Eliminar si sin imports | N/A (código muerto) |
| **P0 (esta slice)** | `runtime/telegram_bot.py` | Eliminar re-export | `duckclaw.graphs.telegram_bot` |
| P1 | `graphs/manager_graph.py` | Mantener hasta migrar imports | `duckclaw.manager.graph` |
| P1 | `graphs/on_the_fly_commands.py` | Dispatcher fino; extraer resto a `commands/*` | `duckclaw.commands.fly_dispatch` |
| P2 | `forge/homeostasis/*` | Eliminar cuando tests verifiquen delegación | `duckclaw.homeostasis.*` |
| P2 | `forge/homeostasis/singleton_writer` | Eliminar | `duckclaw.db_write_queue` |
| P2 | `write_command_handlers.py` (god) | Ya dispatcher; vaciar re-exports legacy | `duckclaw.write_handlers.*` |
| P3 | `admin_db_first.py` | Vaciar | `admin_domains/*` |
| P3 | `admin.py` agregador | Solo montaje + aliases | `admin_domains/*` |
| P3 | `playground_chat.py` | Eliminar fachada ~30 líneas | `admin_domains/playground/` |
| P4 | `services/api-gateway/routers/db_write_compat.py` | Retirar cuando no haya clientes `/api/v1/db/write` | Comandos tipados + db-writer |
| P4 | `workers/factory.py` re-exports | Reducir a API pública mínima | `factory_graph_*`, `workers.*` |

**No tocar en P0–P1:** `on_the_fly_commands`, `db_write_compat`, shims `forge/homeostasis` (migración activa documentada en DB_FIRST).

---

## Mapa fachada → owner canónico

| Fachada | Owner canónico | Notas |
|---------|----------------|-------|
| `duckclaw.graphs.manager_graph` | `duckclaw.manager.graph` | `build_manager_graph` |
| `duckclaw.runtime.telegram_bot` | `duckclaw.graphs.telegram_bot` | Entry PM2 `-m duckclaw.graphs.telegram_bot` |
| `duckclaw.graphs.on_the_fly_commands` | `duckclaw.commands.*` + `fly_dispatch` | Dispatcher compatible |
| `duckclaw.forge.homeostasis.*` | `duckclaw.homeostasis.*` | Tests `test_package_reorg_contracts` |
| `duckclaw.forge.homeostasis.singleton_writer` | `duckclaw.db_write_queue` | Cola única escritura |
| `duckclaw.write_command_handlers` | `duckclaw.write_handlers.<dominio>` | Dispatcher SOA |
| `services/api-gateway/routers/admin.py` | `routers/admin_domains/*` | BFF sin lógica nueva |
| `services/api-gateway/routers/admin_db_first.py` | `admin_domains/runtime_config`, `knowledge` | Transicional |
| `services/api-gateway/routers/db_write_compat.py` | Comandos tipados / db-writer | Solo compat raw query |
| `workers/factory.py` | `factory_graph_assembly`, módulos `factory_graph_*` | Ensamblaje LangGraph |
| `playground_chat.py` | `admin_domains/playground/router.py` | Re-export |

---

## Day 1 smoke

### Camino único (recomendado)

```bash
uv run duckops up
```

Criterio de éxito: prerequisitos OK, wizard (si aplica), migrate, PM2 stack online, `doctor --smoke` 2xx, admin en `:3001`, login → **Playground**.

### Camino granular (debug)

```bash
uv run duckops doctor
uv run duckops init
uv run duckclaw-migrate --verify-only
uv run duckops serve --gateway --pm2 --stack
uv run duckops doctor --smoke
```

Criterio de éxito:

1. `doctor` — Redis OK (o hint docker); migraciones OK si hay DB; admin key no placeholder; seed email/password válidos.
2. `init` — `.env` materializado; paso Consola admin completado; PM2 ecosystems en `config/`.
3. `migrate --verify-only` — `OK: <path>`.
4. `serve --gateway --pm2 --stack` — Gateway y DB-Writer `online`, health OK (o mensaje de espera).
5. `doctor --smoke` — HTTP 2xx en `/health`.

Consola admin: integrada en `duckops up` (menú TUI/web); manual: `cd apps/duckclaw-admin && pnpm dev`.

---

## Comando `duckops doctor` (slice actual)

Diagnóstico de solo lectura implementado en `packages/duckops/duckops/commands/doctor.py`:

- Redis (`resolve_redis_url` + ping)
- Integridad schema (`verify_schema_integrity` si hay ruta hub)
- `DUCKCLAW_ADMIN_API_KEY` (presente y no placeholder)
- Seed login (`DUCKCLAW_ADMIN_EMAIL` + password ≥ 8)
- Puerto gateway (`resolve_gateway_port` + escucha local)

Exit code `1` si fallan checks críticos (Redis o schema cuando hay DB configurada).

Complementa `duckclaw-healthcheck` (infra Redis + probe HTTP opcional) con foco en **onboarding dev**.

### Policies framework y catalog sync (post slice)

`duckops doctor` y `duckops up` (tras smoke) evalúan las cuatro keys de `FRAMEWORK_PROMPT_POLICY_REQUIREMENTS`. Si faltan filas activas en `main.prompt_policy_registry` pero existe fallback en código (capa 0), la fila **Policies framework** queda en warning y **Policies airbag** indica degradación — el stack arranca, pero conviene ejecutar `duckclaw-migrate` (migración 021) o `POST /prompt-policies/restore-framework` en admin. Con `duckops up --strict`, keys críticas sin airbag hacen fallar el comando.

Para alinear `system_prompt/<worker>` del catálogo con los snapshots en DuckDB (sin editar policies framework), el gateway expone `POST /prompt-policies/sync-catalog` → comando tipado `sync_catalog_prompts` vía db-writer. Útil tras importar templates o cambiar `files_snapshot` fuera del editor de policies. Ver [`FRAMEWORK_POLICY_PACK.md`](FRAMEWORK_POLICY_PACK.md) y `duckclaw.catalog_prompt_sync`.

---

## Fase 2 — trabajo pendiente

1. ~~**Admin bootstrap en `duckops init`:** paso TUI obligatorio email/password (o API key) antes de Review final.~~ **Hecho (slice 2026-06-17).**
2. ~~**`duckops serve` unificado:** subcomando o flag que encadene gateway + db-writer + verificación Redis (hoy: `serve --gateway --pm2 --stack`).~~ **Hecho (slice 2026-06-17).**
3. ~~**Smoke:** `duckops doctor --smoke` y alias `duckops smoke`.~~ **Hecho (slice 2026-06-17).**
4. ~~**Post-migrate housekeeping:** `duckops up` materializa policies framework y sync `system_prompt` del catálogo sin paso manual en admin.~~ **Hecho (2026-07-11).**
5. ~~**Doctor onboarding:** filas LLM bootstrap, primer agente (wizard), integraciones opcionales.~~ **Hecho (2026-07-11).** Sin agente semilla automático — el dev crea el suyo en Plantillas.
6. **Retirar `DUCKCLAW_BOT_MODE=echo`** del wizard clásico cuando se confirme que ningún runtime lo lee (hoy solo lo escribe `duckclaw_setup_wizard.py`).
7. **Documentar Sovereign** en spec propia (`SOVEREIGN_WIZARD_V2.md` referenciada en wizard legacy) si no existe en `docs/specs/`.
8. **Plug-and-play real:** build C++ db-writer, MLX opcional, Telegram opcional para smoke, `npm run dev` admin manual, migraciones en hub preexistente sin schema admin.
9. **Smoke login admin** + primer turno Playground (e2e).

---

## Estado actual (post slice fase 2)

| Área | Implementado | Aún manual / bloqueante |
|------|------------|-------------------------|
| Admin bootstrap | Paso TUI Sovereign + `ensure_admin_env_merged` en `--classic` | Re-init no actualiza password si ya hay filas en DuckDB |
| `duckops serve` | `--stack` (default) arranca DB-Writer + ping Redis | PM2 y ecosystems deben existir tras `init` |
| Smoke | `doctor --smoke`, `duckops smoke` | No prueba login admin ni consola Next.js |
| Redis | Doctor falla si no hay ping | Obligatorio para gateway en runtime |
| DB-Writer | PM2 `DuckClaw-DB-Writer` | Requiere binario compilado / ecosystem generado |
| Consola admin | `.env.local` sincronizado | `cd apps/duckclaw-admin && pnpm install && pnpm dev` |
| Telegram / MLX | Opcionales en init | No cubiertos por smoke |

---

## Aceptación de esta slice

- [ ] Spec presente en `docs/specs/features/platform/PLUG_AND_PLAY_ONBOARDING.md`
- [ ] `docs/GETTING_STARTED.md` enlazado desde `docs/README.md`
- [ ] `uv run duckops doctor` disponible
- [ ] Fachadas muertas `graphs/adapters/*` y `runtime/telegram_bot.py` eliminadas sin imports rotos
- [ ] `uv run pytest tests/test_forge_legacy_cleanup.py tests/test_package_reorg_contracts.py -q` verde
