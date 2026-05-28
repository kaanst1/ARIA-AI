"""TTS — edge-tts (Microsoft Neural) birincil, macOS say fallback.

Sesler:
- Türkçe:  tr-TR-EmelNeural (edge-tts) → Yelda fallback
- İngilizce: en-US-AriaNeural (edge-tts) → Samantha fallback
- Diğer:   edge-tts Locale + Compact sesler

Özellikler:
- Non-blocking: arka planda çalar
- Interrupt: yeni mesaj gelince önceki sesi keser
- Markdown temizleme
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import subprocess
import tempfile
import threading
from typing import Optional

from ARIA.core.config import load_config

logger = logging.getLogger("aria.tools.tts")

# ── Ses haritaları ─────────────────────────────────────────────────────────────

EDGE_VOICE_MAP = {
    "tr":    "tr-TR-EmelNeural",
    "tr_TR": "tr-TR-EmelNeural",
    "en":    "en-US-AriaNeural",
    "en_US": "en-US-AriaNeural",
    "en_GB": "en-GB-SoniaNeural",
    "de":    "de-DE-KatjaNeural",
    "fr":    "fr-FR-DeniseNeural",
    "es":    "es-ES-ElviraNeural",
}

SAY_FALLBACK_MAP = {
    "tr":    "Yelda",
    "tr_TR": "Yelda",
    "en":    "Samantha",
    "en_US": "Samantha",
    "en_GB": "Daniel",
    "de":    "Anna",
    "fr":    "Thomas",
    "es":    "Monica",
}

# edge-tts mevcut mu?
try:
    import edge_tts as _edge_tts_module
    EDGE_TTS_AVAILABLE = True
except ImportError:
    EDGE_TTS_AVAILABLE = False
    logger.info("edge-tts yüklü değil → say fallback kullanılacak")

# Aktif konuşma thread/process takibi
_current_proc: Optional[subprocess.Popen] = None
_proc_lock = threading.Lock()
_speaking_flag = threading.Event()

# ── Markdown temizleme ─────────────────────────────────────────────────────────

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
    # Max 900 karakter — ilk 4 cümle
    if len(cleaned) > 900:
        sentences = re.split(r"(?<=[.!?])\s+", cleaned)
        cleaned = " ".join(sentences[:4])
        if len(cleaned) > 900:
            cleaned = cleaned[:900] + "..."
    return cleaned


def _detect_lang(text: str) -> str:
    tr_chars = set("çğışöüÇĞİŞÖÜ")
    if any(c in tr_chars for c in text):
        return "tr"
    tr_words = {"bir", "bu", "ben", "sen", "ve", "için", "ile", "ama", "çok", "olan", "da", "de"}
    if len(set(text.lower().split()) & tr_words) >= 2:
        return "tr"
    return "en"


# ── Stop / Status ──────────────────────────────────────────────────────────────

def stop_speaking() -> None:
    """Aktif sesi durdur."""
    global _current_proc
    _speaking_flag.clear()
    with _proc_lock:
        if _current_proc and _current_proc.poll() is None:
            try:
                _current_proc.terminate()
                _current_proc.wait(timeout=1)
            except Exception:
                pass
            _current_proc = None


def is_speaking() -> bool:
    with _proc_lock:
        return _current_proc is not None and _current_proc.poll() is None


# ── edge-tts yolu ──────────────────────────────────────────────────────────────

async def _edge_tts_to_file(text: str, voice: str, out_path: str) -> None:
    """edge-tts ile ses dosyası üret."""
    import edge_tts
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(out_path)


def _speak_edge(text: str, voice: str) -> None:
    """edge-tts: MP3 üret → afplay ile çal → temizle."""
    global _current_proc

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            tmp_path = f.name

        # Async üretim — yeni event loop (thread içinde)
        loop = asyncio.new_event_loop()
        loop.run_until_complete(_edge_tts_to_file(text, voice, tmp_path))
        loop.close()

        if not _speaking_flag.is_set():
            return  # İptal edildi

        # afplay ile çal
        proc = subprocess.Popen(
            ["afplay", tmp_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        with _proc_lock:
            _current_proc = proc
        proc.wait()

    except Exception as exc:
        logger.error("edge-tts hatası: %s — say fallback", exc)
        # Fallback: say komutu
        lang = "tr" if "Emel" in voice or "tr-TR" in voice else "en"
        say_voice = SAY_FALLBACK_MAP.get(lang, "Yelda")
        try:
            proc = subprocess.Popen(
                ["say", "-v", say_voice, text],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            with _proc_lock:
                _current_proc = proc
            proc.wait()
        except Exception as exc2:
            logger.error("say fallback hatası: %s", exc2)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
        with _proc_lock:
            _current_proc = None
        _speaking_flag.clear()


# ── macOS say yolu ─────────────────────────────────────────────────────────────

def _speak_say(text: str, voice: str) -> None:
    global _current_proc
    try:
        proc = subprocess.Popen(
            ["say", "-v", voice, text],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        with _proc_lock:
            _current_proc = proc
        proc.wait()
    except Exception as exc:
        logger.error("say hatası: %s", exc)
    finally:
        with _proc_lock:
            _current_proc = None
        _speaking_flag.clear()


# ── Ana API ───────────────────────────────────────────────────────────────────

def speak(text: str, lang: Optional[str] = None, block: bool = False) -> None:
    """Metni seslendir — non-blocking, markdown temizler, dili otomatik tespit eder.

    Args:
        text: Seslendirilecek metin (Markdown desteklenir, temizlenir)
        lang: Dil kodu (None → otomatik tespit). Örn: 'tr', 'en'
        block: True → döndürmeden önce tamamlanmasını bekle
    """
    clean = _clean_for_speech(text)
    if not clean:
        return

    detected_lang = lang or _detect_lang(clean)

    stop_speaking()  # Önceki sesi kes
    _speaking_flag.set()

    if EDGE_TTS_AVAILABLE:
        edge_voice = EDGE_VOICE_MAP.get(detected_lang, "tr-TR-EmelNeural")
        target = lambda: _speak_edge(clean, edge_voice)  # noqa: E731
    else:
        say_voice = SAY_FALLBACK_MAP.get(detected_lang, "Yelda")
        target = lambda: _speak_say(clean, say_voice)  # noqa: E731

    if block:
        target()
    else:
        threading.Thread(target=target, daemon=True).start()


def speak_text(text: str) -> None:
    """Geriye dönük uyumluluk wrapper."""
    try:
        config = load_config()
        if not config.enable_tts:
            return
    except Exception:
        pass
    speak(text)
