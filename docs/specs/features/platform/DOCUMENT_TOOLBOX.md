# Document Toolbox v1 — caja transversal de documentos

## Objetivo

Un solo módulo (`duckclaw.document_toolbox`) para toda la plataforma: **ingesta/extracción** (máquina lee), **autoría Word seria** (humano recibe) y **PDF desde ese Word** (LibreOffice), sin conversión genérica markdown→Office (pandoc retirado).

## Carriles (lanes)

| Carril | Motor | Uso |
|--------|-------|-----|
| **ingest_native** | lectura directa UTF-8 | `.md`, `.txt`, `.json`, `.csv` en sync/RAG |
| **extract** | **MarkItDown** | PDF/Office/HTML → **texto plano / md** (ingesta + tool `extract_document_text`) |
| **author_text** | `write_output_document` | Notas/código UTF-8 en OUTPUT vault — **no** es entregable Word |
| **author_word** | **Report Engine** (`docxtpl`) + `render_docx_template` (plantilla built-in) | Word fiel a plantilla del usuario N |
| **export_pdf** | **LibreOffice headless** + `export_docx_to_pdf` | `.docx` ya generado → `.pdf` junto al Word |

**Regla:** MarkItDown **nunca** genera PDF/Word. Solo extrae texto para la IA.  
**Regla:** El Word serio **nunca** se reconstruye desde markdown. Sale de plantilla + placeholders `{{…}}`.  
**Regla:** El PDF serio **sale del Word**, no de markdown→motor.

### Sin pandoc (producto)

`convert_document` / pandoc **retirados** del runtime y del código de producto.  
Manifests antiguos que listen `convert_document` se tratan como skill retirada (no es gap).

### Word → PDF

1. `render_report_instance` (o `render_docx_template`) → `.docx` en `OUTPUT_ROOTS`
2. `export_docx_to_pdf(instance_id=…)` o `relative_path` / `docx_path` bajo OUTPUT/ALLOWED
3. Host necesita LibreOffice (`soffice`): `brew install --cask libreoffice`

### Autoría UTF-8 (`write_output_document`)

- Solo sufijos en `AUTHOR_TEXT_SUFFIXES` (`.md`, `.txt`, `.json`, `.csv`, `.yaml`, `.py`, `.html`, …).
- Rechaza binarios ofimáticos (`.docx`, `.pdf`, `.xlsx`, …): usar Report Engine / `render_docx_template` + `export_docx_to_pdf`.

## Tools baseline (framework)

- `extract_document_text` — binario bajo raíces permitidas → texto (MarkItDown)
- `write_output_document` — texto UTF-8 en vault de salida
- `render_docx_template` — plantilla built-in docxtpl (sin plantilla de usuario)
- `export_docx_to_pdf` — Word → PDF (LibreOffice); siempre en harness
- Report Engine: `list/register/create/patch/status/render_report_*`, `list_report_instances`, `create_blank_document`, `patch_report_image`, `generate_report_docx_from_markdown`
- RAG: `list/read/search_project_knowledge`, `get_project_context`

## Plantillas corporativas

- Seed: `packages/shared/src/duckclaw/seeds/document_templates/`
- Manifiesto en `document_toolbox_v1.json`
- Plantilla built-in: `corporate_report` (título, subtítulo, autor, cuerpo, tenant)
- Plantillas de usuario N: vault → `register_report_template` (Report Engine)

## Variables de entorno

- `DUCKCLAW_KNOWLEDGE_ALLOWED_ROOTS` — lectura/ingesta
- `DUCKCLAW_KNOWLEDGE_OUTPUT_ROOTS` — escritura agente
- Dependencias Python: `uv sync` (markitdown, docxtpl, python-docx en `duckclaw-shared`)
- Host: LibreOffice para PDF (`export_docx_to_pdf`)

## Flujos típicos (N usuarios)

1. **IA lee un PDF/Word ajeno:** `extract_document_text` / sync MarkItDown → RAG
2. **Humano recibe informe serio:** register plantilla → create → patch por `{{campo}}` → `render_report_instance` → opcional `export_docx_to_pdf`
3. **Notas internas:** `write_output_document` (markdown); no sustituye el Word final
