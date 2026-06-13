from __future__ import annotations

from pathlib import Path


def test_admin_auth_routes_live_in_domain_module() -> None:
    admin = Path("services/api-gateway/routers/admin.py").read_text(encoding="utf-8")
    auth = Path("services/api-gateway/routers/admin_domains/auth.py").read_text(encoding="utf-8")

    assert "from routers.admin_domains.auth import router as auth_router" in admin
    assert "router.include_router(auth_router)" in admin
    assert '@router.post("/auth/login")' not in admin
    assert '@router.get("/auth/me")' not in admin
    assert '@router.post("/auth/logout")' not in admin
    assert 'router = APIRouter(prefix="/auth", tags=["admin-auth"])' in auth
    assert '@router.post("/login")' in auth
    assert '@router.get("/me")' in auth
    assert '@router.post("/logout")' in auth


def test_admin_template_routes_live_in_domain_module() -> None:
    admin = Path("services/api-gateway/routers/admin.py").read_text(encoding="utf-8")
    templates = Path("services/api-gateway/routers/admin_domains/templates_catalog.py").read_text(encoding="utf-8")

    assert "from routers.admin_domains.templates_catalog import router as templates_catalog_router" in admin
    assert "router.include_router(templates_catalog_router)" in admin
    assert '@router.get("/templates"' not in admin
    assert '@router.post("/templates"' not in admin
    assert '@router.delete("/templates/{worker_id}"' not in admin
    assert 'router = APIRouter(prefix="/templates", tags=["admin-templates"])' in templates
    assert '@router.get("", dependencies=[Depends(require_admin_key)])' in templates
    assert '@router.get("/{worker_id}", dependencies=[Depends(require_admin_key)])' in templates
    assert '@router.put("/{worker_id}/files/{file_path:path}", dependencies=[Depends(require_admin_key)])' in templates
    assert '@router.delete("/{worker_id}", dependencies=[Depends(require_admin_key)])' in templates
