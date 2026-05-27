"""Güvenli Python kodu çalıştırıcı — sandbox subprocess ile."""

from __future__ import annotations

import logging
import subprocess
import sys
import tempfile
import os
from pathlib import Path

from ARIA.core.registry import register_tool

logger = logging.getLogger("aria.tools.code_runner")

# Yasaklı pattern'lar
_FORBIDDEN_PATTERNS = [
    "os.system(",
    "subprocess.Popen(",
    "subprocess.run(",
    "subprocess.call(",
    "shutil.rmtree(",
    "__import__(",
    "importlib.import_module(",
    "open('/etc",
    "open(\"/etc",
    "exec(",
    "eval(",
    "compile(",
    "__builtins__",
    "ctypes",
    "socket.connect(",
    "urllib.request",
    "requests.get(",
    "requests.post(",
]


class SafeCodeRunner:
    """Python kodunu güvenli subprocess sandbox'ta çalıştırır."""

    def __init__(self) -> None:
        self.python = sys.executable

    def _is_safe(self, code: str) -> tuple[bool, str]:
        """Tehlikeli pattern'ları kontrol et."""
        for pattern in _FORBIDDEN_PATTERNS:
            if pattern in code:
                return False, f"Yasaklı ifade tespit edildi: {pattern}"
        return True, ""

    def run(self, code: str, timeout: int = 10) -> dict:
        """Python kodunu çalıştır ve sonucu döndür."""
        safe, reason = self._is_safe(code)
        if not safe:
            return {
                "stdout": "",
                "stderr": reason,
                "exit_code": -1,
                "error": "Güvenlik ihlali",
            }

        # Geçici dosyaya yaz
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(code)
            tmp_path = f.name

        try:
            result = subprocess.run(
                [self.python, tmp_path],
                capture_output=True,
                text=True,
                timeout=timeout,
                env={**os.environ, "PYTHONPATH": ""},  # temiz env
            )
            return {
                "stdout": result.stdout[:4096],
                "stderr": result.stderr[:2048],
                "exit_code": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {
                "stdout": "",
                "stderr": f"Zaman aşımı: {timeout} saniye",
                "exit_code": -1,
                "error": "timeout",
            }
        except Exception as exc:
            return {
                "stdout": "",
                "stderr": str(exc),
                "exit_code": -1,
                "error": str(exc),
            }
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


_runner = SafeCodeRunner()


@register_tool("run_python")
def run_python(code: str, timeout: int = 10) -> dict:
    """Python kodunu güvenli sandbox'ta çalıştır.

    Args:
        code: Çalıştırılacak Python kodu.
        timeout: Maksimum süre (saniye).

    Returns:
        {'stdout': ..., 'stderr': ..., 'exit_code': ...}
    """
    return _runner.run(code, timeout=timeout)
