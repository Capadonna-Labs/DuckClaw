# Platform Orchestrator Worker

## Objetivo

`platform-orchestrator` es el worker DB-first que acompaña a cada usuario de la consola para crear proyectos, workers, contexto compartido y configuración inicial sin volver a depender de templates legacy ni de cambios manuales en carpetas.

El orquestador debe sentirse como una guía permanente de la plataforma: pregunta qué quiere lograr el usuario, propone una estructura de proyecto, sugiere skills disponibles y prepara un borrador antes de ejecutar cambios.

## Identidad

- `worker_id`: `platform-orchestrator`
- `display_name`: `Platform Orchestrator`
- `source_kind`: `system_seed`
- `source_template_id`: `platform-orchestrator`
- `visibility`: `private`
- `tenant_id`: tenant del perfil autenticado
- `owner_email`: email normalizado del usuario autenticado
- `active`: `true`

Cada usuario tiene su propia fila en `main.admin_worker_catalog`. No es un worker global compartido ni un template de filesystem.

## Disponibilidad

El Gateway debe asegurar el orquestador al resolver el catálogo DB-first del actor. Debe aparecer en:

- `GET /templates`
- `GET /playground/config`
- selectores de worker en proyectos
- chat flotante y Playground

No debe mostrarse como filesystem legacy. No debe poder desactivarse desde la acción normal de Workers.

## Prompt Base

El snapshot inicial en `main.admin_worker_versions` debe contener un prompt base que instruya al worker a:

- entrevistar al usuario sobre objetivos, dominio, restricciones, datos y resultados esperados;
- proponer proyectos y workers como borrador;
- sugerir skills desde el catálogo DB-first;
- pedir confirmación antes de crear o modificar recursos;
- no inventar secretos ni configurar API keys desde chat;
- preferir DB-first y evitar escribir en carpetas legacy.

## Draft Guiado

`POST /workspace/orchestrator/draft` recibe una descripción libre y devuelve un borrador estructurado:

```json
{
  "project": {
    "name": "string",
    "description": "string"
  },
  "workers": [
    {
      "worker_id": "string",
      "display_name": "string",
      "role": "member",
      "system_prompt": "markdown"
    }
  ],
  "shared_context": "markdown",
  "suggested_skills": [
    {
      "name": "string",
      "reason": "string",
      "available": true
    }
  ],
  "questions": ["string"]
}
```

El draft no crea recursos. Solo prepara una propuesta revisable.

## Confirmación

`POST /workspace/orchestrator/confirm` recibe el draft aprobado y crea recursos DB-first:

- proyecto en `main.admin_projects`;
- workers en `main.admin_worker_catalog` y `main.admin_worker_versions` cuando no existan;
- asignaciones en `main.admin_project_agents`;
- contexto markdown en `main.admin_worker_contexts`;
- eventos de auditoría por recurso creado.

La confirmación debe ser idempotente por `request_id` cuando se agregue soporte de UI completo. En la primera fase, la UI debe evitar doble submit y el backend debe reutilizar workers existentes del actor si el `worker_id` ya existe.

## Skills

La sugerencia de skills lee `main.admin_skills` y los snippets expuestos por `GET /catalog/skills`. El orquestador puede recomendar skills no instaladas, pero debe marcarlas como `available=false` y explicar que requieren instalación/configuración.

## Secretos LLM

Provider, modelo y base URL se resuelven por Runtime Settings DB-first:

- `llm.provider`
- `llm.model`
- `llm.base_url`

API keys como `DEEPSEEK_API_KEY` siguen siendo secretos bootstrap por `.env` hasta implementar una bóveda de secretos. La UI no debe enviar secretos al browser. El plan de esa fase está en [`SECRET_SETTINGS.md`](SECRET_SETTINGS.md).

## Criterios de Aceptación

- Un usuario nuevo ve `platform-orchestrator` sin importar si existen carpetas de templates.
- Usuario A no ve ni modifica el orquestador de usuario B.
- `platform-orchestrator` no puede desactivarse desde la acción normal de Workers.
- El draft guiado no escribe en DB.
- La confirmación crea proyecto, workers, contexto y asignaciones en tablas DB-first.
- Tests cubren aislamiento por tenant, bootstrap del worker y endpoints draft/confirm.
