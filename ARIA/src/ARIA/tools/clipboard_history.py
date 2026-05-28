"""Clipboard geçmişi — pbpaste ile periyodik kayıt, ~/.aria/clipboard_history.json."""

from __future__ import annotations

import json
import logging
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

from ARIA.core.registry import register_tool

logger = logging.getLogger("aria.tools.clipboard_history")

_ARIA_DIR = Path.home() / ".aria"
_HISTORY_FILE = _ARIA_DIR / "clipboard_history.json"
_MAX_ENTRIES = 50
_POLL_INTERVAL = 2.0  # saniye

_history: list[dict] = []
_last_content: str = ""
_monitor_thread: threading.Thread | None = None
_running = False


def _load() -> list[dict]:
    try:
        if _HISTORY_FILE.exists():
            return json.loads(_HISTORY_FILE.read_text())
    except Exception:
        pass
    return []


def _save(history: list[dict]) -> None:
    try:
        _ARIA_DIR.mkdir(parents=True, exist_ok=True)
        _HISTORY_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2))
    except Exception as exc:
        logger.warning("Clipboard geçmişi kaydedilemedi: %s", exc)


def _pbpaste() -> str:
    try:
        r = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=3)
        return r.stdout
    except Exception:
        return ""


def _monitor_loop() -> None:
    global _last_content, _history, _running
    _history = _load()
    while _running:
        content = _pbpaste()
        if content and content != _last_content and len(content.strip()) > 0:
            _last_content = content
            entry = {
                "ts": datetime.now().isoformat(timespec="seconds"),
                "content": content[:2000],
                "length": len(content),
            }
            _history.insert(0, entry)
            if len(_history) > _MAX_ENTRIES:
                _history = _history[:_MAX_ENTRIES]
            _save(_history)
        time.sleep(_POLL_INTERVAL)


def start_monitor() -> None:
    """Clipboard izleme thread'ini başlat (API startup'ta çağrılır)."""
    global _monitor_thread, _running
    if _monitor_thread and _monitor_thread.is_alive():
        return
    _running = True
    _monitor_thread = threading.Thread(target=_monitor_loop, daemon=True, name="clipboard-monitor")
    _monitor_thread.start()
    logger.info("Clipboard monitor başlatıldı")


def stop_monitor() -> None:
    global _running
    _running = False


@register_tool("clipboard_history_get")
def clipboard_history_get(limit: int = 20) -> dict:
    """Clipboard geçmişini getir.

    Args:
        limit: Maksimum kayıt sayısı (max 50)

    Returns:
        {'history': list[dict], 'count': int}
    """
    history = _load()
    entries = history[:min(limit, _MAX_ENTRIES)]
    return {"history": entries, "count": len(entries), "success": True}


@register_tool("clipboard_history_clear")
def clipboard_history_clear() -> dict:
    """Clipboard geçmişini temizle.

    Returns:
        {'success': bool}
    """
    try:
        _HISTORY_FILE.write_text("[]")
        global _history
        _history = []
        return {"success": True}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


@register_tool("clipboard_history_search")
def clipboard_history_search(query: str) -> dict:
    """Clipboard geçmişinde ara.

    Args:
        query: Aranacak metin

    Returns:
        {'results': list[dict]}
    """
    history = _load()
    q = query.lower()
    results = [e for e in history if q in e.get("content", "").lower()]
    return {"results": results[:10], "count": len(results), "success": True}
