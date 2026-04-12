# specs/Sandbox_de_Ejecucion_Libre_Basado_en_Strix.md

"""Strix Sandbox: entorno de ejecución libre aislado con Docker.

- StrixSandboxManager: ciclo de vida del contenedor (provisioning, exec, teardown).
- run_in_sandbox(): bucle de auto-corrección (hasta max_retries intentos).
- data_inject(): exporta SQL de DuckDB a /tmp/.../data.csv para montaje read-only.
- sandbox_tool_factory(): StructuredTool para usar en general_graph.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
import shutil
import tempfile
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from duckclaw.forge.schema import SecurityPolicy, load_security_policy, security_policy_to_docker_kwargs

_log = logging.getLogger(__name__)

# Cabecera inyectada antes del código del usuario (Strix / run_sandbox).
# Telegram sendPhoto rechaza PNG con transparencia o procesamiento raro (IMAGE_PROCESS_FAILED):
# fondo blanco opaco + dpi moderado en savefig y rcParams por defecto.
_SANDBOX_PYTHON_HEADER = """# Available: pandas, numpy, matplotlib, mplfinance, seaborn, scipy
# Gráficos en /workspace/output/*.png — compatible con Telegram sendPhoto:
#   plt.savefig('/workspace/output/mi_chart.png', dpi=100, facecolor='white', edgecolor='none', bbox_inches='tight')
try:
    import matplotlib as _mpl_dc
    _mpl_dc.use("Agg")
except Exception:
    pass
try:
    import matplotlib.pyplot as _plt_dc
    _plt_dc.rcParams.update(
        {
            "figure.facecolor": "white",
            "savefig.facecolor": "white",
            "savefig.edgecolor": "none",
            "figure.dpi": 100,
            "savefig.dpi": 100,
        }
    )
except Exception:
    pass
