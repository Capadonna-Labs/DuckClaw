"""Pytest: variables de entorno por defecto para tests (sin secretos)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from env_ids import owner_user_id_from_env, test_telegram_user_id_from_env

# Permite `from scripts.foo import ...` en tests (p. ej. sanitize_traces_for_gemma).
_repo_root = Path(__file__).resolve().parents[1]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

# DuckDB INSTALL json: home escribible (evita ~/.duckdb en CI/sandbox).
_pytest_duckdb_home = _repo_root / ".pytest_duckdb"
_pytest_duckdb_home.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("DUCKCLAW_TEST_DUCKDB_HOME", str(_pytest_duckdb_home))

# API Gateway y db-writer exigen REDIS_URL o DUCKCLAW_REDIS_URL (sin fallback en código).
os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:6379/0")


@pytest.fixture(autouse=True)
def _isolate_test_env_from_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    from env_isolation import isolate_test_env_from_dotenv

    isolate_test_env_from_dotenv(monkeypatch)


@pytest.fixture
def owner_user_id() -> str:
    """``DUCKCLAW_OWNER_ID`` / ``DUCKCLAW_ADMIN_CHAT_ID`` desde .env."""
    uid = owner_user_id_from_env()
    if not uid:
        pytest.skip("Definir DUCKCLAW_OWNER_ID o DUCKCLAW_ADMIN_CHAT_ID en .env")
    return uid


@pytest.fixture
def test_telegram_user_id() -> str:
    return test_telegram_user_id_from_env()


@pytest.fixture
def admin_client(gateway_db: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from gateway_import import load_gateway_app

    monkeypatch.setenv("DUCKCLAW_ADMIN_API_KEY", "test-admin-key")
    monkeypatch.setenv("DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES", "")
    monkeypatch.setenv("DUCKCLAW_REPO_ROOT", str(_repo_root))
    return TestClient(load_gateway_app())


class SessionFakeRedis:
    """Minimal async Redis for admin session tests."""

    def __init__(self) -> None:
        import time

        self._time = time
        self._values: dict[str, str] = {}
        self._expiry: dict[str, float] = {}

    def _purge(self, key: str) -> None:
        exp = self._expiry.get(key)
        if exp is not None and exp <= self._time.monotonic():
            self._values.pop(key, None)
            self._expiry.pop(key, None)

    async def incr(self, key: str) -> int:
        self._purge(key)
        n = int(self._values.get(key, "0")) + 1
        self._values[key] = str(n)
        return n

    async def expire(self, key: str, seconds: int) -> bool:
        self._expiry[key] = self._time.monotonic() + int(seconds)
        return True

    async def get(self, key: str) -> str | None:
        self._purge(key)
        return self._values.get(key)

    async def setex(self, key: str, seconds: int, value: str) -> bool:
        self._values[key] = value
        self._expiry[key] = self._time.monotonic() + int(seconds)
        return True

    async def delete(self, *keys: str) -> int:
        removed = 0
        for key in keys:
            if key in self._values or key in self._expiry:
                removed += 1
            self._values.pop(key, None)
            self._expiry.pop(key, None)
        return removed

    async def ttl(self, key: str) -> int:
        self._purge(key)
        exp = self._expiry.get(key)
        if exp is None:
            return -1
        return max(0, int(exp - self._time.monotonic()))


@pytest.fixture
def session_redis() -> SessionFakeRedis:
    return SessionFakeRedis()


class _GatewayDbAdapter:
    def __init__(self, con) -> None:
        self._con = con

    def execute(self, sql: str, params=None):
        if params is not None:
            return self._con.execute(sql, params)
        return self._con.execute(sql)


@pytest.fixture
def gateway_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    import duckdb

    from duckclaw.admin_console_users import ensure_admin_console_users_table, upsert_console_user
    from duckclaw.gateway_db import GATEWAY_DB_ENV_KEYS
    from duckclaw.shared_db_grants import ensure_user_shared_db_access_table

    p = tmp_path / "gateway.duckdb"
    for key in GATEWAY_DB_ENV_KEYS:
        monkeypatch.setenv(key, str(p))
    con = duckdb.connect(str(p))
    try:
        adapter = _GatewayDbAdapter(con)
        ensure_admin_console_users_table(adapter)
        ensure_user_shared_db_access_table(adapter)
        upsert_console_user(
            adapter,
            email="admin@test.local",
            nombre="Admin Test",
            rol="admin",
            password="secret123",
            initials="AT",
        )
        import importlib

        importlib.import_module("scripts.migrations.003_admin_user_workspaces").apply_migration(con)
        importlib.import_module("scripts.migrations.004_admin_workspace_catalog").apply_migration(con)
    finally:
        con.close()
    return p


@pytest.fixture
def gateway_admin_client(gateway_db: Path, monkeypatch: pytest.MonkeyPatch, session_redis) -> TestClient:
    from gateway_import import load_gateway_app

    monkeypatch.setenv("DUCKCLAW_ADMIN_API_KEY", "test-admin-key")
    monkeypatch.setenv("DUCKCLAW_REPO_ROOT", str(_repo_root))
    client = TestClient(load_gateway_app())
    client.app.state.redis = session_redis
    return client


@pytest.fixture(scope="session")
def catalog_db():
    import subprocess
    import tempfile
    from pathlib import Path

    import duckdb

    from duckclaw.admin_worker_catalog import ensure_admin_worker_catalog_schema
    from duckclaw.catalog_seed import seed_catalog_from_templates

    tmp = Path(tempfile.mkdtemp())
    db = duckdb.connect(str(tmp / "catalog.duckdb"))
    ensure_admin_worker_catalog_schema(db)

    _extract_test_seeds(tmp)
    seed_catalog_from_templates(
        db,
        owner_email="test@duckclaw.local",
        templates_root=str(tmp / "seed_templates"),
        include_template_ids=(),
        tenant_id="default",
    )

    yield db
    db.close()


def _extract_test_seeds(target: Path) -> None:
    """Extract template files from git history for test catalog seeding."""
    import subprocess

    commit = "60295ad"
    templates_source = "packages/agents/src/duckclaw/forge/templates"
    seed_dir = target / "seed_templates"

    # Workers to extract
    for wid in ("BI-Analyst", "default", "finanz", "Job-Hunter", "Manager",
                "PQRSD-Assistant", "Quant-Trader", "research_worker",
                "SIATA-Analyst", "support"):
        wdir = seed_dir / wid
        wdir.mkdir(parents=True, exist_ok=True)
        for fname in ("manifest.yaml", "system_prompt.md", "schema.sql",
                       "seed_data.sql", "soul.md", "domain_closure.md",
                       "security_policy.yaml", "homeostasis.yaml",
                       "AGENT_OVERVIEW.md", "orchestrator_planner.md"):
            src = f"{commit}:{templates_source}/{wid}/{fname}"
            try:
                out = subprocess.check_output(
                    ["git", "show", src],
                    stderr=subprocess.DEVNULL,
                )
                (wdir / fname).write_bytes(out)
            except subprocess.CalledProcessError:
                pass

        # Skills
        try:
            skill_files = subprocess.check_output(
                ["git", "ls-tree", "--name-only", f"{commit}:{templates_source}/{wid}/skills"],
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip().split("\n")
            sdir = wdir / "skills"
            sdir.mkdir(exist_ok=True)
            for sf in skill_files:
                sf = sf.strip()
                if sf:
                    out = subprocess.check_output(
                        ["git", "show", f"{commit}:{templates_source}/{wid}/skills/{sf}"],
                        stderr=subprocess.DEVNULL,
                    )
                    (sdir / sf).write_bytes(out)
        except subprocess.CalledProcessError:
            pass

        # Guardrails
        try:
            gr_files = subprocess.check_output(
                ["git", "ls-tree", "--name-only", f"{commit}:{templates_source}/{wid}/guardrails"],
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip().split("\n")
            gdir = wdir / "guardrails"
            gdir.mkdir(exist_ok=True)
            for gf in gr_files:
                gf = gf.strip()
                if gf:
                    out = subprocess.check_output(
                        ["git", "show", f"{commit}:{templates_source}/{wid}/guardrails/{gf}"],
                        stderr=subprocess.DEVNULL,
                    )
                    (gdir / gf).write_bytes(out)
        except subprocess.CalledProcessError:
            pass


def load_test_manifest(worker_id, db):
    from duckclaw.workers.manifest import load_manifest

    return load_manifest(worker_id, db=db, tenant_id="default")
