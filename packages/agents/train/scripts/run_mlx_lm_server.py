#!/usr/bin/env python3
"""Duckclaw entry for `mlx_lm server`: patch Gemma4 tool JSON parsing, then run the official CLI.

mlx_lm's gemma4 tool parser uses json.loads on a normalized string; model output can still
violate strict JSON (e.g. spaces before bare keys, trailing commas). This module applies
small repairs before delegating to mlx_lm.cli.
"""
from __future__ import annotations

import json
import os
import re
import sys
import warnings
from typing import Any


def _json_repair_candidates(s: str) -> list[str]:
    """Yield unique candidate strings to try with json.loads (H1–H3)."""
    seen: set[str] = set()
    out: list[str] = []

    def add(x: str) -> None:
        if x not in seen:
            seen.add(x)
            out.append(x)

    add(s)
    # H1: trailing commas
    t = re.sub(r",\s*}", "}", s)
    t = re.sub(r",\s*]", "]", t)
    add(t)
    # H2: whitespace before bare keys after { or ,
    k = re.sub(r"([{,])\s*(\w+)\s*:", r'\1"\2":', s)
    add(k)
    kt = re.sub(r"([{,])\s*(\w+)\s*:", r'\1"\2":', t)
    kt = re.sub(r",\s*}", "}", kt)
    kt = re.sub(r",\s*]", "]", kt)
    add(kt)
    # H3: unicode “smart” quotes → ASCII (keys/strings only as whole-string heuristic)
    smart = (
        s.replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2018", "'")
        .replace("\u2019", "'")
    )
    add(smart)
    return out


def _install_gemma4_tool_patch() -> None:
    import mlx_lm.tool_parsers.gemma4 as g4

    _to_json = g4._gemma4_args_to_json

    def _parse_single_wrapped(match: Any) -> dict[str, Any]:
        func_name = match.group(1)
        args_str = match.group(2)
        json_str = _to_json(args_str)
        last_err: json.JSONDecodeError | None = None
        for cand in _json_repair_candidates(json_str):
            try:
                arguments = json.loads(cand)
                return {"name": func_name, "arguments": arguments}
            except json.JSONDecodeError as e:
                last_err = e
                continue
        # H4: Python-literal dict (only when braces look like a single dict)
        try:
            import ast

            stripped = args_str.strip()
            if stripped.startswith("{") and stripped.endswith("}"):
                pyish = (
                    stripped.replace("true", "True")
                    .replace("false", "False")
                    .replace("null", "None")
                )
                obj = ast.literal_eval(pyish)
                if isinstance(obj, dict):
                    return {"name": func_name, "arguments": obj}
        except (SyntaxError, ValueError, TypeError):
            pass
        if last_err is not None:
            raise last_err
        raise RuntimeError("tool args JSON parse failed (no JSONDecodeError)")

    g4._parse_single = _parse_single_wrapped


def main() -> None:
    warnings.filterwarnings(
        "ignore",
        message=".*not recommended for production.*",
        category=UserWarning,
    )
    _install_gemma4_tool_patch()
    server_args = sys.argv[1:]
    sys.argv = [sys.argv[0], "server", *server_args]
    from mlx_lm import cli

    cli.main()


if __name__ == "__main__":
    main()
