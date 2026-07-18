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
- Render: re-valida `template_uri`; escribe el `.docx` final directo en `OUTPUT_ROOTS/` con nombre humano estable (`{titulo_normalizado}_{instance_id}.docx`).

## Analyzer / Tools

Sin cambios de contrato útil: register → create(title) → patch → status → render.

Baseline: skill `report_engine` en `framework_tool_pack_v1` profile `general`.

### Analyzer v2 — tablas

- Detecta placeholders `{{campo.2}}` y `{{ campo.2 }}` (espacios opcionales).
- Recorre `doc.tables[]` y anota `table_index`, `row_index`, `col_index`, `in_table` por campo.
- `analyzer_mode` en análisis: `jinja_tables` cuando hay campos en celdas (persistido como `jinja`).
- Devuelve `tables[]`, `editable_field_count`, `fields_in_tables`.

### Carril obligatorio (agente) — transversal

- **Inbound:** MarkItDown / `extract_document_text` (binario → texto). No genera Word.
- **Outbound serio:** Report Engine únicamente. No hay carril pandoc/`convert_document` en baseline.
- **Criterio:** plantilla(s) visible(s) → Word = `render_report_instance`.
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

### Continuidad de conversación (reanudar vs crear)

Problema: sin memoria de instancia, el agente creaba un `.docx` nuevo por cada mensaje.

- `create_report_instance` persiste `conversation_id` (= `chat_id` de la sesión, vía `set_session_chat_id`).
- `list_report_instances(limit)` lista instancias activas del actor/proyecto con `conversation_id`, `progress` y una `resume_suggestion` (prioriza la de esta conversación; si no, la más reciente).
- `list_report_instances(..., lean=True)` omite `preview_html` (usado por `GET /productivity/artifacts`).
- **Política (directive `report_engine`):** ANTES de crear, el agente llama `list_report_instances`; si hay borrador de la conversación, **reanuda** con ese `instance_id` (patch/render). Crea uno nuevo solo si el usuario lo pide explícitamente.

### Documento desde cero (sin plantilla del usuario) — texto + imágenes

Para «arma un documento con este texto y estas imágenes» sin que el usuario suba plantilla:

- `create_blank_document(title)` genera on-demand (python-docx, **sin binario en git**) un `.docx` en blanco bajo el vault privado del tenant, no en Drive/OUTPUT; lo registra como plantilla del usuario (`template_id` determinista por `tenant+owner`, idempotente) y crea la instancia.
- Schema (`blank_template.BLANK_SECTION_SCHEMA`): huecos de texto (`intro`, `texto_1..3`, `cierre`) e imagen (`imagen_1..3`, `kind=image`). Ninguno `required`; con `ChainableUndefined` los huecos sin usar quedan vacíos.
- El título del documento se inyecta en `{{ titulo }}`: si la sección está vacía, el render usa el `title` de la instancia (no `setdefault`, que no pisa `""`).
- `create_blank_document` también hace `patch` de `titulo` al crear.

### Secciones de imagen (`kind=image`)

- `state.init_state_from_schema` propaga `kind` y `width_in` (default 5.5") a la sección.
- `build_render_context` **excluye** secciones de imagen (necesitan el objeto `DocxTemplate`); `image_render_specs(state)` las expone aparte.
- El render construye `InlineImage` y **ajusta** width/height para que quepan en página (máx. ~6" × 7"): capturas verticales a `width_in=5.5` salían ~9.8" de alto y Google Docs las oculta (hueco en blanco con el PNG sí embebido en `word/media/`).
- Valida que el path esté bajo raíces permitidas (**vault inbound del tenant + OUTPUT**) — anti path-traversal.
- `patch_report_image(instance_id, section_id, image_path)`: coloca la imagen (por su ruta) en una sección `kind=image`; rechaza secciones de texto.

### Imágenes adjuntas en el chat (playground)

- **Carril attachment (siempre):** decode + persist en `db/private/{tenant}/inbound/` + bloque `[IMAGENES_ADJUNTAS]` con mapeo `imagen_N → path`.
- **Carril VLM (opt-in por intención):** solo si el caption pide análisis visual (analiza/describe/OCR/qué ves…). «Ponla en el documento» **no** dispara VLM.
- Si VLM falla o se cancela, las rutas ya persistidas siguen disponibles.
- **Sin API key** para insertar imágenes. VLM local (MLX) o cloud es opcional y separada.
- **Preview Admin:** secciones `kind=image` se muestran como `<img>` (data-URI), no como ruta de disco. El path crudo confundía (“no inyectó”).
- Atajo: `create_blank_document(title, image_paths="ruta1;ruta2", intro="...")` coloca imágenes e intro y luego `render_report_instance`.
- `render_report_instance` reporta `images_embedded` (conteo de `word/media/*`) para verificar inyección.

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
