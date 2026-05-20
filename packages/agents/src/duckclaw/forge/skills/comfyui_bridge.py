"""
ComfyUI Bridge — generación visual vía API REST + WebSocket.

Specs:
- specs/features/platform/COMFYUI_VISUAL_BRIDGE.md (txt2img)
- specs/features/platform/COMFYUI_IMAGE_EDIT.md (img2img)
Requiere: COMFYUI_API_URL (default http://127.0.0.1:8188 si no se define en .env).
"""

from __future__ import annotations

import base64
import copy
import json
import logging
import os
import random
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Optional
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

from duckclaw.utils.logger import log_tool_execution_sync

_log = logging.getLogger(__name__)

_DEFAULT_COMFY_URL = "http://127.0.0.1:8188"
_HTTP_TIMEOUT_SEC = 60.0
_MAX_B64_IN_TOOL_RESPONSE = 500_000
_WORKFLOWS_DIR = Path(__file__).resolve().parent.parent / "templates" / "workflows"

_comfy_jobs_lock = threading.Lock()
_comfy_jobs: dict[str, dict[str, Any]] = {}


class ComfyGenerationCancelled(Exception):
    """El usuario o el gateway canceló la generación en curso."""


def register_comfy_generation(chat_id: str, *, base_url: str, prompt_id: str) -> None:
    cid = (chat_id or "").strip()
    if not cid:
        return
    with _comfy_jobs_lock:
        _comfy_jobs[cid] = {
            "base_url": base_url.rstrip("/"),
            "prompt_id": prompt_id,
            "cancelled": False,
        }


def clear_comfy_generation(chat_id: str) -> None:
    cid = (chat_id or "").strip()
    if not cid:
        return
    with _comfy_jobs_lock:
        _comfy_jobs.pop(cid, None)


def is_comfy_generation_cancelled(chat_id: str) -> bool:
    cid = (chat_id or "").strip()
    if not cid:
        return False
    with _comfy_jobs_lock:
        rec = _comfy_jobs.get(cid)
        return bool(rec and rec.get("cancelled"))


def clear_all_comfy_generations() -> list[str]:
    """Marca cancelados todos los jobs registrados (p. ej. al reiniciar gateway)."""
    with _comfy_jobs_lock:
        chat_ids = list(_comfy_jobs.keys())
        for rec in _comfy_jobs.values():
            rec["cancelled"] = True
    return chat_ids


def _queue_prompt_ids(queue_payload: Any) -> list[str]:
    """Extrae prompt_id de queue_running y queue_pending."""
    if not isinstance(queue_payload, dict):
        return []
    ids: list[str] = []
    for key in ("queue_running", "queue_pending"):
        items = queue_payload.get(key)
        if not isinstance(items, list):
            continue
        for entry in items:
            if isinstance(entry, (list, tuple)) and len(entry) > 1:
                pid = str(entry[1] or "").strip()
                if pid:
                    ids.append(pid)
    return ids


def interrupt_comfy_runtime(base_url: str | None = None) -> dict[str, Any]:
    """POST /interrupt sin vaciar la cola (cancelación por chat / SSE abort)."""
    base = (base_url or _comfy_base_url()).strip().rstrip("/")
    if not base:
        return {"ok": False, "skipped": True, "reason": "COMFYUI_API_URL unset"}
    result: dict[str, Any] = {"ok": True, "base_url": base, "interrupt": False, "errors": []}
    try:
        _http_json("POST", f"{base}/interrupt", {})
        result["interrupt"] = True
    except Exception as exc:
        result["ok"] = False
        result["errors"].append(f"interrupt:{type(exc).__name__}:{exc}")
    return result


def reset_comfyui_runtime(base_url: str | None = None) -> dict[str, Any]:
    """
    Interrumpe ejecución en curso y vacía la cola pendiente de ComfyUI (best-effort).
    Útil al reiniciar ComfyUI o el gateway para evitar trabajos huérfanos.
    """
    base = (base_url or _comfy_base_url()).strip().rstrip("/")
    if not base:
        return {"ok": False, "skipped": True, "reason": "COMFYUI_API_URL unset"}
    result: dict[str, Any] = {
        "ok": True,
        "base_url": base,
        "interrupt": False,
        "deleted_pending": 0,
        "errors": [],
    }
    pending_ids: list[str] = []
    try:
        queue_data = _http_json("GET", f"{base}/queue", None, timeout=10.0)
        pending_ids = _queue_prompt_ids(queue_data)
    except Exception as exc:
        result["errors"].append(f"queue_read:{type(exc).__name__}:{exc}")
    if pending_ids:
        try:
            _http_json("POST", f"{base}/interrupt", {})
            result["interrupt"] = True
        except Exception as exc:
            result["errors"].append(f"interrupt:{type(exc).__name__}:{exc}")
        try:
            _http_json("POST", f"{base}/queue", {"delete": pending_ids}, timeout=10.0)
            result["deleted_pending"] = len(pending_ids)
        except Exception as exc:
            result["errors"].append(f"queue_delete:{type(exc).__name__}:{exc}")
    else:
        result["skipped_interrupt"] = True
    if result["errors"]:
        result["ok"] = bool(result["interrupt"] or result["deleted_pending"])
    _agent_dbg(
        "H6",
        "comfyui_bridge:reset_comfyui_runtime",
        "done",
        {
            "interrupt": result["interrupt"],
            "deleted_pending": result["deleted_pending"],
            "errors": result["errors"][:3],
        },
    )
    return result


