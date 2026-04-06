#!/usr/bin/env python3
"""Run on VPS: patch observability_api.py to include OHLCV router."""
from pathlib import Path

p = Path("/home/capadonna/projects/Capadonna-Driller/services/observability_api.py")
text = p.read_text(encoding="utf-8")
if "_duckclaw_ohlcv_router" in text:
    print("already_patched")
    raise SystemExit(0)
marker = 'version="1.0.0"\n)\n'
insert = (
    marker
    + "\n# DuckClaw: GET /api/market/ohlcv (lake OHLCV contract)\n"
    + "from services.ohlcv_market_routes import router as _duckclaw_ohlcv_router\n"
    + "app.include_router(_duckclaw_ohlcv_router)\n\n"
)
if marker not in text:
    raise SystemExit("marker_not_found")
p.write_text(text.replace(marker, insert, 1), encoding="utf-8")
print("patched_ok")
