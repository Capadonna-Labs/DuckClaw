"""Gateway startup readiness checks (Redis + schema)."""

from __future__ import annotations

import shutil
import subprocess
import sys
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen


def check_redis_readiness(redis_url: str, *, timeout_sec: float = 2.0) -> tuple[bool, str]:
    url = (redis_url or "").strip()
    if not url:
        return False, "REDIS_URL is empty"
    try:
        import redis

        client = redis.from_url(url, decode_responses=True, socket_connect_timeout=timeout_sec)
        client.ping()
        client.close()
        return True, "ok"
    except Exception as exc:
        return False, f"Redis unreachable at {url}: {exc}"


def check_schema_readiness(gateway_db_path: str) -> tuple[bool, str]:
    from duckclaw.schema_migrations import verify_schema_integrity

    ok, message = verify_schema_integrity(gateway_db_path)
    return ok, message


async def assert_gateway_startup_ready(*, redis_url: str, gateway_db_path: str) -> None:
    """Raise RuntimeError with remediation hints when startup prerequisites fail."""
    redis_ok, redis_msg = check_redis_readiness(redis_url)
    if not redis_ok:
        raise RuntimeError(
            f"{redis_msg}. Hint: run `duckclaw-healthcheck --fix` or start Redis locally."
        )

    schema_ok, schema_msg = check_schema_readiness(gateway_db_path)
    if not schema_ok:
        raise RuntimeError(f"{schema_msg}. Hint: run `duckclaw-migrate`.")


def check_fastapi_health(base_url: str, *, timeout_sec: float = 3.0) -> tuple[bool, str]:
    url = (base_url or "").rstrip("/") + "/health"
    try:
        with urlopen(url, timeout=timeout_sec) as resp:
            if int(getattr(resp, "status", 200)) >= 400:
                return False, f"HTTP {resp.status} from {url}"
        return True, "ok"
    except URLError as exc:
        return False, f"Gateway health check failed for {url}: {exc}"
    except Exception as exc:
        return False, str(exc)


def maybe_start_redis_docker(*, image: str = "redis:7-alpine", port: int = 6379) -> tuple[bool, str]:
    """Start a local Redis container. Intended for duckclaw-healthcheck --fix only."""
    if shutil.which("docker") is None:
        return False, "docker not found in PATH"
    name = "duckclaw-redis"
    try:
        inspect = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", name],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if inspect.returncode == 0 and (inspect.stdout or "").strip().lower() == "true":
            return True, f"container {name} already running"
    except Exception as exc:
        return False, f"docker inspect failed: {exc}"

    cmd = [
        "docker",
        "run",
        "-d",
        "--name",
        name,
        "-p",
        f"{port}:6379",
        image,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=False)
    except Exception as exc:
        return False, f"docker run failed: {exc}"
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        if "already in use" in err.lower() or "Conflict" in err:
            start = subprocess.run(
                ["docker", "start", name],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if start.returncode == 0:
                return True, f"started existing container {name}"
        return False, err or f"docker run exit {proc.returncode}"
    return True, f"started container {name} on port {port}"


def print_readiness_failure(message: str) -> None:
    print(message, file=sys.stderr)
