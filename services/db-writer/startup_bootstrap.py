"""One-shot hub bootstrap owned by DB-Writer (not Gateway lifespan)."""

from __future__ import annotations

import logging

logger = logging.getLogger("db-writer.bootstrap")


def run_startup_bootstrap() -> None:
    """Ensure usage tables + seed worker catalog on empty hub DB."""
    from duckclaw import DuckClaw
    from duckclaw.catalog_seed import seed_catalog_if_empty
    from duckclaw.gateway_db import get_gateway_db_path
    from duckclaw.write_handlers.usage_logs import _llm_usage_log_ddl

    hub = (get_gateway_db_path() or "").strip()
    if not hub:
        logger.warning("startup bootstrap skipped: no hub db path")
        return

    db = DuckClaw(hub, read_only=False, engine="python")
    try:
        db.execute(_llm_usage_log_ddl())
        try:
            from duckclaw.media_usage_log import _media_usage_log_ddl_sql

            db.execute(_media_usage_log_ddl_sql())
        except Exception as exc:  # noqa: BLE001
            logger.debug("media_usage_log ddl skipped: %s", exc)
        seeded = seed_catalog_if_empty(db)
        if seeded:
            logger.info("catalog seeded from templates on hub db")
    except Exception as exc:  # noqa: BLE001
        logger.warning("startup bootstrap failed: %s", exc)
    finally:
        try:
            db.close()
        except Exception:
            pass
