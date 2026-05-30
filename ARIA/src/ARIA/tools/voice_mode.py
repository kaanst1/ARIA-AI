"""Tam ses konuşma döngüsü — dinle → yanıtla → dinle (elleri serbest Voice Mode)."""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger("aria.tools.voice_mode")

_active = False
_thread: Optional[threading.Thread] = None
_SILENCE_SEC = 1.5       # Bu kadar sessizlikten sonra konuşma bitti say
_MAX_LISTEN_SEC = 30     # Tek utterance maksimum süresi
_SAMPLE_RATE = 16_000

# WakeWord'den sonra kaç saniye dinlensin
_WAKE_LISTEN_TIMEOUT = 8


def _transcribe_audio(audio_np) -> str:
    """Ses array'ini metne çevir."""
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel("base", device="cpu", compute_type="int8")
        segs, _ = model.transcribe(audio_np.flatten().astype("float32"), language="tr", beam_size=1)
        return " ".join(s.text for s in segs).strip()
    except Exception as exc:
        logger.warning("STT hatası: %s", exc)
        return ""


def _record_until_silence(timeout: float = _MAX_LISTEN_SEC) -> Optional[object]:
    """Sessizliğe kadar kayıt yap, numpy array döndür."""
    try:
        import sounddevice as sd
        import numpy as np

        frames = []
        silence_count = 0
        chunk_sec = 0.3
        chunk_samples = int(_SAMPLE_RATE * chunk_sec)
        silence_threshold = 300  # RMS eşiği

        start = time.time()
        with sd.InputStream(samplerate=_SAMPLE_RATE, channels=1, dtype="int16") as stream:
            while time.time() - start < timeout:
                chunk, _ = stream.read(chunk_samples)
                frames.append(chunk)
                rms = int((chunk.astype("float32") ** 2).mean() ** 0.5)
                if rms < silence_threshold:
                    silence_count += chunk_sec
                    if silence_count >= _SILENCE_SEC and len(frames) > 5:
                        break
                else:
                    silence_count = 0

        if not frames:
            return None
        import numpy as np
        return np.concatenate(frames, axis=0)
    except Exception as exc:
        logger.warning("Kayıt hatası: %s", exc)
        return None


def _tts_speak(text: str) -> None:
    try:
        from ARIA.tools.tts import speak
        speak(text, lang="tr", block=True)
    except Exception as exc:
        logger.warning("TTS hatası: %s", exc)


def _notify(title: str, msg: str) -> None:
    import subprocess
    try:
        subprocess.run(
            ["osascript", "-e", f'display notification "{msg}" with title "{title}"'],
            capture_output=True, timeout=3,
        )
    except Exception:
        pass


def _voice_loop(on_transcript: Optional[Callable[[str], str]] = None) -> None:
    """Ana voice mode döngüsü."""
    global _active
    logger.info("Voice Mode başlatıldı")
    _notify("ARIA Voice Mode", "Dinliyorum — konuşabilirsin")
    _tts_speak("Voice mode aktif. Seni dinliyorum.")

    from ARIA.orchestrator.router import Orchestrator
    orch = Orchestrator()

    while _active:
        try:
            logger.debug("Dinleniyor...")
            audio = _record_until_silence(timeout=_MAX_LISTEN_SEC)
            if audio is None:
                time.sleep(0.2)
                continue

            import numpy as np
            rms = int((audio.astype("float32") ** 2).mean() ** 0.5)
            if rms < 100:  # Tam sessizlik — devam et
                time.sleep(0.1)
                continue

            text = _transcribe_audio(audio)
            if not text or len(text.strip()) < 2:
                continue

            logger.info("Kullanıcı: %s", text)

            # Çıkış komutu
            if any(k in text.lower() for k in ["voice mode kapat", "dinlemeyi durdur", "sessiz ol", "dur aria"]):
                _tts_speak("Voice mode kapatılıyor.")
                _active = False
                break

            # Yanıt üret
            if on_transcript:
                response = on_transcript(text)
            else:
                response = orch.dispatch(text)

            logger.info("ARIA: %s", response[:100])
            _tts_speak(response)

        except Exception as exc:
            logger.error("Voice loop hatası: %s", exc)
            time.sleep(1)

    logger.info("Voice Mode kapatıldı")
    _notify("ARIA Voice Mode", "Voice mode kapatıldı")


def start_voice_mode(on_transcript: Optional[Callable[[str], str]] = None) -> dict:
    """Sürekli dinleme modunu başlat.

    Args:
        on_transcript: Transkript gelince çağrılacak fonksiyon (None = Orchestrator)

    Returns:
        {'success': bool, 'active': bool}
    """
    global _active, _thread
    if _active:
        return {"success": False, "active": True, "message": "Voice mode zaten çalışıyor"}

    try:
        import sounddevice  # noqa
        from faster_whisper import WhisperModel  # noqa
    except ImportError as exc:
        return {"success": False, "active": False, "error": f"Bağımlılık eksik: {exc}"}

    _active = True
    _thread = threading.Thread(
        target=_voice_loop,
        args=(on_transcript,),
        daemon=True,
        name="aria-voice-mode",
    )
    _thread.start()
    return {"success": True, "active": True, "message": "Voice mode başlatıldı"}


def stop_voice_mode() -> dict:
    """Voice mode'u durdur."""
    global _active
    _active = False
    return {"success": True, "active": False}


def is_voice_active() -> bool:
    return _active and _thread is not None and _thread.is_alive()
