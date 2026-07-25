"""PyInstaller hook: namespace ``duckclaw`` spans shared + agents + core."""

from __future__ import annotations

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

_REPO = Path(__file__).resolve().parents[3]
for _sub in ("packages/agents/src", "packages/shared/src", "packages/core/src"):
    _p = str(_REPO / _sub)
    if _p not in sys.path:
        sys.path.insert(0, _p)

hiddenimports = collect_submodules("duckclaw")

_datas = collect_data_files("duckclaw", include_py_files=False)
_forge = _REPO / "packages" / "agents" / "src" / "duckclaw" / "forge"
if _forge.is_dir():
    for _rel in ("seed", "workflows"):
        _src = _forge / _rel
        if _src.is_dir():
            _datas.append((str(_src), str(Path("duckclaw") / "forge" / _rel)))
    for _name in ("entry_router.yaml", "manager_router.yaml"):
        _f = _forge / _name
        if _f.is_file():
            _datas.append((str(_f), str(Path("duckclaw") / "forge")))

datas = _datas
