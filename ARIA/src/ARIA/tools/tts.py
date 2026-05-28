"""TTS — macOS say komutu ile metinden sese çevirme.

Özellikler:
- Türkçe: Yelda sesi (tr_TR)
- İngilizce: Samantha sesi
- Non-blocking: arka planda çalar, ARIA bloklanmaz
- Interrupt: yeni mesaj gelince önceki sesi keser
- Markdown temizleme
"""

from __future__ import annotations

import logging
import re
import subprocess
import threading
from typing import Optional

from ARIA.core.config import load_config

logger = logging.getLogger("aria.tools.tts")

# Aktif konuşma process'i
_current_proc: Optional[subprocess.Popen] = None
_proc_lock = threading.Lock()

VOICE_MAP = {
    "tr": "Yelda",
    "tr_TR": "Yelda",
    "en": "Samantha",
    "en_US": "Samantha",
    "en_GB": "Daniel",
    "de": "Anna",
    "fr": "Thomas",
    "es": "Monica",
}

_MD_CLEAN = [
    re.compile(r"```[\s\S]*?```"),
    re.compile(r"`[^`]*`"),
    re.compile(r"\*{1,3}([^*]*)\*{1,3}"),
    re.compile(r"#{1,6}\s*"),
    re.compile(r"\[([^\]]*)\]\([^)]*\)"),
    re.compile(r"[-*]\s+"),
    re.compile(r"\|\s*[-:]+\s*\|.*"),
    re.compile(r"\|"),
    re.compile(r"\n{2,}"),
]


def _clean_for_speech(text: str) -> str:
    cleaned = text
    for pat in _MD_CLEAN:
        cleaned = pat.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    # Max 800 karakter — ilk 3 cümle
    if len(cleaned) > 800:
        sentences = re.split(r"[.!?]\s+", cleaned)
        cleaned = ". ".join(sentences[:3]) + "."
    return cleaned


def _detect_lang(text: str) -> str:
    tr_chars = set("çğışöüÇĞİŞÖÜ")
    if any(c in tr_chars for c in text):
        return "tr"
    tr_words = {"bir", "bu", "ben", "sen", "ve", "için", "ile", "ama", "çok", "olan"}
    if len(set(text.lower().split()) & tr_words) >= 2:
        return "tr"
    return "en"


def stop_speaking() -> None:
    """Aktif sesi durdur."""
    global _current_proc
    with _proc_lock:
        if _current_proc and _current_proc.poll() is None:
            try:
                _current_proc.terminate()
            except Exception:
                pass
            _current_proc = None


def speak(text: str, lang: Optional[str] = None, block: bool = False) -> None:
    """Metni seslendir — non-blocking, markdown temizler, dili otomatik tespit eder."""
    global _current_proc

    clean = _clean_for_speech(text)
    if not clean:
        return

    detected_lang = lang or _detect_lang(clean)
    voice = VOICE_MAP.get(detected_lang, "Yelda")

    stop_speaking()

    def _run():
        global _current_proc
        try:
            proc = subprocess.Popen(
                ["say", "-v", voice, clean],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            with _proc_lock:
                _current_proc = proc
            proc.wait()
        except Exception as exc:
            logger.error("TTS hatası: %s", exc)

    if block:
        _run()
    else:
        threading.Thread(target=_run, daemon=True).start()


def speak_text(text: str) -> None:
    """Geriye dönük uyumluluk."""
    try:
        config = load_config()
        if not config.enable_tts:
            return
    except Exception:
        pass
    speak(text)


def is_speaking() -> bool:
    with _proc_lock:
        return _current_proc is not None and _current_proc.poll() is None
