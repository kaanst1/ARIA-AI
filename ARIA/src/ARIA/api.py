# ARIA - FastAPI Backend

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, status as http_status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ARIA.core.config import load_config
from ARIA.core.engine import ARIAEngine
from ARIA.core.logging_setup import configure_logging
from ARIA.orchestrator.router import Orchestrator
from ARIA.telemetry.metrics import track_latency

configure_logging()
logger = logging.getLogger("aria.api")


# ── Uygulama yaşam döngüsü ────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(_app: FastAPI):
    config = load_config()
    if config.warmup_on_start:
        try:
            _warmup_engine = ARIAEngine(config)
            _warmup_engine.chat([{"role": "user", "content": config.warmup_message}])
            logger.info("ARIA warm-up tamam")
        except Exception as exc:
            logger.warning("Warm-up hatası: %s", exc)

    # ProactiveScheduler'ı başlat
    try:
        from ARIA.scheduler.proactive import ProactiveScheduler
        _scheduler = ProactiveScheduler()
        _scheduler.start_background()
        logger.info("ProactiveScheduler başlatıldı")
    except Exception as exc:
        logger.warning("ProactiveScheduler başlatılamadı: %s", exc)

    yield


app = FastAPI(title="ARIA API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

orchestrator = Orchestrator()
engine = ARIAEngine()


# ── Auth ──────────────────────────────────────────────────────────────────────

def _check_auth(x_api_key: str | None) -> None:
    config = load_config()
    if not config.require_auth:
        return
    if not config.api_key or x_api_key != config.api_key:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="Geçersiz API anahtarı",
        )


# ── Modeller ─────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    """Chat isteği."""
    message: str
    agent: str = "chat"
    speak: bool = False
    session_id: Optional[int] = None


class ChatResponse(BaseModel):
    """Chat yanıtı."""
    response: str
    agent: str


class SessionCreateRequest(BaseModel):
    """Oturum oluşturma isteği."""
    title: str = "Yeni Sohbet"


# ── Oturum endpoint'leri ──────────────────────────────────────────────────────

@app.get("/sessions")
async def list_sessions(x_api_key: str | None = Header(default=None)):
    """Tüm sohbet oturumlarını listele."""
    _check_auth(x_api_key)
    try:
        from ARIA.memory.conversation_store import ConversationStore
        store = ConversationStore()
        return store.list_sessions()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/sessions")
async def create_session(
    req: SessionCreateRequest,
    x_api_key: str | None = Header(default=None),
):
    """Yeni sohbet oturumu oluştur."""
    _check_auth(x_api_key)
    try:
        from ARIA.memory.conversation_store import ConversationStore
        store = ConversationStore()
        session_id = store.new_session(req.title)
        session = store.get_session(session_id)
        return session
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/sessions/{session_id}")
async def get_session_messages(
    session_id: int,
    x_api_key: str | None = Header(default=None),
):
    """Bir oturumun mesajlarını döndür."""
    _check_auth(x_api_key)
    try:
        from ARIA.memory.conversation_store import ConversationStore
        store = ConversationStore()
        session = store.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Oturum bulunamadı")
        messages = store.get_messages(session_id)
        return {"session": session, "messages": messages}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.delete("/sessions/{session_id}")
