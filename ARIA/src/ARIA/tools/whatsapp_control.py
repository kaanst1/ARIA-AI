"""WhatsApp Desktop kontrolü — AppleScript + System Events.

İki mod:
  1. URL Scheme  : whatsapp://send?phone=...&text=...  (otomatik açar, gönder butonuna basar)
  2. UI Otomasyon: System Events ile arama → seç → yaz → gönder (Erişilebilirlik izni gerekli)

Erişilebilirlik izni için:
  Sistem Ayarları → Gizlilik ve Güvenlik → Erişilebilirlik → Terminal ✓
"""

from __future__ import annotations

import logging
import re
import subprocess
import time
from typing import Optional

from ARIA.core.registry import register_tool

logger = logging.getLogger("aria.tools.whatsapp")


def _run_applescript(script: str, timeout: int = 15) -> tuple[bool, str]:
    """AppleScript çalıştır; (başarı, çıktı) döndür."""
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    ok = result.returncode == 0
    out = result.stdout.strip() or result.stderr.strip()
    return ok, out


def _clean_phone(phone: str) -> str:
    """Telefon numarasını temizle, sadece rakam + başta + bırak."""
    cleaned = re.sub(r"[^\d+]", "", phone.strip())
    # Türkiye numarası: 05xx → +905xx
    if cleaned.startswith("05") and len(cleaned) == 11:
        cleaned = "+9" + cleaned[1:]
    return cleaned


# ── Mod 1: URL Scheme (izin gerektirmez) ────────────────────────────────────

def send_via_url_scheme(phone: str, message: str) -> dict:
    """whatsapp:// URL scheme ile mesaj gönder.

    WhatsApp Desktop açılır, sohbet hazır gelir, mesaj otomatik gönderilir.
    """
    import urllib.parse
    phone_clean = _clean_phone(phone)
    encoded_msg = urllib.parse.quote(message)
    url = f"whatsapp://send?phone={phone_clean}&text={encoded_msg}"

    # URL'yi aç
    ok, out = _run_applescript(f'open location "{url}"')
    if not ok:
        return {"success": False, "error": out, "method": "url_scheme"}

    # WhatsApp açılmasını bekle
    time.sleep(3)

    # Return tuşu ile gönder
    send_script = '''
tell application "System Events"
    tell process "WhatsApp"
        key code 36
    end tell
end tell
'''
    ok2, out2 = _run_applescript(send_script)
    return {
        "success": ok2,
        "method": "url_scheme",
        "phone": phone_clean,
        "message": message[:50] + ("..." if len(message) > 50 else ""),
        "detail": out2 if not ok2 else "Gönderildi",
    }


# ── Mod 2: UI Otomasyon (Erişilebilirlik izni gerekli) ──────────────────────

def send_via_ui(contact_name: str, message: str) -> dict:
    """WhatsApp Desktop UI'ı kontrol ederek isim ile mesaj gönder."""
    script = f'''
tell application "WhatsApp"
    activate
end tell
delay 1.5

tell application "System Events"
    tell process "WhatsApp"
        -- Arama butonunu veya arama kutusunu bul
        set didSearch to false

        -- Cmd+F veya Cmd+N ile yeni chat ara
        key code 3 using command down
        delay 1

        -- İsmi yaz
        keystroke "{contact_name}"
        delay 1.5

        -- İlk sonucu seç
        key code 125
        delay 0.5
        key code 36
        delay 1

        -- Mesajı yaz
        keystroke "{message}"
        delay 0.5

        -- Gönder
        key code 36
    end tell
end tell
'''
    ok, out = _run_applescript(script, timeout=20)
    return {
        "success": ok,
        "method": "ui_automation",
        "contact": contact_name,
        "message": message[:50] + ("..." if len(message) > 50 else ""),
        "detail": out if not ok else "Gönderildi",
    }


# ── Mesaj okuma ──────────────────────────────────────────────────────────────

def get_unread_count() -> dict:
    """WhatsApp'taki okunmamış mesaj sayısını döndür."""
    script = '''
tell application "System Events"
    tell process "WhatsApp"
        try
            set badge to value of UI element 1 of button 1 of UI element 1 of menu bar 1
            return badge
        on error
            return "0"
        end try
    end tell
end tell
'''
    ok, out = _run_applescript(script)
    return {"unread": out if ok else "bilinmiyor", "success": ok}


def check_whatsapp_running() -> bool:
    """WhatsApp çalışıyor mu?"""
    ok, _ = _run_applescript('return application "WhatsApp" is running')
    return ok


# ── Register ─────────────────────────────────────────────────────────────────

@register_tool("whatsapp_send_phone")
def whatsapp_send_phone(phone: str, message: str) -> dict:
    """Telefon numarasına WhatsApp mesajı gönder.

    Args:
        phone: Telefon numarası (05xx veya +905xx formatında)
        message: Gönderilecek mesaj
    """
    return send_via_url_scheme(phone, message)


@register_tool("whatsapp_send_contact")
def whatsapp_send_contact(contact_name: str, message: str) -> dict:
    """Kayıtlı kişi adıyla WhatsApp mesajı gönder.

    Erişilebilirlik izni gerektirir.
    Args:
        contact_name: WhatsApp'ta görünen kişi adı
        message: Gönderilecek mesaj
    """
    return send_via_ui(contact_name, message)


@register_tool("whatsapp_status")
def whatsapp_status() -> dict:
    """WhatsApp durumunu kontrol et."""
    running = check_whatsapp_running()
    result = {"running": running}
    if running:
        result.update(get_unread_count())
    return result
