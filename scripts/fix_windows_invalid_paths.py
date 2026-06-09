#!/usr/bin/env python3
"""Rename GitHub paths invalid on Windows (colon in filename) via Contents API."""
from __future__ import annotations

import base64
import json
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO = "Capadonna-Labs/DuckClaw"
REPO_ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = REPO_ROOT / "debug-97f3cb.log"
SESSION_ID = "97f3cb"

RENAMES = [
    (
        "docs/SoftwareEngineer/Seguridad/Criptografía y Seguridad: Funciones Hash (Hashing).md",
        "docs/SoftwareEngineer/Seguridad/Criptografia-y-Seguridad-Funciones-Hash-Hashing.md",
    ),
    (
        "packages/core/Captura de pantalla 2026-04-15 a la(s) 10.15.50\u202fa.m..png",
        "packages/core/captura-pantalla-2026-04-15-101550.png",
    ),
]


def log(hypothesis_id: str, message: str, data: dict) -> None:
    entry = {
        "sessionId": SESSION_ID,
        "hypothesisId": hypothesis_id,
        "location": "scripts/fix_windows_invalid_paths.py",
        "message": message,
        "data": data,
        "timestamp": int(__import__("time").time() * 1000),
        "runId": "fix-upstream",
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def gh_token() -> str:
    return subprocess.check_output(["gh", "auth", "token"], text=True).strip()


def api(method: str, path: str, body: dict | None = None) -> dict:
    url = f"https://api.github.com/repos/{REPO}{path}"
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {gh_token()}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API {method} {path} -> {exc.code}: {err}") from exc


def git_show(path: str) -> bytes:
    return subprocess.check_output(
        ["git", "-C", str(REPO_ROOT), "show", f"origin/main:{path}"],
    )


def get_file_meta(path: str) -> dict:
    enc = urllib.parse.quote(path, safe="/")
    return api("GET", f"/contents/{enc}?ref=main")


def rename_file(old_path: str, new_path: str) -> None:
    meta = get_file_meta(old_path)
    sha = meta["sha"]
    content_b64 = meta.get("content", "").replace("\n", "")
    if meta.get("encoding") == "base64" and content_b64:
        payload_content = content_b64
    else:
        payload_content = base64.b64encode(git_show(old_path)).decode("ascii")

    api(
        "PUT",
        f"/contents/{urllib.parse.quote(new_path, safe='/')}",
        {
            "message": f"fix(windows): rename path invalid on NTFS\n\n{old_path} -> {new_path}",
            "content": payload_content,
            "branch": "main",
        },
    )
    api(
        "DELETE",
        f"/contents/{urllib.parse.quote(old_path, safe='/')}",
        {
            "message": f"fix(windows): remove NTFS-invalid path after rename\n\n{old_path}",
            "sha": sha,
            "branch": "main",
        },
    )


def main() -> int:
    log("H1", "starting_upstream_rename", {"renames": RENAMES})
    for old, new in RENAMES:
        try:
            rename_file(old, new)
            log("H1", "rename_ok", {"old": old, "new": new})
            print(f"OK: {old} -> {new}")
        except Exception as exc:
            log("H1", "rename_failed", {"old": old, "new": new, "error": str(exc)})
            print(f"FAIL {old}: {exc}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
