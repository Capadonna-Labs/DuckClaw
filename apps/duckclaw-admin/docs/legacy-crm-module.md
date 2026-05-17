# Módulo legacy CRM PQRSD (GovTech)

## Estado actual

El árbol `apps/duckclaw-admin` se reorientó a la **consola DuckClaw Admin**. Las rutas activas están bajo `src/app/(admin)/` (overview, templates, telegram, …).

Queda código del **CRM funcionario** (bandeja PQRSD, Kanban, asistente IA en ticket) del hackathon [retoPWRSomegahack](https://github.com/ManePeqsiCoda/retoPWRSomegahack), **sin rutas App Router** que lo expongan hoy:

| Área | Ubicación | Estado |
|------|-----------|--------|
| Servicios tickets | `src/services/ticketService.ts` | Llama `/api/crm/*` (rutas API no montadas) |
| IA co-pilot | `src/hooks/useIAAssistant.ts`, `src/services/aiService.ts` | Espera `POST /api/ia/regenerar` |
| DuckDB CRM | `src/lib/crm/*` | Lectura/escritura vía gateway `db/read`, `db/write` |
| UI ticket/dashboard | `src/components/ticket/*`, `src/components/dashboard/*` | Sin páginas en `src/app/` |

Para reactivar el CRM dentro del monorepo habría que restaurar rutas `src/app/(crm)/` y `src/app/api/crm/`, `src/app/api/ia/` (o mover la UI a otra app).

Documentación de producto del piloto: [PROJECT_DOCUMENTATION.md](../PROJECT_DOCUMENTATION.md).

---

## Integración IA con DuckClaw (cuando el CRM esté activo)

El panel «Generar con IA» debe proxy al gateway:

```http
POST {DUCKCLAW_GATEWAY_URL}/api/v1/agent/PQRSD-Assistant/chat
```

Cuerpo tipo `ChatRequest`: mensaje con contexto del ticket, `tenant_id: PQRS`, `chat_id: crm-ticket-{idTicket}`.

### Variables (CRM)

| Variable | Uso |
|----------|-----|
| `DUCKCLAW_GATEWAY_URL` | Base del gateway (servidor) |
| `NEXT_PUBLIC_IA_HABILITADA` | `true` para mostrar panel IA |
| `DUCKCLAW_GATEWAY_USER_ID_OVERRIDE` | Solo dev: `user_id` en whitelist PQRS |
| `CRM_DUCKDB_PATH` | Bóveda DuckDB (`pqrsd_crm.tickets`) |
| `CRM_VAULT_USER_ID` | `user_id` para `db/read` y `db/write` |
| `OPENROUTER_API_KEY` | Fallback si `CRM_IA_OPENROUTER_FALLBACK=true` |

Spec persistencia: [`specs/features/finanz/CRM_PQRSD_DUCKDB_PERSISTENCE.md`](../../../specs/features/finanz/CRM_PQRSD_DUCKDB_PERSISTENCE.md).

### Riesgo de dominio

El worker **PQRSD-Assistant** está pensado para orientación ciudadana en Telegram. El CRM lo usa para **redacción institucional**. Mitigación histórica: prefijo `[Modo: redacción de respuesta institucional CRM…]` en el mensaje al gateway. A largo plazo: worker dedicado en Forge + spec SDD.

### Prueba del gateway (sin CRM UI)

```bash
curl -sS -X POST 'http://127.0.0.1:8000/api/v1/agent/PQRSD-Assistant/chat' \
  -H 'Content-Type: application/json' \
  -H 'X-Tenant-Id: PQRS' \
  -d '{
    "message": "Orientación breve para radicar PQRSD.",
    "chat_id": "crm-test-local",
    "user_id": "TU_USER_WHITELIST",
    "username": "Test",
    "tenant_id": "PQRS",
    "chat_type": "private"
  }'
```

### Bootstrap DuckDB CRM

Desde raíz del monorepo:

```bash
pnpm crm:bootstrap-db
# equivalente: uv run python scripts/bootstrap_dbs.py
```

Crea esquema `pqrsd_crm.tickets` en la bóveda configurada.

---

## Archivo histórico

La guía anterior vivía en [GATEWAY_IA_INTEGRATION.md](GATEWAY_IA_INTEGRATION.md); el contenido operativo se consolidó aquí.
