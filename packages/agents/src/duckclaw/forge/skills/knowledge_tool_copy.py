"""Copy y contratos SOTA para tools (Anthropic/OpenAI tool-design 2025–26).

Cada description debe cubrir: qué hace · cuándo usarla · qué NO hacer · qué devuelve.
Prefijos de lane evitan confusión entre RAG, disco, DuckDB y Report Engine.
"""

from __future__ import annotations

# Prefijos estables (namespacing ligero vía texto; nombres de tool se mantienen).
RAG_PREFIX = "[RAG indexado]"
DISK_PREFIX = "[Disco / raíces permitidas]"
DUCKDB_PREFIX = "[DuckDB]"
DOCS_PREFIX = "[OUTPUT / docs]"
REPORT_PREFIX = "[Report Engine]"
RESEARCH_PREFIX = "[Web / offline]"

GET_PROJECT_CONTEXT_DESCRIPTION = (
    f"{RAG_PREFIX} Qué hace: resume el alcance activo (fuentes indexadas + raíces de disco). "
    "Cuándo: al inicio si preguntan qué conocimiento/carpetas hay. "
    "NO inventes docs: si solo están en disk_allowed_roots, dilo. "
    "Devuelve JSON con sources_preview, disk_allowed_roots, lanes, warnings. "
    "Siguiente paso disco: list_disk_folder / read_disk_text / extract_document_text. "
    "Siguiente paso RAG: search_project_knowledge."
)

SEARCH_PROJECT_KNOWLEDGE_DESCRIPTION = (
    f"{RAG_PREFIX} Qué hace: búsqueda semántica en documentos YA indexados (En el chat). "
    "Cuándo: el usuario pregunta por contenido de MacMiniVault u otra fuente ready. "
    "NO listar filesystem ni código no indexado; NO Wikipedia (kiwix_search); NO SQL (read_sql). "
    "Si 0 hits: get_project_context (puede estar solo en disco). "
    "Devuelve JSON {{chunks: [relative_path, excerpt, score]}}."
)

LIST_PROJECT_KNOWLEDGE_DESCRIPTION = (
    f"{RAG_PREFIX} Qué hace: inventario de documentos indexados (relative_path). "
    "Cuándo: listar qué hay en el RAG del alcance. "
    "NO listar disco: usa list_disk_roots / list_disk_folder. "
    "Devuelve JSON con document_count y documents[]."
)

READ_PROJECT_KNOWLEDGE_DESCRIPTION = (
    f"{RAG_PREFIX} Qué hace: lee texto indexado por relative_path "
    "(ej. Aws Knowledge/012_IAM_Usuarios.md). "
    "Cuándo: detalle de un doc ya en el chat. "
    "NO si el archivo solo está en disco → read_disk_text o extract_document_text. "
    "Devuelve JSON {{relative_path, content}} o error."
)

EXTRACT_DOCUMENT_TEXT_DESCRIPTION = (
    f"{DISK_PREFIX} Qué hace: extrae texto de PDF/Word/PPT/HTML (MarkItDown) bajo raíces permitidas. "
    "Cuándo: binarios o Office en disco con path conocido. "
    "NO búsqueda semántica; NO listar carpetas (list_disk_folder); "
    "para .md/.txt/.py usa read_disk_text. "
    "Devuelve JSON {{path, text, char_count}}."
)

LIST_DISK_ROOTS_DESCRIPTION = (
    f"{DISK_PREFIX} Qué hace: lista raíces ALLOWED_ROOTS / mirror (disco, no RAG). "
    "Cuándo: 'qué carpetas puedo leer en disco' sin indexar. "
    "NO implica que estén en el chat; in_chat solo si también hay fuente RAG. "
    "Devuelve JSON {{roots: [label, path, exists]}}. "
    "Para entrar en una carpeta: list_disk_folder(path)."
)

LIST_DISK_FOLDER_DESCRIPTION = (
    f"{DISK_PREFIX} Qué hace: lista subcarpetas/archivos bajo una ruta permitida. "
    "Cuándo: explorar código o docs en disco (ej. /Users/.../Developer/duckclaw). "
    "NO indexa ni busca semánticamente. "
    "Parámetro path: absoluto bajo ALLOWED_ROOTS, o vacío para raíces. "
    "include_files=true para ver archivos (por defecto solo carpetas). "
    "Devuelve JSON tipo browse (entries[], path, parent_path). "
    "Leer archivo: read_disk_text o extract_document_text."
)

READ_DISK_TEXT_DESCRIPTION = (
    f"{DISK_PREFIX} Qué hace: lee texto UTF-8 de un archivo bajo raíces permitidas "
    "(.md, .txt, .py, .ts, .tsx, .json, .yaml, .toml, .css, .html, …). "
    "Cuándo: el usuario pide ver código o un archivo concreto en disco. "
    "NO para PDF/Word (extract_document_text); NO RAG (read_project_knowledge). "
    "path: absoluto o relative_path+root_hint. "
    "Devuelve JSON {{path, content, truncated}} (tope ~80k chars)."
)

READ_SQL_DESCRIPTION = (
    f"{DUCKDB_PREFIX} Qué hace: SQL solo lectura (SELECT/WITH/SHOW/DESCRIBE/EXPLAIN/PRAGMA). "
    "Cuándo: consultar tablas/datos del vault DuckDB del worker. "
    "NO informes Word (Report Engine); NO RAG (search_project_knowledge). "
    "Devuelve resultado tabular o JSON error."
)

ADMIN_SQL_DESCRIPTION = (
    f"{DUCKDB_PREFIX} Qué hace: SQL con posibles escrituras (INSERT/UPDATE/DELETE/DDL) "
    "según policy del worker / tool_surface. "
    "Cuándo: mutaciones explícitas pedidas por el usuario. "
    "NO para lecturas simples → preferir read_sql. "
    "Devuelve status/error JSON."
)

INSPECT_SCHEMA_DESCRIPTION = (
    f"{DUCKDB_PREFIX} Qué hace: lista tablas/esquemas del DuckDB del worker. "
    "Cuándo: 'qué tablas hay' / estructura SQL. "
    "NO para informe mensual/Word (Report Engine). "
    "Devuelve listado de tablas."
)

GET_DB_PATH_DESCRIPTION = (
    f"{DUCKDB_PREFIX} Qué hace: devuelve la ruta del archivo .duckdb del agente. "
    "Cuándo: preguntan el nombre/ruta de la base. "
    "NO ejecuta SQL. Devuelve string path."
)
