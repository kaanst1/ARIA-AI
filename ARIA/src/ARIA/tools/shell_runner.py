"""Güvenli shell komut çalıştırıcı — whitelist tabanlı."""

from __future__ import annotations

import logging
import shlex
import subprocess
from typing import Optional

from ARIA.core.registry import register_tool

logger = logging.getLogger("aria.tools.shell_runner")

# İzin verilen komutlar (whitelist)
_ALLOWED_COMMANDS = {
    "ls", "cat", "find", "grep", "ps", "df", "du", "pwd",
    "echo", "date", "which", "head", "tail", "wc", "sort",
    "uniq", "cut", "tr", "env", "uname", "whoami", "id",
    "uptime", "free", "top",
}

# Kesinlikle yasaklı pattern'lar
_FORBIDDEN_PATTERNS = [
    "rm -rf",
    "rm -fr",
    "sudo ",
    "curl | bash",
    "curl |bash",
    "wget | sh",
    "wget |sh",
    "bash <(",
    "> /dev/sda",
    "dd if=",
    "mkfs",
    "chmod 777",
    "chown root",
    "; rm ",
    "&& rm ",
    "| rm ",
]


class SafeShellRunner:
    """Whitelist tabanlı güvenli shell komut çalıştırıcı."""

    def _is_safe(self, command: str) -> tuple[bool, str]:
        """Komutun güvenli olup olmadığını kontrol et."""
        cmd_lower = command.lower()

        # Yasaklı pattern kontrolü
        for pattern in _FORBIDDEN_PATTERNS:
            if pattern in cmd_lower:
                return False, f"Yasaklı komut pattern: {pattern}"

        # İlk komutu al (pipe/semicolon öncesi)
        try:
            parts = shlex.split(command)
        except ValueError:
            return False, "Geçersiz komut sözdizimi"

        if not parts:
            return False, "Boş komut"

        # İlk token'ın whitelist'te olup olmadığını kontrol et
        base_cmd = parts[0].split("/")[-1]  # path varsa son kısmı al
        if base_cmd not in _ALLOWED_COMMANDS:
            return False, f"İzin verilmeyen komut: {base_cmd}. İzin verilenler: {', '.join(sorted(_ALLOWED_COMMANDS))}"

        return True, ""

    def run(self, command: str, timeout: int = 10) -> dict:
        """Shell komutunu güvenli şekilde çalıştır."""
        safe, reason = self._is_safe(command)
        if not safe:
            return {
                "stdout": "",
                "stderr": reason,
                "exit_code": -1,
                "error": "Güvenlik ihlali",
            }

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return {
                "stdout": result.stdout[:8192],
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


_shell_runner = SafeShellRunner()


@register_tool("run_shell")
def run_shell(command: str, timeout: int = 10) -> dict:
    """Whitelist tabanlı güvenli shell komutu çalıştır.

    Args:
        command: Çalıştırılacak shell komutu.
        timeout: Maksimum süre (saniye).

    Returns:
        {'stdout': ..., 'stderr': ..., 'exit_code': ...}
    """
    return _shell_runner.run(command, timeout=timeout)
