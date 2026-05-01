"""Smoke: multiplex compact debe registrar POST bajo cada path (evita regresiones tipo Telegram 404)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
_API_GW = REPO_ROOT / "services" / "api-gateway"


@pytest.fixture(autouse=True)
def _prepend_api_gateway(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DUCKCLAW_REPO_ROOT", str(tmp_path))
    if str(_API_GW) not in sys.path:
        sys.path.insert(0, str(_API_GW))


@pytest.mark.parametrize(
    ("slug", "vault_key"),
    [
        ("quanttrader", "DUCKCLAW_QUANT_TRADER_DB_PATH"),
        ("siata", "DUCKCLAW_SIATA_DB_PATH"),
        ("finanz", "DUCKCLAW_FINANZ_DB_PATH"),
        ("jobhunter", "DUCKCLAW_JOB_HUNTER_DB_PATH"),
        ("pqrsd-assistant", "DUCKCLAW_PQRSD_ASSISTANT_DB_PATH"),
    ],
)
def test_compact_path_post_registered_not_http_404(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    slug: str,
    vault_key: str,
) -> None:
    """
    Telegram ``getWebhookInfo`` con ``404 Not Found`` indica que la URL llega pero no hay handler:
    típicamente túnel → otro puerto/servicio, o gateway sin ROUTES. Aquí comprobamos el router.
    """
    (tmp_path / "db").mkdir(parents=True, exist_ok=True)
    dbf = tmp_path / "db" / f"{slug}.duckdb"
    dbf.write_bytes(b"")

    tok = f"123456789:AA{slug}_fake_token_smoke_test_only_32charsx"
    monkeypatch.setenv(
        "DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES",
        f"{slug}:{tok}:/api/v1/telegram/{slug}",
    )
    monkeypatch.setenv(vault_key, str(dbf.relative_to(tmp_path)))

    monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET_FINANZ", raising=False)
    monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET_TRABAJO", raising=False)
    monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET", raising=False)

    from fastapi import FastAPI
    from starlette.testclient import TestClient

    from routers.telegram_inbound_webhook import build_telegram_inbound_webhook_router  # noqa: PLC0415

    invoke = AsyncMock(return_value={"response": "", "conversation_id": ""})
    app = FastAPI()
    app.include_router(
        build_telegram_inbound_webhook_router(
            invoke_agent_chat=invoke,
            resolve_effective_telegram_bot_token=lambda: tok,
        )
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.post(
            f"/api/v1/telegram/{slug}",
            json={
                "update_id": 900000000 + hash(slug) % 100000,
                "message": {
                    "message_id": 1,
                    "from": {"id": 1, "is_bot": False, "first_name": "t"},
                    "chat": {"id": 990001, "type": "private"},
                    "date": 1,
                    "text": "ping",
                },
            },
            headers={"Content-Type": "application/json"},
        )
    assert resp.status_code != 404, (
        f"compact POST /api/v1/telegram/{slug} debe existir con ROUTES; "
        f"got {resp.status_code} body={resp.text[:800]}"
    )
