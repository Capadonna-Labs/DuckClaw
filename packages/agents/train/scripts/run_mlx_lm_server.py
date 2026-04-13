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
import time
import warnings
from pathlib import Path
from typing import Any


def _agent_log(hypothesis_id: str, location: str, message: str, data: dict[str, Any]) -> None:
    # #region agent log
    raw = os.environ.get("DUCKCLAW_DEBUG_LOG", "").strip()
    if not raw:
        return
    logp = Path(raw)
    try:
        rec = {
            "sessionId": "4a0206",
            "runId": os.environ.get("DEBUG_RUN_ID", "mlx-server"),
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000),
        }
        logp.parent.mkdir(parents=True, exist_ok=True)
        with logp.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass
    # #endregion agent log


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
                if cand != json_str:
                    _agent_log(
                        "H1",
                        "run_mlx_lm_server.py:_parse_single",
                        "json.loads ok after repair",
                        {
                            "repair": True,
                            "cand_len": len(cand),
                            "orig_len": len(json_str),
                            "func_name": func_name,
                        },
                    )
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
                    _agent_log(
                        "H4",
                        "run_mlx_lm_server.py:_parse_single",
                        "ast.literal_eval ok",
                        {"func_name": func_name, "args_len": len(args_str)},
                    )
                    return {"name": func_name, "arguments": obj}
        except (SyntaxError, ValueError, TypeError):
            pass
        if last_err is not None:
            _agent_log(
                "H5",
                "run_mlx_lm_server.py:_parse_single",
                "all parses failed",
                {
                    "func_name": func_name,
                    "json_len": len(json_str),
                    "err_pos": getattr(last_err, "pos", None),
                    "err_msg": (last_err.msg or "")[:160],
                },
            )
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
