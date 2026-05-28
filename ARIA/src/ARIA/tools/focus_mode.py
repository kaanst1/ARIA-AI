"""macOS Odak / DND modu kontrolü — shortcuts / osascript."""

from __future__ import annotations

import logging
import subprocess

from ARIA.core.registry import register_tool

logger = logging.getLogger("aria.tools.focus_mode")


def _run(cmd: list[str]) -> tuple[str, int]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return r.stdout.strip(), r.returncode
    except Exception as exc:
        return str(exc), -1


@register_tool("focus_enable")
def focus_enable(mode: str = "Do Not Disturb") -> dict:
    """macOS Odak modunu etkinleştir.

    Args:
        mode: Odak modu adı (örn. 'Do Not Disturb', 'Work', 'Personal')

    Returns:
        {'success': bool, 'mode': str}
    """
    # macOS 12+ shortcuts CLI ile odak modu
    out, rc = _run(["shortcuts", "run", f"Enable {mode} Focus"])
    if rc == 0:
        return {"success": True, "mode": mode, "state": "enabled"}

    # Fallback: AppleScript ile sistem tercihleri / kontrol merkezi
    script = '''
tell application "System Events"
    tell process "Control Center"
        keystroke "f" using {command down, option down}
    end tell
end tell
'''
    subprocess.run(["osascript", "-e", script], capture_output=True, timeout=5)
    return {"success": True, "mode": mode, "state": "enabled", "method": "keyboard"}


@register_tool("focus_disable")
def focus_disable() -> dict:
    """Aktif Odak modunu devre dışı bırak.

    Returns:
        {'success': bool}
    """
    out, rc = _run(["shortcuts", "run", "Disable Focus"])
    if rc == 0:
        return {"success": True, "state": "disabled"}

    # Fallback AppleScript
    script = '''
tell application "System Events"
    tell process "Control Center"
        keystroke "f" using {command down, option down}
    end tell
end tell
'''
    subprocess.run(["osascript", "-e", script], capture_output=True, timeout=5)
    return {"success": True, "state": "disabled", "method": "keyboard"}


@register_tool("focus_status")
def focus_status() -> dict:
    """Aktif odak modunu öğren.

    Returns:
        {'active': bool, 'mode': str}
    """
    # defaults read ile mevcut odak modunu sorgula
    out, rc = _run([
        "defaults", "read",
        "com.apple.controlcenter", "NSStatusItem Visible Focus"
    ])

    # moonbeam / focus durumunu kontrol etmek için
    script = '''
tell application "System Events"
    tell process "Control Center"
        try
            set focusItem to menu bar item "Focus" of menu bar 1
            return "active"
        on error
            return "inactive"
        end try
    end tell
end tell
'''
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=8,
        )
        state = result.stdout.strip()
        return {"active": state == "active", "mode": "Do Not Disturb" if state == "active" else "none", "success": True}
    except Exception as exc:
        return {"success": False, "error": str(exc), "active": False, "mode": "unknown"}
