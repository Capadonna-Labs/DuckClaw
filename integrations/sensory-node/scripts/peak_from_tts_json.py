#!/usr/bin/env python3
"""Print peak amplitude from sensory synthesize JSON on stdin."""
from __future__ import annotations

import base64
import json
import struct
import sys


def main() -> int:
    data = json.load(sys.stdin)
    raw = base64.b64decode(data["audio_base64"])
    data_off = raw.find(b"data")
    ds = struct.unpack_from("<I", raw, data_off + 4)[0]
    pcm = raw[data_off + 8 : data_off + 8 + ds]
    n = len(pcm) // 2
    samples = struct.unpack("<" + "h" * n, pcm) if n else ()
    peak = max(abs(s) for s in samples) if samples else 0
    print(f"peak={peak} dur={data.get('duration_sec')}")
    return 0 if peak > 500 else 1


if __name__ == "__main__":
    raise SystemExit(main())