"""

# Imagen base por defecto; sobreescribible con STRIX_SANDBOX_IMAGE
_DEFAULT_IMAGE = "duckclaw/sandbox:latest"
# Imagen browser (OSINT JobHunter / Strix Browser Sandbox); STRIX_BROWSER_IMAGE
_DEFAULT_BROWSER_IMAGE = "duckclaw/browser-env:latest"
# Límites de texto devuelto al LLM en run_browser_sandbox (evitar reventar contexto; MQL5 puede ser largo).
_BROWSER_SANDBOX_STDOUT_TAIL = 4000
_BROWSER_SANDBOX_STDERR_TAIL = 1500
_FALLBACK_IMAGE = "python:3.11-slim"
_SANDBOX_MEMORY = "512m"
_SANDBOX_TIMEOUT = 30          # segundos de timeout por ejecución
_MAX_RETRIES_DEFAULT = 3

# Directorio base de sesiones en el host
_TMP_BASE = Path(tempfile.gettempdir()) / "duckclaw_sandbox"


@dataclass
class ExecutionResult:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False
    artifacts: list[str] = field(default_factory=list)
    attempts: int = 1

    @property
    def success(self) -> bool:
        return self.exit_code == 0 and not self.timed_out

    def to_dict(self) -> dict:
        return {
            "exit_code": self.exit_code,
            "stdout": self.stdout[:8000],
            "stderr": self.stderr[:4000],
            "timed_out": self.timed_out,
            "artifacts": self.artifacts,
            "attempts": self.attempts,
        }


def _docker_client():
    """Devuelve docker.DockerClient o levanta ImportError/DockerException."""
    import docker  # noqa: PLC0415
    return docker.from_env()


def _docker_available() -> bool:
    try:
        c = _docker_client()
        c.ping()
        return True
    except Exception:
        return False


def _image_name() -> str:
    return os.environ.get("STRIX_SANDBOX_IMAGE", _DEFAULT_IMAGE)


def _browser_image_name() -> str:
    return os.environ.get("STRIX_BROWSER_IMAGE", _DEFAULT_BROWSER_IMAGE).strip() or _DEFAULT_BROWSER_IMAGE


def _ensure_image(client: Any, image: str | None = None, *, allow_python_fallback: bool = True) -> str:
    """Verifica que la imagen esté disponible; opcionalmente pull. Sin fallback para imágenes browser explícitas."""
    want = (image or _image_name()).strip()
    try:
        client.images.get(want)
        return want
    except Exception:
        pass
    try:
        client.images.pull(want)
        return want
    except Exception as first_err:
        if not allow_python_fallback or want != _image_name():
            raise RuntimeError(f"No se pudo obtener la imagen Docker {want!r}: {first_err}") from first_err
    try:
        client.images.pull(_FALLBACK_IMAGE)
        _log.warning(
            "Strix sandbox: imagen %r no disponible; usando %s (sin stack analítico preinstalado). "
            "Construye: docker build -t duckclaw/sandbox:latest docker/sandbox/",
            want,
            _FALLBACK_IMAGE,
        )
        return _FALLBACK_IMAGE
    except Exception as e:
        raise RuntimeError(f"No se pudo obtener ninguna imagen Docker para el sandbox: {e}") from e


def _inject_sandbox_python_header(code: str) -> str:
    raw = code or ""
    if "_plt_dc.rcParams" in raw:
        return raw
    stripped = raw.lstrip()
    if stripped:
        first_line = stripped.split("\n", 1)[0]
        if "Available:" in first_line and "pandas" in first_line and "_plt_dc" not in raw:
            nl = stripped.find("\n")
            raw = stripped[nl + 1 :].lstrip() if nl >= 0 else ""
    if not (raw or "").strip():
        return _SANDBOX_PYTHON_HEADER
    return _SANDBOX_PYTHON_HEADER + "\n" + raw


class StrixSandboxManager:
    """Gestiona el ciclo de vida de contenedores Docker para ejecución aislada.

    Spec: sección 4 y 6 de Sandbox_de_Ejecucion_Libre_Basado_en_Strix.md
    - network_mode=none (Zero exfiltration)
    - --cap-drop=ALL
    - mem_limit=512m
    - Montaje de datos en modo read-only; output en read-write
    """

    def __init__(
        self,
        image: str | None = None,
        timeout: int = _SANDBOX_TIMEOUT,
        memory: str = _SANDBOX_MEMORY,
    ):
        self.image = image or _image_name()
        self.timeout = timeout
        self.memory = memory
        self._containers: dict[str, Any] = {}
        self._session_image: dict[str, str] = {}

    def _session_dirs(self, session_id: str) -> tuple[Path, Path]:
        base = _TMP_BASE / session_id
        data_dir = base / "data"
        out_dir = base / "output"
        data_dir.mkdir(parents=True, exist_ok=True)
        out_dir.mkdir(parents=True, exist_ok=True)
        return data_dir, out_dir

    def _get_or_create_container(
        self,
        session_id: str,
        data_dir: Path,
        out_dir: Path,
        policy: SecurityPolicy | None = None,
        secret_env: dict[str, str] | None = None,
        image_override: str | None = None,
    ) -> Any:
        import docker  # noqa: PLC0415

        container_name = f"strix_sandbox_{session_id}"
        client = _docker_client()
        desired_image = (image_override or self.image).strip()
        allow_fb = image_override is None
        resolved_image = _ensure_image(client, desired_image, allow_python_fallback=allow_fb)

        prev_img = self._session_image.get(session_id)
        if prev_img and prev_img != resolved_image and session_id in self._containers:
            try:
                c_old = self._containers.pop(session_id)
                c_old.stop(timeout=3)
                c_old.remove(force=True)
            except Exception:
                pass

        # Reusar si ya está corriendo y misma imagen
        if session_id in self._containers:
            try:
                container = self._containers[session_id]
                container.reload()
                if container.status == "running" and self._session_image.get(session_id) == resolved_image:
                    return container
            except Exception:
                pass

        # Eliminar contenedor antiguo si existe
        try:
            old = client.containers.get(container_name)
            old.stop(timeout=2)
            old.remove(force=True)
        except docker.errors.NotFound:
            pass
        except Exception:
            pass

        pol = policy or SecurityPolicy()
        policy_kwargs = security_policy_to_docker_kwargs(pol)

        # El sandbox siempre monta /workspace/data (RO) y /workspace/output (RW).
        # Si la policy intenta montar esos mismos targets, ignoramos esos mounts para evitar
        # errores 400 de Docker por "mount conflict".
        core_targets = {"/workspace/data", "/workspace/output"}
        volumes: dict[str, dict[str, str]] = {}
        for host_path, cfg in (policy_kwargs.get("volumes") or {}).items():
            bind = (cfg or {}).get("bind")
            if bind and bind in core_targets:
                continue
            volumes[host_path] = cfg

        # Montajes core del sandbox
        volumes[str(data_dir.resolve())] = {"bind": "/workspace/data", "mode": "ro"}
        volumes[str(out_dir.resolve())] = {"bind": "/workspace/output", "mode": "rw"}
        env_vars = {"PYTHONUNBUFFERED": "1"}
        if secret_env:
            env_vars.update(secret_env)

        run_cmd: list[str] = ["tail", "-f", "/dev/null"]
        if image_override:
            env_vars["DISPLAY"] = ":99"
            env_vars["STRIX_CHROME_PROFILE_DIR"] = "/workspace/chrome_profile"
            # Imagen duckclaw/browser-env: Xvfb + fluxbox + x11vnc + websockify/noVNC (:6080); ver strix-browser-init.sh
            run_cmd = ["bash", "-lc", "/usr/local/bin/strix-browser-init.sh"]
            # Perfil persistente de navegador (equiv. a -v ${PWD}/db/private/browser_profile:/workspace/chrome_profile)
            browser_profile_dir = (Path.cwd() / "db" / "private" / "browser_profile").resolve()
            browser_profile_dir.mkdir(parents=True, exist_ok=True)
            volumes[str(browser_profile_dir)] = {"bind": "/workspace/chrome_profile", "mode": "rw"}

        nm = str(policy_kwargs.get("network_mode", "none"))
        run_kw: dict[str, Any] = {
            "command": run_cmd,
            "name": container_name,
            "detach": True,
            "mem_limit": str(policy_kwargs.get("mem_limit", self.memory)),
            "nano_cpus": int(policy_kwargs.get("nano_cpus", int(1e9))),
            "network_mode": nm,
            "cap_drop": policy_kwargs.get("cap_drop", ["ALL"]),
            "security_opt": policy_kwargs.get("security_opt", ["no-new-privileges"]),
            "user": str(policy_kwargs.get("user", "1000:1000")),
            "volumes": volumes,
            "tmpfs": {
                k: v
                for k, v in (policy_kwargs.get("tmpfs") or {}).items()
                if k not in core_targets
            },
            "working_dir": "/workspace",
            "environment": env_vars,
            "remove": False,
        }
        pub = str(os.environ.get("STRIX_BROWSER_PUBLISH_NOVNC", "")).strip().lower()
        if image_override and pub in ("1", "true", "yes", "on") and nm == "bridge":
            # Solo dev: http://127.0.0.1:6080/vnc.html — VNC sin password en contenedor aislado
            run_kw["ports"] = {"6080/tcp": ("127.0.0.1", 6080)}
        container = client.containers.run(resolved_image, **run_kw)
        self._session_image[session_id] = resolved_image
        self._containers[session_id] = container
        return container

    def execute(
        self,
        session_id: str,
        code: str,
        language: str = "python",
        policy: SecurityPolicy | None = None,
        secret_env: dict[str, str] | None = None,
        timeout_seconds: int | None = None,
        image_override: str | None = None,
    ) -> ExecutionResult:
        """Ejecuta código arbitrario en el sandbox del session_id dado.

        Sección 4 de la spec: Execution + Monitoring + Artifact Retrieval.
        """
        data_dir, out_dir = self._session_dirs(session_id)

        try:
            container = self._get_or_create_container(
                session_id,
                data_dir,
                out_dir,
                policy=policy,
                secret_env=secret_env,
                image_override=image_override,
            )
        except Exception as e:
            return ExecutionResult(exit_code=1, stdout="", stderr=f"Error al levantar sandbox: {e}")

        if language == "python":
            cmd = ["python3", "-c", code]
        elif language == "bash":
            cmd = ["bash", "-c", code]
        else:
            return ExecutionResult(exit_code=1, stdout="", stderr=f"Lenguaje no soportado: {language}. Usa python o bash.")

        # Repetir allowed_secrets en exec: el motor puede no heredar todo el env del contenedor
        # cuando ExecConfig.Env está presente; así Tavily/OpenAI/etc. ven la misma clave que al create.
        exec_env = dict(secret_env or {})
        exec_env["PYTHONPATH"] = "/workspace"
        if image_override:
            exec_env["DISPLAY"] = ":99"
            exec_env["STRIX_CHROME_PROFILE_DIR"] = "/workspace/chrome_profile"

        limit = int(timeout_seconds) if timeout_seconds is not None else int(self.timeout)
        limit = max(1, min(limit, 600))

        def _exec_blocking() -> Any:
            return container.exec_run(
                cmd=cmd,
                workdir="/workspace",
                demux=True,
                environment=exec_env,
            )

        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                fut = pool.submit(_exec_blocking)
                try:
                    exec_result = fut.result(timeout=limit)
                except FuturesTimeout:
                    try:
                        container.stop(timeout=10)
                    except Exception:
                        pass
                    self._containers.pop(session_id, None)
                    self._session_image.pop(session_id, None)
                    return ExecutionResult(
                        exit_code=124,
                        stdout="",
                        stderr=f"Sandbox: tiempo de ejecución agotado ({limit}s).",
                        timed_out=True,
                    )
            raw_stdout, raw_stderr = exec_result.output or (b"", b"")
            stdout = (raw_stdout or b"").decode("utf-8", errors="replace").strip()
            stderr = (raw_stderr or b"").decode("utf-8", errors="replace").strip()
            timed_out = False
        except Exception as e:
            return ExecutionResult(exit_code=1, stdout="", stderr=f"Error de ejecución: {e}")

        artifacts = self._collect_artifacts(out_dir, session_id=session_id)

        return ExecutionResult(
            exit_code=exec_result.exit_code or 0,
            stdout=stdout,
            stderr=stderr,
            timed_out=timed_out,
            artifacts=artifacts,
        )

    def _collect_artifacts(self, out_dir: Path, *, session_id: str = "") -> list[str]:
        """Mueve artefactos del directorio de salida a la carpeta de plots del proyecto."""
        artifacts = []
        sid = str(session_id or "").strip()
        wr_bucket = sid if sid.startswith("wr_") else ""
        plots_dir = Path("output") / "sandbox" / (wr_bucket or "default")
        plots_dir.mkdir(parents=True, exist_ok=True)
        for f in out_dir.iterdir():
            if f.is_file():
                dest = plots_dir / f.name
                shutil.copy2(f, dest)
                artifacts.append(str(dest.resolve()))
        return artifacts

    def cleanup(self, session_id: str) -> None:
        """Para y elimina el contenedor de una sesión."""
        import docker  # noqa: PLC0415

        container_name = f"strix_sandbox_{session_id}"
        try:
            client = _docker_client()
            container = client.containers.get(container_name)
            container.stop(timeout=3)
            container.remove(force=True)
        except docker.errors.NotFound:
            pass
        except Exception:
            pass
        self._containers.pop(session_id, None)
        self._session_image.pop(session_id, None)
        # Limpiar directorios temporales
        session_dir = _TMP_BASE / session_id
        shutil.rmtree(session_dir, ignore_errors=True)

    def cleanup_all(self) -> None:
        for sid in list(self._containers.keys()):
            self.cleanup(sid)


# Singleton reutilizable dentro del proceso
_manager: StrixSandboxManager | None = None


def _get_manager() -> StrixSandboxManager:
    global _manager
    if _manager is None:
        _manager = StrixSandboxManager()
    return _manager


def data_inject(db: Any, sql: str, session_id: str) -> str:
    """Exporta el resultado de un SELECT al directorio data/ de la sesión del sandbox.

    Spec (sección 3): firewall de datos — el sandbox solo ve un Parquet/CSV read-only.
    Usa SandboxDataChannel (spec Pipeline_de_Datos_Zero-Copy_con_PyArrow.md):
      - Parquet (columnar, tipado, ≈5× más compacto) cuando PyArrow está disponible.
      - CSV como fallback automático.
    Devuelve la ruta al archivo generado.
    """
    session_dir = _TMP_BASE / session_id
    try:
        from duckclaw.data.arrow_bridge import SandboxDataChannel  # noqa: PLC0415
        return SandboxDataChannel.inject(db, sql, session_dir)
    except ImportError:
        pass
    # Fallback directo si el módulo data no está disponible
    data_dir = session_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    dest = data_dir / "data.csv"
    try:
        db.execute(f"COPY ({sql}) TO '{dest}' (HEADER, DELIMITER ',')")
        return str(dest)
    except Exception:
        try:
            import csv
            raw = db.query(sql)
            rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
            if not rows:
                return ""
            with open(dest, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                writer.writeheader()
                writer.writerows(rows)
            return str(dest)
        except Exception as e:
            return f"Error exportando datos: {e}"


def _correction_prompt(original_request: str, code: str, error: str, attempt: int) -> str:
    return (
        f"El siguiente código Python falló (intento {attempt}).\n\n"
        f"--- CÓDIGO ---\n{code}\n\n"
        f"--- ERROR ---\n{error}\n\n"
        f"--- TAREA ORIGINAL ---\n{original_request}\n\n"
        "Reescribe SOLO el código Python corregido, sin explicaciones, sin markdown, sin triple backtick. "
        "Solo el código puro que se pueda ejecutar directamente con python3 -c."
    )


def _load_allowed_secrets(policy: SecurityPolicy) -> dict[str, str]:
    out: dict[str, str] = {}
    for name in policy.secrets.allowed_secrets:
        key = str(name or "").strip()
        if not key:
            continue
        val = os.environ.get(key)
        if val is not None:
            out[key] = val
    return out


def _is_security_violation(result: ExecutionResult) -> bool:
    txt = f"{result.stderr}\n{result.stdout}".lower()
    return any(
        p in txt
        for p in (
            "permission denied",
            "read-only file system",
            "temporary failure in name resolution",
            "network is unreachable",
            "urlerror",
        )
    )


def run_in_sandbox(
    db: Any,
    llm: Any,
    code: str,
    language: str = "python",
    session_id: str | None = None,
    data_sql: str | None = None,
    original_request: str = "",
    max_retries: int = _MAX_RETRIES_DEFAULT,
    langsmith_tags: list[str] | None = None,
    worker_id: str = "",
    image_override: str | None = None,
    inject_python_header: bool = True,
) -> ExecutionResult:
    """Bucle de auto-corrección del spec (sección 5).

    1. Si data_sql -> inyecta CSV en el workspace del sandbox (protocolo de firewall, sección 3).
    2. Ejecuta el código.
    3. Si falla, pide al LLM que corrija y reintenta (max_retries veces).
    4. Registra intención, código y resultado en LangSmith (sección 7).
    """
    if not _docker_available():
        return ExecutionResult(
            exit_code=1,
            stdout="",
            stderr=(
                "Docker no está disponible en este entorno. "
                "Instala y ejecuta Docker para usar el Sandbox de ejecución libre."
            ),
        )

    sid = session_id or uuid.uuid4().hex[:12]
    manager = _get_manager()
    policy = load_security_policy(worker_id or "default")
    secret_env = _load_allowed_secrets(policy)
    timeout_sec = max(1, min(int(policy.max_execution_time_seconds), 600))

    # Protocolo de firewall: inyectar datos si se requiere
    if data_sql:
        data_inject(db, data_sql, sid)

    lang = (language or "python").strip().lower()
    current_code = code
    result = ExecutionResult(exit_code=1, stdout="", stderr="No ejecutado aún.")
    tags = (langsmith_tags or []) + ["execution_environment:strix_sandbox"]
    if image_override:
        tags = tags + ["execution_environment:strix_browser"]

    for attempt in range(1, max_retries + 1):
        if lang == "python" and inject_python_header:
            exec_code = _inject_sandbox_python_header(current_code)
        else:
            exec_code = current_code
        result = manager.execute(
            sid,
            exec_code,
            language,
            policy=policy,
            secret_env=secret_env,
            timeout_seconds=timeout_sec,
            image_override=image_override,
        )
        result.attempts = attempt

        _langsmith_log(
            intent=original_request,
            code=current_code,
            result=result,
            attempt=attempt,
            tags=tags,
        )

        if result.success:
            break

        if attempt < max_retries and llm is not None:
            error_info = result.stderr or result.stdout or "Error desconocido"
            fix_prompt = _correction_prompt(original_request or code, current_code, error_info, attempt)
            try:
                fixed = llm.invoke(fix_prompt)
                fixed_text = (getattr(fixed, "content", None) or str(fixed) or "").strip()
                # Quitar fences de markdown si el modelo los añade
                fixed_text = re.sub(r"^```(?:python)?\s*", "", fixed_text, flags=re.MULTILINE)
                fixed_text = re.sub(r"```\s*$", "", fixed_text, flags=re.MULTILINE).strip()
                if fixed_text:
                    current_code = fixed_text
            except Exception:
                break

    if _is_security_violation(result):
        try:
            from duckclaw.graphs.on_the_fly_commands import append_task_audit

            append_task_audit(
                db,
                sid,
                worker_id or "sandbox",
                "strix sandbox security violation",
                "SECURITY_VIOLATION_ATTEMPT",
                0,
            )
        except Exception:
            pass
    return result


def _decoded_figure_looks_like_png_or_jpeg(b64: str) -> bool:
    """Evita usar placeholders compactados u otra basura como si fuera imagen."""
    if not isinstance(b64, str) or len(b64.strip()) < 80:
        return False
    low = b64.lower()
    if "omitido" in low or "[truncado" in low:
        return False
    t = "".join(b64.split())
    if t.lower().startswith("data:") and "," in t:
        t = t.split(",", 1)[1].strip()
    t = t.replace("-", "+").replace("_", "/")
    t = t.rstrip("=")
    rem = len(t) % 4
    if rem:
        t += "=" * (4 - rem)
    try:
        raw = base64.b64decode(t, validate=False)
    except Exception:
        return False
    if len(raw) < 24:
        return False
    if len(raw) >= 8 and raw[:8] == b"\x89PNG\r\n\x1a\n":
        return True
    if len(raw) >= 2 and raw[:2] == b"\xff\xd8":
        return True
    return False


def extract_latest_sandbox_figure_base64(messages: list[Any] | None) -> str | None:
    """
    Recorre mensajes del worker (p. ej. ToolMessage de run_sandbox) y devuelve el último
    `figure_base64` válido cuando exit_code == 0. Usado en el manager para enviar el PNG por Telegram.
    Ignora JSON compactado sin figura real (p. ej. sin clave figure_base64 o datos no imagen).
    """
    if not messages:
        return None
    try:
        from langchain_core.messages import ToolMessage
    except ImportError:
        return None

    last: str | None = None
    for m in messages:
        if not isinstance(m, ToolMessage):
            continue
        if getattr(m, "name", None) != "run_sandbox":
            continue
        raw = m.content
        if raw is None:
            continue
        s = raw if isinstance(raw, str) else str(raw)
        s = s.strip()
        if not s.startswith("{"):
            continue
        try:
            data = json.loads(s)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        if data.get("exit_code") != 0:
            continue
        b64 = data.get("figure_base64")
        if isinstance(b64, str) and _decoded_figure_looks_like_png_or_jpeg(b64):
            last = b64
    return last


def _langsmith_log(intent: str, code: str, result: ExecutionResult, attempt: int, tags: list[str]) -> None:
    """Trazabilidad forense (sección 7): registra en LangSmith si está configurado."""
    try:
        api_key = os.environ.get("LANGCHAIN_API_KEY") or os.environ.get("LANGSMITH_API_KEY")
        if not api_key or os.environ.get("LANGCHAIN_TRACING_V2", "").lower() not in ("true", "1"):
            return
        from langsmith import Client  # noqa: PLC0415

        from duckclaw.utils.langsmith_trace import create_completed_langsmith_run

        client = Client(api_key=api_key)
        create_completed_langsmith_run(
            client,
            name="StrixSandbox",
            run_type="tool",
            inputs={"intent": intent, "code": code, "attempt": attempt},
            outputs=result.to_dict(),
            tags=tags,
            extra={"metadata": {"execution_environment": "strix_sandbox"}},
        )
    except Exception:
        pass


# Import name (como en el traceback) -> nombre del paquete en pip cuando difiere.
_KNOWN_IMPORT_TO_PIP: dict[str, str] = {
    "PIL": "Pillow",
    "sklearn": "scikit-learn",
    "yaml": "PyYAML",
    "bs4": "beautifulsoup4",
    "cv2": "opencv-python-headless",
    "dateutil": "python-dateutil",
    "OpenSSL": "pyopenssl",
    "googleapiclient": "google-api-python-client",
}


def _missing_python_modules_from_traceback(text: str) -> list[str]:
    """Nombres de módulo citados en ModuleNotFoundError / ImportError (orden de aparición, sin duplicados)."""
    if not text.strip():
        return []
    seen: set[str] = set()
    out: list[str] = []
    for m in re.finditer(r"No module named ['\"]([^'\"]+)['\"]", text):
        name = (m.group(1) or "").strip()
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    if out:
        return out
    for m in re.finditer(r"No module named ([A-Za-z_][\w.]*)", text):
        name = (m.group(1) or "").strip()
        if not name or name in {"named"}:
            continue
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


def _import_name_to_pip_suggestion(import_name: str) -> str:
    """Sugiere el argumento de `pip install` (p. ej. sklearn -> scikit-learn)."""
    if import_name in _KNOWN_IMPORT_TO_PIP:
        return _KNOWN_IMPORT_TO_PIP[import_name]
    root = import_name.split(".", 1)[0]
    if root in _KNOWN_IMPORT_TO_PIP:
        return _KNOWN_IMPORT_TO_PIP[root]
    return root


def _pip_install_hints_for_missing_modules(modules: list[str]) -> tuple[list[str], str]:
    """(lista única de paquetes pip, línea recomendada para Dockerfile)."""
    seen: set[str] = set()
    pip_names: list[str] = []
    for mod in modules:
        pkg = _import_name_to_pip_suggestion(mod)
        if pkg not in seen:
            seen.add(pkg)
            pip_names.append(pkg)
    line = "pip install --no-cache-dir " + " ".join(pip_names) if pip_names else ""
    return pip_names, line


def _parquet_row_count(path: str) -> int | None:
    try:
        import pyarrow.parquet as pq  # noqa: PLC0415

        meta = pq.read_metadata(path)
        return int(meta.num_rows)
    except Exception:
        return None


def _browser_sandbox_summary(stdout: str, artifacts: list[str]) -> tuple[str, int | None, str | None]:
    """status corto, filas inferidas, nombre de archivo parquet si existe."""
    jobs: int | None = None
    file_hint: str | None = None
    for a in artifacts:
        if Path(a).suffix.lower() == ".parquet":
            file_hint = Path(a).name
            jobs = _parquet_row_count(a)
            break
    if jobs is None and stdout:
        m = re.search(r"(\d+)\s+vacantes", stdout, flags=re.IGNORECASE)
        if not m:
            m = re.search(r"Extracci[oó]n completada:\s*(\d+)", stdout, flags=re.IGNORECASE)
        if m:
            jobs = int(m.group(1))
    if jobs is not None and file_hint is None:
        file_hint = "osint_jobs.parquet"
    st = "success" if file_hint or (jobs is not None and jobs >= 0) else "completed"
    return st, jobs, file_hint


class MercenaryResultObject(BaseModel):
    """Contrato mínimo de /workspace/output/result.json (spec: Caged_Beast_Mercenary)."""

    model_config = ConfigDict(extra="allow")

    status: str
    directive_digest: str


def _mercenary_exchange_root() -> Path:
    return Path("/tmp/duckclaw_exchange")


def _mercenary_image_name() -> str:
    return (os.environ.get("STRIX_MERCENARY_IMAGE") or "").strip() or _image_name()


def _manager_template_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "forge" / "templates" / "Manager"


def _mercenary_security_policy() -> SecurityPolicy:
    md = _manager_template_dir()
    if md.is_dir():
        return load_security_policy("Manager", worker_dir=md)
    return load_security_policy("Manager")


def _mercenary_container_name(task_id: str) -> str:
    raw = (task_id or uuid.uuid4().hex)[:24]
    slug = re.sub(r"[^a-zA-Z0-9_.-]", "_", raw)
    if not slug:
        slug = "task"
    if not re.match(r"^[A-Za-z]", slug):
        slug = f"m_{slug}"
    return f"duckclaw_mercenary_{slug}"[:120]


def _mercenary_entrypoint_command() -> list[str]:
    code = (
        "import os,json,base64,hashlib,time;"
        "from pathlib import Path;"
        "raw=os.environ.get('MERCENARY_DIRECTIVE_B64') or '';"
        "d=base64.urlsafe_b64decode(raw.encode('ascii')).decode('utf-8','replace');"
        "h=hashlib.sha256(d.encode('utf-8')).hexdigest()[:16];"
        "out={'status':'stub_completed','directive_digest':h,'started_at':time.time(),'finished_at':time.time()};"
        "Path('/workspace/output/result.json').write_text(json.dumps(out),encoding='utf-8')"
    )
    return ["python3", "-c", code]


def _mercenary_run_blocking(directive: str, limit: int, tid: str) -> dict[str, Any]:
    import docker  # noqa: PLC0415
    import docker.errors  # noqa: PLC0415

    exchange = _mercenary_exchange_root() / tid
    policy = _mercenary_security_policy()
    b64 = base64.urlsafe_b64encode(directive.strip().encode("utf-8")).decode("ascii")

    client = _docker_client()
    cname = _mercenary_container_name(tid)
    try:
        old = client.containers.get(cname)
        old.remove(force=True)
    except docker.errors.NotFound:
        pass
    except Exception:
        pass

    exchange.mkdir(parents=True, exist_ok=True)
    policy_kw = security_policy_to_docker_kwargs(policy)
    tmpfs = {
        k: v
        for k, v in (policy_kw.get("tmpfs") or {}).items()
        if str(k).rstrip("/") not in {"/workspace/output", "/workspace"}
    }
    volumes = {str(exchange.resolve()): {"bind": "/workspace/output", "mode": "rw"}}
    env = {"PYTHONUNBUFFERED": "1", "MERCENARY_DIRECTIVE_B64": b64}
    img = _ensure_image(client, _mercenary_image_name(), allow_python_fallback=True)
    run_kw: dict[str, Any] = {
        "command": _mercenary_entrypoint_command(),
        "name": cname,
        "detach": True,
        "mem_limit": str(policy_kw.get("mem_limit", "512m")),
        "nano_cpus": int(policy_kw.get("nano_cpus", int(1e9))),
        "network_mode": str(policy_kw.get("network_mode", "none")),
        "cap_drop": policy_kw.get("cap_drop", ["ALL"]),
        "security_opt": policy_kw.get("security_opt", ["no-new-privileges"]),
        "user": str(policy_kw.get("user", "1000:1000")),
        "volumes": volumes,
        "tmpfs": tmpfs,
        "working_dir": "/workspace",
        "environment": env,
        "remove": False,
    }

    container: Any = None
    exit_code = 1
    _log.info("mercenary: create/start name=%s image=%s timeout=%ss", cname, img, limit)
    try:
        container = client.containers.run(img, **run_kw)
        with ThreadPoolExecutor(max_workers=1) as pool:
            fut = pool.submit(container.wait)
            try:
                wait_out = fut.result(timeout=limit)
                exit_code = int((wait_out or {}).get("StatusCode", 1))
            except FuturesTimeout:
                _log.warning("mercenary: timeout after %ss task_id=%s", limit, tid[:12])
                try:
                    container.kill()
                except Exception:
                    pass
                return {
                    "ok": False,
                    "error_code": "MERCENARY_TIMEOUT",
                    "message": f"Tiempo agotado ({limit}s)",
                }
    except Exception as exc:
        _log.exception("mercenary: docker run/wait failed: %s", exc)
        return {
            "ok": False,
            "error_code": "MERCENARY_CONTAINER_ERROR",
            "message": str(exc)[:2000],
        }
    finally:
        if container is not None:
            try:
                container.remove(force=True)
            except Exception:
                pass

    result_path = exchange / "result.json"
    if not result_path.is_file():
        shutil.rmtree(exchange, ignore_errors=True)
        return {
            "ok": False,
            "error_code": "MERCENARY_RESULT_MISSING",
            "message": "result.json no encontrado tras la ejecución",
        }
    try:
        data = json.loads(result_path.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        shutil.rmtree(exchange, ignore_errors=True)
        return {
            "ok": False,
            "error_code": "MERCENARY_JSON_INVALID",
            "message": f"JSON inválido: {exc}",
        }
    if not isinstance(data, dict):
        shutil.rmtree(exchange, ignore_errors=True)
        return {
            "ok": False,
            "error_code": "MERCENARY_JSON_INVALID",
            "message": "result.json debe ser un objeto JSON",
        }
    try:
        MercenaryResultObject.model_validate(data)
    except ValidationError as exc:
        shutil.rmtree(exchange, ignore_errors=True)
        return {
            "ok": False,
            "error_code": "MERCENARY_JSON_INVALID",
            "message": str(exc)[:1500],
        }
    if exit_code != 0:
        shutil.rmtree(exchange, ignore_errors=True)
        return {
            "ok": False,
            "error_code": "MERCENARY_CONTAINER_ERROR",
            "message": f"Contenedor salió con código {exit_code}",
            "result": data,
        }
    shutil.rmtree(exchange, ignore_errors=True)
    _log.info("mercenary: completed task_id=%s", tid[:12])
    return {"ok": True, "result": data, "exit_code": exit_code}


async def run_mercenary_ephemeral_async(
    directive: str,
    timeout_s: int,
    *,
    task_id: str | None = None,
) -> dict[str, Any]:
    if not (directive or "").strip():
        return {"ok": False, "error_code": "MERCENARY_INVALID_INPUT", "message": "directive vacío"}
    limit = max(1, min(int(timeout_s), 600))
    if not _docker_available():
        return {
            "ok": False,
            "error_code": "MERCENARY_DOCKER_UNAVAILABLE",
            "message": "Docker no disponible o daemon inaccesible",
        }
    tid = ((task_id or "").strip() or uuid.uuid4().hex)[:32]
    return await asyncio.to_thread(_mercenary_run_blocking, directive.strip(), limit, tid)


def run_mercenary_ephemeral(directive: str, timeout_s: int = 300, *, task_id: str | None = None) -> dict[str, Any]:
    """Ejecuta el mercenario desde código síncrono (p. ej. nodo LangGraph)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(run_mercenary_ephemeral_async(directive, timeout_s, task_id=task_id))
    with ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(
            asyncio.run,
            run_mercenary_ephemeral_async(directive, timeout_s, task_id=task_id),
        )
        return fut.result()


