"""Apple Calendar entegrasyonu — AppleScript/osascript üzerinden takvim olayları."""

from __future__ import annotations

import json
import logging
import subprocess
from datetime import date, datetime
from typing import Optional

from ARIA.core.registry import register_tool

logger = logging.getLogger("aria.tools.calendar")

# ── AppleScript şablonları ────────────────────────────────────────────────────

_APPLESCRIPT_TODAY = """
set today to current date
set startOfDay to today - (time of today)
set endOfDay to startOfDay + (23 * hours + 59 * minutes + 59)

set outputList to {}

tell application "Calendar"
    repeat with c in calendars
        set cName to name of c
        set theEvents to (every event of c whose start date >= startOfDay and start date <= endOfDay)
        repeat with e in theEvents
            set eTitle to summary of e
            set eStart to start date of e
            set eEnd to end date of e
            try
                set eLocation to location of e
            on error
                set eLocation to ""
            end try
            try
                set eNotes to description of e
            on error
                set eNotes to ""
            end try
            set eStartStr to ((month of eStart as integer) as text) & "/" & ¬
                             ((day of eStart) as text) & " " & ¬
                             ((hours of eStart) as text) & ":" & ¬
                             text -2 thru -1 of ("0" & (minutes of eStart) as text)
            set eEndStr to ((hours of eEnd) as text) & ":" & ¬
                           text -2 thru -1 of ("0" & (minutes of eEnd) as text)
            set entry to eTitle & "|||" & eStartStr & "|||" & eEndStr & "|||" & cName & "|||" & eLocation
            set end of outputList to entry
        end repeat
    end repeat
end tell

set AppleScript's text item delimiters to "~~~"
set outputText to outputList as text
set AppleScript's text item delimiters to ""
return outputText
"""

_APPLESCRIPT_CHECK = """
set today to current date
set startOfDay to today - (time of today)
set endOfDay to startOfDay + (23 * hours + 59 * minutes + 59)

set eventCount to 0

tell application "Calendar"
    repeat with c in calendars
        set theEvents to (every event of c whose start date >= startOfDay and start date <= endOfDay)
        set eventCount to eventCount + (count of theEvents)
    end repeat
end tell

return eventCount as text
"""


# ── Yardımcı fonksiyonlar ─────────────────────────────────────────────────────

def _run_applescript(script: str, timeout: int = 10) -> Optional[str]:
    """AppleScript çalıştır ve çıktısını döndür."""
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            logger.warning("AppleScript hatası: %s", result.stderr.strip())
            return None
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        logger.error("AppleScript zaman aşımına uğradı")
        return None
    except FileNotFoundError:
        logger.error("osascript bulunamadı — macOS dışı platform?")
        return None
    except Exception as exc:
        logger.error("AppleScript çalıştırma hatası: %s", exc)
        return None


def _parse_events(raw: str) -> list[dict]:
    """AppleScript çıktısını dict listesine dönüştür."""
    if not raw:
        return []

    events: list[dict] = []
    for entry in raw.split("~~~"):
        entry = entry.strip()
        if not entry:
            continue
        parts = entry.split("|||")
        if len(parts) < 5:
            continue
        events.append({
            "title": parts[0].strip(),
            "start": parts[1].strip(),
            "end": parts[2].strip(),
            "calendar": parts[3].strip(),
            "location": parts[4].strip() or None,
        })

    # Saate göre sırala
    def sort_key(ev: dict) -> str:
        return ev.get("start", "")

    events.sort(key=sort_key)
    return events


# ── Tool fonksiyonları ────────────────────────────────────────────────────────

@register_tool("calendar_today")
def get_today_events() -> list[dict]:
    """Bugünkü takvim olaylarını döndürür.

    Returns:
        Her olay için {'title', 'start', 'end', 'calendar', 'location'} dict listesi.
        Hata durumunda boş liste.
    """
    raw = _run_applescript(_APPLESCRIPT_TODAY)
    if raw is None:
        logger.warning("Takvim verileri alınamadı")
        return []
    return _parse_events(raw)


@register_tool("calendar_check")
def format_today_events() -> str:
    """Bugünkü olayları okunabilir metin olarak döndürür.

    Returns:
        Bugünün programını içeren Türkçe metin.
    """
    events = get_today_events()
    today_str = datetime.now().strftime("%-d %B %Y")

    if not events:
        return f"Bugün ({today_str}) takviminizde etkinlik yok."

    lines: list[str] = [f"📅 Bugün ({today_str}) — {len(events)} etkinlik:\n"]
    for ev in events:
        location_part = f" — {ev['location']}" if ev.get("location") else ""
        lines.append(
            f"  • {ev['start']} - {ev['end']}  {ev['title']}{location_part}"
            f"  [{ev['calendar']}]"
        )

    return "\n".join(lines)
