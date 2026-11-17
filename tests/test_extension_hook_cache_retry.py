"""A skill hook that failed to resolve is retried, not cached away for the life of the process."""

from __future__ import annotations

from duckclaw.extensions import skills


def test_unresolved_hook_is_not_cached(monkeypatch) -> None:
    hook = lambda **kw: None  # noqa: E731
    results = [[], [hook]]
    monkeypatch.setattr(skills, "_HOOKS_CACHE", None)
    monkeypatch.setattr(skills, "_hook_specs", lambda *a, **k: [("skill_hooks:register_worker_skills", None, None)])
    monkeypatch.setattr(skills, "_build_hooks", lambda *a, **k: results.pop(0))
    assert skills.get_worker_skill_hooks() == []        # half-loaded module on the first build
    assert skills.get_worker_skill_hooks() == [hook]    # resolved on the next one
    assert skills._HOOKS_CACHE == [hook]
