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

### Analyzer v2 — tablas

- Detecta placeholders `{{campo.2}}` y `{{ campo.2 }}` (espacios opcionales).
- Recorre `doc.tables[]` y anota `table_index`, `row_index`, `col_index`, `in_table` por campo.
- `analyzer_mode` en análisis: `jinja_tables` cuando hay campos en celdas (persistido como `jinja`).
- Devuelve `tables[]`, `editable_field_count`, `fields_in_tables`.

### Carril obligatorio (agente) — transversal

- **Criterio único:** el actor tiene ≥1 plantilla Report Engine visible → `convert_document` / `render_docx_template` → `.docx` **bloqueado** (fail-closed si no hay hub).
- Escape explícito: `allow_ad_hoc_docx=true`.
- `generate_report_docx_from_markdown`: solo plantillas de **un** campo; multi-campo → error con `section_ids`.
- `render_report_instance`: exige secciones `required` con contenido; escanea `{{…}}` residuales; `force=true` para borrador.
- `patch_report_section`: devuelve `progress` + `valid_section_ids` si el id es inválido.
- Placeholders Jinja nuevos se marcan `required=true`.
- `write_output_document` libre para texto UTF-8; no es el Word final de plantilla.

### Plantillas con tablas Word

- Cada **celda/hueco** de la plantilla debe tener su propio placeholder Jinja: `{{ seccion.1 }}`, `{{ cuerpo }}`, …
- El render (docxtpl) **conserva** tablas y estilos; solo rellena los placeholders con texto plano.
- **Prohibido** en `patch_report_section`: pegar tablas markdown completas en una sola sección — rompe el layout.
- Saltos de párrafo (`\n\n`) dentro de un placeholder en celda pueden escapar de la tabla; el motor colapsa a `\n` suave.
- Tablas markdown en el contenido se convierten a filas tabuladas (TSV), no a tabla Word nueva.
- Para negrita inline use `**texto**` en la sección (RichText); multilínea simple = texto con `\n`.

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
