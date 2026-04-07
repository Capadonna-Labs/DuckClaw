# Caged Beast (Mercenario): ejecución efímera bajo política Manager

## Objetivo

Patrón **“bestia enjaulada”**: cuando el planner del Manager elige la ruta opcional `mercenary`, se ejecuta **una sola sesión efímera** en contenedor Docker endurecido (alineado con Strix / `SecurityPolicy`), sin delegar código arbitrario al worker estándar del turno. El proceso enjaulado debe materializar su salida solo vía **`/workspace/output/result.json`**.

## Zero-Trust

- Por defecto **sin red** (`network_mode=none` cuando `network.default` es `deny`).
- `cap_drop: ALL`, `no-new-privileges`, usuario no root numérico (`1000:1000`), límites de memoria/CPU según `security_policy_to_docker_kwargs` en `packages/agents/src/duckclaw/forge/schema.py`.
- **Sesión one-shot**: no reutiliza contenedores `strix_sandbox_{session}`; nombre estable `duckclaw_mercenary_{slug}` por tarea, ciclo de vida explícito (wait → eliminar).

## Contrato de montaje (host)

- Directorio de intercambio: `/tmp/duckclaw_exchange/{task_id}/` (creado por el gateway/orquestador).
- Montaje único **RW**: ese directorio → `/workspace/output` en el contenedor.
- No se montan rutas adicionales del host salvo lo que la política permita de forma explícita; en la implementación actual del mercenario **solo** se aplica este volumen (cierre de superficie de ataque).

## Contrato del contenedor

- El proceso **debe** escribir un archivo JSON objeto en **`/workspace/output/result.json`**.
- Si falta el archivo, está vacío o el JSON es inválido, el host devuelve error determinista:
  - `MERCENARY_RESULT_MISSING`
  - `MERCENARY_JSON_INVALID`
- Otros códigos estables:
  - `MERCENARY_DOCKER_UNAVAILABLE`
  - `MERCENARY_TIMEOUT`
  - `MERCENARY_CONTAINER_ERROR` (salida no cero del contenedor, sin `result.json` válido)

## Timeouts y limpieza

- `timeout` acotado entre **1 y 600** segundos (validación en planner y en runtime).
- Espera con `asyncio.wait_for` (o equivalente) alrededor del `wait` del contenedor.
- En timeout o fallo: **`remove(force=True)`** del contenedor vía API Docker.
- En `finally`: `shutil.rmtree` del árbol `/tmp/duckclaw_exchange/{task_id}/` con `ignore_errors=True` y logs estructurados (`INFO` ciclo de vida, `WARNING` timeout).

## Imagen

- Variable de entorno opcional: `STRIX_MERCENARY_IMAGE` (fallback: misma convención que sandbox Strix, p. ej. `duckclaw/sandbox:latest` con fallback `python:3.11-slim` si aplica).

## Planner (Manager)

- Extensión **opcional y retrocompatible** del JSON del planner:

```json
{
  "plan_title": "string",
  "tasks": ["string"],
  "mercenary": null
}
```

o

```json
{
  "plan_title": "string",
  "tasks": ["string"],
  "mercenary": { "directive": "string", "timeout": 300 }
}
```

- Si `mercenary` está presente y bien formado, el turno va **solo** a `mercenary_node` → `END` (no `invoke_worker` en ese turno).

## Herramienta declarativa

- Skill `deploy_mercenary` bajo `forge/templates/Manager/skills/deploy_mercenary.py` (StructuredTool) para uso programático o futuros nodos; el grafo puede invocar el mismo núcleo en `sandbox.py` sin segundo LLM.
