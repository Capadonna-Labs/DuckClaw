# Projects Orchestrator UX

## Objetivo

Separar la creación guiada del catálogo DB-first de proyectos.

- `/projects`: catálogo escalable de proyectos.
- `/projects/orchestrator`: wizard dedicado para crear proyectos con `platform-orchestrator`.
- `/playground?worker=platform-orchestrator&project=<id>`: guía conversacional para proyectos existentes.

## Problema Actual

`/projects` mezcla creación guiada, creación rápida, catálogo, asignación de agentes y navegación al Playground. Esto sirve para validar backend, pero no escala a cientos o miles de proyectos y hace que el borrador del Orchestrator parezca un preview técnico en vez de un flujo de confirmación.

## Contrato UX

### Catálogo

`/projects` debe enfocarse en observar y administrar proyectos existentes.

Debe incluir:

- búsqueda por nombre, descripción y `project_id`;
- filtros;
- ordenamiento;
- paginación;
- acciones por proyecto: abrir, guiar con Orchestrator, asignar agentes, eliminar;
- estado vacío con CTA a `/projects/orchestrator`.

No debe renderizar el textarea largo del Orchestrator.

### Wizard

`/projects/orchestrator` debe crear proyectos nuevos por pasos.

Pasos:

1. Objetivo: usuario describe objetivo, datos y resultado esperado.
2. Preguntas: Orchestrator pide datos faltantes.
3. Borrador revisable: UI muestra proyecto, workers, skills, contexto y riesgos.
4. Confirmación DB-first: UI muestra qué filas se escribirán antes de confirmar.

Nada se guarda hasta confirmar explícitamente.

### Playground

Playground queda para orientar proyectos existentes.

Cuando se abre con:

```text
/playground?worker=platform-orchestrator&project=<project_id>
```

Gateway debe inyectar:

- `admin_projects.name`;
- `admin_projects.description`;
- agentes activos del proyecto.

El chat no debe crear recursos sin pasar por una confirmación explícita.

## API

Primera fase puede reutilizar:

- `GET /workspace/projects`
- `POST /workspace/projects`
- `DELETE /workspace/projects/{project_id}`
- `GET /workspace/projects/{project_id}/agents`
- `POST /workspace/projects/{project_id}/agents`
- `DELETE /workspace/projects/{project_id}/agents/{worker_id}`
- `POST /workspace/orchestrator/draft`
- `POST /workspace/orchestrator/confirm`

Para escalar, `GET /workspace/projects` debe admitir:

- `q`
- `status`
- `sort`
- `direction`
- `limit`
- `offset`

Respuesta:

```json
{
  "projects": [],
  "total": 0,
  "limit": 25,
  "offset": 0
}
```

## Componentes

- `ProjectsCatalogPage`
- `ProjectsCatalogToolbar`
- `ProjectsTable`
- `ProjectActionsMenu`
- `ProjectDeleteConfirmModal`
- `ProjectOrchestratorWizardPage`
- `OrchestratorObjectiveStep`
- `OrchestratorQuestionsStep`
- `OrchestratorDraftReview`
- `OrchestratorDbConfirmStep`

## Criterios de Aceptación

- `/projects` muestra catálogo con búsqueda y paginación.
- `/projects` no contiene el textarea largo del Orchestrator.
- `/projects/orchestrator` existe como ruta dedicada.
- CTA `Nuevo proyecto` apunta a `/projects/orchestrator`.
- Wizard muestra objetivo, preguntas, borrador y confirmación.
- Borrador muestra resumen, proyecto, workers, skills y contexto.
- Confirmación muestra qué se escribirá en DuckDB.
- Confirmar usa endpoints DB-first existentes.
- Eliminar proyecto conserva hard-delete transaccional.
- `Guiar con Orchestrator` conserva `worker=platform-orchestrator&project=<id>`.
- Tests cubren separación de rutas y contrato de catálogo.

## Fuera de Alcance

- guardar secretos;
- crear recursos desde chat sin confirmación;
- edición avanzada de workers dentro del wizard;
- multi-select masivo;
- migración legacy.
