"""Apple Contacts entegrasyonu — AppleScript üzerinden rehber erişimi."""

from __future__ import annotations

import logging
import subprocess

from ARIA.core.registry import register_tool

logger = logging.getLogger("aria.tools.contacts")


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


@register_tool("contacts_search")
def contacts_search(query: str) -> dict:
    """Kişiyi rehberde ara.

    Args:
        query: Ad, soyad veya şirket adı

    Returns:
        {'contacts': list[dict]}
    """
    safe = query.replace('"', '\\"')
    script = f'''
set output to ""
tell application "Contacts"
    set matches to (every person whose name contains "{safe}")
    repeat with p in matches
        set pName to name of p
        set pPhone to ""
        set pEmail to ""
        if (count of phones of p) > 0 then
            set pPhone to value of item 1 of phones of p
        end if
        if (count of emails of p) > 0 then
            set pEmail to value of item 1 of emails of p
        end if
        set output to output & pName & "|" & pPhone & "|" & pEmail & "\\n"
    end repeat
end tell
return output
'''
    try:
        raw = _run_applescript(script)
        contacts = []
        for line in raw.splitlines():
            parts = line.split("|")
            if len(parts) >= 1 and parts[0].strip():
                contacts.append({
                    "name": parts[0].strip(),
                    "phone": parts[1].strip() if len(parts) > 1 else "",
                    "email": parts[2].strip() if len(parts) > 2 else "",
                })
        return {"contacts": contacts, "count": len(contacts), "success": True}
    except Exception as exc:
        logger.warning("Kişi araması başarısız: %s", exc)
        return {"success": False, "error": str(exc), "contacts": []}


@register_tool("contacts_get_phone")
def contacts_get_phone(name: str) -> dict:
    """Kişinin telefon numarasını getir.

    Args:
        name: Kişi adı

    Returns:
        {'name': str, 'phone': str}
    """
    result = contacts_search(name)
    if result["success"] and result["contacts"]:
        c = result["contacts"][0]
        return {"name": c["name"], "phone": c["phone"], "success": bool(c["phone"])}
    return {"success": False, "error": f"'{name}' bulunamadı", "name": name, "phone": ""}


@register_tool("contacts_get_email")
def contacts_get_email(name: str) -> dict:
    """Kişinin e-posta adresini getir.

    Args:
        name: Kişi adı

    Returns:
        {'name': str, 'email': str}
    """
    result = contacts_search(name)
    if result["success"] and result["contacts"]:
        c = result["contacts"][0]
        return {"name": c["name"], "email": c["email"], "success": bool(c["email"])}
    return {"success": False, "error": f"'{name}' bulunamadı", "name": name, "email": ""}
