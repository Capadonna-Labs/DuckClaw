"""Regression: ``from __future__`` debe quedar antes del header matplotlib en run_in_sandbox."""

from __future__ import annotations

from duckclaw.graphs.sandbox import _inject_sandbox_python_header


def test_inject_header_keeps_future_import_at_module_start() -> None:
    snippet = '''"""
Doc del snippet.
"""
from __future__ import annotations

import json
print("ok")
'''
    merged = _inject_sandbox_python_header(snippet)
    assert merged.index('from __future__ import annotations') < merged.index("import matplotlib")
    assert "import json" in merged
    compile(merged, "<sandbox>", "exec")


def test_inject_header_without_future_still_valid() -> None:
    snippet = "import json\nprint(1)\n"
    merged = _inject_sandbox_python_header(snippet)
    compile(merged, "<sandbox>", "exec")
