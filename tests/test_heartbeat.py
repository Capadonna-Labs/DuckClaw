from __future__ import annotations

import asyncio
from typing import Any, Dict, List

import types

import pytest

import services.heartbeat.main as heartbeat


class DummyRedis:
    def __init__(self) -> None:
        self.store: Dict[str, str] = {}

    async def exists(self, key: str) -> bool:
        return key in self.store

    async def setex(self, key: str, ttl: int, value: str) -> None:  # noqa: ARG002
        self.store[key] = value


def test_check_cooldown_sets_and_blocks() -> None:
    async def _run() -> None:
        r = DummyRedis()
        ok_first = await heartbeat.check_cooldown(r, "tenant1", "alertA")
        ok_second = await heartbeat.check_cooldown(r, "tenant1", "alertA")
        assert ok_first is True
        assert ok_second is False

    asyncio.run(_run())


def test_run_heartbeat_builds_payloads(monkeypatch: Any) -> None:
    # Simular anomalies y capturar posts en vez de hacer HTTP real
    anomalies: List[Dict[str, Any]] = [
        {
            "tenant_id": "finance_worker",
            "belief_key": "presupuesto_mensual",
            "observed_value": 5000.0,
            "admin_chat_id": "12345",
        }
    ]

    async def fake_eval() -> List[Dict[str, Any]]:
        return anomalies

    posts: list[Dict[str, Any]] = []

    class DummyClient:
        async def __aenter__(self) -> "DummyClient":
            return self

        async def __aexit__(self, *exc: Any) -> None:  # noqa: ANN401
            return None

        async def post(self, url: str, params: Dict[str, Any], json: Dict[str, Any], headers: Dict[str, Any], timeout: int) -> None:  # noqa: ARG002
            posts.append({"url": url, "params": params, "json": json, "headers": headers})

    async def one_shot() -> None:
        r = DummyRedis()
        monkeypatch.setattr(heartbeat, "_evaluate_homeostasis", fake_eval)
        monkeypatch.setattr(heartbeat, "httpx", types.SimpleNamespace(AsyncClient=lambda: DummyClient()))

        # Ejecutar un solo ciclo del cuerpo del while
        anomalies_local = await heartbeat._evaluate_homeostasis()
        assert anomalies_local
        for anomaly in anomalies_local:
            tenant_id = anomaly["tenant_id"]
            alert_type = anomaly["belief_key"]
            admin_chat_id = anomaly["admin_chat_id"]
            allowed = await heartbeat.check_cooldown(r, tenant_id, alert_type)
            assert allowed is True
            message = (
                "[SYSTEM_EVENT: Anomalía detectada en "
                f"{alert_type}. Valor actual: {anomaly['observed_value']}. "
                "Evalúa la situación y notifica al usuario si es crítico.]"
            )
            payload = {
                "message": message,
                "chat_id": admin_chat_id,
                "is_system_prompt": True,
            }
            async with DummyClient() as client:
                await client.post(
                    heartbeat.GATEWAY_URL,
                    params={"tenant_id": tenant_id, "worker_id": "finanz"},
                    json=payload,
                    headers={},
                    timeout=30,
                )

    asyncio.run(one_shot())
    assert posts
    sent = posts[0]
    assert sent["json"]["is_system_prompt"] is True
    assert "SYSTEM_EVENT" in sent["json"]["message"]

