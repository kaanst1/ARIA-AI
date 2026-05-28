"""Apple Messages (iMessage/SMS) entegrasyonu — AppleScript."""

from __future__ import annotations

import logging
import subprocess
from typing import Optional

from ARIA.core.registry import register_tool

logger = logging.getLogger("aria.tools.imessage")


def _run_applescript(script: str, timeout: int = 15) -> str:
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or "AppleScript hatası")
    return r.stdout.strip()


@register_tool("imessage_send")
def imessage_send(recipient: str, message: str) -> dict:
    """iMessage veya SMS gönder.

    Args:
        recipient: Telefon numarası veya e-posta (Apple ID)
        message: Gönderilecek mesaj metni

    Returns:
        {'success': bool, 'to': str}
    """
    safe_msg = message.replace('"', '\\"').replace("\n", "\\n")
    safe_to = recipient.replace('"', '\\"')
    script = f'''
tell application "Messages"
    set targetService to 1st account whose service type = iMessage
    set targetBuddy to participant "{safe_to}" of targetService
    send "{safe_msg}" to targetBuddy
end tell
'''
    try:
        _run_applescript(script)
        return {"success": True, "to": recipient, "message": message[:50]}
    except Exception as exc:
        logger.warning("iMessage gönderilemedi: %s", exc)
        return {"success": False, "error": str(exc), "to": recipient}


@register_tool("imessage_get_unread")
def imessage_get_unread(limit: int = 5) -> dict:
    """Okunmamış iMessage'ları getir.

    Returns:
        {'messages': list[dict]}
    """
    script = f'''
set output to ""
tell application "Messages"
    set allChats to every chat
    set counter to 0
    repeat with aChat in allChats
        if counter >= {limit} then exit repeat
        try
            set msgList to messages of aChat
            if (count of msgList) > 0 then
                set lastMsg to last item of msgList
                if read of lastMsg is false then
                    set senderName to handle of sender of lastMsg
                    set msgText to content of lastMsg
                    set msgDate to date sent of lastMsg as string
                    set output to output & senderName & "||" & (text 1 thru (min of 200 and (length of msgText)) of msgText) & "||" & msgDate & "\\n"
                    set counter to counter + 1
                end if
            end if
        end try
    end repeat
end tell
return output
'''
    try:
        raw = _run_applescript(script)
        msgs = []
        for line in raw.splitlines():
            parts = line.split("||")
            if len(parts) >= 2:
                msgs.append({
                    "from": parts[0].strip(),
                    "text": parts[1].strip(),
                    "date": parts[2].strip() if len(parts) > 2 else "",
                })
        return {"messages": msgs, "count": len(msgs), "success": True}
    except Exception as exc:
        logger.warning("iMessage okunamadı: %s", exc)
        return {"success": False, "error": str(exc), "messages": []}


@register_tool("imessage_get_conversation")
def imessage_get_conversation(contact: str, limit: int = 10) -> dict:
    """Belirli kişiyle olan son iMessage konuşmasını getir.

    Args:
        contact: Telefon numarası veya isim
        limit: Getirilecek mesaj sayısı

    Returns:
        {'messages': list[dict]}
    """
    safe_contact = contact.replace('"', '\\"')
    script = f'''
set output to ""
tell application "Messages"
    repeat with aChat in (every chat)
        try
            if name of aChat contains "{safe_contact}" then
                set msgList to (last {limit} messages of aChat)
                repeat with msg in msgList
                    set msgSender to handle of sender of msg
                    set msgText to content of msg
                    set msgDate to date sent of msg as string
                    set output to output & msgSender & "||" & (text 1 thru (min of 300 and (length of msgText)) of msgText) & "||" & msgDate & "\\n"
                end repeat
                exit repeat
            end if
        end try
    end repeat
end tell
return output
'''
    try:
        raw = _run_applescript(script)
        msgs = []
        for line in raw.splitlines():
            parts = line.split("||")
            if len(parts) >= 2:
                msgs.append({"from": parts[0].strip(), "text": parts[1].strip(), "date": parts[2].strip() if len(parts) > 2 else ""})
        return {"messages": msgs, "count": len(msgs), "contact": contact, "success": True}
    except Exception as exc:
        return {"success": False, "error": str(exc), "messages": []}