def browser_sandbox_tool_factory(db: Any, llm: Any) -> Any:
    """StructuredTool `run_browser_sandbox` — imagen STRIX_BROWSER_IMAGE, salida Parquet en /workspace/output/."""
    from langchain_core.tools import StructuredTool  # noqa: PLC0415

    def _run(
        code: str,
        language: str = "python",
        data_sql: str = "",
        session_id: str = "",
        worker_id: str = "",
    ) -> str:
        result = run_in_sandbox(
            db=db,
            llm=llm,
            code=code,
            language=language or "python",
            session_id=session_id or uuid.uuid4().hex[:12],
            data_sql=data_sql or None,
            original_request=code,
            worker_id=worker_id or "",
            image_override=_browser_image_name(),
            inject_python_header=False,
        )
        st, jobs_n, parquet_name = _browser_sandbox_summary(result.stdout or "", result.artifacts or [])
        out: dict[str, Any] = {
            "exit_code": result.exit_code,
            "status": st if result.exit_code == 0 else "error",
            "jobs_extracted": jobs_n,
            "file": parquet_name,
            "stdout_tail": (result.stdout or "")[-_BROWSER_SANDBOX_STDOUT_TAIL:],
            "stderr_tail": (result.stderr or "")[-_BROWSER_SANDBOX_STDERR_TAIL:],
        }
        if result.artifacts:
            out["artifacts"] = result.artifacts
        if result.timed_out:
            out["warning"] = "Timeout alcanzado"
        if result.attempts > 1:
            out["auto_corrected_attempts"] = result.attempts
        if result.exit_code != 0:
            raw_err = (result.stderr or result.stdout or "error desconocido").strip()
            err_snip = raw_err[:1500]
            missing_mods = _missing_python_modules_from_traceback(raw_err)
            if missing_mods:
                pip_pkgs, pip_line = _pip_install_hints_for_missing_modules(missing_mods)
                out["missing_pip_packages"] = pip_pkgs
                out["hint"] = (
                    f"{err_snip}\n\nMódulos no encontrados: {', '.join(missing_mods)}.\n"
                    f"Añade en docker/browser-env/Dockerfile: {pip_line}\n"
                    "Reconstruye: docker build -t duckclaw/browser-env:latest docker/browser-env/\n"
                    "Variables: STRIX_BROWSER_IMAGE (opcional)."
                )
            else:
                out["hint"] = err_snip
        compact_keys = (
            "exit_code",
            "status",
            "jobs_extracted",
            "file",
            "stdout_tail",
            "stderr_tail",
            "artifacts",
            "warning",
            "auto_corrected_attempts",
            "hint",
            "missing_pip_packages",
        )
        # compact_keys incluye stdout_tail/stderr_tail para el contrato con el LLM (MQL5, diagnósticos).
        return json.dumps({k: out[k] for k in compact_keys if k in out}, ensure_ascii=False)

    return StructuredTool.from_function(
        _run,
        name="run_browser_sandbox",
        description=(
            "Ejecuta código Python (o bash) en el Strix **browser** sandbox: Chromium vía **Playwright** "
            "(import: playwright.async_api), Xvfb y red según security_policy.yaml del worker. "
            "No uses el paquete Python `browser_use` en código generado (API inestable). "
            "**Estándar de sigilo (recomendado en scripts generados):** "
            "usar contexto persistente para cookies/sesión: "
            "p.chromium.launch_persistent_context(user_data_dir=os.environ.get('STRIX_CHROME_PROFILE_DIR','/workspace/chrome_profile'), "
            "headless=True, args=['--disable-blink-features=AutomationControlled'], user_agent=..., viewport=...); "
            "si no usas contexto persistente, crea browser.new_context con user_agent realista (no el default de Playwright), viewport ~1920x1080, "
            "extra_http_headers con Accept-Language (es-ES,en-US,…); si la URL es mql5.com, Referer https://www.mql5.com/ ; "
            "page.add_init_script para ocultar navigator.webdriver; "
            "Navegación: en **mql5.com** sigue la plantilla `finanz/snippets/mql5_playwright_stealth.py`: "
            "wait_until='networkidle', luego wait_for_timeout(5000) para hidratación SPA, y código vía "
            "`pre, code, .b-code-block, textarea.mql4`. En otros sitios (p. ej. muchos trackers) suele ir mejor "
            "domcontentloaded + wait_for_selector acotado. "
            "**Contrato de salida:** imprime JSON o texto útil a stdout; la tool devuelve stdout_tail/stderr_tail para el agente. "
            "OSINT JobHunter: resúmenes en stdout y/o `/workspace/output/osint_jobs.parquet` (no volcar HTML masivo). "
            "Tras Parquet, `read_sql` con read_parquet y rutas en `artifacts`. "
            "Parámetros: code, language ('python'|'bash'), data_sql opcional, session_id, worker_id."
        ),
    )


