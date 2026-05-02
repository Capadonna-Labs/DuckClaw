#!/usr/bin/env python3
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

LOG_PATH = Path(__file__).resolve().parent.parent / ".cursor" / "debug-94f69d.log"
RUN_ID = f"run-{int(time.time())}"


def debug_log(hypothesis_id: str, location: str, message: str, data: dict[str, Any]) -> None:
    payload = {
        "sessionId": "94f69d",
        "runId": RUN_ID,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=True) + "\n")


def load_env_key() -> str:
    env_path = Path(".env")
    if not env_path.exists():
        return ""
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("REQRES_API_KEY="):
            return line.split("=", 1)[1].strip()
    return ""


def post_json(url: str, headers: dict[str, str], body: dict[str, Any]) -> tuple[int, str]:
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=payload, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")


def get_json(url: str, headers: dict[str, str]) -> tuple[int, str]:
    req = urllib.request.Request(url, method="GET", headers=headers)
    try:
        with urllib.request.urlopen(req) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")


def main() -> int:
    api_key = load_env_key()
    has_key = bool(api_key)

    login_headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "User-Agent": "reqres-debug/1.0",
    }
    login_body = {"email": "eve.holt@reqres.in", "password": "cityslicka"}
    status, body = post_json("https://reqres.in/api/login", login_headers, login_body)

    body_is_json = True
    parsed: dict[str, Any] = {}
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        body_is_json = False


    if not body_is_json or "token" not in parsed:
        print("LOGIN_FAILED")
        print(f"status={status}")
        print(body)
        return 1

    token = str(parsed["token"])

    create_headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "Authorization": f"Bearer {token}",
        "X-Reqres-Env": "prod",
        "User-Agent": "reqres-debug/1.0",
    }
    create_status, create_body = post_json(
        "https://reqres.in/api/collections/users/records",
        create_headers,
        {"data": {"name": "Juan Perez", "job": "Engineer"}},
    )
    create_parsed = json.loads(create_body) if create_body.startswith("{") else {}
    user_id = str(create_parsed.get("data", {}).get("id", ""))

    if not user_id:
        print("CREATE_FAILED")
        print(f"status={create_status}")
        print(create_body)
        return 2

    get_status, get_body = get_json(
        f"https://reqres.in/api/collections/users/records/{user_id}",
        {
            "x-api-key": api_key,
            "Authorization": f"Bearer {token}",
            "X-Reqres-Env": "prod",
            "User-Agent": "reqres-debug/1.0",
        },
    )
    get_parsed = json.loads(get_body) if get_body.startswith("{") else {}
    fetched_id = str(get_parsed.get("data", {}).get("id", ""))

    if get_status != 200:
        print("GET_FAILED")
        print(f"status={get_status}")
        print(get_body)
        return 3

    print("SUCCESS")
    print(f"login_token_length={len(token)}")
    print(f"create_status={create_status}")
    print(f"get_status={get_status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
