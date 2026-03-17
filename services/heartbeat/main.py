from __future__ import annotations

"""
DuckClaw Heartbeat Daemon

Bucle asíncrono que evalúa homeostasis periódicamente y, cuando detecta anomalías,
inyecta un pensamiento interno ([SYSTEM_EVENT]) en el API Gateway.

La integración específica con HomeostasisManager y la definición de anomalies
se implementan en una fase posterior.
"""

import asyncio
import logging
import os
from typing import Any, Dict, List

import httpx
import redis.asyncio as redis

from duckclaw import DuckClaw
from duckclaw.forge.homeostasis import BeliefRegistry, HomeostasisManager
from duckclaw.gateway_db import get_gateway_db_path
from duckclaw.workers.factory import list_workers
from duckclaw.workers.manifest import load_manifest


logger = logging.getLogger("heartbeat")
logging.basicConfig(level=logging.INFO)


REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
GATEWAY_URL = os.getenv(
    "GATEWAY_URL",
    "http://localhost:8000/api/v1/agent/chat",
)
HEARTBEAT_INTERVAL_SECONDS = int(os.getenv("HEARTBEAT_INTERVAL_SECONDS", "3600"))
TAILSCALE_AUTH_KEY = os.getenv("DUCKCLAW_TAILSCALE_AUTH_KEY", "").strip()


async def check_cooldown(r: redis.Redis, tenant_id: str, alert_type: str) -> bool:
    """Verifica si ya enviamos esta alerta recientemente (Anti-Spam)."""
    key = f"cooldown:{tenant_id}:{alert_type}"
    if await r.exists(key):
        return False
    # Bloquear futuras alertas de este tipo por 24 horas (86400 segundos)
    await r.setex(key, 86400, "locked")
    return True


async def _evaluate_homeostasis() -> List[Dict[str, Any]]:
    """
    Recorre workers con homeostasis_config y evalúa sus beliefs.

    Devuelve una lista de dicts con:
    - tenant_id: normalmente el schema/worker_id (ej. finance_worker/finanz)
    - belief_key
    - observed_value (target como proxy cuando no hay observación externa)
    - admin_chat_id: chat al que notificar (por ahora, configurado vía env)
    """
    db_path = get_gateway_db_path()
    db = DuckClaw(db_path)

    anomalies: List[Dict[str, Any]] = []

    # ADMIN_CHAT_ID global por ahora; a futuro podría venir de una tabla de configuración por tenant.
    default_admin_chat_id = os.getenv("DUCKCLAW_ADMIN_CHAT_ID", "").strip()

    for wid in list_workers():
        try:
            spec = load_manifest(wid)
            config = getattr(spec, "homeostasis_config", None) or {}
            registry = BeliefRegistry.from_config(config)
            if not registry.beliefs:
                continue
            schema = spec.schema_name
            manager = HomeostasisManager(db=db, schema=schema, registry=registry)

            # Por simplicidad inicial, usamos target como observed_value para forzar evaluación.
            for belief in registry.beliefs:
                observed_value = belief.target
                plan = manager.check(
                    belief.key,
                    observed_value,
                    auto_update=True,
                    invoke_restoration=False,
                )
                if plan.get("action") == "restore":
                    anomalies.append(
                        {
                            "tenant_id": schema,
                            "belief_key": plan.get("belief_key", belief.key),
                            "observed_value": plan.get("observed", observed_value),
                            "admin_chat_id": default_admin_chat_id,
                        }
                    )
        except Exception as e:  # noqa: BLE001
            logger.exception("Error evaluando homeostasis para worker %s: %s", wid, e)

    return anomalies


async def run_heartbeat() -> None:
    r = redis.from_url(REDIS_URL)

    while True:
        logger.info("Iniciando ciclo de evaluación de Homeostasis...")
        try:
            anomalies = await _evaluate_homeostasis()
            logger.info("Anomalías encontradas: %s", len(anomalies))

            for anomaly in anomalies:
                tenant_id = str(anomaly.get("tenant_id", "")).strip() or "default"
                alert_type = str(anomaly.get("belief_key", "")).strip() or "unknown"
                admin_chat_id = str(anomaly.get("admin_chat_id", "")).strip()
                observed_value = anomaly.get("observed_value")

                if not admin_chat_id:
                    logger.warning(
                        "Anomalía sin admin_chat_id (tenant_id=%s, alert_type=%s)",
                        tenant_id,
                        alert_type,
                    )
                    continue

                if not await check_cooldown(r, tenant_id, alert_type):
                    logger.info(
                        "Cooldown activo para tenant=%s alert_type=%s; no se envía.",
                        tenant_id,
                        alert_type,
                    )
                    continue

                logger.info(
                    "Anomalía detectada en tenant=%s, belief=%s. Inyectando pensamiento...",
                    tenant_id,
                    alert_type,
                )

                message = (
                    "[SYSTEM_EVENT: Anomalía detectada en "
                    f"{alert_type}. Valor actual: {observed_value}. "
                    "Evalúa la situación y notifica al usuario si es crítico.]"
                )
                payload = {
                    "message": message,
                    "chat_id": admin_chat_id,
                    "is_system_prompt": True,
                }

                headers = {}
                if TAILSCALE_AUTH_KEY:
                    headers["X-Tailscale-Auth-Key"] = TAILSCALE_AUTH_KEY

                try:
                    async with httpx.AsyncClient() as client:
                        await client.post(
                            GATEWAY_URL,
                            params={"tenant_id": tenant_id, "worker_id": "finanz"},
                            json=payload,
                            headers=headers,
                            timeout=30,
                        )
                except Exception as e:  # noqa: BLE001
                    logger.exception("Error enviando evento al Gateway: %s", e)

        except Exception as e:  # noqa: BLE001
            logger.exception("Error en ciclo de heartbeat: %s", e)

        await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)


if __name__ == "__main__":
    asyncio.run(run_heartbeat())