async def delete_session(
    session_id: int,
    x_api_key: str | None = Header(default=None),
):
    """Oturumu ve mesajlarını sil."""
    _check_auth(x_api_key)
    try:
        from ARIA.memory.conversation_store import ConversationStore
        store = ConversationStore()
        deleted = store.delete_session(session_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Oturum bulunamadı")
        return {"deleted": session_id}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Chat endpoint'leri ────────────────────────────────────────────────────────

@app.post("/chat/stream")
async def chat_stream(req: ChatRequest, x_api_key: str | None = Header(default=None)):
    """Orchestrator üzerinden routing yapıp streaming cevap döner."""
    _check_auth(x_api_key)
    from ARIA.tools.summarizer import summarize_text

    reduced = summarize_text(req.message)
    route = orchestrator.route(reduced)
    agent_name = route.get("agent", req.agent)

    # Oturum işlemleri
    session_id = req.session_id
    store = None
    try:
        from ARIA.memory.conversation_store import ConversationStore
        store = ConversationStore()
        if session_id is None:
            session_id = store.new_session(req.message[:60])
        store.add_message(session_id, "user", req.message, agent=agent_name)
    except Exception as exc:
        logger.warning("Mesaj kaydedilemedi (user): %s", exc)
        store = None

    full_response: list[str] = []

    def event_stream():
        try:
            for token in engine.stream_chat([{"role": "user", "content": reduced}]):
                full_response.append(token)
                yield f"data: {token}\n\n"
        except Exception as exc:
            yield f"data: [error] {exc}\n\n"
        finally:
            # Stream bitti — assistant mesajını kaydet
            if store is not None and session_id is not None:
                try:
                    complete = "".join(full_response)
                    store.add_message(session_id, "assistant", complete, agent=agent_name)
                except Exception as exc:
                    logger.warning("Mesaj kaydedilemedi (assistant): %s", exc)

    logger.info("stream ajan: %s", agent_name)
    headers = {"X-ARIA-Agent": agent_name}
    if session_id is not None:
        headers["X-Session-ID"] = str(session_id)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers=headers,
    )


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, x_api_key: str | None = Header(default=None)):
    """Tam (non-streaming) chat yanıtı döner."""
    _check_auth(x_api_key)
    from ARIA.tools.summarizer import summarize_text

    metrics: dict = {}
    try:
        with track_latency(metrics, "total_ms"):
            reduced = summarize_text(req.message)
            response, route = orchestrator.dispatch_with_route(
                reduced, session_id=req.session_id
            )
            agent_name = route.get("agent", req.agent)
    except Exception as exc:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )

    # Mesajları kaydet
    if req.session_id is not None:
        try:
            from ARIA.memory.conversation_store import ConversationStore
            store = ConversationStore()
            store.add_message(req.session_id, "user", req.message, agent=agent_name)
            store.add_message(req.session_id, "assistant", response, agent=agent_name)
        except Exception as exc:
            logger.warning("Mesaj kaydedilemedi: %s", exc)

    if req.speak:
        from ARIA.tools.tts import speak_text
        try:
            speak_text(response)
        except Exception as exc:
            logger.warning("TTS hatası: %s", exc)

    if metrics:
        logger.info("chat metrics: %s", metrics)

    return ChatResponse(response=response, agent=agent_name)


# ── OpenAI uyumlu endpoint ────────────────────────────────────────────────────

@app.post("/v1/chat/completions")
async def openai_chat(payload: dict, x_api_key: str | None = Header(default=None)):
    """OpenAI uyumlu chat completions endpoint."""
    _check_auth(x_api_key)
    messages = payload.get("messages", [])
    if not messages:
        raise HTTPException(status_code=400, detail="messages gerekli")

    try:
        response = engine.chat(messages)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return {
        "id": "chatcmpl-local",
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": response},
                "finish_reason": "stop",
            }
        ],
    }


# ── Durum ve sistem bilgisi ───────────────────────────────────────────────────

@app.get("/status")
async def get_status(x_api_key: str | None = Header(default=None)):
    """ARIA ve sistem durumunu döndür."""
    _check_auth(x_api_key)
    base_status = ARIAEngine().doctor()

    # Sistem istatistiklerini ekle
    try:
        from ARIA.tools.system_monitor import get_system_stats, PSUTIL_AVAILABLE
        if PSUTIL_AVAILABLE:
            sys_stats = get_system_stats()
            base_status["system"] = {
                "cpu_percent": sys_stats["cpu"].get("percent"),
                "ram_used_gb": sys_stats["memory"].get("used_gb"),
                "ram_total_gb": sys_stats["memory"].get("total_gb"),
                "ram_percent": sys_stats["memory"].get("percent"),
                "disk_percent": sys_stats["disk"].get("percent"),
                "ollama_running": sys_stats["ollama"].get("running"),
                "ollama_ram_mb": sys_stats["ollama"].get("total_rss_mb"),
            }
    except Exception as exc:
        logger.warning("Sistem istatistikleri alınamadı: %s", exc)

    return base_status


