"""Çeviri ve TTS araçları — lokal LLM + macOS say komutu."""

from __future__ import annotations

import logging
import subprocess
from typing import Optional

from ARIA.core.registry import register_tool

logger = logging.getLogger("aria.tools.translator")

# macOS TTS ses profilleri
_VOICE_MAP = {
    "tr": "Yelda",
    "turkish": "Yelda",
    "en": "Samantha",
    "english": "Samantha",
    "de": "Anna",
    "german": "Anna",
    "fr": "Thomas",
    "french": "Thomas",
    "es": "Jorge",
    "spanish": "Jorge",
    "it": "Alice",
    "italian": "Alice",
    "ja": "Kyoko",
    "japanese": "Kyoko",
    "zh": "Ting-Ting",
    "chinese": "Ting-Ting",
    "ar": "Maged",
    "arabic": "Maged",
}


def _get_voice(lang: str) -> str:
    """Dil kodundan ses profili al."""
    return _VOICE_MAP.get(lang.lower(), "Samantha")


@register_tool("translate")
def translate(text: str, target_lang: str = "Turkish") -> str:
    """Metni lokal LLM ile çevir.

    Args:
        text: Çevrilecek metin.
        target_lang: Hedef dil (örn: Turkish, English, German).

    Returns:
        Çevrilmiş metin.
    """
    try:
        from ARIA.core.engine import ARIAEngine
        engine = ARIAEngine()
        messages = [
            {
                "role": "system",
                "content": (
                    f"You are a professional translator. Translate the given text to {target_lang}. "
                    "Return ONLY the translated text, nothing else. No explanations, no notes."
                ),
            },
            {"role": "user", "content": text},
        ]
        result = engine.chat(messages)
        return result.strip()
    except Exception as exc:
        logger.error("Çeviri hatası: %s", exc)
        return f"Çeviri hatası: {exc}"


@register_tool("speak")
def speak(text: str, lang: str = "tr") -> dict:
    """Metni macOS say komutu ile seslendir.

    Args:
        text: Seslendirilecek metin.
        lang: Dil kodu (tr, en, de, fr...).

    Returns:
        {'success': bool, 'voice': str}
    """
    voice = _get_voice(lang)
    try:
        # Metni 1000 karakterle sınırla
        text_limited = text[:1000]
        result = subprocess.run(
            ["say", "-v", voice, text_limited],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            # Seçilen ses yoksa varsayılana dön
            subprocess.run(
                ["say", text_limited],
                capture_output=True,
                text=True,
                timeout=60,
            )
        return {"success": True, "voice": voice}
    except FileNotFoundError:
        return {"success": False, "error": "say komutu bulunamadı (macOS değil?)"}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "TTS zaman aşımına uğradı"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}
