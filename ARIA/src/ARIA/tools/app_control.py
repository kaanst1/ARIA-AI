"""macOS uygulama kontrolü — aç, kapat, odakla."""

from __future__ import annotations

import logging
import subprocess

from ARIA.core.registry import register_tool

logger = logging.getLogger("aria.tools.app_control")

# Kısaltma → gerçek uygulama adı eşlemesi
_APP_ALIASES: dict[str, str] = {
    "chrome": "Google Chrome",
    "safari": "Safari",
    "firefox": "Firefox",
    "vscode": "Visual Studio Code",
    "code": "Visual Studio Code",
    "terminal": "Terminal",
    "finder": "Finder",
    "spotify": "Spotify",
    "slack": "Slack",
    "zoom": "Zoom",
    "mail": "Mail",
    "notes": "Notes",
    "calendar": "Calendar",
    "takvim": "Calendar",
    "müzik": "Music",
    "music": "Music",
    "photos": "Photos",
    "fotoğraflar": "Photos",
    "messages": "Messages",
    "mesajlar": "Messages",
    "facetime": "FaceTime",
    "xcode": "Xcode",
    "pycharm": "PyCharm",
    "discord": "Discord",
    "whatsapp": "WhatsApp",
    "notion": "Notion",
    "arc": "Arc",
    "iterm": "iTerm2",
    "iterm2": "iTerm2",
}


def _resolve(app_name: str) -> str:
    return _APP_ALIASES.get(app_name.lower().strip(), app_name)


@register_tool("app_open")
def app_open(app_name: str) -> dict:
    """Bir macOS uygulamasını aç veya ön plana getir.

    Args:
        app_name: Uygulama adı veya kısaltma

    Returns:
        {'success': bool, 'app': str}
    """
    resolved = _resolve(app_name)
    try:
        subprocess.run(["open", "-a", resolved], check=True, timeout=10)
        logger.info("Uygulama açıldı: %s", resolved)
        return {"success": True, "app": resolved}
    except subprocess.CalledProcessError:
        return {"success": False, "app": resolved, "error": f"'{resolved}' bulunamadı"}
    except Exception as exc:
        return {"success": False, "app": resolved, "error": str(exc)}


@register_tool("app_quit")
def app_quit(app_name: str) -> dict:
    """Bir macOS uygulamasını kapat.

    Args:
        app_name: Uygulama adı veya kısaltma

    Returns:
        {'success': bool, 'app': str}
    """
    resolved = _resolve(app_name)
    script = f'tell application "{resolved}" to quit'
    try:
        subprocess.run(["osascript", "-e", script], check=True, timeout=10)
        return {"success": True, "app": resolved}
    except Exception as exc:
        return {"success": False, "app": resolved, "error": str(exc)}


@register_tool("app_list_running")
def app_list_running() -> dict:
    """Çalışan uygulamaları listele.

    Returns:
        {'apps': list[str]}
    """
    script = '''
tell application "System Events"
    set appList to name of every process whose background only is false
end tell
return appList
'''
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=10,
        )
        raw = result.stdout.strip()
        apps = [a.strip() for a in raw.split(",") if a.strip()]
        return {"apps": apps, "count": len(apps), "success": True}
    except Exception as exc:
        return {"success": False, "error": str(exc), "apps": []}


@register_tool("app_focus")
def app_focus(app_name: str) -> dict:
    """Uygulamayı ön plana getir (odakla).

    Args:
        app_name: Uygulama adı

    Returns:
        {'success': bool, 'app': str}
    """
    resolved = _resolve(app_name)
    script = f'tell application "{resolved}" to activate'
    try:
        subprocess.run(["osascript", "-e", script], check=True, timeout=10)
        return {"success": True, "app": resolved}
    except Exception as exc:
        return {"success": False, "app": resolved, "error": str(exc)}
