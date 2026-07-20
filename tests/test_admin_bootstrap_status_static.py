from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUTH_SPEC = ROOT / "docs/architecture/ADMIN_IDENTITY_RBAC_ERD.md"
BOOTSTRAP_LIB = ROOT / "apps/duckclaw-admin/src/lib/adminBootstrapStatus.ts"
BOOTSTRAP_ROUTE = ROOT / "apps/duckclaw-admin/src/app/api/admin/bootstrap/status/route.ts"
BOOTSTRAP_HOOK = ROOT / "apps/duckclaw-admin/src/hooks/useAdminBootstrapStatus.ts"
BOOTSTRAP_BANNER = ROOT / "apps/duckclaw-admin/src/components/auth/BootstrapStatusBanner.tsx"
LOGIN_PAGE = ROOT / "apps/duckclaw-admin/src/app/(auth)/login/page.tsx"
AUTH_STORE = ROOT / "apps/duckclaw-admin/src/store/authStore.ts"


def test_admin_login_uses_canonical_auth_spec_and_public_bootstrap_status() -> None:
    spec = AUTH_SPEC.read_text(encoding="utf-8")
    route = BOOTSTRAP_ROUTE.read_text(encoding="utf-8")
    lib = BOOTSTRAP_LIB.read_text(encoding="utf-8")

    assert "POST /api/admin/auth/login" in spec
    assert "POST /api/v1/admin/auth/login" in spec
    assert "resolveAdminBootstrapStatus" in route
    assert "requireAdminRouteAuth" not in route
    assert "DUCKCLAW_ADMIN_API_KEY" not in route
    assert "gatewayBase()" in lib
    assert "/health" in lib
    assert "/api/v1/admin/health" in lib
    assert "canAttemptLogin" in lib
    assert "gateway_unreachable" in lib
    assert "pm2Status" in lib
    assert "recoveryCommand" in lib
    assert "pm2 jlist" in lib


def test_login_page_renders_degraded_gateway_state_without_masking_as_credentials() -> None:
    hook = BOOTSTRAP_HOOK.read_text(encoding="utf-8")
    banner = BOOTSTRAP_BANNER.read_text(encoding="utf-8")
    login = LOGIN_PAGE.read_text(encoding="utf-8")
    store = AUTH_STORE.read_text(encoding="utf-8")

    assert "useAdminBootstrapStatus" in hook
    assert "setInterval" in hook
    assert "BootstrapStatusBanner" in login
    assert "bootstrap.canAttemptLogin" in login
    assert "disabled={isSubmitting || !bootstrap.canAttemptLogin}" in login
    assert "Gateway iniciando" in banner
    assert "Reintentando automáticamente" in banner
    assert "pnpm stack:up" in banner
    assert "status.recoveryCommand" in banner
    assert "gateway_unreachable" in store
    assert "Gateway no disponible" in store


def test_login_defaults_to_playground_after_auth() -> None:
    store = AUTH_STORE.read_text(encoding="utf-8")
    login = LOGIN_PAGE.read_text(encoding="utf-8")

    assert "export function adminPostAuthPath" in store
    assert "return '/playground'" in store
    assert "adminPostAuthPath(saved)" in login
    assert "adminPostAuthPath(null)" in login
    assert "router.replace('/overview'" not in login
