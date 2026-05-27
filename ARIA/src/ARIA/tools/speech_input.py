"""Speech input tool — faster-whisper ile local STT, M4 Mac optimize."""

from __future__ import annotations

import logging
import queue
import tempfile
import threading
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("aria.tools.speech_input")

# ── Opsiyonel bağımlılıklar ──────────────────────────────────────────────────
try:
    import sounddevice as sd  # type: ignore
    import numpy as np  # type: ignore
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False
    logger.warning("sounddevice/numpy yüklü değil — ses girişi devre dışı")

try:
    from faster_whisper import WhisperModel  # type: ignore
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False
    logger.warning("faster-whisper yüklü değil — STT devre dışı")

# ── Sabitler ─────────────────────────────────────────────────────────────────
SAMPLE_RATE = 16_000          # Whisper 16 kHz ister
CHANNELS = 1
DTYPE = "int16"
SILENCE_THRESHOLD = 500       # RMS; bu değerin altı sessizlik sayılır
SILENCE_DURATION = 1.5        # saniye — bu kadar sessizlik varsa kayıt biter
DEFAULT_MODEL_SIZE = "base"   # tiny / base / small / medium / large
DEFAULT_LANGUAGE = "tr"


class SpeechInput:
    """Faster-Whisper tabanlı yerel konuşma-metne çevirici.

    Kullanım::

        stt = SpeechInput(model_size="base")
        text = stt.push_to_talk()        # boşluk tuşu basılı tutulurken kayıt
        text = stt.record_until_silence() # otomatik sessizlik tespiti
    """

    def __init__(
        self,
        model_size: str = DEFAULT_MODEL_SIZE,
        language: str = DEFAULT_LANGUAGE,
        device: str = "auto",
    ) -> None:
        self.model_size = model_size
        self.language = language
        self.device = device
        self._model: Optional[object] = None  # lazy yükle
        self._lock = threading.Lock()

    # ── Model yükleme ─────────────────────────────────────────────────────────

    def _load_model(self) -> None:
        """Modeli tembel yükle — ilk çağrıda bir kez yüklenir."""
        if not WHISPER_AVAILABLE:
            raise RuntimeError("faster-whisper yüklü değil: pip install faster-whisper")
        with self._lock:
            if self._model is None:
                compute_type = "int8"  # M4 CPU'da int8 hızlı
                logger.info("Whisper modeli yükleniyor: %s (%s)", self.model_size, compute_type)
                self._model = WhisperModel(  # type: ignore[attr-defined]
                    self.model_size,
                    device="cpu",
                    compute_type=compute_type,
                )
                logger.info("Whisper modeli hazır")

    # ── Ses kaydı yardımcıları ────────────────────────────────────────────────

    @staticmethod
    def _rms(data: "np.ndarray") -> float:  # type: ignore[name-defined]
        """RMS (ses yoğunluğu) hesapla."""
        return float(np.sqrt(np.mean(data.astype("float32") ** 2)))

    def _record_frames(self, max_seconds: float = 30.0) -> bytes:
        """Sessizlik tespiti ile ses kaydet ve PCM bytes döndür."""
        if not AUDIO_AVAILABLE:
            raise RuntimeError("sounddevice yüklü değil: pip install sounddevice")

        frames: list[bytes] = []
        q: queue.Queue[bytes] = queue.Queue()
        silence_start: list[Optional[float]] = [None]
        stop_event = threading.Event()

        def callback(indata: "np.ndarray", frames_count: int, time_info: object, status: object) -> None:  # noqa: ARG001
            data = indata.copy()
            q.put(data.tobytes())
            if _rms := self._rms(data) < SILENCE_THRESHOLD:  # noqa: F841
                if silence_start[0] is None:
                    silence_start[0] = time.time()
                elif time.time() - silence_start[0] >= SILENCE_DURATION:
                    stop_event.set()
            else:
                silence_start[0] = None

        with sd.InputStream(  # type: ignore[attr-defined]
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=DTYPE,
            callback=callback,
        ):
            deadline = time.time() + max_seconds
            while not stop_event.is_set() and time.time() < deadline:
                try:
                    frames.append(q.get(timeout=0.1))
                except queue.Empty:
                    continue

        # Kalan frame'leri al
        while not q.empty():
            frames.append(q.get_nowait())

        return b"".join(frames)

    def _save_wav(self, pcm_bytes: bytes) -> Path:
        """PCM bytes'ı geçici WAV dosyasına yaz."""
        import wave

        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        with wave.open(tmp.name, "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)  # int16 = 2 byte
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(pcm_bytes)
        return Path(tmp.name)

    def _transcribe(self, wav_path: Path) -> str:
        """WAV dosyasını metne çevir."""
        self._load_model()
        model = self._model
        segments, _info = model.transcribe(  # type: ignore[union-attr]
            str(wav_path),
            language=self.language,
            beam_size=5,
            vad_filter=True,
        )
        text = " ".join(seg.text for seg in segments).strip()
        wav_path.unlink(missing_ok=True)
        return text

    # ── Genel arayüz ──────────────────────────────────────────────────────────

    def push_to_talk(self, max_seconds: float = 30.0) -> str:
        """Tuş basılı tutulurken kayıt yapar gibi davranır.

        Bu implementasyonda max_seconds boyunca kayıt alır; sessizlik
        algılandığında otomatik olarak durur. Terminal bağlamında gerçek
        tuş algılama platforma bağlı olduğundan bu yöntem daha pratiktir.

        Returns:
            Tanınan metin; hata durumunda boş string.
        """
        if not AUDIO_AVAILABLE or not WHISPER_AVAILABLE:
            logger.error("Ses girişi mevcut değil (AUDIO_AVAILABLE=%s, WHISPER_AVAILABLE=%s)",
                         AUDIO_AVAILABLE, WHISPER_AVAILABLE)
            return ""
        try:
            logger.info("Kayıt başladı (maks. %.0f sn)...", max_seconds)
            pcm = self._record_frames(max_seconds=max_seconds)
            if not pcm:
                return ""
            wav = self._save_wav(pcm)
            text = self._transcribe(wav)
            logger.info("Tanınan: %s", text)
            return text
        except Exception as exc:
            logger.error("push_to_talk hatası: %s", exc)
            return ""

    def record_until_silence(self, max_seconds: float = 30.0) -> str:
        """Sessizlik algılanana dek kayıt yap ve metni döndür.

        Args:
            max_seconds: Maksimum kayıt süresi (saniye).

        Returns:
            Tanınan metin; hata durumunda boş string.
        """
        return self.push_to_talk(max_seconds=max_seconds)


# ── Modül düzeyinde yardımcı fonksiyon ───────────────────────────────────────

_default_stt: Optional[SpeechInput] = None


def get_stt(model_size: str = DEFAULT_MODEL_SIZE, language: str = DEFAULT_LANGUAGE) -> SpeechInput:
    """Singleton SpeechInput örneği döndür."""
    global _default_stt
    if _default_stt is None:
        _default_stt = SpeechInput(model_size=model_size, language=language)
    return _default_stt
