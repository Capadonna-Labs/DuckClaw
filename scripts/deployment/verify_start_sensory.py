#!/usr/bin/env python3
from pathlib import Path

p = Path.home() / "Desktop/duckclaw/integrations/sensory-node/scripts/start_sensory.sh"
text = p.read_text(encoding="utf-8")
assert "dirname" in text and "$0" in text and "uvicorn" in text, text
data = p.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
p.write_bytes(data)
print("verified ok, lf-only")
