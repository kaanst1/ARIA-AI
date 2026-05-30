"""Toplantı Asistanı — transkript, özet, aksiyon maddeleri, Notes'a kayıt."""

from __future__ import annotations

import json
import logging
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from ARIA.core.registry import register_tool

logger = logging.getLogger("aria.tools.meeting")

_ARIA_DIR = Path.home() / ".aria"
_MEETINGS_DIR = _ARIA_DIR / "meetings"
_MEETINGS_DIR.mkdir(parents=True, exist_ok=True)

_active_meeting: Optional[dict] = None
_transcript_thread: Optional[threading.Thread] = None
_transcript_chunks: list[str] = []
_recording = False


def _transcribe_chunk(audio_np) -> str:
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel("base", device="cpu", compute_type="int8")
        segs, _ = model.transcribe(
            audio_np.flatten().astype("float32"),
            language="tr",
            beam_size=1,
            vad_filter=True,
        )
        return " ".join(s.text for s in segs).strip()
    except Exception as exc:
        logger.debug("Chunk transkript hatası: %s", exc)
        return ""


def _record_loop(meeting_id: str) -> None:
    global _recording, _transcript_chunks
    try:
        import sounddevice as sd
        import numpy as np

        SAMPLE_RATE = 16_000
        CHUNK_SEC = 15  # Her 15 saniyede transkript

        logger.info("Toplantı kaydı başladı: %s", meeting_id)
        while _recording:
            audio = sd.rec(
                int(CHUNK_SEC * SAMPLE_RATE),
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="int16",
            )
            sd.wait()
            if not _recording:
                break
            text = _transcribe_chunk(audio)
            if text:
                ts = datetime.now().strftime("%H:%M")
                chunk = f"[{ts}] {text}"
                _transcript_chunks.append(chunk)
                logger.debug("Transkript: %s", chunk)

    except ImportError:
        logger.warning("sounddevice yüklü değil — transkript devre dışı")
    except Exception as exc:
        logger.error("Kayıt döngüsü hatası: %s", exc)


def _generate_summary(transcript: str, title: str) -> dict:
    """LLM ile toplantı özeti + aksiyon maddeleri üret."""
    prompt = f"""Aşağıdaki toplantı transkriptini analiz et ve Türkçe yanıt ver.

Toplantı: {title}
Transkript:
{transcript[:4000]}

Şu formatta yanıt ver:
ÖZET: [3-5 cümle toplantı özeti]
KARARLAR: [Alınan kararlar, madde madde]
AKSİYONLAR: [Yapılacaklar listesi, sorumlu kişi varsa belirt]
ÖNEMLİ_NOTLAR: [Dikkat edilmesi gereken önemli noktalar]"""

    try:
        from ARIA.core.engine import ARIAEngine
        raw = ARIAEngine().chat([{"role": "user", "content": prompt}])
        result = {"raw": raw}

        # Parse et
        for section in ["ÖZET", "KARARLAR", "AKSİYONLAR", "ÖNEMLİ_NOTLAR"]:
            if f"{section}:" in raw:
                content = raw.split(f"{section}:")[1]
                next_section = None
                for s in ["ÖZET", "KARARLAR", "AKSİYONLAR", "ÖNEMLİ_NOTLAR"]:
                    if s != section and f"{s}:" in content:
                        next_section = content.index(f"{s}:")
                        break
                result[section.lower()] = content[:next_section].strip() if next_section else content.strip()

        return result
    except Exception as exc:
        logger.error("Özet üretilemedi: %s", exc)
        return {"raw": "Özet üretilemedi", "özet": "Hata"}


def _save_to_notes(title: str, content: str) -> bool:
    """Apple Notes'a kaydet."""
    try:
        safe_title = title.replace('"', '\\"')
        safe_content = content.replace('"', '\\"').replace("\n", "\\n")
        script = f'''
tell application "Notes"
    tell account "iCloud"
        make new note at folder "Notes" with properties {{name:"{safe_title}", body:"{safe_content}"}}
    end tell
end tell
'''
        subprocess.run(["osascript", "-e", script], capture_output=True, timeout=15)
        return True
    except Exception as exc:
        logger.warning("Notes kaydı başarısız: %s", exc)
        return False


