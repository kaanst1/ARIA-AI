"""macOS pano (clipboard) araçları — pbpaste / pbcopy."""

from __future__ import annotations

import logging
import subprocess

from ARIA.core.registry import register_tool

logger = logging.getLogger("aria.tools.clipboard")


def _run(cmd: list[str], input_text: str | None = None, timeout: int = 5) -> tuple[str, int]:
    """Komutu çalıştır, (stdout, returncode) döndür."""
    try:
        result = subprocess.run(
            cmd,
            input=input_text,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout, result.returncode
    except FileNotFoundError:
        return "", -1
    except Exception as exc:
        logger.error("clipboard komut hatası: %s", exc)
        return "", -1


@register_tool("clipboard_read")
def clipboard_read() -> dict:
    """Panodan metin oku (macOS pbpaste).

    Returns:
        {'content': str, 'length': int, 'success': bool}
    """
    text, rc = _run(["pbpaste"])
    if rc != 0:
        return {"content": "", "length": 0, "success": False, "error": "pbpaste başarısız"}
    return {"content": text, "length": len(text), "success": True}


@register_tool("clipboard_write")
def clipboard_write(text: str) -> dict:
    """Metni panoya kopyala (macOS pbcopy).

    Args:
        text: Panoya yazılacak metin.

    Returns:
        {'success': bool}
    """
    _, rc = _run(["pbcopy"], input_text=text)
    if rc != 0:
        return {"success": False, "error": "pbcopy başarısız"}
    return {"success": True, "written_length": len(text)}


def clipboard_analyze_pipeline() -> dict:
    """Panoyu oku ve LLM'e göndermek için hazırla (auto-pipeline).

    Returns:
        {'content': str, 'ready': bool}
    """
    result = clipboard_read()
    if not result["success"] or not result["content"].strip():
        return {"content": "", "ready": False, "error": "Pano boş veya okunamadı"}
    return {"content": result["content"], "ready": True, "length": result["length"]}
