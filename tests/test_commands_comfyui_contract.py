from __future__ import annotations

import importlib
import inspect

from duckclaw.graphs import on_the_fly_commands


CANONICAL_MODULE = "duckclaw.commands.comfyui"
COMFYUI_FUNCTION_EXPORTS = ("execute_comfyui_provider",)
COMFYUI_CONSTANT_EXPORTS = ("_COMFYUI_PROVIDER_KEY",)


def test_comfyui_command_ownership_lives_outside_graphs() -> None:
    comfyui = importlib.import_module(CANONICAL_MODULE)

    for name in COMFYUI_FUNCTION_EXPORTS:
        exported = getattr(on_the_fly_commands, name)
        assert exported.__module__ == CANONICAL_MODULE

    source = inspect.getsource(comfyui)
    assert "duckclaw.graphs.on_the_fly_commands" not in source
    assert "from duckclaw.graphs" not in source


def test_on_the_fly_comfyui_imports_remain_compatible() -> None:
    comfyui = importlib.import_module(CANONICAL_MODULE)

    for name in COMFYUI_FUNCTION_EXPORTS:
        assert getattr(on_the_fly_commands, name) is getattr(comfyui, name)
    for name in COMFYUI_CONSTANT_EXPORTS:
        assert getattr(on_the_fly_commands, name) == getattr(comfyui, name)
