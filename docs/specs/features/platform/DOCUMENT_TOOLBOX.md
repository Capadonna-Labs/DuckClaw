# Document Toolbox v1 — caja transversal de documentos

## Objetivo

Un solo módulo (`duckclaw.document_toolbox`) para toda la plataforma: **ingesta/extracción** (máquina lee) y **autoría Word seria** (humano recibe), sin un tercer carril de conversión genérica (pandoc).

## Carriles (lanes)

| Carril | Motor | Uso |
|--------|-------|-----|
| **ingest_native** | lectura directa UTF-8 | `.md`, `.txt`, `.json`, `.csv` en sync/RAG |
| **extract** | **MarkItDown** | PDF/Office/HTML → **texto plano / md** (ingesta + tool `extract_document_text`) |
| **author_text** | `write_output_document` | Notas/código UTF-8 en OUTPUT vault — **no** es entregable Word |
| **author_word** | **Report Engine** (`docxtpl`) + `render_docx_template` (plantilla built-in) | Word fiel a plantilla del usuario N |

**Regla:** MarkItDown **nunca** genera PDF/Word. Solo extrae texto para la IA.  
**Regla:** El Word serio **nunca** se reconstruye desde markdown. Sale de plantilla + placeholders `{{…}}`.

### Sin pandoc (producto)

`convert_document` / pandoc **no** están en baseline ni se registran en el runtime del worker.  
Código legacy puede existir en el repo; no forma parte del path feliz multi-tenant.

Si un tenant necesita PDF, v2: export desde el `.docx` del Report Engine (LibreOffice headless u otro), no markdown→pandoc.

### Autoría UTF-8 (`write_output_document`)

- Solo sufijos en `AUTHOR_TEXT_SUFFIXES` (`.md`, `.txt`, `.json`, `.csv`, `.yaml`, `.py`, `.html`, …).
- Rechaza binarios ofimáticos (`.docx`, `.pdf`, `.xlsx`, …): usar Report Engine / `render_docx_template`.

## Tools baseline (framework)

- `extract_document_text` — binario bajo raíces permitidas → texto (MarkItDown)
- `write_output_document` — texto UTF-8 en vault de salida
- `render_docx_template` — plantilla built-in docxtpl (sin plantilla de usuario)
- Report Engine: `list/register/create/patch/status/render_report_*`
- RAG: `list/read/search_project_knowledge`, `get_project_context`

## Plantillas corporativas

- Seed: `packages/shared/src/duckclaw/seeds/document_templates/`
- Manifiesto en `document_toolbox_v1.json`
- Plantilla built-in: `corporate_report` (título, subtítulo, autor, cuerpo, tenant)
- Plantillas de usuario N: vault → `register_report_template` (Report Engine)

## Variables de entorno

- `DUCKCLAW_KNOWLEDGE_ALLOWED_ROOTS` — lectura/ingesta
- `DUCKCLAW_KNOWLEDGE_OUTPUT_ROOTS` — escritura agente
- Dependencias: `uv sync --extra document-toolbox` (markitdown, docxtpl, python-docx)

## Flujos típicos (N usuarios)

1. **IA lee un PDF/Word ajeno:** `extract_document_text` / sync MarkItDown → RAG
2. **Humano recibe informe serio:** register plantilla → create → patch por `{{campo}}` (incl. celdas de tabla) → `render_report_instance`
3. **Notas internas:** `write_output_document` (markdown); no sustituye el Word final
