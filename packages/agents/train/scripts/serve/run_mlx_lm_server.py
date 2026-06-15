#!/usr/bin/env python3
"""DuckClaw entrypoint for ``mlx_lm server``.

Installs the small Gemma 4 compatibility patches DuckClaw needs, then delegates
to the official ``mlx_lm`` CLI.
"""

from __future__ import annotations

import json
import os
import re
import sys
import warnings
from typing import Any


def _json_repair_candidates(raw_json: str) -> list[str]:
    seen: set[str] = set()
    candidates: list[str] = []

    def add(value: str) -> None:
        if value not in seen:
            seen.add(value)
            candidates.append(value)

    add(raw_json)

    without_trailing_commas = re.sub(r",\s*}", "}", raw_json)
    without_trailing_commas = re.sub(r",\s*]", "]", without_trailing_commas)
    add(without_trailing_commas)

    quoted_keys = re.sub(r"([{,])\s*(\w+)\s*:", r'\1"\2":', raw_json)
    add(quoted_keys)

    quoted_keys_no_trailing = re.sub(
        r"([{,])\s*(\w+)\s*:",
        r'\1"\2":',
        without_trailing_commas,
    )
    quoted_keys_no_trailing = re.sub(r",\s*}", "}", quoted_keys_no_trailing)
    quoted_keys_no_trailing = re.sub(r",\s*]", "]", quoted_keys_no_trailing)
    add(quoted_keys_no_trailing)

    add(
        raw_json.replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2018", "'")
        .replace("\u2019", "'")
    )
    return candidates


def _install_gemma4_tool_patch() -> None:
    import mlx_lm.tool_parsers.gemma4 as gemma4_parser

    to_json = gemma4_parser._gemma4_args_to_json

    def parse_single_wrapped(match: Any) -> dict[str, Any]:
        func_name = match.group(1)
        args_str = match.group(2)
        json_str = to_json(args_str)
        last_error: json.JSONDecodeError | None = None
        for candidate in _json_repair_candidates(json_str):
            try:
                return {"name": func_name, "arguments": json.loads(candidate)}
            except json.JSONDecodeError as exc:
                last_error = exc

        try:
            import ast

            stripped = args_str.strip()
            if stripped.startswith("{") and stripped.endswith("}"):
                pyish = (
                    stripped.replace("true", "True")
                    .replace("false", "False")
                    .replace("null", "None")
                )
                parsed = ast.literal_eval(pyish)
                if isinstance(parsed, dict):
                    return {"name": func_name, "arguments": parsed}
        except (SyntaxError, ValueError, TypeError):
            pass

        if last_error is not None:
            raise last_error
        raise RuntimeError("Gemma 4 tool args JSON parse failed.")

    gemma4_parser._parse_single = parse_single_wrapped


def _env_load_strict() -> bool:
    return (os.environ.get("DUCKCLAW_MLX_LOAD_STRICT") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _install_mlx_load_model_skip_extra_weights() -> None:
    if _env_load_strict():
        return

    import mlx_lm.utils as mlx_utils

    original_load_model = mlx_utils.load_model

    def load_model_wrapped(*args: Any, **kwargs: Any) -> Any:
        kwargs["strict"] = False
        return original_load_model(*args, **kwargs)

    mlx_utils.load_model = load_model_wrapped  # type: ignore[assignment]


def main() -> None:
    warnings.filterwarnings(
        "ignore",
        message=".*not recommended for production.*",
        category=UserWarning,
    )
    _install_mlx_load_model_skip_extra_weights()
    _install_gemma4_tool_patch()
    sys.argv = [sys.argv[0], "server", *sys.argv[1:]]

    from mlx_lm import cli

    cli.main()


if __name__ == "__main__":
    main()
