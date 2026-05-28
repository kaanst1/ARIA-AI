"""Global hotkey — Cmd+Shift+Space ile ARIA'yı aç (pynput)."""

from __future__ import annotations

import logging
import subprocess
import threading
from typing import Callable, Optional

logger = logging.getLogger("aria.tools.global_hotkey")

_listener_thread: Optional[threading.Thread] = None
_running = False

_FRONTEND_URL = "http://localhost:5173"


def _open_aria() -> None:
    """ARIA frontend'ini tarayıcıda aç veya ön plana getir."""
    try:
        # Önce zaten açık mı kontrol et
        script = f'''
tell application "System Events"
    set ariaOpen to false
    repeat with proc in (every process whose name is "Safari" or name is "Google Chrome" or name is "Arc" or name is "Firefox")
        try
            repeat with win in windows of proc
                if URL of win contains "localhost:5173" then
                    set ariaOpen to true
                    tell proc to set frontmost to true
                    exit repeat
                end if
            end repeat
        end try
    end repeat
    if not ariaOpen then
        do shell script "open {_FRONTEND_URL}"
    end if
end tell
'''
        subprocess.run(["osascript", "-e", script], capture_output=True, timeout=8)
    except Exception:
        subprocess.run(["open", _FRONTEND_URL], capture_output=True, timeout=5)


def _start_listener(on_trigger: Optional[Callable] = None) -> None:
    global _running
    try:
        from pynput import keyboard

        _HOTKEY = {keyboard.Key.cmd, keyboard.Key.shift, keyboard.KeyCode.from_char(' ')}
        _current_keys: set = set()

        def on_press(key):
            _current_keys.add(key)
            # Cmd+Shift+Space kontrolü
            if (keyboard.Key.cmd in _current_keys and
                    keyboard.Key.shift in _current_keys and
                    keyboard.KeyCode.from_char(' ') in _current_keys):
                logger.info("Global hotkey tetiklendi: Cmd+Shift+Space")
                if on_trigger:
                    on_trigger()
                else:
                    _open_aria()

        def on_release(key):
            _current_keys.discard(key)

        with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
            logger.info("Global hotkey dinleniyor: Cmd+Shift+Space → ARIA")
            while _running:
                import time
                time.sleep(0.1)
            listener.stop()

    except ImportError:
        logger.warning("pynput kurulu değil — global hotkey devre dışı. 'pip install pynput' ile kur.")
    except Exception as exc:
        logger.error("Global hotkey başlatılamadı: %s", exc)


def start_global_hotkey(on_trigger: Optional[Callable] = None) -> bool:
    """Global hotkey dinlemeyi başlat.

    Args:
        on_trigger: Hotkey basıldığında çağrılacak fonksiyon (None = ARIA'yı aç)

    Returns:
        True if başlatıldı
    """
    global _listener_thread, _running
    try:
        import pynput  # noqa
    except ImportError:
        logger.warning("pynput yok — global hotkey devre dışı")
        return False

    if _listener_thread and _listener_thread.is_alive():
        return True

    _running = True
    _listener_thread = threading.Thread(
        target=_start_listener,
        args=(on_trigger,),
        daemon=True,
        name="aria-global-hotkey",
    )
    _listener_thread.start()
    return True


def stop_global_hotkey() -> None:
    global _running
    _running = False
