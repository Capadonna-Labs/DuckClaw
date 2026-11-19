# Security Policy

## Reporting a vulnerability

Do not open a public issue. Report it privately through
[GitHub's "Report a vulnerability"](https://github.com/Capadonna-Labs/DuckClaw/security/advisories/new)
form, with the affected version or commit, steps to reproduce, and the impact you see.

What to expect:

- Acknowledgement within 48 hours.
- An assessment and, for confirmed issues, a fix or mitigation plan within 7 days.
- Credit in the advisory once a fix is released, unless you prefer to stay anonymous.

Please give us a reasonable window to ship a fix before disclosing publicly.

## Supported versions

Only the latest `main` receives security fixes.

## Scope notes

DuckClaw runs agents that call tools, external APIs and LLMs. Of particular interest:
bypasses of the DB-Writer boundary (direct writes to the hub DuckDB), worker manifest
escapes (a worker reaching tables, tools or delegates its manifest does not grant),
secret leakage from `admin_runtime_settings` or the admin BFF, and auth bypasses on
`/api/v1/admin/*`.
