# CRM PQRSD — persistencia en DuckDB (GovTech)

## Objetivo

Persistir tickets y respuestas oficiales del CRM Next (`external/retoPWRSomegahack`) en el archivo DuckDB de bóveda del usuario (misma variable que el worker **PQRSD-Assistant**: `DUCKCLAW_PQRSD_ASSISTANT_DB_PATH`), para que la bandeja y el detalle lean datos reutilizables entre sesiones y las escrituras de negocio respeten el **singleton writer** (cola Redis + db-writer) cuando aplica la mutación vía API Gateway.

## Alcance

- Esquema dedicado **`pqrsd_crm`** (no escribe en `pqrsd_assistant.orientation_notes` del template Forge).
- Tabla **`pqrsd_crm.tickets`** con columnas alineadas al tipo frontend `Ticket` (camelCase en UI; snake_case en SQL).
- **Lecturas**: Route Handlers Next llaman **`POST /api/v1/db/read`** en el API Gateway (DuckDB `read_only` en el proceso Python), con `db_path` = `CRM_DUCKDB_PATH` y `user_id` de bóveda (evita abrir DuckDB en modo escritura desde el proceso Next).
- **Escrituras** (respuesta oficial, cambio de estado Kanban): `POST` al API Gateway **`/api/v1/db/write`** con `query` + `params`, mismos `user_id` / `db_path`.
- **Bootstrap** (DDL + seed inicial desde `TICKETS_MOCK`): opcional vía `CRM_AUTO_BOOTSTRAP=true` en desarrollo; en producción se recomienda aplicar DDL con cliente DuckDB y seed controlado.

## Esquema SQL

```sql
CREATE SCHEMA IF NOT EXISTS pqrsd_crm;

CREATE TABLE IF NOT EXISTS pqrsd_crm.tickets (
  id_ticket VARCHAR PRIMARY KEY,
  tipo_solicitud VARCHAR NOT NULL,
  id_secretaria VARCHAR NOT NULL,
  fecha_creacion TIMESTAMP NOT NULL,
  fecha_limite TIMESTAMP NOT NULL,
  estado VARCHAR NOT NULL,
  contenido_raw VARCHAR NOT NULL,
  resumen_ia VARCHAR,
  respuesta_sugerida VARCHAR,
  canal_origen VARCHAR NOT NULL,
  nombre_ciudadano VARCHAR NOT NULL,
  updated_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_pqrsd_crm_tickets_sec_est
  ON pqrsd_crm.tickets (id_secretaria, estado);
```

## Estados

Valores alineados a `TicketEstado` en TypeScript: `Pendiente`, `En_Revision`, `Resuelto`.

## Contrato de API Next (CRM)

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/crm/tickets` | Query `idSecretaria`, filtros opcionales; devuelve JSON `{ data: Ticket[] }`. |
| GET | `/api/crm/tickets/[id]` | Detalle por `id_ticket` + comprobación `idSecretaria`. |
| POST | `/api/crm/tickets/[id]/respond` | Body `{ respuestaFinal, idSecretaria }`; encola `UPDATE` vía Gateway (o muta mock). |
| PATCH | `/api/crm/tickets/[id]/state` | Body `{ idSecretaria, estado }`; Kanban — encola `UPDATE` de estado. |

## Variables de entorno (Next)

| Variable | Uso |
|----------|-----|
| `CRM_DUCKDB_PATH` | Ruta absoluta al `.duckdb` (p. ej. `db/private/<vault_user_id>/pqrsd-assistantdb1.duckdb`). Si no está definida, el CRM usa datos mock en memoria. |
| `DUCKCLAW_GATEWAY_URL` | Base URL del API Gateway (lecturas `db/read` y escrituras `db/write`). |
| `CRM_VAULT_USER_ID` | `user_id` para `db/read` y `db/write` (debe coincidir con carpeta `db/private/<id>/`). |
| `CRM_TENANT_ID` | Opcional; default `PQRS` o `default` según despliegue. |
| `CRM_AUTO_BOOTSTRAP` | `true` solo en dev: crea esquema/tabla y si está vacía inserta seed desde mock. |

## Notas

- El nombre del archivo puede ser `pqrsd-assistantdb1.duckdb` o `pqrsd_assistant.duckdb`; lo relevante es la variable de entorno que apunte al archivo correcto.
- El worker PQRSD-Assistant permanece **read_only** en Forge; el CRM no depende de `allowed_tables` para estas escrituras.

## Referencias

- [`POST /api/v1/db/write`](services/api-gateway/main.py), [`POST /api/v1/db/read`](services/api-gateway/main.py)
- [`CRM resumen ejecutivo Gateway.md`](CRM%20resumen%20ejecutivo%20Gateway.md) (panel IA; persistencia de resumen sigue siendo mejora futura opcional)
