# Contributing to DuckClaw

Thanks for helping. DuckClaw is a generic, DB-first multi-agent harness; read
[CLAUDE.md](CLAUDE.md) for the architecture before changing anything that writes data.

## Workflow

1. Fork the repo and create a branch from `main` (`fix/...`, `feat/...`, `chore/...`).
2. Keep the change small and focused; one concern per pull request.
3. Open a pull request that says what changed, why, and how you tested it.

## Ground rules

- **Only the DB-Writer writes DuckDB.** Gateway, agents and indexers open the hub
  `read_only=True` and send typed commands (`duckclaw.write_commands`) through the
  Redis queue. See `docs/api/DB_WRITER_CONTRACT.md`.
- **No vertical-specific code.** Names, schemas, hosts or paths that belong to one
  deployment or domain live in that deployment's own extension repo, not here.
- **No secrets or personal data** in code, tests, fixtures or commit messages.
- New admin endpoints get their own module under
  `services/api-gateway/routers/admin_domains/`.

## Setup and checks

```bash
uv sync
uv run duckclaw-migrate
uvx ruff check packages services harness_core scripts --select F821 --exclude "**/deprecated/**"
uvx ruff check services --select RUF006
uv run pytest tests/ -m "not integration" --ignore tests/run_singleton_writer_pipeline.py --ignore tests/deprecated
```

Admin UI (`apps/duckclaw-admin`): `pnpm admin:install`, then
`pnpm --dir apps/duckclaw-admin test`.

CI runs the same lint and test commands; a pull request must pass them.

## Conduct

Participation is governed by the [Code of Conduct](CODE_OF_CONDUCT.md).
Security issues follow [SECURITY.md](SECURITY.md), not public issues.