# ── Diğer endpoint'ler ────────────────────────────────────────────────────────

@app.get("/presets")
async def presets(x_api_key: str | None = Header(default=None)):
    _check_auth(x_api_key)
    from ARIA.core.presets import list_presets
    return {"presets": list_presets()}


@app.post("/presets/apply")
async def apply_preset(payload: dict, x_api_key: str | None = Header(default=None)):
    _check_auth(x_api_key)
    from ARIA.core.presets import apply_preset
    name = payload.get("name", "")
    if not name:
        raise HTTPException(status_code=400, detail="Preset adı gerekli")
    config = apply_preset(name)
    return {"applied": name, "config": config.__dict__}


@app.get("/hardware")
async def hardware(x_api_key: str | None = Header(default=None)):
    _check_auth(x_api_key)
    from ARIA.engine.selector import detect_hardware
    return detect_hardware()


@app.get("/models")
async def models(x_api_key: str | None = Header(default=None)):
    _check_auth(x_api_key)
    from ARIA.engine.selector import list_models
    return {"models": list_models()}


# ── Yeni endpoint'ler ─────────────────────────────────────────────────────────

from fastapi import UploadFile, File, Query
import tempfile
import os


@app.post("/speech/record/start")
async def speech_record_start(x_api_key: str | None = Header(default=None)):
    """Python tarafında mikrofon kaydını başlat (Tauri/WKWebView uyumlu)."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.audio_recorder import get_recorder
        result = get_recorder().start()
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/speech/record/stop")
async def speech_record_stop(
    language: str = "tr",
    x_api_key: str | None = Header(default=None),
):
    """Kaydı durdur ve transkript et."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.audio_recorder import get_recorder
        result = get_recorder().stop_and_transcribe(language=language)
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/speech/record/status")
async def speech_record_status(x_api_key: str | None = Header(default=None)):
    """Kayıt durumunu döndür."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.audio_recorder import get_recorder, AUDIO_AVAILABLE, WHISPER_AVAILABLE
        return {
            "recording": get_recorder().is_recording,
            "audio_available": AUDIO_AVAILABLE,
            "whisper_available": WHISPER_AVAILABLE,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/speech/transcribe")
async def speech_transcribe(
    file: UploadFile = File(...),
    x_api_key: str | None = Header(default=None),
):
    """Ses dosyasını transkript et (faster-whisper ile)."""
    _check_auth(x_api_key)
    try:
        from faster_whisper import WhisperModel
        WHISPER_OK = True
    except ImportError:
        WHISPER_OK = False

    if not WHISPER_OK:
        raise HTTPException(status_code=501, detail="faster-whisper yüklü değil")

    # Geçici dosyaya kaydet
    suffix = os.path.splitext(file.filename or "audio.wav")[1] or ".wav"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        from faster_whisper import WhisperModel
        model = WhisperModel("small", device="cpu", compute_type="int8")
        segments, info = model.transcribe(tmp_path, beam_size=5)
        transcript = " ".join(seg.text.strip() for seg in segments)
        return {
            "transcript": transcript,
            "language": info.language,
            "duration": info.duration,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


@app.post("/file/analyze")
async def file_analyze(
    file: UploadFile = File(...),
    x_api_key: str | None = Header(default=None),
):
    """Dosyayı yükle ve içeriğini analiz et."""
    _check_auth(x_api_key)
    content_bytes = await file.read()
    filename = file.filename or "file"

    # Metin olarak çözümle
    try:
        text_content = content_bytes.decode("utf-8", errors="replace")
    except Exception:
        raise HTTPException(status_code=400, detail="Dosya metin olarak okunamadı")

    # 50KB limit
    if len(text_content) > 50 * 1024:
        text_content = text_content[:50 * 1024] + "\n\n[...dosya kesildi, max 50KB]"

    try:
        prompt = (
            f"Dosya adı: {filename}\n\n"
            f"İçerik:\n{text_content[:3000]}\n\n"
            "Bu dosyayı analiz et: içerik, yapı, önemli bilgiler ve özet."
        )
        response = engine.chat([{"role": "user", "content": prompt}])
        return {"filename": filename, "analysis": response, "size": len(content_bytes)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/system/stats")
async def system_stats(x_api_key: str | None = Header(default=None)):
    """Detaylı sistem istatistikleri."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.system_monitor import get_system_stats, PSUTIL_AVAILABLE
        if not PSUTIL_AVAILABLE:
            raise HTTPException(status_code=501, detail="psutil yüklü değil")
        return get_system_stats()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/feeds")
