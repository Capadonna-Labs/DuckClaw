"""Tests forge_context.vault_binding (template → DuckDB path)."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_normalize_vault_binding_private() -> None:
    from duckclaw.vaults import normalize_vault_binding

    out = normalize_vault_binding({"scope": "private", "vault_id": "quant_traderdb1"})
    assert out == {"scope": "private", "vault_id": "quant_traderdb1"}


def test_normalize_vault_binding_shared_rejects_traversal() -> None:
    from duckclaw.vaults import normalize_vault_binding, resolve_template_vault_path

    assert normalize_vault_binding({"scope": "shared", "path": "../etc/passwd"}) is not None
    assert resolve_template_vault_path(
        {"scope": "shared", "path": "../etc/passwd"}, "u1", require_exists=False
    ) is None


def test_resolve_template_vault_path_private(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from duckclaw.vaults import resolve_template_vault_path, vault_file_path

    monkeypatch.setenv("DUCKCLAW_REPO_ROOT", str(tmp_path))
    uid = "user1"
    p = vault_file_path(uid, "myvault")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x" * 100)

    resolved = resolve_template_vault_path(
        {"scope": "private", "vault_id": "myvault"}, uid, require_exists=True
    )
    assert resolved is not None
    assert resolved.endswith("myvault.duckdb")


def test_list_vault_options_for_user_scoped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from duckclaw.vaults import list_vault_options_for_user

    monkeypatch.setenv("DUCKCLAW_REPO_ROOT", str(tmp_path))
    priv = tmp_path / "db" / "private" / "alice"
    priv.mkdir(parents=True)
    (priv / "a.duckdb").write_bytes(b"a")
    (priv / "b.duckdb").write_bytes(b"b")
    shared = tmp_path / "db" / "shared"
    shared.mkdir(parents=True)
    (shared / "catalog.duckdb").write_bytes(b"c")

    opts = list_vault_options_for_user("alice")
    scopes = {o["scope"] for o in opts}
    assert "private" in scopes
    assert "shared" in scopes
    private_ids = {o["vault_id"] for o in opts if o["scope"] == "private"}
    assert private_ids == {"a", "b"}


def test_load_manifest_parses_vault_binding(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from duckclaw.forge import WORKERS_TEMPLATES_DIR
    from duckclaw.workers.manifest import load_manifest

    worker_dir = Path(WORKERS_TEMPLATES_DIR) / "_test_vault_bind"
    if worker_dir.is_dir():
        import shutil

        shutil.rmtree(worker_dir)
    worker_dir.mkdir(parents=True)
    (worker_dir / "manifest.yaml").write_text(
        """
name: Test
id: test_vault
schema_name: main
forge_context:
  vault_binding:
    scope: private
    vault_id: finanzdb1
""".strip(),
        encoding="utf-8",
    )
    try:
        spec = load_manifest("_test_vault_bind")
        assert spec.forge_vault_binding == {"scope": "private", "vault_id": "finanzdb1"}
    finally:
        import shutil

        shutil.rmtree(worker_dir, ignore_errors=True)
