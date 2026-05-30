"""Sesli Not Günlüğü — konuş, transkript et, Obsidian daily note + dosyaya kaydet."""

from __future__ import annotations

import json
import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from ARIA.core.registry import register_tool

logger = logging.getLogger("aria.tools.voice_journal")

_ARIA_DIR = Path.home() / ".aria"
_JOURNAL_DIR = _ARIA_DIR / "journal"
_JOURNAL_DIR.mkdir(parents=True, exist_ok=True)


def _record_audio(duration_sec: int = 60, silence_stop: bool = True) -> Optional[object]:
    """Ses kaydet — sessizlik algılandığında veya süre dolunca dur."""
    try:
        import sounddevice as sd
        import numpy as np

        SAMPLE_RATE = 16_000
        CHUNK_SEC = 0.5
        CHUNK_SAMPLES = int(SAMPLE_RATE * CHUNK_SEC)
        SILENCE_THRESHOLD = 300
        MAX_SILENCE_SEC = 2.5
        MIN_SPEECH_SEC = 1.0

        frames = []
        silence_count = 0.0
        speech_count = 0.0
        total = 0.0

        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16") as stream:
            while total < duration_sec:
                chunk, _ = stream.read(CHUNK_SAMPLES)
                frames.append(chunk)
                rms = int((chunk.astype("float32") ** 2).mean() ** 0.5)

                if rms < SILENCE_THRESHOLD:
                    silence_count += CHUNK_SEC
                    if silence_stop and silence_count >= MAX_SILENCE_SEC and speech_count >= MIN_SPEECH_SEC:
                        break
                else:
                    silence_count = 0.0
                    speech_count += CHUNK_SEC

                total += CHUNK_SEC

        if not frames:
            return None
        return np.concatenate(frames, axis=0)
    except ImportError:
        raise RuntimeError("sounddevice kurulu değil")
    except Exception as exc:
        logger.error("Ses kaydı hatası: %s", exc)
        return None


def _transcribe(audio_np) -> str:
    """Whisper ile transkript et."""
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel("base", device="cpu", compute_type="int8")
        segs, _ = model.transcribe(audio_np.flatten().astype("float32"), language="tr", beam_size=2)
        return " ".join(s.text.strip() for s in segs).strip()
    except ImportError:
        raise RuntimeError("faster-whisper kurulu değil")


def _tts(text: str) -> None:
    try:
        from ARIA.tools.tts import speak
        speak(text, lang="tr", block=False)
    except Exception:
        pass


def _notify(title: str, msg: str) -> None:
    try:
        subprocess.run(
            ["osascript", "-e", f'display notification "{msg}" with title "{title}"'],
            capture_output=True, timeout=3,
        )
    except Exception:
        pass


@register_tool("journal_record")
def journal_record(
    title: str = "",
    duration_sec: int = 120,
    save_to_obsidian: bool = True,
    add_summary: bool = True,
) -> dict:
    """Sesli not al — konuş, transkript et, kaydet.

    Args:
        title: Girdi başlığı (boş = otomatik tarih)
        duration_sec: Maksimum kayıt süresi (sessizlik gelince erken biter)
        save_to_obsidian: Obsidian daily note'a ekle
        add_summary: LLM ile kısa özet üret

    Returns:
        {'success': bool, 'transcript': str, 'summary': str, 'file': str}
    """
    now = datetime.now()
    title = title or f"Günlük — {now.strftime('%d.%m.%Y %H:%M')}"

    _tts("Dinliyorum, konuşmaya başlayabilirsin.")
    _notify("ARIA Sesli Günlük", "Kayıt başladı — sessizlik algılandığında duracak")

    try:
        audio = _record_audio(duration_sec=duration_sec, silence_stop=True)
    except RuntimeError as exc:
        return {"success": False, "error": str(exc)}

    if audio is None:
        return {"success": False, "error": "Ses algılanamadı"}

    _notify("ARIA Sesli Günlük", "Transkript oluşturuluyor…")

    try:
        transcript = _transcribe(audio)
    except RuntimeError as exc:
        return {"success": False, "error": str(exc)}

    if not transcript.strip():
        return {"success": False, "error": "Transkript boş"}

    # LLM özeti
    summary = ""
    if add_summary:
        try:
            from ARIA.core.engine import ARIAEngine
            prompt = f"Aşağıdaki günlük notunu 2-3 cümle ile özetle:\n\n{transcript}"
            summary = ARIAEngine().chat([{"role": "user", "content": prompt}])
        except Exception as exc:
            logger.warning("Özet üretilemedi: %s", exc)

    # Dosyaya kaydet
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H-%M")
    file_path = _JOURNAL_DIR / f"{date_str}_{time_str}.md"

    content = f"# {title}\n\n**Tarih:** {now.strftime('%d.%m.%Y %H:%M')}\n\n"
    if summary:
        content += f"## Özet\n{summary}\n\n"
    content += f"## Transkript\n{transcript}\n"

    file_path.write_text(content, encoding="utf-8")

    # Obsidian daily note'a ekle
    obsidian_saved = False
    if save_to_obsidian:
        try:
            from ARIA.tools.obsidian import obsidian_append_daily
            short = summary or transcript[:150]
            result = obsidian_append_daily(f"**{title}:** {short}", heading="Sesli Notlar")
            obsidian_saved = result.get("success", False)
        except Exception as exc:
            logger.warning("Obsidian kaydı başarısız: %s", exc)

    _tts("Kaydedildi.")
    _notify("ARIA Sesli Günlük", f"'{title}' kaydedildi — {len(transcript.split())} kelime")

    return {
        "success": True,
        "title": title,
        "transcript": transcript,
        "summary": summary,
        "file": str(file_path),
        "obsidian_saved": obsidian_saved,
        "word_count": len(transcript.split()),
    }


@register_tool("journal_list")
def journal_list(limit: int = 10) -> dict:
    """Kayıtlı günlük notlarını listele.

    Returns:
        {'entries': list[dict]}
    """
    files = sorted(_JOURNAL_DIR.glob("*.md"), reverse=True)[:limit]
    entries = []
    for f in files:
        try:
            text = f.read_text(encoding="utf-8")
            lines = text.splitlines()
            title = lines[0].lstrip("#").strip() if lines else f.stem
            preview = next((l for l in lines[3:] if l.strip()), "")
            entries.append({"file": str(f), "title": title, "preview": preview[:100], "date": f.stem[:10]})
        except Exception:
            pass
    return {"entries": entries, "count": len(entries), "success": True}


@register_tool("journal_read")
def journal_read(date: Optional[str] = None, file_path: Optional[str] = None) -> dict:
    """Belirli bir günlük notunu oku.

    Args:
        date: YYYY-MM-DD formatında tarih
        file_path: Dosya yolu

    Returns:
        {'content': str, 'title': str}
    """
    if file_path:
        p = Path(file_path)
    elif date:
        matches = list(_JOURNAL_DIR.glob(f"{date}_*.md"))
        if not matches:
            return {"success": False, "error": f"{date} tarihli not bulunamadı"}
        p = matches[0]
    else:
        # En son not
        files = sorted(_JOURNAL_DIR.glob("*.md"), reverse=True)
        if not files:
            return {"success": False, "error": "Hiç not yok"}
        p = files[0]

    try:
        content = p.read_text(encoding="utf-8")
        lines = content.splitlines()
        title = lines[0].lstrip("#").strip() if lines else p.stem
        return {"success": True, "content": content, "title": title, "file": str(p)}
    except Exception as exc:
        return {"success": False, "error": str(exc)}
