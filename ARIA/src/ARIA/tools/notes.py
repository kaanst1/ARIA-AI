"""Apple Notes entegrasyonu — AppleScript üzerinden."""

from __future__ import annotations

import logging
import subprocess
from typing import Optional

from ARIA.core.registry import register_tool

logger = logging.getLogger("aria.tools.notes")


def _run_applescript(script: str) -> str:
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "AppleScript hatası")
    return result.stdout.strip()


@register_tool("notes_create")
def notes_create(title: str, body: str, folder: str = "Notes") -> dict:
    """Apple Notes'a yeni not ekle.

    Args:
        title: Not başlığı
        body: Not içeriği
        folder: Klasör adı (varsayılan: Notes)

    Returns:
        {'success': bool, 'title': str}
    """
    safe_title = title.replace('"', '\\"')
    safe_body = body.replace('"', '\\"').replace("\n", "\\n")
    script = f'''
tell application "Notes"
    tell account "iCloud"
        set theFolder to folder "{folder}"
        make new note at theFolder with properties {{name:"{safe_title}", body:"{safe_body}"}}
    end tell
end tell
'''
    try:
        _run_applescript(script)
        return {"success": True, "title": title}
    except Exception as exc:
        logger.warning("Not oluşturulamadı: %s", exc)
        return {"success": False, "error": str(exc)}


@register_tool("notes_list")
def notes_list(folder: str = "Notes", limit: int = 10) -> dict:
    """Apple Notes'taki son notları listele.

    Returns:
        {'notes': list[dict], 'count': int}
    """
    script = f'''
set output to ""
tell application "Notes"
    tell account "iCloud"
        set theNotes to notes of folder "{folder}"
        set i to 0
        repeat with n in theNotes
            if i >= {limit} then exit repeat
            set output to output & name of n & "||" & (modification date of n as string) & "\\n"
            set i to i + 1
        end repeat
    end tell
end tell
return output
'''
    try:
        raw = _run_applescript(script)
        notes = []
        for line in raw.splitlines():
            if "||" in line:
                parts = line.split("||", 1)
                notes.append({"title": parts[0].strip(), "modified": parts[1].strip()})
        return {"notes": notes, "count": len(notes), "success": True}
    except Exception as exc:
        logger.warning("Notlar listelenemedi: %s", exc)
        return {"success": False, "error": str(exc), "notes": []}


@register_tool("notes_search")
def notes_search(query: str) -> dict:
    """Apple Notes'ta arama yap.

    Returns:
        {'results': list[dict]}
    """
    safe_query = query.replace('"', '\\"').lower()
    script = f'''
set output to ""
tell application "Notes"
    set theNotes to every note
    repeat with n in theNotes
        set noteName to name of n
        set noteBody to plaintext of n
        if (noteBody contains "{safe_query}") or (noteName contains "{safe_query}") then
            set output to output & noteName & "||" & (text 1 thru (min of 200 and (length of noteBody)) of noteBody) & "\\n---\\n"
        end if
    end repeat
end tell
return output
'''
    try:
        raw = _run_applescript(script)
        results = []
        for chunk in raw.split("\n---\n"):
            chunk = chunk.strip()
            if "||" in chunk:
                parts = chunk.split("||", 1)
                results.append({"title": parts[0].strip(), "preview": parts[1].strip()})
        return {"results": results, "count": len(results), "success": True}
    except Exception as exc:
        logger.warning("Not araması başarısız: %s", exc)
        return {"success": False, "error": str(exc), "results": []}