def cancel_comfy_generation_for_chat(chat_id: str) -> bool:
    """Marca cancelación y POST /interrupt en ComfyUI (best-effort)."""
    cid = (chat_id or "").strip()
    if not cid:
        return False
    with _comfy_jobs_lock:
        rec = _comfy_jobs.get(cid)
        if not rec:
            return False
        rec["cancelled"] = True
        base_url = str(rec.get("base_url") or _comfy_base_url()).rstrip("/")
    try:
        interrupt_comfy_runtime(base_url)
        _agent_dbg("H5", "comfyui_bridge:cancel_comfy_generation_for_chat", "interrupt_ok", {"chat_id": cid})
    except Exception as exc:
        _log.warning("ComfyUI /interrupt failed chat_id=%s: %s", cid, exc)
        _agent_dbg(
            "H5",
            "comfyui_bridge:cancel_comfy_generation_for_chat",
            "interrupt_failed",
            {"chat_id": cid, "err": type(exc).__name__},
        )
    return True


def _raise_if_comfy_cancelled(chat_id: str) -> None:
    if is_comfy_generation_cancelled(chat_id):
        raise ComfyGenerationCancelled("Generación de imagen cancelada.")


def _comfy_base_url() -> str:
    raw = (os.environ.get("COMFYUI_API_URL") or _DEFAULT_COMFY_URL).strip().rstrip("/")
    return raw


def _comfy_timeout_sec() -> float:
    try:
        return float(os.environ.get("COMFYUI_TIMEOUT_SEC") or "420")
    except ValueError:
        return 420.0


def _agent_dbg(hypothesis_id: str, location: str, message: str, data: dict[str, Any]) -> None:
    # #region agent log
    try:
        line = json.dumps(
            {
                "sessionId": "fd1dbb",
                "hypothesisId": hypothesis_id,
                "location": location,
                "message": message,
                "data": data,
                "timestamp": int(time.time() * 1000),
            }
        )
        with open(
            "/Users/juanjosearevalocamargo/Desktop/duckclaw/.cursor/debug-fd1dbb.log",
            "a",
            encoding="utf-8",
        ) as _f:
            _f.write(line + "\n")
    except OSError:
        pass
    # #endregion


def _default_img2img_denoise() -> float:
    try:
        return float(os.environ.get("COMFYUI_IMG2IMG_DENOISE") or "0.55")
    except ValueError:
        return 0.55


def _comfy_ws_url(base_http: str, client_id: str) -> str:
    parsed = urllib_parse.urlparse(base_http)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    host = parsed.netloc or parsed.path
    return f"{scheme}://{host}/ws?clientId={urllib_parse.quote(client_id)}"


def _http_json(
    method: str,
    url: str,
    body: dict[str, Any] | None = None,
    *,
    timeout: float = _HTTP_TIMEOUT_SEC,
) -> Any:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib_request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib_request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib_error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        raise ValueError(f"ComfyUI HTTP {getattr(e, 'code', '?')}: {err_body[:500]}") from e
    except urllib_error.URLError as e:
        raise ValueError(f"No se pudo conectar con ComfyUI en {url}: {e}") from e
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError("ComfyUI devolvió un cuerpo que no es JSON válido.") from e


def _http_bytes(url: str, *, timeout: float = _HTTP_TIMEOUT_SEC) -> bytes:
    req = urllib_request.Request(url, method="GET")
    try:
        with urllib_request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib_error.HTTPError as e:
        raise ValueError(f"ComfyUI HTTP {getattr(e, 'code', '?')} al descargar imagen.") from e
    except urllib_error.URLError as e:
        raise ValueError(f"No se pudo descargar imagen desde ComfyUI: {e}") from e


def load_workflow_template(name: str) -> tuple[dict[str, Any], dict[str, Any]]:
    stem = (name or "comfy_default").strip() or "comfy_default"
    wf_path = _WORKFLOWS_DIR / f"{stem}.json"
    meta_path = _WORKFLOWS_DIR / f"{stem}.meta.json"
    if not wf_path.is_file():
        raise FileNotFoundError(f"Workflow ComfyUI no encontrado: {wf_path}")
    workflow = json.loads(wf_path.read_text(encoding="utf-8"))
    meta: dict[str, Any] = {}
    if meta_path.is_file():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if not isinstance(workflow, dict):
        raise ValueError(f"Workflow {stem} debe ser un objeto JSON (formato API).")
    return workflow, meta if isinstance(meta, dict) else {}


