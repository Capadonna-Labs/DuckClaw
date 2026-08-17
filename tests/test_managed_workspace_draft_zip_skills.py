"""Managed workspace draft: skill merge, policy v2 seed, confirm-with-import wiring."""

from __future__ import annotations

import io
import json
import tempfile
import zipfile
from pathlib import Path

import pytest

from gateway_import import ensure_gateway_on_sys_path


@pytest.fixture
def db_with_migrations():
    import duckdb

    from duckclaw.schema_migrations import run_pending_migrations

    tmp = Path(tempfile.mkdtemp())
    con = duckdb.connect(str(tmp / "test.duckdb"))
    run_pending_migrations(con)
    con.execute(
        "INSERT INTO main.admin_console_users (email, nombre, rol, password_hash) "
        "VALUES ('test@d.local', 'Test', 'admin', 'hash')"
    )
    con.execute(
        "INSERT INTO main.admin_user_profiles (email, tenant_id) "
        "VALUES ('test@d.local', 'default')"
    )
    yield con
    con.close()


@pytest.fixture
def managed_draft_mod():
    ensure_gateway_on_sys_path()
    from routers.admin_domains import workspace_managed_draft as mod

    return mod


def test_merge_suggested_skills_prefers_catalog_available(managed_draft_mod) -> None:
    merged = managed_draft_mod._merge_suggested_skills(
        [{"name": "Finance Tracker", "reason": "catalog", "available": True}],
        [
            {"name": "Finance Tracker", "reason": "llm overwrite", "available": False},
            {"name": "Budget Notes", "reason": "from llm", "available": False},
        ],
    )
    by_name = {item["name"]: item for item in merged}
    assert by_name["Finance Tracker"]["available"] is True
    assert by_name["Budget Notes"]["available"] is False


def test_merge_suggested_skills_keeps_catalog_when_llm_empty(managed_draft_mod) -> None:
    merged = managed_draft_mod._merge_suggested_skills(
        [{"name": "sql-helper", "reason": "hit", "available": True}],
        [],
    )
    assert len(merged) == 1
    assert merged[0]["name"] == "sql-helper"
    assert merged[0]["available"] is True


def test_prompt_tokens_expand_finance_synonyms(managed_draft_mod) -> None:
    tokens = managed_draft_mod._prompt_tokens("Administrar mis finanzas personales y el presupuesto")
    assert "finanzas" in tokens or "finance" in tokens
    assert "budget" in tokens or "presupuesto" in tokens


def test_managed_workspace_draft_policy_v2_seed_has_rich_sections() -> None:
    seed_path = Path(
        "packages/shared/src/duckclaw/seeds/managed_workspace_draft_policy_v2.json"
    )
    seed = json.loads(seed_path.read_text(encoding="utf-8"))
    policy = seed["policy"]
    shared = policy["fallback"]["shared_context_template"]
    for section in (
        "## Objetivo",
        "## Alcance",
        "## Datos y fuentes",
        "## Workers y roles",
        "## Skills sugeridas",
        "## Riesgos y límites",
        "## Primeros pasos",
    ):
        assert section in shared
        assert section in policy["draft_prompt_template"]


def test_confirm_with_import_route_and_spawn_imports_field() -> None:
    managed = Path(
        "services/api-gateway/routers/admin_domains/workspace_managed_draft.py"
    ).read_text(encoding="utf-8")
    commands = Path("packages/shared/src/duckclaw/write_commands.py").read_text(encoding="utf-8")
    handler = Path("packages/shared/src/duckclaw/write_handlers/workspace.py").read_text(
        encoding="utf-8"
    )

    assert "confirm-with-import" in managed
    assert "spawn_imports" in commands
    assert "import_spawn_package_to_catalog" in handler
    assert "_spawn_imports_from_uploads" in managed
    assert "analyze_spawn_package_from_bytes" in managed


def _minimal_spawn_zip(worker_id: str = "finance-zip-agent") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        root = f"{worker_id}-spawn-package"
        zf.writestr(
            f"{root}/manifest.yaml",
            f"id: {worker_id}\nname: Finance Zip\nskills: []\ntools: []\n",
        )
        zf.writestr(f"{root}/soul.md", "# soul\n")
        zf.writestr(f"{root}/system_prompt.md", "# system\n")
    return buf.getvalue()


def test_spawn_imports_from_uploads_parses_zip(managed_draft_mod, monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio

    monkeypatch.setattr(managed_draft_mod, "_runtime_tool_names", lambda: [])

    class _Upload:
        def __init__(self, raw: bytes, filename: str = "pkg.zip") -> None:
            self._raw = raw
            self.filename = filename

        async def read(self) -> bytes:
            return self._raw

    raw = _minimal_spawn_zip()
    imports = asyncio.run(
        managed_draft_mod._spawn_imports_from_uploads(
            [_Upload(raw)],
            [
                {
                    "file_index": 0,
                    "worker_id_override": None,
                    "role": "member",
                    "confirm_high_risk": False,
                }
            ],
        )
    )
    assert len(imports) == 1
    assert imports[0]["manifest"]["id"] == "finance-zip-agent"
    assert any(str(name).endswith("soul.md") or name == "soul.md" for name in imports[0]["files"])


def test_confirm_workspace_managed_draft_with_spawn_imports(db_with_migrations) -> None:
    from duckclaw.write_command_handlers import dispatch_command

    con = db_with_migrations
    payload = {
        "command_type": "confirm_workspace_managed_draft",
        "command_version": 1,
        "task_id": "task-managed-confirm-zip-1",
        "tenant_id": "default",
        "actor_email": "test@d.local",
        "project_id": "prj_managed_zip_1",
        "project_name": "Finanzas ZIP",
        "project_description": "Proyecto con worker importado",
        "workers": [],
        "shared_context": "# Contexto\n## Objetivo\nGestionar finanzas.",
        "suggested_skills": [],
        "source_kind": "managed_draft",
        "context_title": "Contexto compartido",
        "change_note": "Created from DB-first managed draft",
        "spawn_imports": [
            {
                "manifest": {
                    "id": "finance-zip-agent",
                    "name": "Finance Zip",
                    "skills": [],
                    "tools": [],
                },
                "files": {
                    "manifest.yaml": "id: finance-zip-agent\nname: Finance Zip\nskills: []\ntools: []\n",
                    "soul.md": "# soul\n",
                    "system_prompt.md": "# system\n",
                },
                "role": "member",
                "confirm_high_risk": False,
            }
        ],
    }

    dispatch_command(con, payload)

    project = con.execute(
        "SELECT COUNT(*) FROM main.admin_projects WHERE project_id = 'prj_managed_zip_1'"
    ).fetchone()[0]
    worker = con.execute(
        "SELECT COUNT(*) FROM main.admin_worker_catalog "
        "WHERE tenant_id = 'default' AND worker_id = 'finance-zip-agent'"
    ).fetchone()[0]
    assignment = con.execute(
        "SELECT COUNT(*) FROM main.admin_project_agents pa "
        "JOIN main.admin_worker_catalog w ON w.worker_uid = pa.worker_uid "
        "WHERE pa.project_id = 'prj_managed_zip_1' AND w.worker_id = 'finance-zip-agent'"
    ).fetchone()[0]

    assert project == 1
    assert worker == 1
    assert assignment == 1
