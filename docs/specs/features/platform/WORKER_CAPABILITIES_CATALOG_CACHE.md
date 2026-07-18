# Worker Capabilities Catalog Cache

## Objetivo

Cache in-process en el Gateway del payload de `GET /api/v1/admin/workers/{worker_id}/capabilities`, siguiendo el mismo patrón que `manager_worker_cache` (TTL + LRU + invalidación explícita).

No es caché de UI. El admin solo consume; la fuente de verdad optimizada vive en el proceso Gateway.

## Alcance v1

- **Incluye:** payload de capabilities (skills, tools_runtime, gaps, optional flags).
- **No incluye:** `playground/config`, documentos RAG, policy de sandbox por chat, resultados de tools.

## Clave y política

- Clave: `{actor_normalized}:{worker_id_normalized}`.
- TTL por defecto: **120s** (`DUCKCLAW_WORKER_CAPABILITIES_CATALOG_CACHE_TTL_SEC`).
- Max entradas: **64** (`DUCKCLAW_WORKER_CAPABILITIES_CATALOG_CACHE_MAX_ENTRIES`).
- Enable: `DUCKCLAW_WORKER_CAPABILITIES_CATALOG_CACHE_ENABLED` (default `true`).

## Invalidación

1. `POST /api/v1/admin/gateway/release-worker-cache` — vacía graph cache **y** capabilities catalog.
2. Write handlers de workers (upsert catalog / update file manifest / upsert user-agent) — invalidan por `worker_id`.
3. Expiración TTL (docker_ok / tools_runtime pueden cambiar sin write).

## Métricas

`release-worker-cache` y health exponen `worker_capabilities_catalog_cache` (enabled, entries, max_entries, ttl_sec).

## UI

El playground **no** debe refetch capabilities al toggle sandbox. Refetch solo al cambiar `workerId` (o al invalidar servidor vía TTL/write/release).
