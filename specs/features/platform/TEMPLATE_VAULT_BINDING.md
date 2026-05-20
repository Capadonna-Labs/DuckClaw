# Template vault binding (Plantillas → DuckDB)

**Objetivo:** En runtime, una plantilla puede fijar bóveda vía `manifest.yaml` (`forge_context.vault_binding`). En la **consola admin**, la bóveda activa se elige **por conversación** (Playground / chat flotante → `PUT /playground/vault`), no en la página Workers.

---

## Contrato `forge_context.vault_binding`

```yaml
forge_context:
  vault_binding:
    scope: private          # private | shared
    vault_id: quant_traderdb1   # sin .duckdb; obligatorio si scope=private
    # path: db/shared/catalog.duckdb   # obligatorio si scope=shared (relativo al repo)
```

| Campo | Reglas |
|-------|--------|
| `scope` | `private` → `db/private/{vault_user_id}/{vault_id}.duckdb` |
| `scope` | `shared` → `path` debe estar bajo `db/shared/` (sin `..`) |
| Ausente | Comportamiento legacy (`resolve_active_vault` / hub gateway) |

---

## ACL (listado admin)

`GET /api/v1/admin/templates/{id}/vault-options?vault_user_id=` devuelve solo:

- `db/private/{vault_user_id}/**/*.duckdb`
- `db/shared/**/*.duckdb`

Default `vault_user_id`: `DUCKCLAW_OWNER_ID` o `DUCKCLAW_ADMIN_CHAT_ID`.

---

## Runtime

1. **Delegación worker:** si `WorkerSpec.forge_vault_binding` está definido, `vault_db_path` = `resolve_template_vault_path(binding, vault_user_id)` (archivo debe existir).
2. **`/vault`:** tras sesión/multiplex y antes del registry multi-bóveda, si `entry_worker_id` o `get_worker_id_for_chat` tiene binding → mostrar ruta fijada; `list|new|use|rm` rechazados con mensaje explícito.

---

## API Admin

| Método | Ruta | Body |
|--------|------|------|
| PUT | `/playground/vault` | `{ "chat_id", "vault_db_path?" }` — **UI principal** |
| GET | `/playground/config?chat_id=` | Incluye `vault`, `vault_options` |
| GET | `/templates/{id}/vault-options` | Query `vault_user_id` (API legacy / automatización) |
| GET | `/templates/{id}/vault-binding` | — |
| PUT | `/templates/{id}/vault-binding` | `{ "scope", "vault_id?", "path?" }` (manifest; sin UI Workers) |

Prioridad en playground chat: `vault_db_path` del body → meta conversación → `resolve_template_vault_path` / vault activo.

---

## Ver también

- [Multi-Vault System](../../../docs/operations/Multi-Vault-System.md)
- [DuckClaw Admin UI](DUCKCLAW_ADMIN_UI.md)
