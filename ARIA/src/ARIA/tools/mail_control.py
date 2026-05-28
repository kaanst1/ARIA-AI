"""Apple Mail.app entegrasyonu — AppleScript üzerinden e-posta."""

from __future__ import annotations

import logging
import subprocess
from typing import Optional

from ARIA.core.registry import register_tool

logger = logging.getLogger("aria.tools.mail")


def _run_applescript(script: str) -> str:
    """AppleScript çalıştır ve çıktısını döndür."""
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=20,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "AppleScript hatası")
    return result.stdout.strip()


@register_tool("send_email")
def send_email(to: str, subject: str, body: str) -> dict:
    """Apple Mail.app üzerinden e-posta gönder.

    Args:
        to: Alıcı e-posta adresi
        subject: Konu
        body: Mesaj gövdesi
    """
    try:
        safe_to = to.replace('"', '\\"')
        safe_subject = subject.replace('"', '\\"')
        safe_body = body.replace('"', '\\"').replace("\n", "\\n")

        script = f"""
tell application "Mail"
    set newMsg to make new outgoing message with properties {{subject:"{safe_subject}", content:"{safe_body}", visible:false}}
    tell newMsg
        make new to recipient at end of to recipients with properties {{address:"{safe_to}"}}
    end tell
    send newMsg
end tell
"""
        _run_applescript(script)
        return {
            "success": True,
            "to": to,
            "subject": subject,
            "message": f"E-posta '{to}' adresine gönderildi.",
        }
    except Exception as exc:
        logger.error("E-posta gönderilemedi: %s", exc)
        return {"success": False, "error": str(exc)}


@register_tool("get_unread_emails")
def get_unread_emails(count: int = 5) -> list[dict]:
    """Apple Mail.app'ten okunmamış e-postaları getir.

    Args:
        count: Getirilecek maksimum e-posta sayısı (varsayılan: 5)
    """
    try:
        script = f"""
tell application "Mail"
    set unreadMessages to (messages of inbox whose read status is false)
    set output to ""
    set counter to 0
    repeat with msg in unreadMessages
        if counter >= {count} then exit repeat
        set msgFrom to sender of msg
        set msgSubject to subject of msg
        set msgDate to date received of msg as string
        try
            set msgContent to content of msg
            if length of msgContent > 200 then
                set msgPreview to text 1 thru 200 of msgContent
            else
                set msgPreview to msgContent
            end if
        on error
            set msgPreview to ""
        end try
        -- Newlines'ı temizle
        set output to output & msgFrom & "|||" & msgSubject & "|||" & msgDate & "|||" & msgPreview & "<<<END>>>"
        set counter to counter + 1
    end repeat
    return output
end tell
"""
        raw = _run_applescript(script)
        results = []
        for entry in raw.split("<<<END>>>"):
            entry = entry.strip()
            if not entry:
                continue
            parts = entry.split("|||")
            if len(parts) >= 4:
                # Preview'daki newline'ları temizle
                preview = parts[3].strip().replace("\n", " ").replace("\r", " ")
                results.append({
                    "from": parts[0].strip(),
                    "subject": parts[1].strip(),
                    "date": parts[2].strip(),
                    "preview": preview[:300],
                })
        return results
    except Exception as exc:
        logger.error("E-postalar alınamadı: %s", exc)
        return []


@register_tool("get_email_count")
def get_email_count() -> dict:
    """Apple Mail.app'teki okunmamış e-posta sayısını döndür."""
    try:
        script = """
tell application "Mail"
    set unreadCount to (count of (messages of inbox whose read status is false))
    return unreadCount as string
end tell
"""
        raw = _run_applescript(script)
        count = int(raw.strip()) if raw.strip().isdigit() else 0
        return {"success": True, "unread_count": count}
    except Exception as exc:
        logger.error("E-posta sayısı alınamadı: %s", exc)
        return {"success": False, "error": str(exc), "unread_count": 0}
