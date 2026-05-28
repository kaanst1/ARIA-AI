"""Apple Reminders entegrasyonu — AppleScript üzerinden macOS Reminders."""

from __future__ import annotations

import logging
import subprocess
from typing import Optional

from ARIA.core.registry import register_tool

logger = logging.getLogger("aria.tools.reminders")


def _run_applescript(script: str) -> str:
    """AppleScript çalıştır ve çıktısını döndür."""
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "AppleScript hatası")
    return result.stdout.strip()


@register_tool("add_reminder")
def add_reminder(
    title: str,
    due_date: Optional[str] = None,
    due_time: Optional[str] = None,
    notes: str = "",
    list_name: str = "Reminders",
) -> dict:
    """Apple Reminders'a yeni hatırlatıcı ekle.

    Args:
        title: Hatırlatıcı başlığı
        due_date: Bitiş tarihi (YYYY-MM-DD formatında), örn. "2025-01-15"
        due_time: Bitiş saati (HH:MM formatında), örn. "09:30"
        notes: Ek notlar
        list_name: Liste adı (varsayılan: "Reminders")
    """
    try:
        props = f'{{name:"{title}"'

        if due_date:
            # Tarih parse et
            parts = due_date.split("-")
            if len(parts) == 3:
                year, month, day = parts
                time_str = due_time or "09:00"
                h, m = (time_str.split(":") + ["00"])[:2]
                # AppleScript date string
                date_str = f"{month}/{day}/{year} {h}:{m}:00"
                props += f', due date:date "{date_str}"'

        if notes:
            safe_notes = notes.replace('"', '\\"')
            props += f', body:"{safe_notes}"'

        props += "}"

        script = f"""
tell application "Reminders"
    set theList to list "{list_name}"
    make new reminder at end of theList with properties {props}
    return "ok"
end tell
"""
        _run_applescript(script)
        return {
            "success": True,
            "title": title,
            "due_date": due_date,
            "due_time": due_time,
            "list": list_name,
        }
    except Exception as exc:
        logger.error("Reminder eklenemedi: %s", exc)
        return {"success": False, "error": str(exc)}


@register_tool("get_reminders")
def get_reminders(
    list_name: Optional[str] = None,
    completed: bool = False,
) -> list[dict]:
    """Apple Reminders'dan hatırlatıcıları getir.

    Args:
        list_name: Belirli bir listeyi filtrele (None → tümü)
        completed: True ise tamamlananları da getir
    """
    try:
        completed_filter = "true" if completed else "false"
        if list_name:
            safe_list = list_name.replace('"', '\\"')
            script = f"""
tell application "Reminders"
    set theList to list "{safe_list}"
    set theReminders to (every reminder in theList whose completed is {completed_filter})
    set output to ""
    repeat with r in theReminders
        set rName to name of r
        try
            set rDue to due date of r
            set rDueStr to (month of rDue as integer) as text & "/" & (day of rDue) as text & "/" & (year of rDue) as text & " " & (hours of rDue) as text & ":" & text -2 thru -1 of ("0" & (minutes of rDue) as text)
        on error
            set rDueStr to ""
        end try
        try
            set rNotes to body of r
        on error
            set rNotes to ""
        end try
        set output to output & rName & "|||" & rDueStr & "|||" & rNotes & "|||" & "{safe_list}" & "\\n"
    end repeat
    return output
end tell
"""
        else:
            script = f"""
tell application "Reminders"
    set output to ""
    repeat with theList in lists
        set lName to name of theList
        set theReminders to (every reminder in theList whose completed is {completed_filter})
        repeat with r in theReminders
            set rName to name of r
            try
                set rDue to due date of r
                set rDueStr to (month of rDue as integer) as text & "/" & (day of rDue) as text & "/" & (year of rDue) as text & " " & (hours of rDue) as text & ":" & text -2 thru -1 of ("0" & (minutes of rDue) as text)
            on error
                set rDueStr to ""
            end try
            try
                set rNotes to body of r
            on error
                set rNotes to ""
            end try
            set output to output & rName & "|||" & rDueStr & "|||" & rNotes & "|||" & lName & "\\n"
        end repeat
    end repeat
    return output
end tell
"""

        raw = _run_applescript(script)
        results = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split("|||")
            if len(parts) >= 4:
                results.append({
                    "title": parts[0],
                    "due": parts[1] or None,
                    "notes": parts[2] or "",
                    "list": parts[3],
                })
        return results
    except Exception as exc:
        logger.error("Reminders alınamadı: %s", exc)
        return []


@register_tool("complete_reminder")
def complete_reminder(title: str, list_name: Optional[str] = None) -> dict:
    """Apple Reminders'da bir hatırlatıcıyı tamamlandı olarak işaretle.

    Args:
        title: Tamamlanacak hatırlatıcının başlığı
        list_name: Aranacak liste (None → tüm listeler)
    """
    try:
        safe_title = title.replace('"', '\\"')
        if list_name:
            safe_list = list_name.replace('"', '\\"')
            script = f"""
tell application "Reminders"
    set theList to list "{safe_list}"
    set theReminder to first reminder in theList whose name is "{safe_title}"
    set completed of theReminder to true
    return "ok"
end tell
"""
        else:
            script = f"""
tell application "Reminders"
    repeat with theList in lists
        try
            set theReminder to first reminder in theList whose name is "{safe_title}"
            set completed of theReminder to true
            return "ok"
        end try
    end repeat
    return "not found"
end tell
"""
        result = _run_applescript(script)
        if result == "not found":
            return {"success": False, "error": f"'{title}' bulunamadı"}
        return {"success": True, "completed": title}
    except Exception as exc:
        logger.error("Reminder tamamlanamadı: %s", exc)
        return {"success": False, "error": str(exc)}