async def list_feeds(x_api_key: str | None = Header(default=None)):
    """Kayıtlı RSS feed'lerini listele."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.rss_reader import _feed_manager
        return {"feeds": _feed_manager.list_feeds()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


class FeedAddRequest(BaseModel):
    name: str
    url: str


@app.post("/feeds")
async def add_feed(req: FeedAddRequest, x_api_key: str | None = Header(default=None)):
    """Yeni RSS feed ekle."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.rss_reader import _feed_manager
        _feed_manager.add_feed(req.name, req.url)
        return {"success": True, "name": req.name, "url": req.url}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/files/search")
async def files_search(
    q: str = Query(..., description="Arama sorgusu"),
    x_api_key: str | None = Header(default=None),
):
    """Dosya sistemi indexinde arama yap."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.file_index import search_files
        results = search_files(q)
        return {"query": q, "results": results, "count": len(results)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/clipboard/analyze")
async def clipboard_analyze(x_api_key: str | None = Header(default=None)):
    """Panoyu oku ve analiz et."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.clipboard import clipboard_read
        result = clipboard_read()
        if not result["success"] or not result["content"].strip():
            return {"analysis": "Pano boş veya okunamadı", "content": ""}

        content = result["content"]
        prompt = f"Panodaki içeriği analiz et ve özetle:\n\n{content[:3000]}"
        analysis = engine.chat([{"role": "user", "content": prompt}])
        return {"content": content[:500], "analysis": analysis}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/reports/daily")
async def daily_report(x_api_key: str | None = Header(default=None)):
    """Son günlük raporu döndür."""
    _check_auth(x_api_key)
    try:
        from ARIA.scheduler.proactive import ProactiveScheduler
        scheduler = ProactiveScheduler()
        report = scheduler.get_daily_report()
        if not report:
            return {"report": "Henüz günlük rapor oluşturulmadı.", "available": False}
        return {"report": report, "available": True}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


class CalendarAddRequest(BaseModel):
    title: str
    date: str
    time: str
    duration_minutes: int = 60


@app.post("/calendar/add")
async def calendar_add(req: CalendarAddRequest, x_api_key: str | None = Header(default=None)):
    """Apple Calendar'a etkinlik ekle."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.calendar_tools import add_event
        result = add_event(req.title, req.date, req.time, req.duration_minutes)
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── TTS endpoint'leri ────────────────────────────────────────────────────────

class SpeakRequest(BaseModel):
    text: str
    lang: Optional[str] = None  # None → otomatik tespit


@app.post("/speak")
async def speak_endpoint(req: SpeakRequest, x_api_key: str | None = Header(default=None)):
    """Metni Yelda (TR) veya Samantha (EN) ile seslendir."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.tts import speak
        speak(req.text, lang=req.lang, block=False)
        return {"success": True, "speaking": True}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/speak/stop")
