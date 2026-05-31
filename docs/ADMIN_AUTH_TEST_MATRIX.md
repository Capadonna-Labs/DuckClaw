# Admin Auth Test Matrix

## Automated Checks

```bash
uv run pytest tests/test_admin_bff_route_auth_static.py tests/test_admin_access.py tests/test_admin_auth_sessions.py -q
uv run pytest tests/test_admin_user_profiles.py tests/test_admin_user_agents.py -q
pnpm --dir apps/duckclaw-admin exec tsc --noEmit
pnpm --dir apps/duckclaw-admin lint
```

## Coverage

| Area | Expected result | Test owner |
| --- | --- | --- |
| Login | Sets `session` and `csrf_token` cookies | `tests/test_admin_auth_sessions.py` |
| Session refresh | `/auth/me` refreshes Redis TTL | `tests/test_admin_auth_sessions.py` |
| Logout | Deletes Redis session and clears auth | `tests/test_admin_auth_sessions.py` |
| Rate limiting | Excess login attempts return `429` | `tests/test_admin_auth_sessions.py` |
| Password hashing | Argon2id authenticates and uses unique salts | `tests/test_admin_access.py` |
| PBKDF2 migration | Legacy hashes migrate to Argon2id on success | `tests/test_admin_access.py` |
| BFF RBAC | Admin routes do not trust spoofable role/actor headers | `tests/test_admin_bff_route_auth_static.py` |
| User profile | Authenticated users get stable unique tenants | `tests/test_admin_user_profiles.py` |
| Runtime agents | User-created agents are tenant scoped and outside repo templates | `tests/test_admin_user_agents.py` |

## Manual Smoke

1. Start Redis, API Gateway and admin UI.
2. Log in with `DUCKCLAW_ADMIN_EMAIL` / `DUCKCLAW_ADMIN_PASSWORD`.
3. Confirm `session` is HttpOnly and `csrf_token` is readable by the browser.
4. Call `/api/admin/auth/me`; it should return the user and profile.
5. Attempt a mutating BFF request without `X-CSRF-Token`; it should return `403`.
6. Create an agent as a normal user; it should appear in Playground but not under global repo templates.
7. Log in as another user; the first user's runtime agent should not appear.
