"""Smoke: edit_visual_asset via FLUX Kontext [pro] (requiere FAL_KEY en entorno)."""

from __future__ import annotations

import glob
import json
import os
import sys

from duckclaw.forge.skills import fal_bridge


class _SmokeDb:
    _read_only = False

    def execute(self, sql: str) -> None:
        pass

    def query(self, sql: str):
        return json.dumps([{"total": 0.0}])


def main() -> int:
    root = (os.environ.get("CAPADONNA_DRILLER_ROOT") or "/root/Capadonna-Driller").strip()
    tenant = (os.environ.get("SMOKE_TENANT_ID") or "user-juanjoarevalo57-79c5ca60b91d4f3e").strip()
    pattern = os.path.join(root, "db", "private", tenant, "inbound", "*.jpg")
    inbound = sorted(glob.glob(pattern))
    if not inbound:
        print(f"no inbound jpg under {pattern}", file=sys.stderr)
        return 1
    src = inbound[-1]
    fal_cfg = {
        "enabled": True,
        "default_image_edit_endpoint": "fal-ai/flux-pro/kontext",
    }
    body = fal_bridge._build_fal_edit_request_body(
        endpoint="fal-ai/flux-pro/kontext",
        image_uri="data:image/jpeg;base64,abc",
        edit_prompt="Cambia el color de la ropa a amarillo",
        denoise=0.55,
        fal_config=fal_cfg,
    )
    if "strength" in body:
        print("kontext body must not include strength", file=sys.stderr)
        return 1
    print("body_ok guidance_scale=", body.get("guidance_scale"))
    print("source", src)
    fal_bridge._state_delta_base = lambda: {
        "tenant_id": tenant,
        "user_id": "smoke",
        "target_db_path": "",
    }
    out = fal_bridge._fal_edit_visual_asset_impl(
        src,
        "Cambia el color de la ropa a amarillo",
        fal_config=fal_cfg,
        duckclaw_db=_SmokeDb(),
    )
    payload = json.loads(out)
    summary = {
        "ok": payload.get("ok"),
        "model_endpoint": payload.get("model_endpoint"),
        "file_path": payload.get("file_path"),
        "cost_usd": payload.get("cost_usd"),
        "latency_sec": payload.get("latency_sec"),
        "error": payload.get("error"),
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
