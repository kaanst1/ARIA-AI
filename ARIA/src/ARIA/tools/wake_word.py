"""Wake word tespiti — sounddevice + faster-whisper ile "Hey ARIA" dinleme."""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger("aria.tools.wake_word")

_WAKE_WORDS = ["hey aria", "aria", "hey arya", "hey arıa"]
_SAMPLE_RATE = 16000
_CHUNK_SECONDS = 2
_SILENCE_THRESHOLD = 0.01
_running = False
_thread: Optional[threading.Thread] = None
_callback: Optional[Callable[[str], None]] = None


def _transcribe_chunk(audio_data) -> str:
    """Ses verisini Whisper ile metne çevir."""
    try:
        from faster_whisper import WhisperModel
        import numpy as np

        model = WhisperModel("tiny", device="cpu", compute_type="int8")
        audio_np = audio_data.flatten().astype("float32")

        segments, _ = model.transcribe(audio_np, language="tr", beam_size=1)
        text = " ".join(seg.text for seg in segments).strip().lower()
        return text
    except Exception as exc:
        logger.debug("Transkripsiyon hatası: %s", exc)
        return ""


def _is_wake_word(text: str) -> bool:
    return any(w in text for w in _WAKE_WORDS)


def _listen_loop(on_wake: Callable[[str], None]) -> None:
    global _running
    try:
        import sounddevice as sd
        import numpy as np

        logger.info("Wake word dinleme başladı")

        while _running:
            try:
                audio = sd.rec(
                    int(_CHUNK_SECONDS * _SAMPLE_RATE),
                    samplerate=_SAMPLE_RATE,
                    channels=1,
                    dtype="float32",
                )
                sd.wait()

                # Sessizlik kontrolü — CPU boşa harcama
                if np.abs(audio).mean() < _SILENCE_THRESHOLD:
                    time.sleep(0.1)
                    continue

                text = _transcribe_chunk(audio)
                if text and _is_wake_word(text):
                    logger.info("Wake word tespit edildi: '%s'", text)
                    on_wake(text)
                    time.sleep(1.5)  # Çift tetiklemeyi önle

            except Exception as exc:
                logger.debug("Dinleme döngüsü hatası: %s", exc)
                time.sleep(0.5)

    except ImportError:
        logger.warning("sounddevice veya faster-whisper yok — wake word devre dışı")


def start_wake_word(on_wake: Callable[[str], None]) -> bool:
    """Wake word dinlemeyi arka planda başlat.

    Args:
        on_wake: Wake word tespitinde çağrılacak fonksiyon (metin alır)

    Returns:
        True if başlatıldı
    """
    global _running, _thread, _callback
    if _thread and _thread.is_alive():
        return True

    _callback = on_wake
    _running = True
    _thread = threading.Thread(
        target=_listen_loop,
        args=(on_wake,),
        daemon=True,
        name="aria-wake-word",
    )
    _thread.start()
    return True


def stop_wake_word() -> None:
    global _running
    _running = False


def is_listening() -> bool:
    return _thread is not None and _thread.is_alive() and _running
