"""Filtro canónico de variables Node/Next para procesos PM2 Python."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from importlib import resources
from typing import Any


def _load_spec() -> dict[str, Any]:
    raw = resources.files("duckclaw.seeds").joinpath("pm2_node_dev_env_filter_v1.json").read_text(
        encoding="utf-8"
    )
    return json.loads(raw)


@lru_cache(maxsize=1)
def pm2_node_dev_env_filter_spec() -> dict[str, Any]:
    return _load_spec()


def pm2_node_dev_blocked_prefixes() -> tuple[str, ...]:
    spec = pm2_node_dev_env_filter_spec()
    return tuple(spec["blocked_prefixes"])


def pm2_node_dev_blocked_extra_prefixes() -> tuple[str, ...]:
    spec = pm2_node_dev_env_filter_spec()
    return tuple(spec.get("blocked_extra_prefixes") or ())


def pm2_node_dev_blocked_keys() -> frozenset[str]:
    spec = pm2_node_dev_env_filter_spec()
    return frozenset(spec["blocked_keys"])


def pm2_node_dev_allowed_keys() -> frozenset[str]:
    spec = pm2_node_dev_env_filter_spec()
    return frozenset(spec["allowed_keys"])


def pm2_node_dev_allowed_prefixes() -> tuple[str, ...]:
    spec = pm2_node_dev_env_filter_spec()
    return tuple(spec.get("allowed_prefixes") or ())


def is_pm2_node_dev_blocked_key(key: str) -> bool:
    if key in pm2_node_dev_blocked_keys():
        return True
    for prefix in pm2_node_dev_blocked_extra_prefixes():
        if key.startswith(prefix):
            return True
    return any(key.startswith(prefix) for prefix in pm2_node_dev_blocked_prefixes())


def ecosystem_pm2_node_dev_filter_env_js_lines() -> list[str]:
    """Genera ``filter_env`` para ecosystem.*.config.cjs."""
    spec = pm2_node_dev_env_filter_spec()
    lines = ["      filter_env: ["]
    for prefix in spec["blocked_prefixes"]:
        lines.append(f'        /^{re.escape(prefix)}/,')
    for key in spec["blocked_keys"]:
        if not any(key.startswith(p) for p in spec["blocked_prefixes"]):
            lines.append(f'        "{key}",')
    lines.append("      ],")
    return lines
