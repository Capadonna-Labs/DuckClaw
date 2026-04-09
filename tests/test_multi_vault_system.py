from __future__ import annotations

import pytest

from duckclaw.graphs.on_the_fly_commands import handle_command
from duckclaw.workers.manifest import WorkerSpec
from duckclaw.workers import factory as worker_factory
from duckclaw.vaults import (
    create_vault,
    list_vaults,
    remove_vault,
    resolve_active_vault,
    shared_tenant_dir,
    switch_vault,
    validate_user_db_path,
    vault_scope_id_for_tenant,
)


@pytest.fixture(autouse=True)
def _duckclaw_repo_root_is_tmp(tmp_path, monkeypatch):
    """Evita leer/escribir db/ del monorepo real si DUCKCLAW_REPO_ROOT está definido en el entorno."""
    monkeypatch.setenv("DUCKCLAW_REPO_ROOT", str(tmp_path))
    monkeypatch.delenv("DUCKCLAW_PM2_PROCESS_NAME", raising=False)
    monkeypatch.delenv("DUCKCLAW_PM2_MATCHED_APP_NAME", raising=False)
    monkeypatch.delenv("DUCKCLAW_DB_PATH", raising=False)
    monkeypatch.delenv("DUCKCLAW_FINANZ_DB_PATH", raising=False)
    monkeypatch.delenv("DUCKCLAW_JOB_HUNTER_DB_PATH", raising=False)
    monkeypatch.delenv("DUCKCLAW_SIATA_DB_PATH", raising=False)
    monkeypatch.delenv("DUCKCLAW_QUANT_TRADER_DB_PATH", raising=False)
    monkeypatch.delenv("DUCKCLAW_WAR_ROOM_ACL_DB_PATH", raising=False)
    monkeypatch.delenv("DUCKDB_PATH", raising=False)


class _DummyDB:
    def execute(self, *_args, **_kwargs):
        return None

    def query(self, *_args, **_kwargs):
        return "[]"


