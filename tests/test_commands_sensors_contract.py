from __future__ import annotations

import importlib
import inspect

from duckclaw.graphs import on_the_fly_commands


CANONICAL_MODULE = "duckclaw.commands.sensors"
SENSORS_EXPORTS = (
    "_ssh_reach_icon",
    "_capadonna_lake_status_lines",
    "_sensor_line_bullet",
    "_browser_sandbox_sensor_lines",
    "execute_sensors",
)


def test_sensors_command_ownership_lives_outside_graphs() -> None:
    sensors = importlib.import_module(CANONICAL_MODULE)

    for name in SENSORS_EXPORTS:
        exported = getattr(on_the_fly_commands, name)
        assert exported.__module__ == CANONICAL_MODULE

    source = inspect.getsource(sensors)
    assert "duckclaw.graphs.on_the_fly_commands" not in source
    assert "from duckclaw.graphs" not in source


def test_sensors_module_has_no_vertical_runtime_defaults() -> None:
    sensors = importlib.import_module(CANONICAL_MODULE)
    source = inspect.getsource(sensors).lower()

    forbidden = {
        "quant",
        "trader",
        "finance",
        "finanz",
        "ibkr",
        "pqrs",
        "pqrsd",
        "leila",
        "war room",
        "job hunter",
    }
    leaked = sorted(marker for marker in forbidden if marker in source)

    assert leaked == []


def test_on_the_fly_sensors_imports_remain_compatible() -> None:
    sensors = importlib.import_module(CANONICAL_MODULE)

    for name in SENSORS_EXPORTS:
        assert getattr(on_the_fly_commands, name) is getattr(sensors, name)