def inject_clip_prompts(
    workflow: dict[str, Any],
    positive: str,
    negative: str,
    meta: dict[str, Any],
) -> dict[str, Any]:
    wf = copy.deepcopy(workflow)
    pos_ids = [str(x) for x in (meta.get("positive_clip_nodes") or [])]
    neg_ids = [str(x) for x in (meta.get("negative_clip_nodes") or [])]
    clip_nodes = [
        (nid, node)
        for nid, node in wf.items()
        if isinstance(node, dict) and node.get("class_type") == "CLIPTextEncode"
    ]
    if not pos_ids and clip_nodes:
        pos_ids = [clip_nodes[0][0]]
    if not neg_ids and len(clip_nodes) > 1:
        neg_ids = [clip_nodes[1][0]]
    for nid in pos_ids:
        node = wf.get(nid)
        if isinstance(node, dict) and "inputs" in node:
            node["inputs"]["text"] = positive
    for nid in neg_ids:
        node = wf.get(nid)
        if isinstance(node, dict) and "inputs" in node:
            node["inputs"]["text"] = negative or ""
    return wf


def list_comfy_checkpoints(base_url: str) -> list[str]:
    """Lista checkpoints visibles para CheckpointLoaderSimple en ComfyUI."""
    try:
        info = _http_json("GET", f"{base_url.rstrip('/')}/object_info/CheckpointLoaderSimple")
    except (ValueError, OSError) as e:
        _log.debug("list_comfy_checkpoints failed: %s", e)
        return []
    if not isinstance(info, dict):
        return []
    node = info.get("CheckpointLoaderSimple")
    if not isinstance(node, dict):
        return []
    required = node.get("input", {}).get("required", {})
    if not isinstance(required, dict):
        return []
    ckpt_cfg = required.get("ckpt_name")
    if isinstance(ckpt_cfg, list) and ckpt_cfg and isinstance(ckpt_cfg[0], list):
        return [str(x) for x in ckpt_cfg[0] if str(x).strip()]
    return []


def apply_checkpoint(
    workflow: dict[str, Any],
    meta: dict[str, Any],
    base_url: str,
) -> tuple[dict[str, Any], Optional[str]]:
    """
    Asigna ckpt_name al nodo CheckpointLoaderSimple.
    Devuelve (workflow, error) si no hay ningún checkpoint instalado.
    """
    available = list_comfy_checkpoints(base_url)
    preferred = str(meta.get("default_ckpt_name") or "v1-5-pruned-emaonly.safetensors").strip()
    chosen: Optional[str] = None
    if preferred and preferred in available:
        chosen = preferred
    elif available:
        chosen = available[0]
    else:
        home = (os.environ.get("COMFYUI_HOME") or os.path.expanduser("~/ComfyUI")).strip()
        return workflow, (
            "No hay checkpoints en ComfyUI. Copia un modelo .safetensors o .ckpt en "
            f"{home}/models/checkpoints/ "
            "(por ejemplo SD 1.5). Reinicia ComfyUI (pm2 restart ComfyUI) y vuelve a generar."
        )

    wf = copy.deepcopy(workflow)
    loader_id = str(meta.get("checkpoint_loader_node") or "").strip()
    if not loader_id:
        for nid, node in wf.items():
            if isinstance(node, dict) and node.get("class_type") == "CheckpointLoaderSimple":
                loader_id = str(nid)
                break
    if loader_id and loader_id in wf:
        node = wf[loader_id]
        if isinstance(node, dict) and isinstance(node.get("inputs"), dict):
            node["inputs"]["ckpt_name"] = chosen
    return wf, None


def apply_aspect_ratio(
    workflow: dict[str, Any],
    aspect_ratio: str,
    meta: dict[str, Any],
) -> dict[str, Any]:
    wf = copy.deepcopy(workflow)
    ratio = (aspect_ratio or "1:1").strip()
    presets = meta.get("aspect_presets") if isinstance(meta.get("aspect_presets"), dict) else {}
    dims = presets.get(ratio)
    if not isinstance(dims, (list, tuple)) or len(dims) < 2:
        dims = presets.get("1:1", [1024, 1024])
    width, height = int(dims[0]), int(dims[1])
    latent_id = str(meta.get("latent_image_node") or "").strip()
    if latent_id and latent_id in wf:
        node = wf[latent_id]
        if isinstance(node, dict) and isinstance(node.get("inputs"), dict):
            node["inputs"]["width"] = width
            node["inputs"]["height"] = height
            return wf
    for node in wf.values():
        if isinstance(node, dict) and node.get("class_type") == "EmptyLatentImage":
            if isinstance(node.get("inputs"), dict):
                node["inputs"]["width"] = width
                node["inputs"]["height"] = height
            break
    return wf


def inject_load_image(workflow: dict[str, Any], uploaded_name: str, meta: dict[str, Any]) -> dict[str, Any]:
    wf = copy.deepcopy(workflow)
    nid = str(meta.get("load_image_node") or "").strip()
    if not nid:
        for k, node in wf.items():
            if isinstance(node, dict) and node.get("class_type") == "LoadImage":
                nid = str(k)
                break
    if nid and nid in wf:
        node = wf[nid]
        if isinstance(node, dict) and isinstance(node.get("inputs"), dict):
            node["inputs"]["image"] = (uploaded_name or "").strip()
    return wf


def _comfy_sampler_steps() -> Optional[int]:
    raw = (os.environ.get("COMFYUI_SAMPLER_STEPS") or "").strip()
    if not raw:
        return None
    try:
        steps = int(raw)
    except ValueError:
        return None
    return max(4, min(50, steps))


