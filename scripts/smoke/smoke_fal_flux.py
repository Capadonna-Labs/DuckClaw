"""Smoke opt-in Fal.ai Flux (requiere FAL_KEY en env)."""

from __future__ import annotations

import json
import os
import sys


def main() -> int:
    if not (os.environ.get("FAL_KEY") or "").strip():
        print("FAL_KEY no configurada; omitiendo smoke.", file=sys.stderr)
        return 0
    from duckclaw.forge.skills.fal_bridge import _generate_flux_image_impl

    out = _generate_flux_image_impl("smoke test: red sphere studio lighting")
    data = json.loads(out)
    if not data.get("ok"):
        print(out, file=sys.stderr)
        return 1
    print(
        json.dumps(
            {k: data[k] for k in ("media_url", "file_path", "cost_usd", "latency_sec") if k in data},
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