def test_resolve_active_vault_bootstraps_default(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    vault_id, db_path = resolve_active_vault("1726618406")
    assert vault_id == "default"
    assert db_path.endswith("default.duckdb")


def test_create_switch_remove_vault_cycle(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _ = resolve_active_vault("user1")
    created = create_vault("user1", "inversiones")
    assert created["vault_id"].startswith("inversiones")
    assert switch_vault("user1", created["vault_id"]) is True
    active_id, active_path = resolve_active_vault("user1")
    assert active_id == created["vault_id"]
    assert validate_user_db_path("user1", active_path) is True
    assert remove_vault("user1", created["vault_id"]) is True
    active_id_after, _ = resolve_active_vault("user1")
    assert active_id_after == "default"


def test_vault_command_flow(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db = _DummyDB()
    out = handle_command(db, "chat1", "/vault", requester_id="u1", tenant_id="default", vault_user_id="u1")
    assert out and "Bóveda activa" in out
    out = handle_command(db, "chat1", "/vault new trabajo", requester_id="u1", tenant_id="default", vault_user_id="u1")
    assert out and "Bóveda creada" in out
    rows = list_vaults("u1")
    target = [r for r in rows if r["vault_id"] != "default"][0]["vault_id"]
    out = handle_command(db, "chat1", f"/vault use {target}", requester_id="u1", tenant_id="default", vault_user_id="u1")
    assert out and "activa actual" in out


def test_scoped_resolve_ignores_finanzdb_on_disk(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DUCKCLAW_MULTI_VAULT_INITIAL_VAULT_ID", raising=False)
    user = "1726618406"
    private_dir = tmp_path / "db" / "private" / user
    private_dir.mkdir(parents=True, exist_ok=True)
    (private_dir / "finanzdb1.duckdb").write_bytes(b"x" * 200_000)
    active_id, active_path = resolve_active_vault(user, scope_id="trabajo")
    assert active_id == "default"
    assert active_path.endswith("default.duckdb")


def test_scoped_initial_vault_from_env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DUCKCLAW_MULTI_VAULT_INITIAL_VAULT_ID", "job_hunter")
    user = "1726618406"
    private_dir = tmp_path / "db" / "private" / user
    private_dir.mkdir(parents=True, exist_ok=True)
    (private_dir / "finanzdb1.duckdb").write_bytes(b"x" * 200_000)
    active_id, active_path = resolve_active_vault(user, scope_id="trabajo")
    assert active_id == "job_hunter"
    assert "job_hunter" in active_path


def test_vault_scope_id_for_tenant_slug():
    assert vault_scope_id_for_tenant("default") == ""
    assert vault_scope_id_for_tenant("") == ""
    assert vault_scope_id_for_tenant("Trabajo") == "trabajo"


def test_read_only_skips_agent_config_ddl_rw_persists_chat_state(tmp_path) -> None:
    """Gateway fly path debe usar DuckClaw RW: en RO no hay CREATE y SELECT a agent_config falla."""
    from duckclaw import DuckClaw
    from duckclaw.graphs.on_the_fly_commands import _ensure_agent_config, get_chat_state, set_chat_state

    p = tmp_path / "vault.duckdb"
    _bootstrap = DuckClaw(str(p), read_only=False)
    _bootstrap.execute("SELECT 1")
    _bootstrap.close()

    ro = DuckClaw(str(p), read_only=True)
    _ensure_agent_config(ro)
    assert get_chat_state(ro, "chat1", "team_templates") == ""
    ro.close()

    rw = DuckClaw(str(p), read_only=False)
    _ensure_agent_config(rw)
    set_chat_state(rw, "chat1", "team_templates", '["Job-Hunter"]')
    assert get_chat_state(rw, "chat1", "team_templates") == '["Job-Hunter"]'
    rw.close()


def test_vault_fly_uses_session_duckdb_path_over_dedicated_env(tmp_path, monkeypatch):
    """Multiplex: el gateway abre DuckClaw(bóveda del bot); /vault debe mostrar ese archivo, no la FINANZ por defecto."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DUCKCLAW_REPO_ROOT", str(tmp_path))
    fin = tmp_path / "finanzdb1.duckdb"
    fin.write_bytes(b"x" * 100)
    siata = tmp_path / "siatadb1.duckdb"
    siata.write_bytes(b"y" * 100)
    monkeypatch.setenv("DUCKCLAW_FINANZ_DB_PATH", str(fin))
    monkeypatch.setenv("DUCKCLAW_PM2_PROCESS_NAME", "DuckClaw-Gateway")

    db = _DummyDB()
    db._path = str(siata.resolve())
    out = handle_command(db, "c1", "/vault", tenant_id="SIATA", vault_user_id="u1", requester_id="u1")
    assert out and "siatadb1.duckdb" in out
    assert "finanzdb1.duckdb" not in out
    assert "Tenant: SIATA" in out


def test_vault_fly_quant_trader_label_from_path(tmp_path, monkeypatch):
    """/vault con sesión en quant_traderdb1 muestra etiqueta Quant Trader aunque tenant sea Finanzas."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DUCKCLAW_REPO_ROOT", str(tmp_path))
    q = tmp_path / "quant_traderdb1.duckdb"
    q.write_bytes(b"x" * 100)
    db = _DummyDB()
    db._path = str(q.resolve())
    out = handle_command(db, "c1", "/vault", tenant_id="Finanzas", vault_user_id="u1", requester_id="u1")
    assert out and "quant_traderdb1.duckdb" in out
    assert "Quant Trader" in out
    assert "gateway (Finanz)" not in out


def test_vault_command_scoped_tenant(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DUCKCLAW_MULTI_VAULT_INITIAL_VAULT_ID", raising=False)
    db = _DummyDB()
    private_dir = tmp_path / "db" / "private" / "u1"
    private_dir.mkdir(parents=True, exist_ok=True)
    (private_dir / "finanzdb1.duckdb").write_bytes(b"x" * 200_000)
    out = handle_command(db, "chat1", "/vault", requester_id="u1", tenant_id="Trabajo", vault_user_id="u1")
    assert out and "default" in out
    assert "finanzdb1" not in out


def test_resolve_promotes_existing_non_default_when_default_active(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    user = "1726618406"
    # Bootstraps default as active
    _ = resolve_active_vault(user)
    # Create a larger real vault file manually (simulate prior data)
    private_dir = tmp_path / "db" / "private" / user
    private_dir.mkdir(parents=True, exist_ok=True)
    real_vault = private_dir / "finanzdb1.duckdb"
    real_vault.write_bytes(b"x" * 200_000)
    active_id, active_path = resolve_active_vault(user)
    assert active_id == "finanzdb1"
    assert active_path.endswith("finanzdb1.duckdb")


def test_validate_shared_paths_user_and_tenant(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    user = "u-shared"
    tenant = "Leila Store"
    private_dir = tmp_path / "db" / "private" / user
    private_dir.mkdir(parents=True, exist_ok=True)
    shared_user = tmp_path / "db" / "shared" / user
    shared_user.mkdir(parents=True, exist_ok=True)
    tid_slug = "leila_store"
    shared_tenant = tmp_path / "db" / "shared" / tid_slug
    shared_tenant.mkdir(parents=True, exist_ok=True)
    p_private = private_dir / "x.duckdb"
    p_private.write_bytes(b"x")
    p_su = shared_user / "a.duckdb"
    p_su.write_bytes(b"x")
    p_st = shared_tenant / "cat.duckdb"
    p_st.write_bytes(b"x")

    assert validate_user_db_path(user, str(p_private.resolve())) is True
    assert validate_user_db_path(user, str(p_su.resolve())) is True
    assert validate_user_db_path(user, str(p_st.resolve())) is False
    assert validate_user_db_path(user, str(p_st.resolve()), tenant_id=tenant) is True
    assert validate_user_db_path(user, str(p_st.resolve()), tenant_id="other_tenant") is False


def test_resolve_shared_db_path_requires_manifest_env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    spec = WorkerSpec(
        worker_id="w",
        logical_worker_id="w",
        name="W",
        schema_name="w",
        llm_required=None,
        temperature=0.2,
        topology="general",
        skills_list=[],
        allowed_tables=[],
        read_only=False,
        worker_dir=tmp_path,
        forge_shared_db_path_env="DUCKCLAW_SHARED_DB_PATH",
    )
    monkeypatch.delenv("DUCKCLAW_SHARED_DB_PATH", raising=False)
    assert worker_factory._resolve_shared_db_path(spec, None) is None
    monkeypatch.setenv("DUCKCLAW_SHARED_DB_PATH", str(tmp_path / "c.duckdb"))
    assert worker_factory._resolve_shared_db_path(spec, None) == str(tmp_path / "c.duckdb")
    assert worker_factory._resolve_shared_db_path(spec, "/override/path.duckdb") == "/override/path.duckdb"


def test_shared_tenant_dir_ensures_folder(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    d = shared_tenant_dir("Acme Corp")
    assert d.is_dir()
    assert "shared" in d.parts
    assert "acme_corp" == d.name


def test_list_and_use_detect_files_not_pre_registered(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    user = "u-detector"
    private_dir = tmp_path / "db" / "private" / user
    private_dir.mkdir(parents=True, exist_ok=True)
    (private_dir / "inversiones.duckdb").write_bytes(b"x" * 50_000)
    # list_vaults should discover filesystem vault and register it.
    rows = list_vaults(user)
    ids = {r["vault_id"] for r in rows}
    assert "inversiones" in ids
    assert switch_vault(user, "inversiones") is True
    active_id, _ = resolve_active_vault(user)
    assert active_id == "inversiones"
