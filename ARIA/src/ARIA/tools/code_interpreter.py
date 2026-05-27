"""Code interpreter tool wrapper."""

from __future__ import annotations

import io
import contextlib
from ARIA.core.registry import register_tool


@register_tool("code_interpreter")
def run_code(code: str) -> str:
    """Execute code in a controlled environment."""
    allowed_builtins = {
        "print": print,
        "range": range,
        "len": len,
        "sum": sum,
        "min": min,
        "max": max,
    }
    globals_dict = {"__builtins__": allowed_builtins}
    locals_dict: dict = {}

    stdout = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout):
            exec(code, globals_dict, locals_dict)
    except Exception as exc:
        return f"Hata: {exc}"

    output = stdout.getvalue().strip()
    return output or "(cikti yok)"