def apply_sampler_steps(workflow: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    """Aplica COMFYUI_SAMPLER_STEPS al KSampler del workflow (admin / tuning)."""
    steps = _comfy_sampler_steps()
    if steps is None:
        return workflow
    wf = copy.deepcopy(workflow)
    nid = str(meta.get("ksampler_node") or "3").strip() or "3"
    node = wf.get(nid)
    if isinstance(node, dict) and isinstance(node.get("inputs"), dict):
        node["inputs"]["steps"] = steps
        return wf
    for n in wf.values():
        if isinstance(n, dict) and n.get("class_type") == "KSampler":
            if isinstance(n.get("inputs"), dict):
                n["inputs"]["steps"] = steps
            break
    return wf


def inject_ksampler_denoise(workflow: dict[str, Any], denoise: float, meta: dict[str, Any]) -> dict[str, Any]:
    wf = copy.deepcopy(workflow)
    nid = str(meta.get("ksampler_node") or "3").strip() or "3"
    node = wf.get(nid)
    if isinstance(node, dict) and isinstance(node.get("inputs"), dict):
        node["inputs"]["denoise"] = max(0.05, min(1.0, float(denoise)))
    else:
        for n in wf.values():
            if isinstance(n, dict) and n.get("class_type") == "KSampler":
                if isinstance(n.get("inputs"), dict):
                    n["inputs"]["denoise"] = max(0.05, min(1.0, float(denoise)))
                break
    return wf


def _allowed_source_roots(tenant_id: str) -> list[Path]:
    from duckclaw.vaults import user_vault_dir

    tid = (tenant_id or "default").strip() or "default"
    base = user_vault_dir(tid).resolve()
    return [(base / "inbound").resolve(), (base / "artifacts").resolve()]


def validate_source_image_path(file_path: str, tenant_id: str) -> Path:
    raw = (file_path or "").strip()
    if not raw:
        raise ValueError("source_image_path vacío")
    try:
        resolved = Path(raw).resolve()
    except OSError as e:
        raise ValueError(f"Ruta inválida: {raw}") from e
    if resolved.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
        raise ValueError("source_image_path debe ser .png, .jpg, .jpeg o .webp")
    if not resolved.is_file():
        raise ValueError(f"Archivo no encontrado: {resolved}")
    allowed = _allowed_source_roots(tenant_id)
    if not any(str(resolved).startswith(str(root)) for root in allowed):
        raise ValueError("source_image_path fuera de inbound/ o artifacts/ del tenant")
    return resolved


def upload_image_to_comfy(local_path: Path, base_url: str) -> str:
    """POST /upload/image; retorna el nombre de archivo en el input de ComfyUI."""
    file_bytes = local_path.read_bytes()
    filename = local_path.name or "input.png"
    boundary = f"----duckclaw{uuid.uuid4().hex}"
    crlf = b"\r\n"
    parts: list[bytes] = [
        f"--{boundary}".encode(),
        b'Content-Disposition: form-data; name="image"; filename="' + filename.encode() + b'"',
        b"Content-Type: application/octet-stream",
        b"",
        file_bytes,
        f"--{boundary}--".encode(),
        b"",
    ]
    body = crlf.join(parts)
    url = f"{base_url.rstrip('/')}/upload/image"
    req = urllib_request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib_request.urlopen(req, timeout=_HTTP_TIMEOUT_SEC) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib_error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        raise ValueError(f"ComfyUI upload HTTP {getattr(e, 'code', '?')}: {err_body[:300]}") from e
    except urllib_error.URLError as e:
        raise ValueError(f"No se pudo subir imagen a ComfyUI: {e}") from e
    data = json.loads(raw) if raw.strip() else {}
    if not isinstance(data, dict):
        raise ValueError("ComfyUI /upload/image no devolvió JSON válido.")
    name = str(data.get("name") or "").strip()
    if not name:
        raise ValueError(f"ComfyUI upload sin nombre de archivo: {data}")
    return name


def tenant_inbound_dir(tenant_id: str) -> Path:
    from duckclaw.vaults import user_vault_dir

    tid = (tenant_id or "default").strip() or "default"
    path = user_vault_dir(tid) / "inbound"
    path.mkdir(parents=True, exist_ok=True)
    return path


def queue_prompt(workflow: dict[str, Any], client_id: str, base_url: str) -> str:
    payload = {"prompt": workflow, "client_id": client_id}
    resp = _http_json("POST", f"{base_url}/prompt", payload)
    if not isinstance(resp, dict):
        raise ValueError("ComfyUI /prompt no devolvió un objeto JSON.")
    prompt_id = str(resp.get("prompt_id") or "").strip()
    if not prompt_id:
        node_errors = resp.get("node_errors")
        raise ValueError(f"ComfyUI rechazó el workflow: {node_errors or resp}")
    _agent_dbg(
        "H7",
        "comfyui_bridge:queue_prompt",
        "queued",
        {"prompt_id": prompt_id, "base_url": base_url},
    )
    return prompt_id


def _history_prompt_finished(prompt_id: str, base_url: str) -> bool:
    """True si /history ya tiene imagen de salida para el prompt."""
    try:
        resolve_output_image(prompt_id, base_url)
        return True
    except ValueError:
        return False


def _poll_history_until_done(
    prompt_id: str,
    base_url: str,
    deadline: float,
    *,
    chat_id: str = "",
) -> None:
    """Fallback HTTP cuando el WS se cae pero ComfyUI sigue generando."""
    while time.monotonic() < deadline:
        _raise_if_comfy_cancelled(chat_id)
        if _history_prompt_finished(prompt_id, base_url):
            _agent_dbg(
                "H1",
                "comfyui_bridge:_poll_history_until_done",
                "history_ready",
                {"prompt_id": prompt_id},
            )
            return
        time.sleep(2.0)
    raise TimeoutError(
        f"ComfyUI no completó el prompt {prompt_id} en el tiempo límite (poll /history)."
    )


def wait_for_completion(
    prompt_id: str,
    client_id: str,
    base_url: str,
    *,
    timeout_sec: float,
    chat_id: str = "",
) -> None:
    ws_url = _comfy_ws_url(base_url, client_id)
    deadline = time.monotonic() + timeout_sec
    _agent_dbg(
        "H2",
        "comfyui_bridge:wait_for_completion",
        "start",
        {"prompt_id": prompt_id, "timeout_sec": timeout_sec},
    )
    if _history_prompt_finished(prompt_id, base_url):
        _agent_dbg(
            "H3",
            "comfyui_bridge:wait_for_completion",
            "already_in_history",
            {"prompt_id": prompt_id},
        )
        return

    try:
        from websockets.sync.client import connect
    except ImportError as e:
        raise ValueError("Paquete websockets no disponible para ComfyUI.") from e

    ws_exc: BaseException | None = None
    try:
        # Sin ping automático: durante SD en MPS ComfyUI puede no responder pings
        # mientras carga el modelo (~4 min) y el cliente cierra con 1011.
        with connect(
            ws_url,
            open_timeout=30,
            close_timeout=5,
            ping_interval=None,
        ) as ws:
            while time.monotonic() < deadline:
                _raise_if_comfy_cancelled(chat_id)
                if _history_prompt_finished(prompt_id, base_url):
                    _agent_dbg(
                        "H1",
                        "comfyui_bridge:wait_for_completion",
                        "history_ready_during_ws",
                        {"prompt_id": prompt_id},
                    )
                    return
                remaining = max(1.0, deadline - time.monotonic())
                try:
                    raw = ws.recv(timeout=min(30.0, remaining))
                except TimeoutError:
                    continue
                if isinstance(raw, bytes):
                    continue
                try:
                    message = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if not isinstance(message, dict):
                    continue
                if message.get("type") != "executing":
                    continue
                data = message.get("data")
                if not isinstance(data, dict):
                    continue
                if str(data.get("prompt_id") or "") != prompt_id:
                    continue
                if data.get("node") is None:
                    _agent_dbg(
                        "H2",
                        "comfyui_bridge:wait_for_completion",
                        "ws_executing_done",
                        {"prompt_id": prompt_id},
                    )
                    return
    except Exception as exc:
        ws_exc = exc
        _agent_dbg(
            "H1",
            "comfyui_bridge:wait_for_completion",
            "ws_failed_fallback_poll",
            {"prompt_id": prompt_id, "err": type(exc).__name__, "msg": str(exc)[:200]},
        )

    if _history_prompt_finished(prompt_id, base_url):
        return
    try:
        _poll_history_until_done(prompt_id, base_url, deadline, chat_id=chat_id)
        return
    except ComfyGenerationCancelled:
        raise
    except TimeoutError:
        if ws_exc is not None:
            raise TimeoutError(
                f"ComfyUI no completó el prompt {prompt_id} en {timeout_sec:.0f}s "
                f"(WS: {type(ws_exc).__name__})."
            ) from ws_exc
        raise


def resolve_output_image(prompt_id: str, base_url: str) -> dict[str, str]:
    resp = _http_json("GET", f"{base_url}/history/{urllib_parse.quote(prompt_id)}")
    if not isinstance(resp, dict):
        raise ValueError("ComfyUI /history no devolvió JSON válido.")
    entry = resp.get(prompt_id)
    if not isinstance(entry, dict):
        raise ValueError(f"Sin historial para prompt_id={prompt_id}.")
    outputs = entry.get("outputs")
    if not isinstance(outputs, dict):
        raise ValueError("ComfyUI history sin outputs.")
    for node_out in outputs.values():
        if not isinstance(node_out, dict):
            continue
        images = node_out.get("images")
        if not isinstance(images, list) or not images:
            continue
        first = images[0]
        if isinstance(first, dict) and first.get("filename"):
            return {
                "filename": str(first["filename"]),
                "subfolder": str(first.get("subfolder") or ""),
                "type": str(first.get("type") or "output"),
            }
    raise ValueError("ComfyUI no produjo ninguna imagen en outputs.")


def download_image(
    filename: str,
    *,
    subfolder: str = "",
    file_type: str = "output",
    base_url: str,
) -> bytes:
    q = urllib_parse.urlencode(
        {
            "filename": filename,
            "subfolder": subfolder,
            "type": file_type,
        }
    )
    return _http_bytes(f"{base_url}/view?{q}")


def tenant_artifacts_dir(tenant_id: str) -> Path:
    from duckclaw.vaults import user_vault_dir

    tid = (tenant_id or "default").strip() or "default"
    path = user_vault_dir(tid) / "artifacts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _visual_state_delta_target_db_path() -> str:
    """
    DuckDB donde db-writer crea ``main.visual_assets``.

    Usa el hub del gateway (p. ej. finanzdb1), no la bóveda activa del worker
    (p. ej. quant_traderdb1): durante ComfyUI el grafo mantiene RO/RW abierto en
    la bóveda del worker y el writer singleton no puede tomar lock en el mismo archivo.
    """
    try:
        from duckclaw.gateway_db import get_gateway_db_path

        return (get_gateway_db_path() or "").strip()
    except Exception:
        return ""


def _state_delta_base() -> dict[str, str]:
    from duckclaw.forge.skills.quant_tool_context import (
        get_quant_tool_tenant_id,
        get_quant_tool_user_id,
    )

    return {
        "tenant_id": get_quant_tool_tenant_id() or "default",
        "user_id": get_quant_tool_user_id() or "default",
        "target_db_path": _visual_state_delta_target_db_path(),
    }


def _error_json(message: str) -> str:
    return json.dumps({"ok": False, "error": message}, ensure_ascii=False)


@log_tool_execution_sync(name="generate_visual_asset")
def _generate_visual_asset_impl(
    prompt: str,
    negative_prompt: str = "",
    aspect_ratio: str = "1:1",
    *,
    comfyui_config: Optional[dict] = None,
    duckclaw_db: Any = None,
) -> str:
    cfg = comfyui_config if isinstance(comfyui_config, dict) else {}
    base_url = _comfy_base_url()
    if not base_url:
        return _error_json("COMFYUI_API_URL no está configurada. Añádela al .env del gateway.")

    pos = (prompt or "").strip()
    if not pos:
        return _error_json("El parámetro prompt no puede estar vacío.")

    template_name = str(cfg.get("template") or "comfy_default").strip() or "comfy_default"
    timeout_sec = _comfy_timeout_sec()
    client_id = str(uuid.uuid4())
    from duckclaw.forge.skills.quant_tool_context import get_quant_tool_chat_id

    chat_id = get_quant_tool_chat_id()

    try:
        workflow, meta = load_workflow_template(template_name)
        workflow = inject_clip_prompts(workflow, pos, negative_prompt or "", meta)
        workflow = apply_aspect_ratio(workflow, aspect_ratio, meta)
        workflow = apply_sampler_steps(workflow, meta)
        workflow, ckpt_err = apply_checkpoint(workflow, meta, base_url)
        if ckpt_err:
            return _error_json(ckpt_err)
        if "3" in workflow and isinstance(workflow["3"], dict):
            inputs = workflow["3"].get("inputs")
            if isinstance(inputs, dict):
                inputs["seed"] = random.randint(0, 2**32 - 1)

        _agent_dbg(
            "H7",
            "comfyui_bridge:generate_visual_asset_impl",
            "before_queue",
            {"base_url": base_url, "chat_id": chat_id, "template": template_name},
        )
        prompt_id = queue_prompt(workflow, client_id, base_url)
        register_comfy_generation(chat_id, base_url=base_url, prompt_id=prompt_id)
        try:
            wait_for_completion(
                prompt_id,
                client_id,
                base_url,
                timeout_sec=timeout_sec,
                chat_id=chat_id,
            )
        finally:
            clear_comfy_generation(chat_id)
        img_meta = resolve_output_image(prompt_id, base_url)
        image_bytes = download_image(
            img_meta["filename"],
            subfolder=img_meta.get("subfolder", ""),
            file_type=img_meta.get("type", "output"),
            base_url=base_url,
        )
    except ComfyGenerationCancelled as e:
        return _error_json(str(e))
    except TimeoutError as e:
        return _error_json(str(e))
    except (ValueError, FileNotFoundError, OSError) as e:
        _log.warning("generate_visual_asset failed: %s", e)
        return _error_json(str(e))

    base = _state_delta_base()
    tenant_id = base["tenant_id"]
    artifact_id = str(uuid.uuid4())
    ext = ".png"
    if len(image_bytes) >= 12 and image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        ext = ".webp"
    elif len(image_bytes) >= 2 and image_bytes[:2] == b"\xff\xd8":
        ext = ".jpg"

    out_path = tenant_artifacts_dir(tenant_id) / f"{artifact_id}{ext}"
    out_path.write_bytes(image_bytes)
    file_path = str(out_path.resolve())

    mutation = {
        "id": artifact_id,
        "prompt": pos,
        "negative_prompt": (negative_prompt or "").strip(),
        "file_path": file_path,
        "aspect_ratio": (aspect_ratio or "1:1").strip() or "1:1",
        "prompt_id_comfy": prompt_id,
        "operation": "txt2img_generate",
        "source_image_path": "",
    }
    target_db = base.get("target_db_path") or ""
    if target_db:
        from duckclaw.forge.skills.visual_state_delta import push_visual_state_delta_sync

        ok_delta = push_visual_state_delta_sync(
            {**base, "delta_type": "VISUAL_ASSET_UPSERT", "mutation": mutation},
            duckclaw_db=duckclaw_db,
        )
        if not ok_delta:
            _log.warning("VISUAL_ASSET_UPSERT no encolado en Redis (REDIS_URL?)")

    payload: dict[str, Any] = {
        "ok": True,
        "file_path": file_path,
        "artifact_id": artifact_id,
        "artifacts": [file_path],
        "prompt_id": prompt_id,
        "aspect_ratio": mutation["aspect_ratio"],
        "message": "Imagen generada y registrada.",
    }
    if len(image_bytes) <= _MAX_B64_IN_TOOL_RESPONSE:
        payload["figure_base64"] = base64.b64encode(image_bytes).decode("ascii")
    return json.dumps(payload, ensure_ascii=False)


def _persist_visual_asset(
    *,
    base: dict[str, str],
    mutation: dict[str, Any],
    duckclaw_db: Any,
) -> None:
    target_db = base.get("target_db_path") or ""
    if not target_db:
        return
    from duckclaw.forge.skills.visual_state_delta import push_visual_state_delta_sync

    ok_delta = push_visual_state_delta_sync(
        {**base, "delta_type": "VISUAL_ASSET_UPSERT", "mutation": mutation},
        duckclaw_db=duckclaw_db,
    )
    if not ok_delta:
        _log.warning("VISUAL_ASSET_UPSERT no encolado en Redis (REDIS_URL?)")


def _finish_image_payload(
    *,
    image_bytes: bytes,
    tenant_id: str,
    message: str,
    prompt_id: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    artifact_id = str(uuid.uuid4())
    ext = ".png"
    if len(image_bytes) >= 12 and image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        ext = ".webp"
    elif len(image_bytes) >= 2 and image_bytes[:2] == b"\xff\xd8":
        ext = ".jpg"
    out_path = tenant_artifacts_dir(tenant_id) / f"{artifact_id}{ext}"
    out_path.write_bytes(image_bytes)
    file_path = str(out_path.resolve())
    payload: dict[str, Any] = {
        "ok": True,
        "file_path": file_path,
        "artifacts": [file_path],
        "prompt_id": prompt_id,
        "message": message,
    }
    if extra:
        payload.update(extra)
    if len(image_bytes) <= _MAX_B64_IN_TOOL_RESPONSE:
        payload["figure_base64"] = base64.b64encode(image_bytes).decode("ascii")
    return payload


@log_tool_execution_sync(name="edit_visual_asset")
def _edit_visual_asset_impl(
    source_image_path: str,
    edit_prompt: str,
    negative_prompt: str = "blurry, distorted, low quality, deformed face",
    denoise: float | None = None,
    *,
    comfyui_config: Optional[dict] = None,
    duckclaw_db: Any = None,
) -> str:
    cfg = comfyui_config if isinstance(comfyui_config, dict) else {}
    base_url = _comfy_base_url()
    if not base_url:
        return _error_json("COMFYUI_API_URL no está configurada.")

    edit_text = (edit_prompt or "").strip()
    if not edit_text:
        return _error_json("edit_prompt no puede estar vacío.")

    base = _state_delta_base()
    tenant_id = base["tenant_id"]
    try:
        src = validate_source_image_path(source_image_path, tenant_id)
    except ValueError as e:
        return _error_json(str(e))

    template_name = str(cfg.get("edit_template") or "comfy_img2img_edit").strip() or "comfy_img2img_edit"
    den = _default_img2img_denoise() if denoise is None else float(denoise)
    timeout_sec = _comfy_timeout_sec()
    client_id = str(uuid.uuid4())
    from duckclaw.forge.skills.quant_tool_context import get_quant_tool_chat_id

    chat_id = get_quant_tool_chat_id()

    try:
        uploaded_name = upload_image_to_comfy(src, base_url)
        workflow, meta = load_workflow_template(template_name)
        workflow = inject_load_image(workflow, uploaded_name, meta)
        workflow = inject_clip_prompts(workflow, edit_text, negative_prompt or "", meta)
        workflow = inject_ksampler_denoise(workflow, den, meta)
        if "3" in workflow and isinstance(workflow["3"], dict):
            inputs = workflow["3"].get("inputs")
            if isinstance(inputs, dict):
                inputs["seed"] = random.randint(0, 2**32 - 1)

        prompt_id = queue_prompt(workflow, client_id, base_url)
        register_comfy_generation(chat_id, base_url=base_url, prompt_id=prompt_id)
        try:
            wait_for_completion(
                prompt_id,
                client_id,
                base_url,
                timeout_sec=timeout_sec,
                chat_id=chat_id,
            )
        finally:
            clear_comfy_generation(chat_id)
        img_meta = resolve_output_image(prompt_id, base_url)
        image_bytes = download_image(
            img_meta["filename"],
            subfolder=img_meta.get("subfolder", ""),
            file_type=img_meta.get("type", "output"),
            base_url=base_url,
        )
    except ComfyGenerationCancelled as e:
        return _error_json(str(e))
    except TimeoutError as e:
        return _error_json(str(e))
    except (ValueError, FileNotFoundError, OSError) as e:
        _log.warning("edit_visual_asset failed: %s", e)
        return _error_json(str(e))

    artifact_id = str(uuid.uuid4())
    mutation = {
        "id": artifact_id,
        "prompt": edit_text,
        "negative_prompt": (negative_prompt or "").strip(),
        "file_path": "",
        "aspect_ratio": "source",
        "prompt_id_comfy": prompt_id,
        "operation": "img2img_edit",
        "source_image_path": str(src),
    }
    payload = _finish_image_payload(
        image_bytes=image_bytes,
        tenant_id=tenant_id,
        message="Imagen editada y registrada.",
        prompt_id=prompt_id,
        extra={"source_image_path": str(src), "denoise": den, "operation": "img2img_edit"},
    )
    mutation["file_path"] = str(payload["file_path"])
    _persist_visual_asset(base=base, mutation=mutation, duckclaw_db=duckclaw_db)
    return json.dumps(payload, ensure_ascii=False)


def _generate_visual_asset_tool(
    config: Optional[dict] = None,
    duckclaw_db: Any = None,
) -> Optional[Any]:
    cfg = config if isinstance(config, dict) else {}
    if cfg.get("enabled") is False:
        return None
    if not _comfy_base_url():
        return None

    def _run(prompt: str, negative_prompt: str = "", aspect_ratio: str = "1:1") -> str:
        return _generate_visual_asset_impl(
            prompt,
            negative_prompt=negative_prompt,
            aspect_ratio=aspect_ratio,
            comfyui_config=cfg,
            duckclaw_db=duckclaw_db,
        )

    try:
        from langchain_core.tools import StructuredTool
    except ImportError:
        return None

    return StructuredTool.from_function(
        _run,
        name="generate_visual_asset",
        description=(
            "Genera una imagen con ComfyUI a partir de un prompt de texto. "
            "Parámetros: prompt (obligatorio), negative_prompt (opcional), "
            "aspect_ratio (1:1, 16:9, 9:16, 4:3, 3:4). "
            "Guarda el archivo en artifacts del tenant y devuelve file_path. "
            "Usar cuando el usuario pida ilustración, diagrama visual o arte generado."
        ),
    )


def read_artifact_image_as_b64(file_path: str, tenant_id: str) -> str:
    """Lee PNG/WebP/JPEG bajo db/private/{tenant}/artifacts/ o inbound/ y devuelve base64 o vacío."""
    try:
        resolved = Path(file_path).resolve()
    except OSError:
        return ""
    allowed = _allowed_source_roots(tenant_id)
    if not any(str(resolved).startswith(str(root)) for root in allowed):
        return ""
    if resolved.suffix.lower() not in (".png", ".webp", ".jpg", ".jpeg"):
        return ""
    if not resolved.is_file():
        return ""
    try:
        raw = resolved.read_bytes()
    except OSError:
        return ""
    if len(raw) < 32:
        return ""
    if len(raw) > _MAX_B64_IN_TOOL_RESPONSE:
        return ""
    return base64.b64encode(raw).decode("ascii")


def register_comfyui_skill(
    tools_list: list[Any],
    comfyui_config: Optional[dict] = None,
    *,
    duckclaw_db: Any = None,
) -> None:
    if comfyui_config is None:
        return
    cfg = comfyui_config if isinstance(comfyui_config, dict) else {}
    if cfg.get("enabled") is False:
        return
    gen_tool = _generate_visual_asset_tool(cfg, duckclaw_db=duckclaw_db)
    if gen_tool is not None:
        tools_list.append(gen_tool)
    edit_tool = _edit_visual_asset_tool(cfg, duckclaw_db=duckclaw_db)
    if edit_tool is not None:
        tools_list.append(edit_tool)


def _edit_visual_asset_tool(
    config: Optional[dict] = None,
    duckclaw_db: Any = None,
) -> Optional[Any]:
    cfg = config if isinstance(config, dict) else {}
    if cfg.get("enabled") is False:
        return None
    if not _comfy_base_url():
        return None

    def _run(
        source_image_path: str,
        edit_prompt: str,
        negative_prompt: str = "blurry, distorted, low quality, deformed face",
        denoise: float = 0.55,
    ) -> str:
        return _edit_visual_asset_impl(
            source_image_path,
            edit_prompt,
            negative_prompt=negative_prompt,
            denoise=denoise,
            comfyui_config=cfg,
            duckclaw_db=duckclaw_db,
        )

    try:
        from langchain_core.tools import StructuredTool
    except ImportError:
        return None

    return StructuredTool.from_function(
        _run,
        name="edit_visual_asset",
        description=(
            "Edita una foto existente con ComfyUI (img2img). "
            "Parámetros: source_image_path (ruta absoluta en inbound/ o artifacts/ del tenant), "
            "edit_prompt (instrucciones en español), negative_prompt (opcional), denoise (0.35-0.75, default 0.55). "
            "Usar cuando el mensaje incluya [COMFYUI_EDIT ...] o el usuario pida modificar una foto enviada."
        ),
    )