async def speak_stop(x_api_key: str | None = Header(default=None)):
    """Aktif sesi durdur."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.tts import stop_speaking
        stop_speaking()
        return {"success": True, "speaking": False}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/speak/status")
async def speak_status(x_api_key: str | None = Header(default=None)):
    """Konuşma durumunu döndür."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.tts import is_speaking
        return {"speaking": is_speaking()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── WhatsApp endpoint'leri ───────────────────────────────────────────────────

class WhatsAppSendRequest(BaseModel):
    contact: str          # İsim veya telefon numarası
    message: str
    use_phone: bool = False  # True → URL scheme (numara), False → UI otomasyon (isim)


@app.post("/whatsapp/send")
async def whatsapp_send(req: WhatsAppSendRequest, x_api_key: str | None = Header(default=None)):
    """WhatsApp mesajı gönder."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.whatsapp_control import send_via_url_scheme, send_via_ui
        if req.use_phone:
            result = send_via_url_scheme(req.contact, req.message)
        else:
            result = send_via_ui(req.contact, req.message)
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/whatsapp/status")
async def whatsapp_status_endpoint(x_api_key: str | None = Header(default=None)):
    """WhatsApp durumunu kontrol et."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.whatsapp_control import whatsapp_status
        return whatsapp_status()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Brief endpoint'leri ─────────────────────────────────────────────────────

@app.post("/brief/morning")
async def morning_brief_endpoint(x_api_key: str | None = Header(default=None)):
    """Sabah briefini üret ve Yelda ile seslendir.

    Alarm tarafından otomatik tetiklenir. Frontend'den de çağrılabilir.
    """
    _check_auth(x_api_key)
    try:
        from ARIA.agents.brief import BriefAgent
        agent = BriefAgent()
        brief_text = agent.run(speak=True)
        return {"success": True, "brief": brief_text}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/brief/calendar")
async def calendar_today_endpoint(x_api_key: str | None = Header(default=None)):
    """Bugünkü takvim etkinliklerini döndür."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.calendar_tools import get_today_events, get_week_events, format_today_events
        today = get_today_events()
        week = get_week_events()
        formatted = format_today_events()
        return {
            "today": today,
            "week": week,
            "formatted": formatted,
            "today_count": len(today),
            "week_count": len(week),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Alarm endpoint'leri ─────────────────────────────────────────────────────

class AlarmSetRequest(BaseModel):
    time_str: str              # "10:00", "10", "22:30"
    message: str = "Alarm vakti!"


class TimerSetRequest(BaseModel):
    minutes: int
    message: str = "Süre doldu!"


@app.post("/alarm")
async def alarm_set(req: AlarmSetRequest, x_api_key: str | None = Header(default=None)):
    """Belirtilen saatte alarm kur."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.alarm import set_alarm
        result = set_alarm(req.time_str, req.message)
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "Alarm kurulamadı"))
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/timer")
async def timer_set(req: TimerSetRequest, x_api_key: str | None = Header(default=None)):
    """N dakika sonra alarm kur."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.alarm import set_timer
        result = set_timer(req.minutes, req.message)
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "Timer kurulamadı"))
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/alarms")
async def alarms_list(x_api_key: str | None = Header(default=None)):
    """Kurulu at alarm'larını listele."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.alarm import list_alarms
        return list_alarms()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.delete("/alarm/{job_id}")
async def alarm_cancel(job_id: int, x_api_key: str | None = Header(default=None)):
    """at alarm'ını iptal et."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.alarm import cancel_alarm
        result = cancel_alarm(job_id)
        if not result.get("success"):
            raise HTTPException(status_code=400, detail="Alarm iptal edilemedi")
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    """aria-api entry point (pyproject.toml scripts)."""
    import uvicorn
    uvicorn.run("ARIA.api:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    main()
