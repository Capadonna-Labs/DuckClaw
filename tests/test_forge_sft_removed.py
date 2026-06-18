from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_forge_sft_training_runtime_is_removed() -> None:
    removed_paths = [
        REPO_ROOT / "packages/agents/src/duckclaw/forge/sft",
        REPO_ROOT / "packages/agents/src/duckclaw/forge/skills/sft_bridge.py",
        REPO_ROOT / "packages/agents/src/duckclaw/forge/eval",
        REPO_ROOT / "services/api-gateway/routers/admin_train.py",
    ]

    for path in removed_paths:
        if not path.exists():
            continue
        if path.is_file():
            raise AssertionError(f"legacy SFT runtime file still exists: {path}")
        py_files = sorted(path.rglob("*.py"))
        assert py_files == [], f"legacy SFT runtime Python still present under {path}: {py_files}"


def test_mlops_train_and_traces_are_canonical_entrypoints() -> None:
    from duckclaw.train import MlxSFT
    from duckclaw.traces import TraceCollector

    assert MlxSFT and TraceCollector


def test_runtime_code_does_not_import_or_register_legacy_forge_sft_training() -> None:
    scanned_roots = [
        REPO_ROOT / "packages/agents/src/duckclaw",
        REPO_ROOT / "services/api-gateway",
    ]
    banned_tokens = (
        "duckclaw.forge.sft",
        "duckclaw.forge.skills.sft_bridge",
        "collect_sft_dataset",
        "admin_train",
    )
    allowlist_suffixes = (
        "duckclaw/train/",
        "duckclaw/traces/",
    )

    offenders: list[str] = []
    for root in scanned_roots:
        for path in root.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            rel = path.relative_to(REPO_ROOT).as_posix()
            if any(rel.startswith(prefix) for prefix in allowlist_suffixes):
                continue
            text = path.read_text(encoding="utf-8")
            for token in banned_tokens:
                if token in text:
                    offenders.append(f"{rel} contains {token!r}")

    assert offenders == []
