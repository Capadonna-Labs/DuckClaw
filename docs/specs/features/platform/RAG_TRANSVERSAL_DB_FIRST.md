# RAG Transversal DB-First

## Objetivo

Implementar una capa RAG transversal para proyectos y agentes DuckClaw. AWS, ciberseguridad, finanzas o cualquier carpeta documental son fuentes de conocimiento, no implementaciones separadas.

## Principios

- DuckDB es source of truth para fuentes, documentos, chunks, scopes y auditoría.
- El índice vectorial es derivado y reconstruible.
- El Gateway no escribe DuckDB directamente; toda mutación pasa por comandos tipados y DB-Writer.
- `main.admin_worker_contexts` queda para contexto Markdown corto y curado.
- `main.semantic_memory` queda para memoria conversacional/manual existente.
- El retrieval se consume por interfaz, para permitir migrar a Qdrant, pgvector, Pinecone o Weaviate sin cambiar UI ni modelo de dominio.

## Modelo De Datos

- `main.admin_knowledge_sources`: fuente lógica importada. Contiene `tenant_id`, `project_id`, `worker_uid`, `source_kind`, `source_uri`, `status`, `embedding_model`, `metadata_json`.
- `main.admin_knowledge_documents`: documento normalizado por fuente. Contiene path relativo, título, MIME, checksum e idempotencia por `source_id + relative_path`.
- `main.admin_knowledge_chunks`: unidades recuperables. Contiene texto, índices, offsets, `embedding FLOAT[384]`, `embedding_status`, `embedding_model`, metadata y estado activo.

## Retrieval

Primera implementación:

- Vector search con DuckDB VSS/HNSW cuando embeddings están `READY`.
- Lexical fallback sobre texto cuando no hay VSS o embeddings.
- Filtros obligatorios por `tenant_id`, y opcionales por `project_id`, `worker_uid`, `source_id`.
- Resultado con citas: `source_id`, `document_id`, `relative_path`, `chunk_index`, `score`, `text`.

## Ingesta Admin

La consola Admin soporta dos flujos:

- **Subir archivos desde el navegador:** flujo principal para el usuario. Usa selector de archivos o drag/drop, envía `multipart/form-data` al BFF y el Gateway normaliza documentos/chunks sin depender de rutas locales del browser.
- **Importar ruta del servidor:** flujo avanzado para carpetas grandes ya disponibles en el Mac mini/VPS. La ruta debe estar bajo `DUCKCLAW_KNOWLEDGE_ALLOWED_ROOTS`.

Ambos flujos deben pedir scope explícito: proyecto obligatorio cuando se gestione desde `/knowledge`, y agente opcional para limitar retrieval a un worker.

Evolución planificada:

- DuckDB FTS/BM25.
- RRF para fusionar vector + BM25.
- Reranking opcional por cross-encoder.
- GraphRAG adaptativo solo para preguntas multi-hop.

## Escalabilidad

- DuckDB VSS es viable para RAG local/private y datasets medianos.
- El índice HNSW debe caber en RAM; por eso se filtra por tenant/proyecto/fuente antes de rankear.
- Para SaaS grande, el `KnowledgeRetriever` debe poder cambiar de backend manteniendo DuckDB como control plane.
- Benchmarks obligatorios antes de prometer escala: `10k`, `100k`, `1M` chunks, con p50/p95 y recall@k.

## Seguridad

- Prohibido importar rutas arbitrarias sin validación.
- Bloquear path traversal, archivos ocultos y nombres con secretos evidentes.
- Mantener Habeas Data: soft-delete primero, purge/reindex posterior.
- No exponer contenido de otro tenant/proyecto/agente.

## Criterios De Aceptación

- Migraciones crean tablas knowledge y son idempotentes.
- Comandos tipados crean/actualizan fuentes, documentos, chunks y soft-delete de fuentes.
- Ingesta chunkifica documentos Markdown/texto/JSON/CSV de forma determinística.
- Search devuelve chunks filtrados por scope y funciona con fallback lexical.
- Admin expone una sección “RAG” bajo “Agentes” con selección proyecto/agente, carga de archivos y ruta servidor avanzada.
- El detalle de proyecto muestra resumen de fuentes RAG y enlaza al gestor RAG filtrado por proyecto.
- La implementación no contiene lógica específica de AWS.
