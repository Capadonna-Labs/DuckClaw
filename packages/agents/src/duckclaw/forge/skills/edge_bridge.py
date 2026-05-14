import ctypes
import json
import logging
import argparse
import importlib.util
import os
import time
from pathlib import Path
from typing import Optional, List, Any, Callable

from duckclaw_edge_devices.client import (
    close_serial,
    load_edge_core,
    open_serial,
    read_telemetry,
)

_log = logging.getLogger(__name__)


def _resolve_push_quant_state_delta_sync() -> Callable[[dict[str, Any]], bool]:
    """Import desde paquete duckclaw, archivo hermano en VPS, o fallback inline (sin segundo .py)."""
    here = Path(__file__).resolve().parent
    try:
        from duckclaw.forge.skills.quant_state_delta import (
            push_quant_state_delta_sync as _fn,
        )

        return _fn
    except ModuleNotFoundError:
        pass

    sibling = here / "quant_state_delta.py"
    if sibling.is_file():
        spec = importlib.util.spec_from_file_location(
            "duckclaw_forge_quant_state_delta", sibling
        )
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            fn = getattr(mod, "push_quant_state_delta_sync", None)
            if callable(fn):
                return fn  # type: ignore[return-value]

    _default_q = "duckclaw:state_delta:quant"

    def push_quant_state_delta_sync(payload: dict[str, Any]) -> bool:
        def _queue_key() -> str:
            return (
                os.environ.get("DUCKCLAW_QUANT_STATE_DELTA_QUEUE") or _default_q
            ).strip()

        url = (os.environ.get("REDIS_URL") or os.environ.get("DUCKCLAW_REDIS_URL") or "").strip()
        if not url:
            _log.warning("[quant_state_delta] REDIS_URL ausente; omitiendo enqueue")
            return False
        try:
            import redis

            r = redis.from_url(url, decode_responses=True)
            r.lpush(_queue_key(), json.dumps(payload, ensure_ascii=False))
            return True
        except Exception as exc:  # noqa: BLE001
            _log.warning("[quant_state_delta] LPUSH falló: %s", exc)
            return False

    return push_quant_state_delta_sync


push_quant_state_delta_sync = _resolve_push_quant_state_delta_sync()

_lib: Optional[ctypes.CDLL] = None


def _load_lib() -> Optional[ctypes.CDLL]:
    global _lib
    if _lib is not None:
        return _lib
    _lib = load_edge_core()
    if _lib is None:
        _log.error(
            "[edge_bridge] No se encontró libedgecore (DUCKCLAW_EDGE_LIB_PATH o rutas por defecto)."
        )
    return _lib


def poll_edge_device(port: str, baud_rate: int, emit_interval_sec: float, tenant_id: str, schema: List[str]) -> None:
    lib = _load_lib()
    if not lib:
        raise RuntimeError("No se pudo cargar libedgecore.")

    is_system_mode = port.lower() == "system"
    _log.info(
        f"[edge_bridge] Iniciando modo: {'SYSTEM' if is_system_mode else 'SERIAL'} | Tenant: {tenant_id}"
    )

    fd = -1
    if not is_system_mode:
        while True:
            fd = open_serial(lib, port, baud_rate)
            if fd >= 0:
                break
            _log.warning(f"[edge_bridge] Fallo al abrir {port}. Reintentando en 5s...")
            time.sleep(5)

    try:
        while True:
            if is_system_mode:
                res, data = read_telemetry(lib, system=True, fd=-1)
                time.sleep(emit_interval_sec)
            else:
                res, data = read_telemetry(lib, system=False, fd=fd)

            if res == 0:
                device_id = data.device_id.decode("utf-8", errors="ignore").strip()
                metrics = {
                    metric_name: round(float(data.data[i]), 4)
                    for i, metric_name in enumerate(schema)
                    if i < 8
                }

                payload = {
                    "tenant_id": tenant_id,
                    "worker": "edge_bridge",
                    "delta_type": "EDGE_TELEMETRY_UPSERT",
                    "mutation": {
                        "device_id": device_id,
                        "timestamp_ms": int(data.timestamp_ms),
                        "metrics": metrics,
                    },
                }

                if push_quant_state_delta_sync(payload):
                    _log.info(f"[edge_bridge] Emitido: {device_id} | {metrics}")

            elif res == -1 and not is_system_mode:
                _log.error("[edge_bridge] Dispositivo desconectado.")
                break

    except KeyboardInterrupt:
        pass
    finally:
        if not is_system_mode:
            close_serial(lib, fd)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--port", type=str, required=True, help="Puerto serial o 'system' para VPS stats"
    )
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--interval", type=float, default=5.0)
    parser.add_argument("--tenant", type=str, default="INFRA")
    parser.add_argument("--schema", type=str, required=True)

    args = parser.parse_args()
    schema_list = [s.strip() for s in args.schema.split(",")]

    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
    poll_edge_device(args.port, args.baud, args.interval, args.tenant, schema_list)
