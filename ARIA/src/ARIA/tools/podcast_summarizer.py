"""YouTube/podcast ses indirme ve özetleme — yt-dlp + faster-whisper."""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

from ARIA.core.registry import register_tool

logger = logging.getLogger("aria.tools.podcast_summarizer")

# Availability flags
try:
    import yt_dlp
    YTDLP_AVAILABLE = True
except ImportError:
    YTDLP_AVAILABLE = False

try:
    from faster_whisper import WhisperModel
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False

_ARIA_MEDIA_DIR = Path.home() / ".aria" / "media"


def _download_audio(url: str, output_dir: Path) -> Optional[str]:
    """yt-dlp ile ses indir, dosya yolunu döndür."""
    if not YTDLP_AVAILABLE:
        return None

    output_dir.mkdir(parents=True, exist_ok=True)
    output_tmpl = str(output_dir / "%(id)s.%(ext)s")

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": output_tmpl,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "128",
        }],
        "quiet": True,
        "no_warnings": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            video_id = info.get("id", "unknown")
            # mp3 dosyasını bul
            for ext in ["mp3", "m4a", "webm", "ogg", "opus"]:
                candidate = output_dir / f"{video_id}.{ext}"
                if candidate.exists():
                    return str(candidate)
        # Herhangi bir ses dosyasını bul
        for f in output_dir.iterdir():
            if f.is_file() and f.suffix in {".mp3", ".m4a", ".webm", ".ogg", ".opus"}:
                return str(f)
        return None
    except Exception as exc:
        logger.error("yt-dlp indirme hatası: %s", exc)
        return None


def _transcribe_audio(audio_path: str) -> Optional[str]:
    """faster-whisper ile ses dosyasını transkript et."""
    if not WHISPER_AVAILABLE:
        return None

    try:
        model = WhisperModel("small", device="cpu", compute_type="int8")
        segments, info = model.transcribe(audio_path, beam_size=5)
        text_parts = []
        for segment in segments:
            text_parts.append(segment.text.strip())
        return " ".join(text_parts)
    except Exception as exc:
        logger.error("Transkript hatası: %s", exc)
        return None


def _summarize_transcript(transcript: str, url: str) -> str:
    """LLM ile transkripti özetle."""
    try:
        from ARIA.core.engine import ARIAEngine
        engine = ARIAEngine()

        # Transkripti 4000 karakterle sınırla
        limited = transcript[:4000]
        if len(transcript) > 4000:
            limited += f"\n\n[...devamı var, {len(transcript)} karakter toplam]"

        messages = [
            {
                "role": "system",
                "content": (
                    "Sen bir içerik özetleyicisin. Verilen transkripti Türkçe olarak "
                    "kapsamlı şekilde özetle. Ana noktaları, önemli bilgileri ve sonuçları "
                    "madde madde listele. Format: ## Özet, ### Ana Noktalar, ### Önemli Bilgiler"
                ),
            },
            {
                "role": "user",
                "content": f"Video/Podcast URL: {url}\n\nTranskript:\n{limited}\n\nÖzetle.",
            },
        ]
        return engine.chat(messages)
    except Exception as exc:
        return f"Özetleme hatası: {exc}"


@register_tool("summarize_video")
def summarize_video(url: str) -> dict:
    """YouTube/podcast videosunu indir, transkript çıkar ve özetle.

    Args:
        url: YouTube veya diğer desteklenen video URL'si.

    Returns:
        {'summary': str, 'transcript': str, 'success': bool}
    """
    if not YTDLP_AVAILABLE:
        return {
            "success": False,
            "error": "yt-dlp yüklü değil",
            "summary": "Video indirme devre dışı.",
        }

    # Ses indir
    audio_path = _download_audio(url, _ARIA_MEDIA_DIR)
    if not audio_path:
        return {
            "success": False,
            "error": "Ses indirilemedi",
            "summary": "Video indirme başarısız oldu.",
        }

    transcript = None
    summary = ""

    # Transkript çıkar
    if WHISPER_AVAILABLE:
        transcript = _transcribe_audio(audio_path)

    if transcript:
        summary = _summarize_transcript(transcript, url)
    else:
        # Whisper yoksa sadece URL ile özet dene
        try:
            from ARIA.core.engine import ARIAEngine
            engine = ARIAEngine()
            messages = [
                {"role": "system", "content": "Sen bir içerik analistsin."},
                {"role": "user", "content": f"Bu YouTube/podcast URL'si hakkında ne biliyorsun? {url}\n(Transkript mevcut değil, genel bilgi ver)"},
            ]
            summary = engine.chat(messages)
        except Exception as exc:
            summary = f"Whisper mevcut değil. Manuel transkript gerekiyor. (yt-dlp ile ses indirildi: {audio_path})"

    # Geçici dosyayı temizle
    try:
        if audio_path and Path(audio_path).exists():
            os.unlink(audio_path)
    except Exception:
        pass

    return {
        "success": True,
        "summary": summary,
        "transcript": (transcript[:1000] + "...") if transcript and len(transcript) > 1000 else (transcript or ""),
        "whisper_used": WHISPER_AVAILABLE,
    }
