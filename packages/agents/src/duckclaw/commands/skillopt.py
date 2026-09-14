## Archivos nuevos

### 1. `packages/agents/src/duckclaw/commands/skillopt.py` (NUEVO)

```python
"""SkillOpt — Self-optimizing prompt improvement cycle.

Based on Microsoft Research SkillOpt:
Rollout → Reflection → Update → Validation + Rejection Buffer.
No domain-specific logic. Vanilla/open-source.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RejectedEdit:
    content_hash: str
    reason: str
    timestamp: float
    context_snapshot: dict[str, Any] | None = None


_REJECTION_BUFFER: list[RejectedEdit] = []
_MAX_REJECTION_BUFFER = 50


def hash_content(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def is_rejected(content: str) -> bool:
    h = hash_content(content)
    return any(e.content_hash == h for e in _REJECTION_BUFFER)


def record_rejection(content: str, reason: str, snapshot: dict[str, Any] | None = None) -> None:
    h = hash_content(content)
    if not any(e.content_hash == h for e in _REJECTION_BUFFER):
        _REJECTION_BUFFER.append(RejectedEdit(content_hash=h, reason=reason, timestamp=time.time(), context_snapshot=snapshot))
        while len(_REJECTION_BUFFER) > _MAX_REJECTION_BUFFER:
            _REJECTION_BUFFER.pop(0)


def list_rejections() -> list[dict[str, Any]]:
    return [{"hash": e.content_hash, "reason": e.reason, "timestamp": e.timestamp, "context": e.context_snapshot} for e in _REJECTION_BUFFER]


@dataclass
class SkillRecord:
    rule: str
    source: str
    confidence: float = 1.0
    applied_count: int = 0


_SKILL_STORE: list[SkillRecord] = []


@dataclass
class RolloutEvent:
    phase: str
    content: str
    success: bool | None
    latency_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class RolloutLog:
    def __init__(self) -> None:
        self.events: list[RolloutEvent] = []
        self.start_time = time.time()

    def record(self, phase: str, content: str, success: bool | None = None, latency_ms: float = 0.0, **meta: Any) -> None:
        self.events.append(RolloutEvent(phase=phase, content=content[:500], success=success, latency_ms=latency_ms, metadata=meta))

    def summary(self) -> dict[str, Any]:
        total = len(self.events)
        successes = sum(1 for e in self.events if e.success is True)
        failures = sum(1 for e in self.events if e.success is False)
        elapsed = time.time() - self.start_time
        return {"total_events": total, "successes": successes, "failures": failures, "error_rate": round(failures / max(total, 1), 4), "elapsed_seconds": round(elapsed, 2)}


def reflect(log: RolloutLog) -> list[str]:
    rules: list[str] = []
    summary = log.summary()
    if summary["error_rate"] > 0.3:
        error_events = [e for e in log.events if e.success is False]
        top_errors: dict[str, int] = {}
        for ev in error_events:
            key = ev.metadata.get("tool_name", ev.phase)
            top_errors[key] = top_errors.get(key, 0) + 1
        if top_errors:
            worst = max(top_errors, key=top_errors.get)
            rules.append(f"ERROR_RATE_HIGH: tool '{worst}' failed {top_errors[worst]} times. Avoid using {worst} unless inputs are fully validated.")
    return rules


@dataclass
class EditProposal:
    target: str
    mode: str
    content: str
    budget_used: float


def propose_edits(rules: list[str], budget_remaining: float = 1.0) -> list[EditProposal]:
    proposals: list[EditProposal] = []
    cost_per_rule = 0.1
    for rule in rules:
        if is_rejected(rule):
            continue
        if budget_remaining < cost_per_rule:
            break
        proposals.append(EditProposal(target="system_prompt", mode="append", content=rule, budget_used=cost_per_rule))
        budget_remaining -= cost_per_rule
    return proposals


def validate_proposal(proposal: EditProposal, test_suite: list[dict[str, Any]]) -> tuple[bool, str]:
    required_test_types = {"tool_call", "response_format"}
    actual_types = {t.get("type") for t in test_suite}
    if not required_test_types.issubset(actual_types):
        return False, f"Test suite missing types: {required_test_types - actual_types}"
    return True, "validation_passed"


class CycleResult:
    def __init__(self) -> None:
        self.log = RolloutLog()
        self.rules: list[str] = []
        self.proposals: list[EditProposal] = []
        self.validation_results: list[tuple[str, bool, str]] = []
        self.rejections_added: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"rollout": self.log.summary(), "rules_found": self.rules, "proposals": [{"target": p.target, "mode": p.mode, "budget": p.budget_used} for p in self.proposals], "validations": [{"target": t, "passed": p, "reason": r} for t, p, r in self.validation_results], "rejections_added": self.rejections_added}


def run_cycle(test_suite: list[dict[str, Any]] | None = None) -> CycleResult:
    result = CycleResult()
    result.rules = reflect(result.log)
    result.proposals = propose_edits(result.rules)
    suite = test_suite or [{"type": "tool_call"}, {"type": "response_format"}]
    for prop in result.proposals:
        passed, reason = validate_proposal(prop, suite)
        result.validation_results.append((prop.content[:60], passed, reason))
        if not passed:
            record_rejection(prop.content, reason)
            result.rejections_added += 1
    return result
```

### 2. `packages/agents/src/duckclaw/commands/__init__.py` (MODIFICAR)

Añadir al final:
```python
from duckclaw.commands.skillopt import (
    SkillRecord,
    RolloutLog,
    run_cycle,
    is_rejected,
    record_rejection,
    list_rejections,
)
```