"""Pytest: variables de entorno por defecto para tests (sin secretos)."""

from __future__ import annotations

import os

# API Gateway y db-writer exigen REDIS_URL o DUCKCLAW_REDIS_URL (sin fallback en código).
os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:6379/0")
