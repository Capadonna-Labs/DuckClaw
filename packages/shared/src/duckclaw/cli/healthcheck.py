"""Infrastructure healthcheck CLI (Redis + optional gateway HTTP probe)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here, *here.parents]:
        if (parent / "packages" / "shared").is_dir():
            return parent
    return Path.cwd()


def _load_dotenv() -> None:
    if os.environ.get("DUCKCLAW_DISABLE_DOTENV") == "1":
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(_repo_root() / ".env")
    except ImportError:
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DuckClaw infrastructure healthcheck")
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Try to start local Redis via docker (CLI-only remediation)",
    )
    parser.add_argument(
        "--gateway-url",
        default="",
        help="Optional FastAPI base URL to probe /health",
    )
    parser.add_argument(
        "--redis-url",
        default="",
        help="Override Redis URL (default from gateway settings)",
    )
    args = parser.parse_args(argv)

    _load_dotenv()
    from duckclaw.gateway.settings import get_gateway_settings
    from duckclaw.infra.readiness import (
        check_fastapi_health,
        check_redis_readiness,
        maybe_start_redis_docker,
    )

    settings = get_gateway_settings()
    redis_url = (args.redis_url or settings.resolved_redis_url()).strip()
    failures: list[str] = []

    redis_ok, redis_msg = check_redis_readiness(redis_url)
    if not redis_ok:
        if args.fix:
            fixed, fix_msg = maybe_start_redis_docker()
            print(fix_msg)
            if fixed:
                redis_ok, redis_msg = check_redis_readiness(redis_url)
        if not redis_ok:
            failures.append(redis_msg)

    gateway_url = (args.gateway_url or os.environ.get("GATEWAY_INTERNAL_URL") or "").strip()
    if gateway_url:
        http_ok, http_msg = check_fastapi_health(gateway_url)
        if not http_ok:
            failures.append(http_msg)

    if failures:
        for item in failures:
            print(item, file=sys.stderr)
        return 1

    print(f"OK redis={redis_url}" + (f" gateway={gateway_url}" if gateway_url else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
