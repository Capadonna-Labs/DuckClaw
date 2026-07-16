# Productividad — bandeja de artefactos (design v1)

Fecha: 2026-07-15

## Objetivo

`/productividad` es la bandeja unificada de entregables del agente: informes Word, dashboards, archivos de sandbox promovidos a storage local, y salidas al vault cuando el usuario lo pide.

## Lanes

| Lane | Persistencia | Origen |
|------|--------------|--------|
| `storage` | `storage/artifacts/{tenant}/…` (repo, gitignored) | Copia al cerrar run sandbox; otros writers locales |
| `report` | DuckDB `admin_report_instances` | Report Engine |
| `vault` | Bajo `DUCKCLAW_KNOWLEDGE_OUTPUT_ROOTS` | `write_output` / convert / render / promote / index desde Explorer |

Sandbox scratch (`output/sandbox/`) **mantiene TTL**. Al registrar un run se **copia** a `storage/` y se indexa; el TTL no borra el índice storage.

## Identidad

`artifact_id`. Índice: `admin_productivity_artifacts`.

## API

- `GET /productivity/artifacts` — lista unificada
- `DELETE /productivity/artifacts/{id}` — soft-delete (+ unlink si storage)
- `POST /productivity/artifacts/{id}/promote-to-vault` — copia storage → OUTPUT (`Productividad/`)
- `GET /productivity/vault/browse` — Finder de OUTPUT_ROOTS
- `POST /productivity/vault/index` — indexa un path del vault en la bandeja

## UI

- Tab **Artefactos** (default): subvistas **Bandeja** | **Explorer vault**
- Storage: botón promover (upload icon) + eliminar
- Vault Explorer: navegar OUTPUT e **Indexar** archivo

## Fuera de alcance

- Indexar storage en RAG
- Borrar bytes del vault desde la UI (solo soft-delete del índice)
