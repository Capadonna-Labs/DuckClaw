
# Strix Sandbox & Security Policy Engine (Zero-Trust Execution)

## 1. Objetivo Arquitectónico
Implementar un entorno de ejecución efímero y aislado (Sandbox) basado en contenedores sin privilegios, gobernado por un motor de políticas declarativas inspirado en NVIDIA OpenShell. Este componente permite a los trabajadores virtuales (ej. `bi_analyst`, `job_finder`) ejecutar código Python o SQL dinámico generado por el LLM sin comprometer el sistema host (Mac Mini M4), garantizando el cumplimiento de Habeas Data mediante el bloqueo de exfiltración de red y el montaje de datos en modo estricto de Solo Lectura (Read-Only).

## 2. Infraestructura Base (OrbStack / Docker Rootless)
Dado que el host es una Mac Mini M4, se utilizará el motor de contenedores de OrbStack configurado para ejecución sin privilegios.

*   **Imagen Base:** `python:3.12-slim` (o una imagen personalizada `duckclaw-strix-base` pre-empaquetada con `polars`, `pyarrow` y `requests`).
*   **Imagen `docker/sandbox` (referencia):** además de pandas, matplotlib, mplfinance, seaborn, duckdb, scipy, scikit-learn, pyarrow, requests, vaderSentiment, incluye **`yfinance`** para scripts que descarguen datos Yahoo (^VIX, etc.). Si la política de red del worker es `deny`, las llamadas de red de `yfinance` fallarán en runtime; el import y el código offline siguen siendo válidos.
*   **Restricciones de Daemon:**
    *   Ejecución forzada con `--user 1000:1000`.
    *   Drop de todas las capabilities del kernel: `--cap-drop=ALL`.
    *   Límites de recursos (cgroups): Máximo 512MB RAM, 1 CPU core por ejecución.

## 3. Motor de Políticas Declarativas (Pydantic Schema)

El `Forge` debe validar las reglas de seguridad antes de instanciar cualquier contenedor.

*   **Ubicación:** `packages/agents/src/duckclaw/forge/schema.py`
*   **Contrato de Datos:**

```python
from pydantic import BaseModel, Field
from typing import List, Dict, Literal

class NetworkPolicy(BaseModel):
    default: Literal["allow", "deny"] = "deny"
    allow_list: List[str] = Field(default_factory=list, description="Dominios o IPs permitidas si default es deny")

class FileSystemPolicy(BaseModel):
    readonly_mounts: List[str] = Field(default_factory=list, description="Rutas del host a montar como RO")
    ephemeral_volumes: List[str] = Field(default_factory=lambda: ["/tmp/workspace"], description="Volúmenes tmpfs en RAM")

class SecretPolicy(BaseModel):
    in_memory_only: bool = True
    allowed_secrets: List[str] = Field(default_factory=list, description="Nombres de variables de entorno permitidas")

class SecurityPolicy(BaseModel):
    network: NetworkPolicy = NetworkPolicy()
    filesystem: FileSystemPolicy = FileSystemPolicy()
    secrets: SecretPolicy = SecretPolicy()
    max_execution_time_seconds: int = Field(default=30, le=600)
```

## 4. Plantilla de Seguridad por Worker (`security_policy.yaml`)

Cada trabajador virtual en `templates/workers/` debe incluir su política. Si no existe, el `Forge` asume denegación total.

*   **Ejemplo para `bi_analyst`:**
```yaml
# templates/workers/bi_analyst/security_policy.yaml
network:
  default: deny
  allow_list:[] # Análisis 100% offline
filesystem:
  readonly_mounts:
    - "/opt/duckclaw/tmp/exports:/workspace/data:ro" # Donde el Gateway deja los PyArrow
  ephemeral_volumes:
    - "/workspace/output" # Donde el agente guarda los gráficos generados
secrets:
  in_memory_only: true
  allowed_secrets:[]
max_execution_time_seconds: 45
```

## 5. Especificación de Skill: `StrixSandboxRunner`

Este es el puente entre LangGraph y el demonio de contenedores.

*   **Ubicación:** `packages/agents/src/duckclaw/forge/skills/strix_runner.py`
*   **Lógica de Ejecución:**
    1.  **Lectura de Política:** Cargar y validar el `security_policy.yaml` del `worker_id` actual.
    2.  **Preparación de Datos (Zero-Copy):** Si el agente necesita datos de DuckDB, el Gateway exporta un archivo `.arrow` a `/opt/duckclaw/tmp/exports/session_id.arrow`.
    3.  **Inyección de Secretos:** Leer los secretos permitidos desde el *Secret Vault* del host y pasarlos como variables de entorno al contenedor (Docker los inyecta en el espacio de memoria del proceso PID 1, no en disco).
    4.  **Ejecución Aislada:**
        ```python
        import docker
        client = docker.from_env()
        
        # Construir kwargs basados en la política
        container_kwargs = {
            "image": "duckclaw-strix-base",
            "command": ["python", "-c", agent_generated_code],
            "user": "1000:1000",
            "cap_drop": ["ALL"],
            "network_mode": "none" if policy.network.default == "deny" else "bridge",
            "volumes": policy.filesystem.readonly_mounts,
            "tmpfs": {vol: "" for vol in policy.filesystem.ephemeral_volumes},
            "environment": {k: get_secret(k) for k in policy.secrets.allowed_secrets},
            "mem_limit": "512m",
            "detach": True
        }
        
        container = client.containers.run(**container_kwargs)
        try:
            result = container.wait(timeout=policy.max_execution_time_seconds)
            logs = container.logs().decode('utf-8')
            return {"exit_code": result["StatusCode"], "output": logs}
        finally:
            container.remove(force=True)
        ```

## 6. Protocolo de Validación y Auditoría (Forensics)

Para certificar que el Sandbox es seguro, el pipeline de CI/CD (o un test manual) debe ejecutar los siguientes vectores de ataque y verificar que fallan:

1.  **Prueba de Exfiltración (SSRF/Data Leak):**
    *   *Código inyectado:* `import urllib.request; urllib.request.urlopen("http://google.com")`
    *   *Resultado esperado:* `urllib.error.URLError: [Errno -3] Temporary failure in name resolution` (Bloqueo de red).
2.  **Prueba de Acceso a Host (LFI):**
    *   *Código inyectado:* `open('/etc/passwd', 'r').read()`
    *   *Resultado esperado:* Lee el `/etc/passwd` del contenedor (inofensivo), no el de la Mac Mini.
    *   *Código inyectado 2:* `open('/workspace/data/test.txt', 'w').write('hack')`
    *   *Resultado esperado:* `Read-only file system` (Bloqueo de escritura en montajes RO).
3.  **Auditoría en LangSmith:**
    *   Cualquier `exit_code != 0` devuelto por el contenedor debe registrarse en el `task_audit_log` con el flag `SECURITY_VIOLATION_ATTEMPT` si el error corresponde a un `PermissionError` o `NetworkError`, permitiendo auditar si el LLM está siendo víctima de un *Prompt Injection*.