from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

MANAGER_CORE_FILES = (
    REPO_ROOT / "packages/agents/src/duckclaw/manager/graph.py",
    REPO_ROOT / "packages/agents/src/duckclaw/manager/routing.py",
    REPO_ROOT / "packages/agents/src/duckclaw/manager/fast_plans.py",
)

VERTICAL_MANAGER_CORE_RE = re.compile(
    r"(?i)(?<![a-z0-9])("
    r"job(?:[_-]?hunter)?"
    r"|empleo"
    r"|trabajo"
    r"|vacante"
    r"|hunter"
    r"|finanz(?:as)?"
    r"|finance"
    r"|quant(?:[_-]?trader)?"
    r"|trader"
    r"|pqrsd?"
    r"|leila"
    r"|war[_ -]?room"
    r"|wr_"
    r")(?![a-z0-9])"
)


def test_manager_graph_and_routing_do_not_hardcode_verticals() -> None:
    offenders: list[str] = []
    for path in MANAGER_CORE_FILES:
        source = path.read_text(encoding="utf-8", errors="ignore")
        rel_path = path.relative_to(REPO_ROOT).as_posix()
        for line_no, line in enumerate(source.splitlines(), start=1):
            for match in VERTICAL_MANAGER_CORE_RE.finditer(line):
                offenders.append(f"{rel_path}:{line_no}: {match.group(0)}")

    assert offenders == []
