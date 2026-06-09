#!/usr/bin/env python3
from pathlib import Path

root = Path.home() / "Desktop/duckclaw/integrations/sensory-node/scripts"
for f in root.glob("*.sh"):
    data = f.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    f.write_bytes(data)
    print("fixed", f)
