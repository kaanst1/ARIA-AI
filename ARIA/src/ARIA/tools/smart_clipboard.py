"""Akıllı Clipboard Aksiyonları — kopyalanan içeriği tanı, otomatik aksiyon öner."""

from __future__ import annotations

import logging
import re
import subprocess
from typing import Optional

from ARIA.core.registry import register_tool

logger = logging.getLogger("aria.tools.smart_clipboard")

# İçerik tipi tespiti için pattern'lar
_URL_RE = re.compile(r"^https?://\S+$", re.MULTILINE)
_CODE_KEYWORDS = {"def ", "function ", "class ", "import ", "const ", "let ", "var ",
                  "return ", "if (", "for (", "while (", "=>", "#!/", "SELECT ", "INSERT "}
_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
_JSON_RE = re.compile(r"^\s*[\[{]")
_PHONE_RE = re.compile(r"^[\+\d\s\-\(\)]{8,20}$")


def _detect_type(content: str) -> str:
    """İçerik tipini tespit et."""
    stripped = content.strip()

    if _URL_RE.match(stripped):
        return "url"
    if _EMAIL_RE.match(stripped):
        return "email"
    if _PHONE_RE.match(stripped):
        return "phone"
    if _JSON_RE.match(stripped):
        try:
            import json
            json.loads(stripped)
            return "json"
        except Exception:
            pass
    if any(kw in stripped for kw in _CODE_KEYWORDS):
        return "code"
    if len(stripped.split()) > 50:
        return "long_text"
    if stripped.endswith((".py", ".js", ".ts", ".go", ".rs", ".java", ".cpp", ".c")):
        return "file_path"

    return "text"


def _get_clipboard() -> str:
    r = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=3)
    return r.stdout


def _suggest_actions(content_type: str, content: str) -> list[dict]:
    """İçerik tipine göre aksiyon önerileri üret."""
    actions = []
    short = content[:80].replace("\n", " ")

    if content_type == "url":
        actions += [
            {"id": "summarize_url", "label": "Sayfayı özetle", "icon": "📄"},
            {"id": "open_browser", "label": "Tarayıcıda aç", "icon": "🌐"},
            {"id": "extract_links", "label": "Linkleri çıkar", "icon": "🔗"},
        ]
    elif content_type == "code":
        actions += [
            {"id": "review_code", "label": "Kodu incele", "icon": "🔍"},
            {"id": "explain_code", "label": "Kodu açıkla", "icon": "💡"},
            {"id": "fix_code", "label": "Hataları düzelt", "icon": "🛠"},
        ]
    elif content_type == "json":
        actions += [
            {"id": "format_json", "label": "JSON formatla", "icon": "✨"},
            {"id": "explain_json", "label": "JSON yapısını açıkla", "icon": "💡"},
        ]
    elif content_type == "long_text":
        actions += [
            {"id": "summarize", "label": "Özetle", "icon": "📝"},
            {"id": "translate", "label": "Türkçeye çevir", "icon": "🌍"},
            {"id": "save_note", "label": "Nota kaydet", "icon": "💾"},
        ]
    elif content_type == "email":
        actions += [
            {"id": "compose_email", "label": "Mail yaz", "icon": "✉️"},
            {"id": "contact_info", "label": "Kişi bilgisi ara", "icon": "👤"},
        ]
    elif content_type == "text":
        actions += [
            {"id": "summarize", "label": "Özetle", "icon": "📝"},
            {"id": "translate", "label": "Çevir", "icon": "🌍"},
            {"id": "improve", "label": "Geliştir", "icon": "✨"},
        ]

    return actions


@register_tool("clipboard_analyze_smart")
def clipboard_analyze_smart() -> dict:
    """Panodaki içeriği akıllıca analiz et ve aksiyon öner.

    Returns:
        {'type': str, 'content_preview': str, 'actions': list[dict], 'auto_suggestion': str}
    """
    content = _get_clipboard()
    if not content.strip():
        return {"success": True, "type": "empty", "actions": [], "auto_suggestion": "Pano boş"}

    content_type = _detect_type(content)
    actions = _suggest_actions(content_type, content)
    preview = content[:150].replace("\n", " ").strip()

    # Otomatik öneri
    suggestion = {
        "url": f"'{preview[:50]}' adresini özetleyeyim mi?",
        "code": "Kodu inceleyelim mi?",
        "json": "JSON'ı formatlaşayım mı?",
        "long_text": "Bu metni özetleyeyim mi?",
        "email": "Bu adrese mail yazayım mı?",
        "text": "Ne yapmamı istersin?",
        "empty": "Pano boş",
        "phone": f"{preview} numarasını arayalım mı?",
        "file_path": "Bu dosyayı analiz edeyim mi?",
    }.get(content_type, "")

    return {
        "success": True,
        "type": content_type,
        "content_preview": preview,
        "content_length": len(content),
        "actions": actions,
        "auto_suggestion": suggestion,
    }


