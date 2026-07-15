# Report Engine v1 — documentos por plantilla (transversal)

## Objetivo

Motor DB-first para que **cualquier persona N** construya documentos Office a partir de **sus** plantillas (Word hoy; Excel/PPT v2). El nicho vive en la plantilla y en el prompt, **no** en campos de producto tipo «periodo mensual».

Complementa `document_toolbox` (extract/author/convert) y no reemplaza `custom_reports` (dashboards HTML).

## Modelo mental (flujo canónico)

```
Plantilla (.docx + schema)  →  Instancia (draft)  →  Secciones (patch)  →  Render (docx)
```

| Paso | Qué pide el usuario / UI | Qué hace el sistema |
|------|--------------------------|---------------------|
| 1. Plantilla | Elegir .docx del vault o plantilla ya registrada | Analyzer → `section_schema` |
| 2. Nombre | Solo **título** del documento | `create_report_instance` → `instance_id` |
| 3. Secciones | Contenido (chat o tools) | `patch_report_section` |
| 4. Render | «Genera el Word» | `render_report_instance` → `OUTPUT_ROOTS/reports/{id}.docx` |

**Identidad:** `instance_id` (UUID corto). No hay identidad de negocio obligatoria aparte.

**Prohibido en create (producto):** pedir periodo, mes, campaña, edición, etc. Si el usuario quiere «marzo 2026» en el documento, va en el **título** o en una **sección** de la plantilla (`{{periodo}}`, etc.), no en un campo transversal del motor.

## Superficies

| Superficie | Uso |
|------------|-----|
| **Chat (NL)** | «Rellena / exporta con mi plantilla» — tools; sin jerga de tools |
| **Admin → Informes Word** | Lista instancias, wizard (plantilla + título), preview, Completar en Chat |
| **Tools** | skill `report_engine` |

## Entidades

### `admin_report_templates`
- `template_id`, `tenant_id`, `owner_email`
- `name`, `template_uri`
- `section_schema_json` — `[{ "id", "label", "required" }]` (ids dotted `a.b`)
- `analyzer_mode`: `jinja` | `headings` | `mixed`
- `visibility`: `private` | `tenant`

### `admin_report_instances`
- `instance_id` — **PK de producto**
- `template_id`, `tenant_id`, `owner_email`, `project_id` (opc.)
- `title` — nombre humano
- `state_json` — secciones
- `preview_html`, `rendered_docx_uri`, `status`
- `period_key` — **columna legacy ignorada**; no se expone en create UI; tools no deben pedirla; siempre `''` en flux nuevo

No hay soft-unique por periodo. Pueden coexistir N instancias activas de la misma plantilla.

## Auth

- Upsert plantilla: solo owner.
- Crear instancia: plantilla visible (`owner` o `visibility=tenant`).
- Render: re-valida `template_uri`; escribe en `OUTPUT_ROOTS/reports/{instance_id}.docx`.

## Analyzer / Tools

Sin cambios de contrato útil: register → create(title) → patch → status → render.

Baseline: skill `report_engine` en `framework_tool_pack_v1` profile `general`.

## Admin API

- `GET/POST` templates + register
- `POST /report-instances` body: `{ template_id, title, project_id? }` — **sin** `period_key` en contrato de producto
- `GET` instances / preview
- `DELETE` instance | template (soft)

## Criterios de aceptación

- Create Admin: solo plantilla + título.
- Chat policy: no preguntar periodo; crear instancia con título derivado del pedido del usuario.
- Dos usuarios no se pisan plantillas.
- Analizer sin markers → fail-loud.
- `period_key` no aparece en labels UI de create.