@register_tool("meeting_start")
def meeting_start(title: str = "") -> dict:
    """Toplantı kaydını başlat (transkript + zaman damgası).

    Args:
        title: Toplantı başlığı

    Returns:
        {'success': bool, 'meeting_id': str, 'title': str}
    """
    global _active_meeting, _transcript_thread, _transcript_chunks, _recording

    if _recording:
        return {"success": False, "error": "Toplantı zaten kaydediliyor"}

    meeting_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    title = title or f"Toplantı {datetime.now().strftime('%d.%m.%Y %H:%M')}"

    _active_meeting = {
        "id": meeting_id,
        "title": title,
        "started_at": datetime.now().isoformat(),
        "transcript_file": str(_MEETINGS_DIR / f"{meeting_id}.json"),
    }
    _transcript_chunks = []
    _recording = True

    _transcript_thread = threading.Thread(
        target=_record_loop,
        args=(meeting_id,),
        daemon=True,
        name=f"aria-meeting-{meeting_id}",
    )
    _transcript_thread.start()

    # macOS bildirimi
    subprocess.run(
        ["osascript", "-e", f'display notification "Kayıt başladı" with title "ARIA Toplantı: {title}"'],
        capture_output=True, timeout=5,
    )

    logger.info("Toplantı başladı: %s (%s)", title, meeting_id)
    return {"success": True, "meeting_id": meeting_id, "title": title}


@register_tool("meeting_stop")
def meeting_stop(save_to_notes: bool = True) -> dict:
    """Toplantıyı durdur, özet üret ve kaydet.

    Returns:
        {'success': bool, 'summary': dict, 'transcript_lines': int, 'notes_saved': bool}
    """
    global _recording, _active_meeting, _transcript_chunks

    if not _recording or not _active_meeting:
        return {"success": False, "error": "Aktif toplantı yok"}

    _recording = False
    time.sleep(1)  # Son chunk'ın bitmesini bekle

    meeting = _active_meeting.copy()
    transcript_lines = len(_transcript_chunks)
    full_transcript = "\n".join(_transcript_chunks)

    # Özet üret
    summary = _generate_summary(full_transcript, meeting["title"])

    # Dosyaya kaydet
    meeting_data = {
        **meeting,
        "ended_at": datetime.now().isoformat(),
        "transcript": _transcript_chunks,
        "summary": summary,
    }
    Path(meeting["transcript_file"]).write_text(
        json.dumps(meeting_data, ensure_ascii=False, indent=2)
    )

    # Notes'a kaydet
    notes_saved = False
    if save_to_notes:
        note_content = f"Toplantı: {meeting['title']}\nTarih: {meeting['started_at'][:10]}\n\n"
        note_content += summary.get("raw", "")
        note_content += f"\n\n--- TRANSKRIPT ---\n{full_transcript}"
        notes_saved = _save_to_notes(f"Toplantı: {meeting['title']}", note_content)

    # Bildirim
    subprocess.run(
        ["osascript", "-e", f'display notification "{transcript_lines} satır transkript" with title "ARIA Toplantı Tamamlandı"'],
        capture_output=True, timeout=5,
    )

    _active_meeting = None
    _transcript_chunks = []

    return {
        "success": True,
        "meeting_id": meeting["id"],
        "title": meeting["title"],
        "transcript_lines": transcript_lines,
        "summary": summary,
        "notes_saved": notes_saved,
        "file": meeting["transcript_file"],
    }


@register_tool("meeting_status")
def meeting_status() -> dict:
    """Aktif toplantı durumunu döndür.

    Returns:
        {'active': bool, 'title': str, 'transcript_lines': int}
    """
    return {
        "active": _recording,
        "title": _active_meeting.get("title", "") if _active_meeting else "",
        "transcript_lines": len(_transcript_chunks),
        "meeting_id": _active_meeting.get("id", "") if _active_meeting else "",
        "success": True,
    }


@register_tool("meeting_list")
def meeting_list(limit: int = 10) -> dict:
    """Kayıtlı toplantıları listele.

    Returns:
        {'meetings': list[dict]}
    """
    files = sorted(_MEETINGS_DIR.glob("*.json"), reverse=True)[:limit]
    meetings = []
    for f in files:
        try:
            data = json.loads(f.read_text())
            meetings.append({
                "id": data.get("id"),
                "title": data.get("title"),
                "date": data.get("started_at", "")[:10],
                "transcript_lines": len(data.get("transcript", [])),
                "file": str(f),
            })
        except Exception:
            pass
    return {"meetings": meetings, "count": len(meetings), "success": True}
