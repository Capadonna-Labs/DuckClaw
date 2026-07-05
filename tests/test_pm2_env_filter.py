"""Tests para filtro PM2 compartido (seed JSON ↔ codegen ↔ BFF)."""

from __future__ import annotations

import json
from pathlib import Path


def _seed_path() -> Path:
    return Path(__file__).resolve().parents[1] / "packages/shared/src/duckclaw/seeds/pm2_node_dev_env_filter_v1.json"


def _load_seed() -> dict:
    return json.loads(_seed_path().read_text(encoding="utf-8"))


def test_seed_loads_from_package_resources() -> None:
    from duckclaw.ops.pm2_env_filter import pm2_node_dev_env_filter_spec

    pkg = pm2_node_dev_env_filter_spec()
    disk = _load_seed()
    assert pkg["blocked_prefixes"] == disk["blocked_prefixes"]
    assert set(pkg["blocked_keys"]) == set(disk["blocked_keys"])


def test_blocked_key_detection_matches_seed() -> None:
    from duckclaw.ops.pm2_env_filter import is_pm2_node_dev_blocked_key

    seed = _load_seed()
    for prefix in seed["blocked_prefixes"]:
        assert is_pm2_node_dev_blocked_key(f"{prefix}example") is True
    for key in seed["blocked_keys"]:
        assert is_pm2_node_dev_blocked_key(key) is True
    for extra in seed.get("blocked_extra_prefixes", []):
        assert is_pm2_node_dev_blocked_key(f"{extra}name") is True
    assert is_pm2_node_dev_blocked_key("DUCKCLAW_GATEWAY_URL") is False


def test_filter_env_js_lines_cover_seed() -> None:
    from duckclaw.ops.pm2_env_filter import ecosystem_pm2_node_dev_filter_env_js_lines

    seed = _load_seed()
    lines = "\n".join(ecosystem_pm2_node_dev_filter_env_js_lines())
    for prefix in seed["blocked_prefixes"]:
        assert f"/^{prefix}/" in lines
    for key in seed["blocked_keys"]:
        if not any(key.startswith(p) for p in seed["blocked_prefixes"]):
            assert f'"{key}"' in lines


def test_pm2_recycle_shell_matches_process_names() -> None:
    from duckclaw.ops.pm2_recycle import pm2_recycle_gateway_shell, pm2_recycle_db_writer_shell

    seed = _load_seed()
    gw = seed["pm2_processes"]["gateway"]
    dw = seed["pm2_processes"]["db_writer"]
    gw_shell = pm2_recycle_gateway_shell(repo_root="/tmp/repo")
    dw_shell = pm2_recycle_db_writer_shell(repo_root="/tmp/repo")
    assert f'pm2 delete {gw["name"]}' in gw_shell
    assert gw["ecosystem"] in gw_shell
    assert "PM2_RECYCLE_GATEWAY_OK" in gw_shell
    assert f'pm2 delete {dw["name"]}' in dw_shell
    assert dw["ecosystem"] in dw_shell
    assert "PM2_RECYCLE_DB_WRITER_OK" in dw_shell


def test_ts_seed_json_exists_for_bff_parity() -> None:
    """El BFF importa el mismo JSON; este test falla si el path deja de existir."""
    assert _seed_path().is_file()
