import json
import os
import subprocess

key = ""
for line in open("/root/duckclaw/.env"):
    if line.startswith("DUCKCLAW_ADMIN_API_KEY="):
        key = line.split("=", 1)[1].strip()
        break

proc = subprocess.run(
    [
        "curl",
        "-sS",
        "-w",
        "\n%{http_code}",
        "-H",
        f"X-Admin-Key: {key}",
        "-H",
        "X-Duckclaw-Actor: juanjoarevalo57@gmail.com",
        "http://127.0.0.1:8000/api/v1/admin/mcp/connectors",
    ],
    capture_output=True,
    text=True,
    check=False,
)
body, status = proc.stdout.rsplit("\n", 1)
print("status", status)
if status == "200":
    data = json.loads(body)
    for c in data.get("connectors", []):
        print(c.get("connector_id"), "has_auth", c.get("has_auth"))
else:
    print(body[:500])
