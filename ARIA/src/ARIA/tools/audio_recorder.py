"""Lokal ses kaydı — sounddevice ile Python tarafında kayıt yapar.

WKWebView (Tauri/macOS) getUserMedia kısıtlamasını bypass eder.
Tüm ses işleme Python'da, hiçbir şey dışarıya çıkmaz.
"""

from __future__ import annotations

import logging
import tempfile
import threading
import wave
from pathlib import Path
from typing import Optional

logger = logging.getLogger("aria.tools.audio_recorder")

try:
    import sounddevice as sd
    import numpy as np
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False
    logger.warning("sounddevice/numpy yüklü değil")

try:
    from faster_whisper import WhisperModel
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False
    logger.warning("faster-whisper yüklü değil")

SAMPLE_RATE = 16_000
CHANNELS = 1
DTYPE = "int16"

# Singleton model — ilk çağrıda yüklenir
_model: Optional[object] = None
_model_lock = threading.Lock()


def _get_model() -> object:
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                logger.info("Whisper modeli yükleniyor (base, int8)...")
                _model = WhisperModel("base", device="cpu", compute_type="int8")
                logger.info("Whisper hazır")
    return _model


class AudioRecorder:
    """Thread-safe ses kaydedici — start/stop API'si."""

    def __init__(self) -> None:
        self._frames: list[bytes] = []
        self._recording = False
        self._stream: Optional[object] = None
        self._lock = threading.Lock()

    def start(self) -> dict:
        """Kaydı başlat."""
        if not AUDIO_AVAILABLE:
            return {"success": False, "error": "sounddevice yüklü değil"}
        with self._lock:
            if self._recording:
                return {"success": False, "error": "Zaten kayıt yapılıyor"}
            self._frames = []
            self._recording = True

        def callback(indata, frames, time_info, status):  # noqa: ARG001
            if self._recording:
                self._frames.append(indata.copy().tobytes())

        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=DTYPE,
            callback=callback,
        )
        self._stream.start()
        logger.info("Kayıt başladı")
        return {"success": True, "recording": True}

    def stop_and_transcribe(self, language: str = "tr") -> dict:
        """Kaydı durdur, transkript et, sonucu döndür."""
        with self._lock:
            if not self._recording:
                return {"success": False, "error": "Kayıt yapılmıyor"}
            self._recording = False

        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        if not self._frames:
            return {"success": False, "error": "Ses verisi yok", "transcript": ""}

        # WAV dosyasına yaz
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        try:
            with wave.open(tmp.name, "wb") as wf:
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(2)  # int16 = 2 byte
                wf.setframerate(SAMPLE_RATE)
                wf.writeframes(b"".join(self._frames))

            if not WHISPER_AVAILABLE:
                return {"success": False, "error": "faster-whisper yüklü değil", "transcript": ""}

            model = _get_model()
            segments, info = model.transcribe(  # type: ignore
                tmp.name,
                language=language,
                beam_size=5,
                vad_filter=True,
            )
            transcript = " ".join(seg.text.strip() for seg in segments).strip()
            logger.info("Transkript: %s", transcript[:80])
            return {
                "success": True,
                "transcript": transcript,
                "language": info.language,
                "duration": info.duration,
            }
        except Exception as exc:
            logger.error("Transkript hatası: %s", exc)
            return {"success": False, "error": str(exc), "transcript": ""}
        finally:
            try:
                Path(tmp.name).unlink(missing_ok=True)
            except Exception:
                pass

    @property
    def is_recording(self) -> bool:
        return self._recording


# Global singleton recorder
_recorder = AudioRecorder()


def get_recorder() -> AudioRecorder:
    return _recorder