def sandbox_tool_factory(db: Any, llm: Any) -> Any:
    """Crea el StructuredTool 'run_sandbox' para usar en general_graph.

    Parámetros de entrada para el LLM:
    - code: código Python o Bash a ejecutar
    - language: 'python' (default) o 'bash'
    - data_sql: SQL opcional — el resultado se monta como data.csv dentro del sandbox
    - session_id: identificador de sesión (reutiliza contenedor si ya existe)
    """
    from langchain_core.tools import StructuredTool  # noqa: PLC0415

    def _run(
        code: str,
        language: str = "python",
        data_sql: str = "",
        session_id: str = "",
        worker_id: str = "",
    ) -> str:
        result = run_in_sandbox(
            db=db,
            llm=llm,
            code=code,
            language=language or "python",
            session_id=session_id or uuid.uuid4().hex[:12],
            data_sql=data_sql or None,
            original_request=code,
            worker_id=worker_id or "",
        )
        out = {
            "exit_code": result.exit_code,
            "output": result.stdout or result.stderr,
            "stdout": result.stdout or "",
            "figure_base64": None,
        }
        if result.artifacts:
            out["artifacts"] = result.artifacts
            for art in result.artifacts:
                ap = Path(str(art))
                if ap.suffix.lower() == ".png" and ap.is_file():
                    try:
                        out["figure_base64"] = base64.standard_b64encode(ap.read_bytes()).decode("ascii")
                        break
                    except OSError:
                        continue
        if result.timed_out:
            out["warning"] = "Timeout alcanzado"
        if result.attempts > 1:
            out["auto_corrected_attempts"] = result.attempts
        if result.exit_code != 0:
            raw_err = (result.stderr or result.stdout or "error desconocido").strip()
            err_snip = raw_err[:1500]
            missing_mods = _missing_python_modules_from_traceback(raw_err)
            if missing_mods:
                pip_pkgs, pip_line = _pip_install_hints_for_missing_modules(missing_mods)
                out["missing_pip_packages"] = pip_pkgs
                out["output"] = (
                    f"Error en Sandbox: {err_snip}\n\n"
                    f"Módulos no encontrados en la imagen del sandbox: {', '.join(missing_mods)}.\n"
                    f"Para habilitarlos, añade en docker/sandbox/Dockerfile (junto al resto de pip): "
                    f"{pip_line}\n"
                    "Luego reconstruye la imagen del sandbox (docker build …) y reinicia el gateway.\n"
                    "También revisa nombres de columnas y datos; no uses librerías externas no listadas en la imagen."
                )
            else:
                out["output"] = (
                    f"Error en Sandbox: {err_snip}. Por favor, verifica los nombres de las columnas y "
                    "asegúrate de no usar librerías externas no listadas."
                )
        return json.dumps(out, ensure_ascii=False)

    return StructuredTool.from_function(
        _run,
        name="run_sandbox",
        description=(
            "Ejecuta código Python o Bash en un sandbox Docker aislado (sin acceso a red ni al host). "
            "Usa cuando el usuario pida ejecutar scripts, análisis complejos, modelos, gráficos dinámicos o código libre. "
            "Para PNG con matplotlib: guardar en /workspace/output/ con savefig(dpi=100, facecolor='white', edgecolor='none'). "
            "Parámetros: code (str), language ('python'|'bash'), data_sql (SQL para inyectar datos), session_id (str), worker_id (str opcional para política)."
        ),
    )
