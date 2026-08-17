from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_auth_proxy_maps_gateway_fetch_failures_to_503() -> None:
    text = (ROOT / "apps/duckclaw-admin/src/lib/authProxy.ts").read_text(encoding="utf-8")

    assert "gateway_unreachable" in text
    assert "catch" in text
    assert "status: 503" in text


def test_admin_middleware_allows_next_dev_hydration() -> None:
    text = (ROOT / "apps/duckclaw-admin/src/middleware.ts").read_text(encoding="utf-8")

    assert "isDev" in text
    assert "'unsafe-eval'" in text
    assert "'unsafe-inline'" in text


def test_initial_registration_uses_the_db_first_auth_path() -> None:
    auth = (ROOT / "services/api-gateway/routers/admin_domains/auth.py").read_text(encoding="utf-8")
    register_page = (ROOT / "apps/duckclaw-admin/src/app/(auth)/register/page.tsx").read_text(
        encoding="utf-8"
    )
    register_proxy = (
        ROOT / "apps/duckclaw-admin/src/app/api/admin/auth/register/route.ts"
    ).read_text(encoding="utf-8")
    login = (ROOT / "apps/duckclaw-admin/src/app/(auth)/login/page.tsx").read_text(
        encoding="utf-8"
    )

    assert 'class AdminRegisterBody(AdminLoginBody)' in auth
    assert '@router.post("/register")' in auth
    assert "count_console_users(db) > 0" in auth
    assert "UpsertConsoleUserCommand" in auth
    assert "proxyAuthToGateway(req, 'register'" in register_proxy
    assert "updateDesktopAdminCredentials" in register_proxy
    assert "/api/admin/auth/register" in register_page
    assert "Crear cuenta inicial" in register_page
    assert 'href="/register"' in login
