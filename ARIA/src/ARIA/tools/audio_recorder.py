"""Lokal ses kaydı — sounddevice ile Python tarafında kayıt yapar.

WKWebView (Tauri/macOS) getUserMedia kısıtlamasını bypass eder.
"""

from __future__ import annotations

import logging
import tempfile
import threading
import time
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

# Singleton model
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
    """Thread-safe ses kaydedici."""

    def __init__(self) -> None:
        self._frames: list[bytes] = []
        self._recording = False
        self._stream: Optional[object] = None

    def _reset(self) -> None:
        """State'i sıfırla."""
        self._recording = False
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        self._frames = []

    def start(self) -> dict:
        """Kaydı başlat."""
        if not AUDIO_AVAILABLE:
            return {"success": False, "error": "sounddevice yüklü değil"}

        # Önceki session varsa temizle
        if self._recording or self._stream:
            self._reset()

        self._frames = []
        self._recording = True

        def callback(indata, frames_count, time_info, status):
            if status:
                logger.debug("Ses durumu: %s", status)
            if self._recording:
                self._frames.append(bytes(indata))

        try:
            self._stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype=DTYPE,
                blocksize=1024,
                callback=callback,
            )
            self._stream.start()
            logger.info("Kayıt başladı")
            return {"success": True, "recording": True}
        except Exception as exc:
            self._reset()
            logger.error("Kayıt başlatılamadı: %s", exc)
            return {"success": False, "error": str(exc)}

    def stop_and_transcribe(self, language: str = "tr") -> dict:
        """Kaydı durdur, transkript et."""
        if not self._recording:
            # Zaten durdu, frames varsa transkript et
            if not self._frames:
                return {"success": False, "error": "Kayıt yapılmıyor", "transcript": ""}

        self._recording = False

        # Stream'i durdur
        if self._stream:
            try:
                self._stream.stop()
                time.sleep(0.1)  # Frame'lerin flush olmasını bekle
                self._stream.close()
            except Exception as exc:
                logger.warning("Stream kapatma hatası: %s", exc)
            self._stream = None

        frames = self._frames[:]
        self._frames = []

        if not frames:
            return {"success": False, "error": "Ses verisi yok (çok kısa kayıt?)", "transcript": ""}

        logger.info("Toplam frame: %d (~%.1f sn)", len(frames),
                    len(frames) * 1024 / SAMPLE_RATE)

        if not WHISPER_AVAILABLE:
            return {"success": False, "error": "faster-whisper yüklü değil", "transcript": ""}

        # WAV dosyasına yaz
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_path = tmp.name

            with wave.open(tmp_path, "wb") as wf:
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(2)
                wf.setframerate(SAMPLE_RATE)
                wf.writeframes(b"".join(frames))

            model = _get_model()
            segments, info = model.transcribe(  # type: ignore
                tmp_path,
                language=language,
                beam_size=5,
                vad_filter=False,        # VAD kapalı — kısa/sessiz kayıtları filtrelemesin
                no_speech_threshold=0.9, # çok yüksek threshold — neredeyse her şeyi kabul et
            )
            transcript = " ".join(seg.text.strip() for seg in segments).strip()
            logger.info("Transkript (%s): '%s'", info.language, transcript[:80])
            return {
                "success": True,
                "transcript": transcript,
                "language": info.language,
                "duration": round(info.duration, 1),
            }
        except Exception as exc:
            logger.error("Transkript hatası: %s", exc)
            return {"success": False, "error": str(exc), "transcript": ""}
        finally:
            if tmp_path:
                try:
                    Path(tmp_path).unlink(missing_ok=True)
                except Exception:
                    pass

    @property
    def is_recording(self) -> bool:
        return self._recording


# Global singleton
_recorder = AudioRecorder()


def get_recorder() -> AudioRecorder:
    return _recorder
