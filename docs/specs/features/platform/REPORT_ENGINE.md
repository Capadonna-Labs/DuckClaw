# Report Engine v1 — informes por plantilla (transversal)

## Objetivo

Motor DB-first para que **cualquier usuario N** construya informes Office a partir de **su** plantilla Word, con secciones dinámicas, estado persistente y tools de agente. Complementa `document_toolbox` (primitivas) y no reemplaza `custom_reports` (HTML dashboards).

## Entidades

### `admin_report_templates`
- `template_id`, `tenant_id`, `owner_email`
- `name`, `template_uri` (`.docx` en vault)
- `section_schema_json` — `[{ "id", "label", "required" }]`
- `analyzer_mode`: `jinja` | `headings` | `mixed`
- `visibility`: `private` | `tenant`

### `admin_report_instances`
- `instance_id`, `template_id`, `tenant_id`, `owner_email`
- `project_id` (opcional, alinea RAG)
- `title`, `period_key` (ej. `2026-06`, `Q1-2026`)
- `state_json` — `{ "section_id": { "status", "content", "updated_at" } }`
- `status`: `draft` | `ready` | `archived`
- `preview_html`, `rendered_docx_uri`, `conversation_id`

## Autorización

- **Plantilla:** owner o `visibility=tenant` (mismo `tenant_id`)
- **Instancia:** `owner_email` o miembro del `project_id`
- Escrituras vía `command_type` + db-writer (ACID)

## Tools (baseline documentos / perfil reports)

| Tool | Acción |
|------|--------|
| `list_report_templates` | Plantillas visibles para el tenant/actor |
| `register_report_template` | Analiza `.docx` en vault y registra plantilla |
| `create_report_instance` | Nueva instancia desde plantilla |
| `get_report_status` | Secciones, faltantes, % completo |
| `patch_report_section` | Añadir/reemplazar contenido de una sección |
| `render_report_instance` | Genera DOCX (+ preview HTML) |

## Flujo agente (cualquier N)

1. Usuario sube plantilla Word al vault (Jinja `{{ seccion_x }}` o títulos Heading 1).
2. `register_report_template("plantillas/informe.docx", "Informe mensual")`
3. `create_report_instance(template_id, title, period_key, project_id)`
4. Usuario: «agrega esto a obligaciones_1» → `patch_report_section(instance_id, "obligaciones_1", content, mode=append)`
5. `get_report_status` → «faltan: conclusiones, anexos»
6. `render_report_instance` → DOCX en vault; `convert_document` → PDF si hace falta

## Ofimática (carriles)

| Formato | Ingress (MarkItDown) | Authoría | Entrega |
|---------|---------------------|----------|---------|
| Word `.docx` | `extract_document_text` | `render_docx_template`, report engine | `convert_document` |
| Excel `.xlsx` | `extract_document_text` | v2: `openpyxl` lane | v2 |
| PowerPoint `.pptx` | `extract_document_text` | v2: `python-pptx` lane | v2 |
| PDF | extract + convert | — | `convert_document` |

## Relación con `custom_reports`

- `custom_reports`: HTML vivo, dashboards, chat-id legacy.
- Report Engine: estado estructurado + Word. Preview HTML de instancia puede publicarse a iframe en fase 2.

## Dependencias

- `uv sync --extra document-toolbox`
- `pandoc` en host para PDF
