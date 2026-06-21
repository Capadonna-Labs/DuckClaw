# Document Toolbox v1 — caja transversal de documentos

## Objetivo

Un solo módulo (`duckclaw.document_toolbox`) para toda la plataforma: ingesta, extracción, autoría y conversión de documentos, sin mezclar responsabilidades.

## Carriles (lanes)

| Carril | Motor | Uso |
|--------|-------|-----|
| **ingest_native** | lectura directa UTF-8 | `.md`, `.txt`, `.json`, `.csv` en sync/RAG |
| **extract** | **MarkItDown** | PDF/Office/HTML → **texto plano** (ingesta + tool `extract_document_text`) |
| **author** | `write_output_document`, `render_docx_template` | Crear artefactos en OUTPUT vault |
| **convert** | **pandoc** | Entregar formatos finales (`docx`, `pdf`, `html`) desde fuentes de texto |

**Regla:** MarkItDown **nunca** genera PDF/Word. Solo extrae texto. Pandoc **nunca** ingesta binarios.

## Tools baseline (framework)

- `extract_document_text` — lee binario bajo raíces permitidas → texto
- `write_output_document` — escribe texto/código en vault de salida
- `render_docx_template` — rellena plantilla corporativa DOCX (docxtpl)
- `convert_document` — pandoc: `.md`/`.html`/`.txt` → `docx`/`pdf`/`html`
- RAG existente: `list/read/search_project_knowledge`, `get_project_context`

## Plantillas corporativas

- Seed: `packages/shared/src/duckclaw/seeds/document_templates/`
- Manifiesto en `document_toolbox_v1.json`
- Plantilla built-in: `corporate_report` (título, subtítulo, autor, cuerpo, tenant)

## Variables de entorno

- `DUCKCLAW_KNOWLEDGE_ALLOWED_ROOTS` — lectura/ingesta
- `DUCKCLAW_KNOWLEDGE_OUTPUT_ROOTS` — escritura agente
- Dependencias opcionales: `uv sync --extra document-toolbox` (markitdown, docxtpl, python-docx)
- Host: `pandoc` (+ motor PDF) para conversión

## Flujos típicos

1. **Ingesta fiable:** PDF en vault → sync usa MarkItDown → chunks RAG
2. **Lectura adhoc:** `extract_document_text("contrato.pdf")` sin esperar índice
3. **Informe corporativo:** `render_docx_template("corporate_report", {...}, "informes/q1.docx")`
4. **Entrega PDF:** `write_output_document` o plantilla DOCX → `convert_document(..., "pdf")`
