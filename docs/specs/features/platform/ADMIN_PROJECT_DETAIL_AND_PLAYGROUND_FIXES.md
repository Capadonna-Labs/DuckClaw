# Admin Project Detail And Playground Fixes

## Objetivo

Cerrar brechas de UX/DB-first en DuckClaw Admin para proyectos, agentes y conversaciones:

- La tabla de proyectos debe permitir abrir una vista de detalle del proyecto.
- La eliminación definitiva de un proyecto debe pedir confirmación visible con consecuencias claras.
- El detalle debe mostrar datos del proyecto y agentes asignados desde DuckDB.
- El editor de worker debe explicar dónde viven `system_prompt.md`, `soul.md` y los contextos DB.
- El Playground debe respetar el proyecto activo y no conservar un `worker_id` preferido que no pertenece al proyecto.
- Las conversaciones nuevas no deben quedarse con títulos genéricos repetidos si ya existe una primera pregunta del usuario.

## Reglas

- Mantener patrón BFF/Gateway: el browser llama `src/app/api/admin/*`, y el Gateway lee/escribe DuckDB.
- No reactivar fallbacks filesystem para proyectos, Kanban, ComfyUI o `.env`.
- Los datos de proyecto y agentes salen de `main.admin_projects` y `main.admin_project_agents`.
- Los contextos del agente salen de `main.admin_worker_contexts`; los snapshots de prompt/manifest salen de versiones del catálogo.

## Criterios De Aceptación

- `ProjectsTable` tiene acción visible `Ver` hacia `/projects/[projectId]`.
- `Eliminar definitivo` abre un modal de confirmación antes de llamar al Gateway.
- `/projects/[projectId]` muestra nombre, descripción, estado, tenant, owner y agentes asignados.
- Desde detalle se puede ir a Playground con el agente del proyecto y `project_id`.
- El Playground selecciona el primer agente del proyecto cuando el worker actual no pertenece a ese proyecto.
- El selector de conversación muestra títulos derivados de la primera pregunta cuando el título sigue siendo `Conversación YYYY-MM-DD`.
- Tests estáticos/API/conversaciones cubren estas reglas.
