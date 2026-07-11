# Conocimiento — refactor layout (cards verticales)

**Fecha:** 2026-07-11  
**Estado:** implementado — 2026-07-11  
**Patrones:** `UIUX-PATTERNS.md` → Cards, Status, Progressive Disclosure, Blank Slate, Settings

---

## Objetivo

Refactorizar `/knowledge` para:

1. Unificar el **header** con Workers y Proyectos (sin caja `rounded-3xl` ni copy largo).
2. Aprovechar ancho en desktop con **panel lateral + grid de cards verticales**.
3. Reducir ruido visual (banners horizontales, filas apiladas full-width).

**Sin cambios de backend** — solo composición y componentes en `apps/duckclaw-admin`.

---

## 1. Header (canónico admin)

**Patrón:** igual que `templates/page.tsx` y `projects/page.tsx`.

```
┌─────────────────────────────────────────────────────────┐
│ [Database icon] Conocimiento          [Ver proyecto?]     │
│ Una línea: documentos indexados para el chat.             │
│ ● Listo · 11670 fragmentos · [Playground →]  (opcional)   │
└─────────────────────────────────────────────────────────┘
```

- **Quitar:** `rounded-3xl border` del header, label uppercase «CONOCIMIENTO», párrafo de alcance Plataforma/Proyecto.
- **Título:** `Conocimiento` (sidebar ya dice la sección; no duplicar eyebrow).
- **Subtítulo:** una línea máxima, tono operativo.
- **Acción derecha:** `Ver proyecto` solo si `projectId` en query (como CTA de otras vistas).
- **Status inline** (patrón **Status**): chip de una línea derivado de `summarizeKnowledgeSources` — reemplaza el banner verde/ámbar full-width. Link texto «Playground» en el chip, no botón grande.

---

## 2. Layout desktop — panel lateral + grid

**Patrón:** **Cards** + **Settings** (panel fijo con prefs, contenido principal aparte).

```
lg:grid lg:grid-cols-12 gap-6

┌──────────────┬──────────────────────────────────────────┐
│  Panel (~4)  │  Fuentes registradas (~8)                │
│  sticky top  │  grid md:2 xl:3                          │
│              │  ┌────┐ ┌────┐ ┌────┐                      │
│  Alcance     │  │card│ │card│ │card│                      │
│  Agregar     │  └────┘ └────┘ └────┘                      │
│  [Indexar]   │                                          │
└──────────────┴──────────────────────────────────────────┘
```

### Panel izquierdo (`KnowledgeControlPanel`)

Contenedor único `rounded-2xl border p-4`, `lg:sticky lg:top-4`:

| Bloque | Contenido | Patrón |
|--------|-----------|--------|
| Alcance | 2 selects (proyecto, agente opcional) | Settings — sin sección separada full-width |
| Agregar | checkbox embeddings, `KnowledgeFolderBrowser`, preview, botón Indexar | Wizard-lite — flujo vertical compacto |
| Avanzado | «Subir archivos sueltos» colapsado | **Progressive Disclosure** |

- **Quitar** textos explicativos largos bajo cada control; máximo una línea de hint donde sea imprescindible (agente opcional).
- Warning `DUCKCLAW_KNOWLEDGE_ALLOWED_ROOTS` se mantiene inline compacto en el panel.

### Panel derecho (`KnowledgeSourcesGrid`)

- Header fila: «Fuentes registradas» + botón Refrescar.
- **Grid:** `grid gap-3 md:grid-cols-2 xl:grid-cols-3` (patrón Cards — scroll vertical único).
- **Blank Slate** cuando `sources.length === 0`: mensaje + CTA implícito «indexa desde el panel izquierdo» (sin banner ámbar aparte).

---

## 3. `KnowledgeSourceCard` — vertical

**Patrón Cards:** título + badge + resumen + acciones; no sobrecargar.

Estructura vertical (`flex flex-col`, altura mínima ~180px, estilo cercano a `AgentCard`):

```
┌─────────────────────┐
│ MacMiniVault  LISTO │
│ 49 docs · 11670 fr. │
│ [progress si index] │
│ Ver archivos ▾      │
│ ─────────────────── │
│ [Sincronizar]       │
│ [Eliminar del RAG]  │
└─────────────────────┘
```

- **Quitar** `md:flex-row` (layout horizontal).
- Acciones apiladas o en fila compacta al **pie** de la card.
- «Ver archivos» / detalle URI: **Progressive Disclosure** (colapsado por defecto si texto largo).
- `KnowledgeStatusBadge` y `KnowledgeIndexingProgress` sin cambio de lógica.

---

## 4. `KnowledgePlaygroundBanner` → `KnowledgeScopeStatus`

| Antes | Después |
|-------|---------|
| Sección full-width con 2–3 párrafos | Chip/status de 1 línea en header o bajo subtítulo |
| Botón «Abrir Playground» prominente | Link texto en el chip |
| Estados vacío/indexing/error como banners | Vacío → Blank Slate en grid; indexing → badge en cards afectadas + chip «Indexando…» |

Componente nuevo pequeño o refactor del banner existente; **no** eliminar la lógica de `summarizeKnowledgeSources`.

---

## 5. Archivos tocados

| Archivo | Acción |
|---------|--------|
| `knowledge/page.tsx` | Composición: header plano + grid 12 cols |
| `KnowledgeControlPanel.tsx` | **Nuevo** — alcance + agregar + upload colapsado |
| `KnowledgeSourcesGrid.tsx` | **Nuevo** — grid + empty/loading |
| `KnowledgeSourceCard.tsx` | Layout vertical |
| `KnowledgePlaygroundBanner.tsx` | Refactor → `KnowledgeScopeStatus.tsx` (chip compacto) |
| `test_admin_session_knowledge_ui_static.py` | Actualizar aserciones de layout/status |

**No tocar:** `KnowledgeFolderBrowser`, APIs, `adminService`, lógica de jobs/polling en `page.tsx` (solo mover JSX a subcomponentes).

---

## 6. Responsive

| Breakpoint | Comportamiento |
|------------|----------------|
| `< lg` | Stack: header → status chip → panel control → grid 1 col |
| `≥ lg` | Panel sticky izquierda + grid 2–3 cols |
| `≥ xl` | Grid 3 cols fuentes |

---

## 7. Criterios de aceptación

1. Header visualmente consistente con Workers/Proyectos (sin caja decorativa).
2. En viewport ≥1280px, panel izquierdo y grid de fuentes visibles sin scroll excesivo en header/banners.
3. Cada fuente es una card vertical escaneable; acciones al pie.
4. Banner Playground full-width eliminado; estado resumido en chip.
5. «Subir archivos sueltos» sigue disponible colapsado.
6. Tests estáticos actualizados y verdes.

---

## 8. Fuera de alcance

- Buscador/filtro de fuentes.
- `ConfirmDangerModal` para eliminar (mantener confirm nativo por ahora).
- Cambios en indexación backend o PM2.

---

## Self-review

- [x] Sin TBD ni placeholders.
- [x] Alineado con UIUX-PATTERNS citados.
- [x] Scope acotado a frontend admin.
- [x] Una sola dirección de layout (opción A).
