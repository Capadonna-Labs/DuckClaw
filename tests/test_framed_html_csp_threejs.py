"""The framed report HTML (iframe in the admin) must be able to run a Three.js scene: same CSP in the three places that serve it."""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SOURCES = {
    "middleware": (_ROOT / "apps/duckclaw-admin/src/middleware.ts", r"FRAMED_HTML_CSP =(.*?);\n\n"),
    "report route": (_ROOT / "apps/duckclaw-admin/src/app/api/admin/reports/[reportId]/route.ts", r"REPORT_HTML_CSP =(.*?);\n\n"),
    "gateway": (_ROOT / "services/api-gateway/routers/reports.py", r"_CSP = \((.*?)\n\)"),
}


def _policy(name: str) -> str:
    path, pattern = _SOURCES[name]
    block = re.search(pattern, path.read_text(encoding="utf-8").replace("\r\n", "\n"), re.S).group(1)
    return "".join(re.findall(r'"([^"]*)"', block))


def test_every_framed_html_policy_lets_a_threejs_scene_run() -> None:
    for name in _SOURCES:
        csp = _policy(name)
        assert "unpkg.com" in csp and "cdn.jsdelivr.net" in csp, name                  # three@x and its addons from the allowed CDNs
        assert "'wasm-unsafe-eval'" in csp and "'unsafe-eval'" not in csp.replace("'wasm-unsafe-eval'", ""), name   # Draco/KTX2 WASM, never general eval
        assert "worker-src 'self' blob:" in csp, name                                    # decoder workers
        assert re.search(r"connect-src [^;]*blob:", csp) and re.search(r"media-src [^;]*blob:", csp), name   # embedded textures, video textures
        assert re.search(r"img-src [^;]*blob:", csp), name
