"""Email zekası — sınıflandırma, toplantı çıkarma, taslak önerisi."""

from __future__ import annotations

import logging
import re
from typing import Optional

from ARIA.core.registry import register_tool

logger = logging.getLogger("aria.tools.email_intel")

# Kategori anahtar kelimeleri
_CATEGORIES = {
    "acil": ["urgent", "acil", "asap", "hemen", "kritik", "important", "önemli"],
    "toplantı": ["meeting", "toplantı", "görüşme", "zoom", "teams", "takvim", "davet", "invite", "calendar"],
    "fatura": ["invoice", "fatura", "ödeme", "payment", "receipt", "makbuz", "borç"],
    "spam": ["unsubscribe", "abonelik", "newsletter", "promotion", "deal", "offer", "win", "winner"],
    "iş": ["proje", "project", "deadline", "teslim", "görev", "task", "rapor", "report"],
    "kişisel": ["arkadaş", "aile", "family", "friend", "sevgili"],
}

_MEETING_PATTERNS = [
    r"\b(\d{1,2})[./](\d{1,2})[./](\d{2,4})\b",          # 15.06.2025
    r"\b(\d{1,2})\s+(Ocak|Şubat|Mart|Nisan|Mayıs|Haziran|Temmuz|Ağustos|Eylül|Ekim|Kasım|Aralık)\b",
    r"\b(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b",
    r"\b(Pazartesi|Salı|Çarşamba|Perşembe|Cuma|Cumartesi|Pazar)\b",
    r"\b(\d{1,2}):(\d{2})\s*(AM|PM|am|pm)?\b",             # 14:30
    r"\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\b",
]

_LINK_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)
_ZOOM_PATTERN = re.compile(r"zoom\.us/j/\d+", re.IGNORECASE)
_TEAMS_PATTERN = re.compile(r"teams\.microsoft\.com/l/meetup", re.IGNORECASE)


@register_tool("email_classify")
def email_classify(subject: str, body: str, sender: str = "") -> dict:
    """Maili kategorize et ve öncelik belirle.

    Args:
        subject: Mail konusu
        body: Mail içeriği
        sender: Gönderici adresi

    Returns:
        {'category': str, 'priority': str, 'tags': list[str], 'is_meeting': bool}
    """
    text = f"{subject} {body} {sender}".lower()

    tags = []
    for cat, keywords in _CATEGORIES.items():
        if any(k in text for k in keywords):
            tags.append(cat)

    is_meeting = any(cat in tags for cat in ["toplantı"])
    if not is_meeting:
        # Pattern bazlı toplantı tespiti
        for pat in _MEETING_PATTERNS[:4]:
            if re.search(pat, text, re.IGNORECASE):
                is_meeting = True
                if "toplantı" not in tags:
                    tags.append("toplantı")
                break

    # Öncelik
    if "acil" in tags:
        priority = "yüksek"
    elif "toplantı" in tags or "iş" in tags:
        priority = "orta"
    elif "spam" in tags:
        priority = "düşük"
    else:
        priority = "normal"

    category = tags[0] if tags else "genel"

    return {
        "category": category,
        "priority": priority,
        "tags": tags,
        "is_meeting": is_meeting,
        "success": True,
    }


@register_tool("email_extract_meeting")
def email_extract_meeting(subject: str, body: str) -> dict:
    """Mailden toplantı bilgilerini çıkar.

    Returns:
        {'found': bool, 'dates': list, 'times': list, 'links': list, 'platform': str}
    """
    text = f"{subject}\n{body}"

    dates = []
    for pat in _MEETING_PATTERNS[:2]:
        dates.extend(re.findall(pat, text, re.IGNORECASE))

    times = re.findall(r"\b(\d{1,2}):(\d{2})\s*(AM|PM|am|pm)?\b", text)

    links = _LINK_PATTERN.findall(text)
    zoom_links = _ZOOM_PATTERN.findall(text)
    teams_links = _TEAMS_PATTERN.findall(text)

    platform = "bilinmiyor"
    if zoom_links:
        platform = "Zoom"
    elif teams_links:
        platform = "Teams"
    elif any("meet.google" in l for l in links):
        platform = "Google Meet"

    found = bool(dates or times or zoom_links or teams_links)

    return {
        "found": found,
        "dates": [" ".join(d) if isinstance(d, tuple) else d for d in dates[:3]],
        "times": [f"{t[0]}:{t[1]}{t[2]}" for t in times[:3]],
        "links": links[:3],
        "platform": platform,
        "success": True,
    }


@register_tool("email_draft_reply")
def email_draft_reply(subject: str, body: str, sender: str, tone: str = "profesyonel") -> dict:
    """Maile otomatik taslak yanıt üret.

    Args:
        subject: Orijinal konu
        body: Orijinal mail gövdesi
        sender: Gönderici adı/email
        tone: 'profesyonel' | 'samimi' | 'kısa'

    Returns:
        {'draft': str, 'subject': str}
    """
    tone_map = {
        "profesyonel": "resmi ve profesyonel bir dilde",
        "samimi": "samimi ve sıcak bir dilde",
        "kısa": "çok kısa ve öz (3-4 cümle)",
    }
    tone_desc = tone_map.get(tone, tone_map["profesyonel"])

    prompt = (
        f"Aşağıdaki maile {tone_desc} Türkçe taslak yanıt yaz.\n"
        f"Konu: {subject}\n"
        f"Gönderen: {sender}\n"
        f"İçerik:\n{body[:800]}\n\n"
        f"Sadece yanıt metnini yaz, açıklama ekleme."
    )

    try:
        from ARIA.core.engine import ARIAEngine
        draft = ARIAEngine().chat([{"role": "user", "content": prompt}])
        reply_subject = f"Re: {subject}" if not subject.startswith("Re:") else subject
        return {"draft": draft, "subject": reply_subject, "success": True}
    except Exception as exc:
        return {"success": False, "error": str(exc), "draft": "", "subject": ""}


@register_tool("email_summarize")
def email_summarize(emails: list[dict]) -> dict:
    """Birden fazla maili özetle ve önceliklendir.

    Args:
        emails: [{'subject': str, 'from': str, 'body': str, 'date': str}, ...]

    Returns:
        {'summary': str, 'urgent': list, 'meetings': list}
    """
    if not emails:
        return {"summary": "Okunmamış mail yok.", "urgent": [], "meetings": [], "success": True}

    urgent = []
    meetings = []
    lines = [f"📬 {len(emails)} okunmamış mail:\n"]

    for e in emails[:10]:
        subj = e.get("subject", "?")
        sender = e.get("from", "?")
        body = e.get("body", "")

        info = email_classify(subj, body, sender)
        is_urgent = info["priority"] == "yüksek"
        is_meeting = info["is_meeting"]

        icon = "🔴" if is_urgent else ("📅" if is_meeting else "📧")
        lines.append(f"{icon} {subj} — {sender}")

        if is_urgent:
            urgent.append({"subject": subj, "from": sender})
        if is_meeting:
            mtg = email_extract_meeting(subj, body)
            meetings.append({"subject": subj, "from": sender, **mtg})

    return {
        "summary": "\n".join(lines),
        "urgent": urgent,
        "meetings": meetings,
        "success": True,
    }
