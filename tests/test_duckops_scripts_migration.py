from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from duckops.cli import app


runner = CliRunner()


def test_duckops_exposes_script_replacement_commands() -> None:
    commands = (
        ["ingress", "serve-admin", "--dry-run"],
        ["ingress", "restore-admin-serve", "--dry-run"],
        ["ingress", "telegram-check", "--dry-run"],
        ["ingress", "telegram-register-webhooks", "--dry-run"],
        ["ingress", "telegram-start", "--dry-run"],
        ["mcp", "prefetch", "reddit", "--dry-run"],
        ["comfyui", "start", "--dry-run"],
        ["db", "bootstrap", "--dry-run"],
        ["db", "check-locks", "--dry-run"],
        ["db", "authorized-users", "--dry-run"],
        ["db", "fresh-dev", "--dry-run"],
        ["db", "migrate-legacy-axis", "--dry-run"],
        ["deploy", "spawn-install", "--dry-run"],
    )
    for command in commands:
        result = runner.invoke(app, command)
        assert result.exit_code == 0, (command, result.output)
        assert "dry-run" in result.output.lower()


def test_one_off_scripts_removed_from_active_scripts() -> None:
    removed = (
        "scripts/crm_origin_check.py",
        "scripts/openweather_city.py",
        "scripts/experimental/remap_weights.py",
        "scripts/fresh_dev_platform.sh",
        "scripts/migrate_legacy_axis_vault.sh",
        "scripts/doctor.py",
        "scripts/bootstrap_dbs.py",
        "scripts/migrate.py",
        "scripts/healthcheck.py",
        "scripts/bootstrap_team_admin.py",
        "scripts/register_webhooks.py",
        "scripts/restore_tailscale_admin_serve.py",
        "scripts/start_telegram_ingress.py",
        "scripts/check_telegram_ingress.py",
        "scripts/import_templates_to_catalog.py",
        "scripts/cleanup_default_duckdb_tenant_schemas.py",
        "scripts/migrations/003_admin_user_workspaces.py",
        "scripts/migrations/004_admin_workspace_catalog.py",
        "scripts/telegram/stop_discord_mcp_port_8000.sh",
        "packages/shared/scripts/sync_telegram_duckdb.sh",
        "packages/shared/scripts/install_duckclaw.sh",
        "docs/core",
        "docs/operations",
        "docs/architecture/UIUX-PATTERNS.md",
        "docs/architecture/DB_FIRST_CORE_REFACTOR.md",
        "docs/architecture/ADMIN_IDENTITY_RBAC_ERD.md",
        "docs/architecture/infra-bootstrap.md",
        "docs/architecture/TAILSCALE_CONFIGURATION.md",
        "apps/duckclaw-admin/docs",
    )
    for path in removed:
        assert not Path(path).exists(), path


def test_duckops_modules_replace_retired_scripts() -> None:
    present = (
        "packages/duckops/duckops/db_bootstrap.py",
        "packages/duckops/duckops/db_vault_ops.py",
        "packages/duckops/duckops/db_cleanup_tenant.py",
        "packages/duckops/duckops/ingress_register_webhooks.py",
        "packages/duckops/duckops/ingress_restore_admin.py",
        "packages/duckops/duckops/ingress_telegram_start.py",
        "packages/duckops/duckops/import_templates_cli.py",
    )
    for path in present:
        assert Path(path).is_file(), path


def test_surviving_docs_are_contracts_not_implementation_journals() -> None:
    architecture = Path("docs/architecture")
    surviving = {p.name for p in architecture.glob("*.md")}
    assert surviving == {
        "GATEWAY_DB_WRITER_BOUNDARIES.md",
        "GATEWAY_PROCESS_BOUNDARIES.md",
        "MULTI_VAULT_SYSTEM.md",
        "singleton_writer.md",
        "system_overview.md",
        "tri_cameral_memory.md",
    }
    banned_fragments = (
        "Instrucciones Para Subagentes",
        "Lo Movido O Limpiado",
        "Hito 2",
        "packages/shared/scripts/",
    )
    for path in architecture.glob("*.md"):
        text = path.read_text(encoding="utf-8")
        for needle in banned_fragments:
            assert needle not in text, f"{path}: still mentions {needle}"
