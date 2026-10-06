"""read_disk_text paths: root_hint by root name, and 'did you mean' for a wrong path."""

from __future__ import annotations

from pathlib import Path

import pytest

from duckclaw.forge.rag import knowledge_paths as kp


@pytest.fixture()
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    r = tmp_path / "Vertical-Repo"
    (r / "workers" / "app" / "lib").mkdir(parents=True)
    (r / "workers" / "app" / "lib" / "bridge.py").write_text("x = 1\n", encoding="utf-8")
    (r / ".venv" / "lib").mkdir(parents=True)
    (r / ".venv" / "lib" / "bridge.py").write_text("vendored\n", encoding="utf-8")
    monkeypatch.setattr(kp, "knowledge_allowed_roots", lambda: [r.resolve()])
    monkeypatch.setattr(kp, "knowledge_output_roots", lambda: [])
    return r.resolve()


def test_root_hint_accepts_the_root_name(root: Path) -> None:
    got = kp.resolve_readable_document_path(relative_path="workers/app/lib/bridge.py", root_hint="Vertical-Repo")
    assert got == root / "workers" / "app" / "lib" / "bridge.py"


def test_wrong_path_suggests_the_real_location(root: Path) -> None:
    for path in ("lib/bridge.py", str(root / "lib" / "bridge.py")):
        with pytest.raises(ValueError) as exc:
            kp.resolve_readable_document_path(relative_path=path, root_hint="Vertical-Repo")
        msg = str(exc.value)
        assert str(root / "workers" / "app" / "lib" / "bridge.py") in msg
        assert ".venv" not in msg
