"""Tests for integration catalog API and seed pack."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from duckclaw.integration_catalog import (
    integration_catalog_api_payload,
    list_integration_catalog_entries,
    load_integration_secrets_pack,
)


def test_load_integration_secrets_pack_has_groups() -> None:
    pack = load_integration_secrets_pack()
    assert pack["pack_version"] == "framework_integration_secrets_v1"
    groups = pack.get("groups") or []
    assert len(groups) >= 2
    ids = {entry.integration_id for entry in list_integration_catalog_entries()}
    assert "tavily" in ids
    assert "deepseek" in ids
    assert "openweather" in ids
    assert "fal" in ids


def test_validate_integration_secrets_pack_rejects_duplicate_id() -> None:
    from duckclaw.integration_catalog import validate_integration_secrets_pack

    with pytest.raises(ValueError, match="duplicate integration id"):
        validate_integration_secrets_pack(
            {
                "groups": [
                    {
                        "id": "g",
                        "integrations": [
                            {"id": "dup", "setting_key": "a.api_key"},
                            {"id": "dup", "setting_key": "b.api_key"},
                        ],
                    }
                ]
            }
        )


def test_integration_pack_override_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from duckclaw.integration_catalog import (
        clear_integration_catalog_cache,
        list_integration_catalog_entries,
        load_integration_secrets_pack,
    )

    custom = tmp_path / "custom_pack.json"
    custom.write_text(
        """
        {
          "pack_version": "custom_v1",
          "groups": [{
            "id": "custom",
            "title": "Custom",
            "integrations": [{
              "id": "only_one",
              "setting_key": "only_one.api_key",
              "label": "Only",
              "env_keys": ["ONLY_ONE_KEY"],
              "related_skills": ["only_one"]
            }]
          }]
        }
        """,
        encoding="utf-8",
    )
    monkeypatch.setenv("DUCKCLAW_INTEGRATION_SECRETS_PACK_PATH", str(custom))
    clear_integration_catalog_cache()
    try:
        assert load_integration_secrets_pack()["pack_version"] == "custom_v1"
        ids = {e.integration_id for e in list_integration_catalog_entries()}
        assert ids == {"only_one"}
    finally:
        monkeypatch.delenv("DUCKCLAW_INTEGRATION_SECRETS_PACK_PATH", raising=False)
        clear_integration_catalog_cache()


def test_integration_catalog_api_requires_admin_key(admin_client: TestClient) -> None:
    response = admin_client.get("/api/v1/admin/integrations/catalog")
    assert response.status_code == 401


def test_integration_catalog_api_payload_shape(admin_client: TestClient) -> None:
    response = admin_client.get(
        "/api/v1/admin/integrations/catalog",
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["pack_version"] == "framework_integration_secrets_v1"
    assert "pack_source" in data
    assert isinstance(data["groups"], list)
    assert len(data["groups"]) >= 2
    assert isinstance(data["integrations"], list)
    tavily = next((row for row in data["integrations"] if row["id"] == "tavily"), None)
    assert tavily is not None
    assert tavily["setting_key"] == "tavily.api_key"
    assert "research" in tavily["related_skills"]
    assert "configured" in tavily
