"""Runtime: namespace ``duckclaw`` spans multiple src trees in the frozen bundle."""

import os
import sys

if getattr(sys, "frozen", False):
    _base = getattr(sys, "_MEIPASS", "")
    for _site in ("agents_site", "shared_site", "core_site"):
        _p = os.path.join(_base, _site)
        if os.path.isdir(_p) and _p not in sys.path:
            sys.path.insert(0, _p)
