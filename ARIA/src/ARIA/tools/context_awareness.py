"""Bağlam farkındalığı — ön plandaki uygulama, yaklaşan toplantı, öneriler."""

from __future__ import annotations

import logging
import subprocess
from datetime import datetime, timedelta
from typing import Optional

from ARIA.core.registry import register_tool

logger = logging.getLogger("aria.tools.context")


def _run_applescript(script: str, timeout: int = 8) -> str:
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=timeout)
    return r.stdout.strip()


@register_tool("context_get_frontmost_app")
def context_get_frontmost_app() -> dict:
    """Şu an ön planda olan uygulamayı döndür.

    Returns:
        {'app': str, 'window_title': str}
    """
    script = '''
tell application "System Events"
    set frontApp to name of first application process whose frontmost is true
    set winTitle to ""
    try
        set winTitle to name of front window of application process frontApp
    end try
    return frontApp & "||" & winTitle
end tell
'''
    try:
        raw = _run_applescript(script)
        parts = raw.split("||", 1)
        return {"app": parts[0].strip(), "window_title": parts[1].strip() if len(parts) > 1 else "", "success": True}
    except Exception as exc:
        return {"success": False, "error": str(exc), "app": "", "window_title": ""}


@register_tool("context_upcoming_meetings")
def context_upcoming_meetings(minutes_ahead: int = 30) -> dict:
    """Önümüzdeki N dakika içindeki toplantıları getir.

    Returns:
        {'meetings': list[dict], 'next': dict | None}
    """
    try:
        from ARIA.tools.calendar_tools import get_today_events
        now = datetime.now()
        cutoff = now + timedelta(minutes=minutes_ahead)
        events = get_today_events()
        upcoming = []
        for ev in events:
            try:
                start_str = ev.get("start", "")
                start_dt = datetime.strptime(f"{now.date()} {start_str}", "%Y-%m-%d %H:%M")
                if now <= start_dt <= cutoff:
                    minutes_left = int((start_dt - now).total_seconds() / 60)
                    upcoming.append({**ev, "minutes_until": minutes_left})
            except Exception:
                pass
        upcoming.sort(key=lambda x: x.get("minutes_until", 9999))
        return {"meetings": upcoming, "next": upcoming[0] if upcoming else None, "success": True}
    except Exception as exc:
        return {"success": False, "error": str(exc), "meetings": [], "next": None}


@register_tool("context_suggest")
def context_suggest() -> dict:
    """Mevcut bağlama göre ARIA önerisi üret.

    Returns:
        {'suggestion': str, 'reason': str}
    """
    suggestions = []

    # Yaklaşan toplantı kontrolü
    meetings = context_upcoming_meetings(15)
    if meetings.get("next"):
        mtg = meetings["next"]
        mins = mtg.get("minutes_until", 0)
        title = mtg.get("title", "toplantı")
        suggestions.append({
            "suggestion": f"'{title}' toplantısına {mins} dakika var. Hazırlık notu ister misin?",
            "reason": "upcoming_meeting",
            "priority": 10,
        })

    # Ön plan uygulaması
    app_info = context_get_frontmost_app()
    app = app_info.get("app", "")
    win = app_info.get("window_title", "")

    app_suggestions = {
        "Xcode": ("Xcode'da çalışıyorsun. Kod incelemesi veya debug yardımı ister misin?", "xcode_active"),
        "Visual Studio Code": ("VS Code açık. Bir dosyayı analiz etmemi ister misin?", "vscode_active"),
        "Terminal": ("Terminal'de çalışıyorsun. Komut yardımı lazım mı?", "terminal_active"),
        "Mail": ("Mail açık. Gelen kutusu özetini çıkarayım mı?", "mail_active"),
        "Safari": (f"'{win}' sayfasına bakıyorsun. Bu sayfayı özetleyeyim mi?", "safari_active"),
        "Google Chrome": (f"Chrome'da çalışıyorsun. Araştırma yardımı ister misin?", "chrome_active"),
    }
    if app in app_suggestions:
        text, reason = app_suggestions[app]
        suggestions.append({"suggestion": text, "reason": reason, "priority": 5})

    # Saat bazlı öneriler
    hour = datetime.now().hour
    if 7 <= hour <= 9 and not suggestions:
        suggestions.append({"suggestion": "Sabah briefini almak ister misin?", "reason": "morning_time", "priority": 8})
    elif 12 <= hour <= 13 and not suggestions:
        suggestions.append({"suggestion": "Öğle arası — yarım günlük özet çıkarayım mı?", "reason": "lunch_time", "priority": 4})
    elif 17 <= hour <= 19 and not suggestions:
        suggestions.append({"suggestion": "Günü kapatıyorsun. Bugünkü özeti oluşturayım mı?", "reason": "eod_time", "priority": 6})

    if not suggestions:
        return {"suggestion": None, "reason": "no_context", "success": True}

    best = max(suggestions, key=lambda x: x["priority"])
    return {"suggestion": best["suggestion"], "reason": best["reason"], "success": True}
