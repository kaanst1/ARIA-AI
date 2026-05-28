"""Pomodoro zamanlayıcı — macOS bildirimi + TTS ile."""

from __future__ import annotations

import logging
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
import json

from ARIA.core.registry import register_tool

logger = logging.getLogger("aria.tools.pomodoro")

_ARIA_DIR = Path.home() / ".aria"
_STATE_FILE = _ARIA_DIR / "pomodoro_state.json"

_DEFAULT_WORK = 25
_DEFAULT_BREAK = 5
_DEFAULT_LONG_BREAK = 15
_DEFAULT_CYCLES = 4

_timer_thread: Optional[threading.Thread] = None
_active = False
_state: dict = {}


def _notify(title: str, message: str, sound: str = "Glass") -> None:
    script = f'display notification "{message}" with title "{title}" sound name "{sound}"'
    try:
        subprocess.run(["osascript", "-e", script], capture_output=True, timeout=5)
    except Exception:
        pass


def _speak(text: str) -> None:
    try:
        from ARIA.tools.tts import speak
        speak(text, lang="tr", block=False)
    except Exception:
        pass


def _save_state(state: dict) -> None:
    _ARIA_DIR.mkdir(parents=True, exist_ok=True)
    _STATE_FILE.write_text(json.dumps(state, ensure_ascii=False))


def _load_state() -> dict:
    try:
        if _STATE_FILE.exists():
            return json.loads(_STATE_FILE.read_text())
    except Exception:
        pass
    return {"active": False}


def _run_timer(work_min: int, break_min: int, long_break_min: int, cycles: int) -> None:
    global _active, _state

    for cycle in range(1, cycles + 1):
        if not _active:
            break

        # Çalışma süresi
        _state = {"active": True, "phase": "work", "cycle": cycle, "total_cycles": cycles,
                  "started": datetime.now().isoformat(), "duration_min": work_min}
        _save_state(_state)
        _notify("ARIA Pomodoro", f"Döngü {cycle}/{cycles} — {work_min} dakika çalışma başlıyor!", "Morse")
        _speak(f"Döngü {cycle}. {work_min} dakika çalışma başlıyor.")

        time.sleep(work_min * 60)
        if not _active:
            break

        # Uzun ya da kısa mola
        is_long = (cycle % cycles == 0)
        break_dur = long_break_min if is_long else break_min
        break_label = f"{break_dur} dakika uzun mola" if is_long else f"{break_dur} dakika kısa mola"

        _state = {"active": True, "phase": "break", "cycle": cycle, "total_cycles": cycles,
                  "started": datetime.now().isoformat(), "duration_min": break_dur}
        _save_state(_state)
        _notify("ARIA Pomodoro", f"Mola zamanı! {break_label}", "Hero")
        _speak(f"Harika! {break_label} zamanı.")

        time.sleep(break_dur * 60)
        if not _active:
            break

    if _active:
        _notify("ARIA Pomodoro", f"{cycles} döngü tamamlandı! Harika çalışma!", "Fanfare")
        _speak(f"Tebrikler! {cycles} pomodoro döngüsü tamamlandı.")

    _active = False
    _save_state({"active": False, "completed": True, "cycles_done": cycles})


@register_tool("pomodoro_start")
def pomodoro_start(
    work_minutes: int = _DEFAULT_WORK,
    break_minutes: int = _DEFAULT_BREAK,
    long_break_minutes: int = _DEFAULT_LONG_BREAK,
    cycles: int = _DEFAULT_CYCLES,
) -> dict:
    """Pomodoro zamanlayıcısını başlat.

    Args:
        work_minutes: Çalışma süresi (dakika)
        break_minutes: Kısa mola (dakika)
        long_break_minutes: Uzun mola (dakika)
        cycles: Döngü sayısı

    Returns:
        {'success': bool, 'message': str}
    """
    global _active, _timer_thread
    if _active:
        return {"success": False, "message": "Pomodoro zaten çalışıyor. Önce durdur."}

    _active = True
    _timer_thread = threading.Thread(
        target=_run_timer,
        args=(work_minutes, break_minutes, long_break_minutes, cycles),
        daemon=True,
        name="aria-pomodoro",
    )
    _timer_thread.start()
    return {
        "success": True,
        "message": f"{cycles}x{work_minutes} dk pomodoro başlatıldı. {break_minutes} dk kısa, {long_break_minutes} dk uzun mola.",
        "work_minutes": work_minutes,
        "cycles": cycles,
    }


@register_tool("pomodoro_stop")
def pomodoro_stop() -> dict:
    """Pomodoro'yu durdur.

    Returns:
        {'success': bool}
    """
    global _active
    if not _active:
        return {"success": False, "message": "Aktif pomodoro yok."}
    _active = False
    _save_state({"active": False, "stopped": True})
    _notify("ARIA Pomodoro", "Pomodoro durduruldu.", "Basso")
    return {"success": True, "message": "Pomodoro durduruldu."}


@register_tool("pomodoro_status")
def pomodoro_status() -> dict:
    """Pomodoro durumunu döndür.

    Returns:
        {'active': bool, 'phase': str, 'cycle': int}
    """
    state = _load_state()
    state["success"] = True
    return state
