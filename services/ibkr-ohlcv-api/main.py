"""
OHLCV HTTP API standalone (contrato DuckClaw). En Capadonna suele montarse el router en
observability_api.py en lugar de este proceso.

Variables: ver docstring en ohlcv_market_routes.py
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from ohlcv_market_routes import router as ohlcv_router

app = FastAPI(
    title="IBKR OHLCV API",
    version="1.0.0",
)
app.include_router(ohlcv_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=os.environ.get("OHLCV_BIND_HOST", "0.0.0.0"),
        port=int((os.environ.get("OHLCV_BIND_PORT") or os.environ.get("PORT") or "8002")),
    )
