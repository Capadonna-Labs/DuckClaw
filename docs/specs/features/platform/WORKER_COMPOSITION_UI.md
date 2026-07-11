# Worker Composition UI

## Objetivo

Configurar **skills opcionales**, **toggles** y **MCP grants** sin editar YAML. Todos los workers nuevos usan **`tool_profile: general`** (baseline completo); el agente decide qué herramientas invocar según el turno y el system prompt.

## Modelo de capacidades

| Capa | Qué controla |
|------|----------------|
| **Baseline** | Siempre `general` → SQL, esquema, RAG, documentos (`framework_tool_pack_v1.json`) |
| **Comportamiento** | system prompt + soul (rol, cuándo usar SQL vs RAG) |
| **Extras UI** | `web_search`, `browser_sandbox`, skills opcionales, MCP grants |
| **Legacy** | `minimal` / `rag_only` solo en manifests antiguos; el editor guided fuerza `general` al guardar |

## Superficies

| Superficie | Componentes |
|------------|-------------|
| Wizard paso 1 | `WorkerRoleTemplatePicker` — plantillas de rol (prompt + toggles sugeridos) |
| Wizard paso 2 | `WorkerCompositionPanel`, `WorkerMcpGrantsPicker` |
| Editor Herramientas | `ManifestGuidedPanel`, `WorkerSkillPickerPanel`, `WorkerMcpGrantsPanel` |
| Playground Run settings | `PlaygroundWorkerCapabilitiesPanel` — gaps + link al editor |
| Listado | `/templates` patrón plano |

## Plantillas de rol (Fase C)

Fuente: `apps/duckclaw-admin/src/lib/workerRoleTemplates.ts`

- `general`, `data_analyst`, `support`, `devops`
- Todas aplican `tool_profile: general`
- Diferencia = **prompt semilla** + toggles sugeridos (web/sandbox), no recorte de baseline

## Wizard — reglas

1. LLM draft policy exige `tool_profile: general`.
2. `normalizeAgentDraft` y `UpsertUserAgentCommand` fuerzan `general` en backend.
3. Tras confirm: poll task → grants MCP opcionales.

## Playground

Panel **Herramientas** en Run settings: `PlaygroundWorkerCapabilitiesPanel` (solo lectura).

- Cuenta skills efectivas / manifest, MCP grants, toggles research/sandbox
- Lista gaps de runtime (Tavily, Docker, tools faltantes)
- Enlace a `/templates/{id}?focus=manifest.yaml`

## Fuera de alcance

- Edición inline de skills en Playground
- Multi-tenant presets
- Instalación one-click de skills sugeridas

## Tests

- `workerRoleTemplates.test.ts`, `draftManifestYaml.test.ts`
- `test_admin_workers_ui_static.py`, `test_admin_playground_ui_static.py`
