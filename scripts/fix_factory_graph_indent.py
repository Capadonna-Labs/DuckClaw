#!/usr/bin/env python3
"""Fix indentation in generated factory_graph_* modules."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "packages/agents/src/duckclaw/workers"


def strip_template_indent(text: str) -> str:
    lines = text.splitlines()
    out: list[str] = []
    for line in lines:
        if line.startswith("            "):
            out.append(line[12:])
        else:
            out.append(line)
    return "\n".join(out).strip() + "\n"


def indent_block(text: str, spaces: int = 4) -> str:
    prefix = " " * spaces
    return "\n".join(prefix + line if line.strip() else line for line in text.splitlines())


def fix_setup(path: Path) -> None:
    raw = strip_template_indent(path.read_text(encoding="utf-8"))
    lines = raw.splitlines()
    # Find injection point after ctx.db = db
    start = next(i for i, ln in enumerate(lines) if ln.strip() == "ctx.db = db")
    # Find context_guard_config block
    guard_idx = next(
        i for i, ln in enumerate(lines) if ln.strip().startswith("context_guard_config =")
    )
    head = "\n".join(lines[: start + 1])
    body = "\n".join(lines[start + 1 : guard_idx])
    tail = "\n".join(lines[guard_idx:])
    fixed = head + "\n" + indent_block(body) + "\n" + tail
    path.write_text(fixed, encoding="utf-8")


def fix_make_node_file(path: Path, *, unpack_end_marker: str | None = None) -> None:
    raw = strip_template_indent(path.read_text(encoding="utf-8"))
    lines = raw.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if re.match(r"def make_\w+\(ctx", line):
            out.append(line)
            i += 1
            # optional blank
            if i < len(lines) and not lines[i].strip():
                out.append(lines[i])
                i += 1
            # unpack block until blank line before def inner
            unpack: list[str] = []
            while i < len(lines):
                if lines[i].startswith("def ") and "state" in lines[i]:
                    break
                if lines[i].strip().startswith("from duckclaw") and unpack:
                    break
                unpack.append(lines[i])
                i += 1
            while i < len(lines) and lines[i].strip().startswith("from duckclaw"):
                unpack.append(lines[i])
                i += 1
                if i < len(lines) and lines[i].strip() == ")":
                    unpack.append(lines[i])
                    i += 1
            for u in unpack:
                out.append(("    " + u) if u.strip() else u)
            if unpack and unpack[-1].strip():
                out.append("")
            continue
        out.append(line)
        i += 1
    path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")


def main() -> None:
    for name in sorted(ROOT.glob("factory_graph_*.py")):
        if name.name == "factory_graph_builder.py":
            continue
        text = name.read_text(encoding="utf-8")
        if name.name == "factory_graph_setup.py":
            fix_setup(name)
            print(f"fixed setup: {len(name.read_text().splitlines())} lines")
            continue
        if name.name == "factory_graph_context.py":
            name.write_text(strip_template_indent(text), encoding="utf-8")
            print(f"fixed {name.name}")
            continue
        if "make_" in text:
            fix_make_node_file(name)
            print(f"fixed {name.name}: {len(name.read_text().splitlines())} lines")
        else:
            name.write_text(strip_template_indent(text), encoding="utf-8")
            print(f"stripped {name.name}: {len(name.read_text().splitlines())} lines")


if __name__ == "__main__":
    main()