@register_tool("clipboard_action")
def clipboard_action(action_id: str, extra: str = "") -> dict:
    """Panodaki içerik üzerinde aksiyon çalıştır.

    Args:
        action_id: Aksiyon ID'si (clipboard_analyze_smart'tan dönen)
        extra: Ek parametre (dil, format vb.)

    Returns:
        {'result': str}
    """
    content = _get_clipboard()
    if not content.strip():
        return {"success": False, "error": "Pano boş"}

    try:
        from ARIA.core.engine import ARIAEngine
        engine = ARIAEngine()

        prompts = {
            "summarize": f"Şu metni Türkçe kısaca özetle:\n\n{content[:3000]}",
            "summarize_url": None,  # özel işlem
            "translate": f"Şu metni {'Türkçeye' if extra != 'tr' else 'İngilizceye'} çevir:\n\n{content[:3000]}",
            "review_code": f"Bu kodu incele, hataları ve iyileştirmeleri söyle:\n\n```\n{content[:3000]}\n```",
            "explain_code": f"Bu kodu adım adım Türkçe açıkla:\n\n```\n{content[:3000]}\n```",
            "fix_code": f"Bu koddaki hataları düzelt ve açıkla:\n\n```\n{content[:3000]}\n```",
            "format_json": None,  # özel işlem
            "explain_json": f"Bu JSON yapısını açıkla:\n\n```json\n{content[:2000]}\n```",
            "improve": f"Bu metni daha iyi yaz (dili ve anlatımı geliştir):\n\n{content[:3000]}",
            "save_note": None,  # özel işlem
        }

        if action_id == "summarize_url":
            from ARIA.tools.browser_automation import browser_scrape
            scraped = browser_scrape(content.strip())
            if scraped["success"]:
                prompt = f"Bu sayfa içeriğini özetle:\n\n{scraped['content'][:3000]}"
                result = engine.chat([{"role": "user", "content": prompt}])
            else:
                result = f"Sayfa açılamadı: {scraped.get('error')}"

        elif action_id == "format_json":
            import json as jsonlib
            try:
                parsed = jsonlib.loads(content)
                result = jsonlib.dumps(parsed, ensure_ascii=False, indent=2)
                # Panoya kopyala
                subprocess.run(["pbcopy"], input=result.encode(), timeout=3)
                result = "JSON formatlandı ve panoya kopyalandı:\n\n" + result[:500]
            except Exception as exc:
                result = f"Geçerli JSON değil: {exc}"

        elif action_id == "open_browser":
            from ARIA.tools.browser_control import browser_open_url
            browser_open_url(content.strip())
            result = f"Açıldı: {content.strip()[:80]}"

        elif action_id == "save_note":
            from ARIA.tools.notes import notes_create
            title = f"Pano Notu {__import__('datetime').datetime.now().strftime('%d.%m %H:%M')}"
            notes_create(title, content[:2000])
            result = f"Apple Notes'a kaydedildi: {title}"

        elif action_id == "extract_links":
            from ARIA.tools.browser_automation import browser_extract_links
            r = browser_extract_links(content.strip())
            links = r.get("links", [])
            result = "\n".join(f"• {l['text']}: {l['href']}" for l in links[:10])
            result = result or "Link bulunamadı"

        else:
            prompt = prompts.get(action_id)
            if not prompt:
                return {"success": False, "error": f"Bilinmeyen aksiyon: {action_id}"}
            result = engine.chat([{"role": "user", "content": prompt}])

        return {"success": True, "action": action_id, "result": result}

    except Exception as exc:
        logger.error("Clipboard aksiyon hatası: %s", exc)
        return {"success": False, "error": str(exc)}
