# Block C — Obsidian / Vault lectura y salida

## Objetivo

Sincronizar carpetas Obsidian (vault) ya presentes en el host hacia RAG con re-import incremental, y permitir que agentes escriban markdown de vuelta a rutas controladas.

## Variables de entorno

- `DUCKCLAW_KNOWLEDGE_ALLOWED_ROOTS`: rutas separadas por `:` (macOS/Linux) o `;` (Windows) bajo las cuales se permite **ingesta** (lectura para RAG). Opcionalmente incluye `DUCKCLAW_REPO_ROOT`.
- `DUCKCLAW_KNOWLEDGE_OUTPUT_ROOTS`: rutas donde el agente puede **escribir** markdown. Si no está definido, cae en `ALLOWED_ROOTS`.

## Sync incremental

- Solo fuentes `source_kind=folder` con `source_uri` local bajo raíces permitidas.
- Por cada archivo admitido: comparar `checksum` con `admin_knowledge_documents`.
- Sin cambio → omitir (no re-chunkificar).
- Cambiado o nuevo → upsert documento + chunks.
- Eliminado del disco → soft-delete documento y chunks.
- Metadata de fuente: `last_sync_at`, `sync_stats` (scanned, upserted, skipped, removed, chunks).

## Skill write_output_document

- Escribe `.md` / `.txt` bajo `OUTPUT_ROOTS` con las mismas reglas anti-traversal que ingesta.
- No escribe fuera de raíces configuradas.
- Respuesta JSON: `relative_path`, `byte_size`, `checksum`.

## Sync automático

- **Tras `write_output_document`:** re-indexa el archivo en fuentes carpeta del proyecto (si `DUCKCLAW_KNOWLEDGE_AUTO_SYNC` ≠ off).
- **Polling gateway:** cada `DUCKCLAW_KNOWLEDGE_AUTO_SYNC_POLL_SEC` (default 15s) detecta cambios en vault/Obsidian vía fingerprint mtime y sync incremental.
- Desactivar: `DUCKCLAW_KNOWLEDGE_AUTO_SYNC=false`.

## Admin

- Botón «Sincronizar» en fuentes tipo carpeta/ruta servidor.
- Hint de `ALLOWED_ROOTS` / `OUTPUT_ROOTS` en sección ruta avanzada.

## Criterios de aceptación

- Re-sync no re-indexa archivos sin cambios.
- Archivos nuevos/modificados/borrados se reflejan en RAG.
- `write_output_document` rechaza rutas fuera de raíces y nombres secretos.
- Tests unitarios para plan de sync y validación de rutas.
