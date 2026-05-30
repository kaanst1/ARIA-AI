# ARIA - FastAPI Backend

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, File, Header, HTTPException, UploadFile, status as http_status
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

    # Clipboard geçmişi izleme başlat
    try:
        from ARIA.tools.clipboard_history import start_monitor as _start_clipboard
        _start_clipboard()
    except Exception as exc:
        logger.warning("Clipboard monitor başlatılamadı: %s", exc)

    # Workflow scheduler başlat
    try:
        from ARIA.automation.workflow_engine import ensure_default_workflows, start_workflow_scheduler
        ensure_default_workflows()
        start_workflow_scheduler()
        logger.info("Workflow scheduler başlatıldı")
    except Exception as exc:
        logger.warning("Workflow scheduler başlatılamadı: %s", exc)

    # Wake word dinlemeyi başlat
    try:
        config = load_config()
        if getattr(config, "enable_speech_input", False):
            from ARIA.tools.wake_word import start_wake_word
            from ARIA.orchestrator.router import Orchestrator
            _orch = Orchestrator()
            def _on_wake(text: str):
                logger.info("Wake word tetiklendi: %s", text)
                try:
                    _orch.dispatch("hey aria ne önerirsin")
                except Exception:
                    pass
            start_wake_word(_on_wake)
            logger.info("Wake word dinleme başlatıldı")
    except Exception as exc:
        logger.warning("Wake word başlatılamadı: %s", exc)

    # Global hotkey başlat (Cmd+Shift+Space → ARIA'yı aç)
    try:
        from ARIA.tools.global_hotkey import start_global_hotkey
        start_global_hotkey()
        logger.info("Global hotkey başlatıldı: Cmd+Shift+Space")
    except Exception as exc:
        logger.warning("Global hotkey başlatılamadı: %s", exc)

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


# ── Config endpoint'leri ─────────────────────────────────────────────────────

class WeatherCityRequest(BaseModel):
    city: str


@app.post("/config/weather-city")
async def set_weather_city(req: WeatherCityRequest, x_api_key: str | None = Header(default=None)):
    """Hava durumu şehrini güncelle."""
    _check_auth(x_api_key)
    try:
        from ARIA.core.config import load_config, save_config
        config = load_config()
        config.weather_city = req.city.strip()
        save_config(config)
        return {"success": True, "weather_city": config.weather_city}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/config/weather-city")
async def get_weather_city(x_api_key: str | None = Header(default=None)):
    """Mevcut hava durumu şehrini döndür."""
    _check_auth(x_api_key)
    try:
        from ARIA.core.config import load_config
        config = load_config()
        return {"weather_city": getattr(config, "weather_city", "Ankara")}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Reminders endpoint'leri ──────────────────────────────────────────────────

class ReminderAddRequest(BaseModel):
    title: str
    due_date: Optional[str] = None   # "YYYY-MM-DD"
    due_time: Optional[str] = None   # "HH:MM"
    notes: str = ""
    list_name: str = "Reminders"


@app.post("/reminders")
async def reminders_add(req: ReminderAddRequest, x_api_key: str | None = Header(default=None)):
    """Apple Reminders'a yeni hatırlatıcı ekle."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.reminders import add_reminder
        result = add_reminder(
            title=req.title,
            due_date=req.due_date,
            due_time=req.due_time,
            notes=req.notes,
            list_name=req.list_name,
        )
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Hatırlatıcı eklenemedi"))
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/reminders")
async def reminders_list(
    list_name: Optional[str] = None,
    completed: bool = False,
    x_api_key: str | None = Header(default=None),
):
    """Apple Reminders'dan hatırlatıcıları listele."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.reminders import get_reminders
        items = get_reminders(list_name=list_name, completed=completed)
        return {"reminders": items, "count": len(items)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Spotify endpoint'leri ────────────────────────────────────────────────────

class SpotifyPlayRequest(BaseModel):
    query: Optional[str] = None


class SpotifyVolumeRequest(BaseModel):
    level: int  # 0-100


@app.post("/spotify/play")
async def spotify_play_endpoint(req: SpotifyPlayRequest, x_api_key: str | None = Header(default=None)):
    """Spotify'da çal (query varsa ara ve çal)."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.spotify_control import spotify_play
        return spotify_play(query=req.query)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/spotify/pause")
async def spotify_pause_endpoint(x_api_key: str | None = Header(default=None)):
    """Spotify'ı duraklat."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.spotify_control import spotify_pause
        return spotify_pause()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/spotify/next")
async def spotify_next_endpoint(x_api_key: str | None = Header(default=None)):
    """Spotify'da sonraki şarkı."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.spotify_control import spotify_next
        return spotify_next()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/spotify/previous")
async def spotify_previous_endpoint(x_api_key: str | None = Header(default=None)):
    """Spotify'da önceki şarkı."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.spotify_control import spotify_previous
        return spotify_previous()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/spotify/current")
async def spotify_current_endpoint(x_api_key: str | None = Header(default=None)):
    """Spotify'da şu an çalan şarkının bilgisi."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.spotify_control import spotify_current
        return spotify_current()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/spotify/volume")
async def spotify_volume_endpoint(req: SpotifyVolumeRequest, x_api_key: str | None = Header(default=None)):
    """Spotify ses seviyesini ayarla."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.spotify_control import spotify_volume
        return spotify_volume(level=req.level)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Ekran analizi endpoint'leri ──────────────────────────────────────────────

class ScreenAnalyzeRequest(BaseModel):
    question: str = "Ekranda ne var?"


@app.post("/screen/analyze")
async def screen_analyze_endpoint(req: ScreenAnalyzeRequest, x_api_key: str | None = Header(default=None)):
    """Ekranı yakala ve LLM vision ile analiz et."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.screen_capture import analyze_screen
        result = analyze_screen(question=req.question)
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Analiz başarısız"))
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/screen/capture")
async def screen_capture_endpoint(x_api_key: str | None = Header(default=None)):
    """Sadece ekran görüntüsü al (analiz yok), dosya olarak döndür."""
    _check_auth(x_api_key)
    import os as _os
    from fastapi.responses import FileResponse
    try:
        from ARIA.tools.screen_capture import capture_screen
        result = capture_screen()
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Ekran yakalanamadı"))
        path = result["path"]
        return FileResponse(
            path,
            media_type="image/png",
            filename="aria_screen.png",
            background=None,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Mail endpoint'leri ───────────────────────────────────────────────────────

class MailSendRequest(BaseModel):
    to: str
    subject: str
    body: str


@app.post("/mail/send")
async def mail_send_endpoint(req: MailSendRequest, x_api_key: str | None = Header(default=None)):
    """Apple Mail üzerinden e-posta gönder."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.mail_control import send_email
        result = send_email(to=req.to, subject=req.subject, body=req.body)
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "E-posta gönderilemedi"))
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/mail/unread")
async def mail_unread_endpoint(
    count: int = 5,
    x_api_key: str | None = Header(default=None),
):
    """Apple Mail'den okunmamış e-postaları listele."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.mail_control import get_unread_emails
        emails = get_unread_emails(count=count)
        return {"emails": emails, "count": len(emails)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Ses döngüsü (voice round-trip) endpoint'i ────────────────────────────────

@app.post("/speech/chat")
async def speech_chat_endpoint(x_api_key: str | None = Header(default=None)):
    """Single-shot sesli komut: kayıt → transkript → chat → seslendir.

    5 saniye kayıt alır, transkript eder, ARIA'ya gönderir, cevabı seslendirir.
    """
    _check_auth(x_api_key)
    import asyncio

    try:
        from ARIA.tools.audio_recorder import get_recorder, AUDIO_AVAILABLE
        if not AUDIO_AVAILABLE:
            raise HTTPException(status_code=501, detail="sounddevice yüklü değil")

        recorder = get_recorder()

        # Kaydı başlat
        start_result = recorder.start()
        if not start_result.get("success"):
            raise HTTPException(status_code=500, detail=start_result.get("error", "Kayıt başlatılamadı"))

        # 5 saniye bekle
        await asyncio.sleep(5)

        # Kaydı durdur ve transkript et
        stop_result = recorder.stop_and_transcribe(language="tr")
        transcript = stop_result.get("transcript", "").strip()

        if not transcript:
            return {
                "success": False,
                "transcript": "",
                "response": "Ses algılanamadı, lütfen tekrar dene.",
                "agent": "chat",
            }

        # Chat'e gönder
        try:
            from ARIA.tools.summarizer import summarize_text
            reduced = summarize_text(transcript)
        except Exception:
            reduced = transcript

        route = orchestrator.route(reduced)
        agent_name = route.get("agent", "chat")

        response_text = ""
        for token in engine.stream_chat([{"role": "user", "content": reduced}]):
            response_text += token

        # Seslendir
        try:
            from ARIA.tools.tts import speak
            speak(response_text, lang="tr", block=False)
        except Exception as exc:
            logger.warning("TTS hatası: %s", exc)

        return {
            "success": True,
            "transcript": transcript,
            "response": response_text,
            "agent": agent_name,
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Hava Durumu ───────────────────────────────────────────────────────────────

@app.get("/weather")
async def weather_current_endpoint(city: str | None = None, x_api_key: str | None = Header(default=None)):
    """Anlık hava durumu."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.weather import weather_current
        return weather_current(city)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/weather/forecast")
async def weather_forecast_endpoint(city: str | None = None, days: int = 3, x_api_key: str | None = Header(default=None)):
    """Hava tahmini (1-3 gün)."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.weather import weather_forecast
        return weather_forecast(city, days=min(days, 3))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Apple Notes ───────────────────────────────────────────────────────────────

class NoteCreate(BaseModel):
    title: str
    body: str
    folder: str = "Notes"


@app.post("/notes")
async def notes_create_endpoint(note: NoteCreate, x_api_key: str | None = Header(default=None)):
    """Yeni Apple Not oluştur."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.notes import notes_create
        return notes_create(note.title, note.body, note.folder)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/notes")
async def notes_list_endpoint(folder: str = "Notes", limit: int = 10, x_api_key: str | None = Header(default=None)):
    """Apple Notes listesi."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.notes import notes_list
        return notes_list(folder, limit)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/notes/search")
async def notes_search_endpoint(q: str, x_api_key: str | None = Header(default=None)):
    """Apple Notes'ta arama yap."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.notes import notes_search
        return notes_search(q)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Uygulama Kontrolü ─────────────────────────────────────────────────────────

class AppRequest(BaseModel):
    app_name: str


@app.post("/app/open")
async def app_open_endpoint(req: AppRequest, x_api_key: str | None = Header(default=None)):
    """macOS uygulaması aç."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.app_control import app_open
        return app_open(req.app_name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/app/quit")
async def app_quit_endpoint(req: AppRequest, x_api_key: str | None = Header(default=None)):
    """macOS uygulaması kapat."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.app_control import app_quit
        return app_quit(req.app_name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/app/running")
async def app_running_endpoint(x_api_key: str | None = Header(default=None)):
    """Çalışan uygulamaları listele."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.app_control import app_list_running
        return app_list_running()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Kişiler ───────────────────────────────────────────────────────────────────

@app.get("/contacts/search")
async def contacts_search_endpoint(q: str, x_api_key: str | None = Header(default=None)):
    """Rehberde kişi ara."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.contacts import contacts_search
        return contacts_search(q)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Odak Modu ─────────────────────────────────────────────────────────────────

class FocusRequest(BaseModel):
    mode: str = "Do Not Disturb"


@app.post("/focus/enable")
async def focus_enable_endpoint(req: FocusRequest, x_api_key: str | None = Header(default=None)):
    """Odak modunu etkinleştir."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.focus_mode import focus_enable
        return focus_enable(req.mode)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/focus/disable")
async def focus_disable_endpoint(x_api_key: str | None = Header(default=None)):
    """Odak modunu devre dışı bırak."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.focus_mode import focus_disable
        return focus_disable()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/focus/status")
async def focus_status_endpoint(x_api_key: str | None = Header(default=None)):
    """Odak modu durumunu öğren."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.focus_mode import focus_status
        return focus_status()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Tarayıcı Kontrolü ────────────────────────────────────────────────────────

class BrowserOpenRequest(BaseModel):
    url: str
    browser: str | None = None


class BrowserSearchRequest(BaseModel):
    query: str
    engine: str = "google"


@app.post("/browser/open")
async def browser_open_endpoint(req: BrowserOpenRequest, x_api_key: str | None = Header(default=None)):
    """Tarayıcıda URL aç."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.browser_control import browser_open_url
        return browser_open_url(req.url, req.browser)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/browser/current")
async def browser_current_tab_endpoint(browser: str | None = None, x_api_key: str | None = Header(default=None)):
    """Aktif tarayıcı sekmesini getir."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.browser_control import browser_get_current_tab
        return browser_get_current_tab(browser)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/browser/search")
async def browser_search_endpoint(req: BrowserSearchRequest, x_api_key: str | None = Header(default=None)):
    """Tarayıcıda arama yap."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.browser_control import browser_search
        return browser_search(req.query, req.engine)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Spotlight Arama ───────────────────────────────────────────────────────────

@app.get("/spotlight/search")
async def spotlight_search_endpoint(
    q: str,
    kind: str | None = None,
    limit: int = 10,
    x_api_key: str | None = Header(default=None),
):
    """Spotlight ile dosya ara."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.spotlight_search import spotlight_search
        return spotlight_search(q, kind=kind, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Clipboard Geçmişi ────────────────────────────────────────────────────────

@app.get("/clipboard/history")
async def clipboard_history_endpoint(limit: int = 20, x_api_key: str | None = Header(default=None)):
    """Clipboard geçmişini getir."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.clipboard_history import clipboard_history_get
        return clipboard_history_get(limit)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.delete("/clipboard/history")
async def clipboard_history_clear_endpoint(x_api_key: str | None = Header(default=None)):
    """Clipboard geçmişini temizle."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.clipboard_history import clipboard_history_clear
        return clipboard_history_clear()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/clipboard/history/search")
async def clipboard_history_search_endpoint(q: str, x_api_key: str | None = Header(default=None)):
    """Clipboard geçmişinde arama yap."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.clipboard_history import clipboard_history_search
        return clipboard_history_search(q)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Sohbet Geçmişi Export ─────────────────────────────────────────────────────

@app.get("/sessions/{session_id}/export")
async def session_export(session_id: int, x_api_key: str | None = Header(default=None)):
    """Sohbet geçmişini JSON olarak dışa aktar."""
    _check_auth(x_api_key)
    try:
        from ARIA.memory.conversation_store import ConversationStore
        store = ConversationStore()
        messages = store.get_context_messages(session_id, n=1000)
        return {
            "session_id": session_id,
            "message_count": len(messages),
            "messages": messages,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Workflow Motoru ───────────────────────────────────────────────────────────

class WorkflowCreate(BaseModel):
    name: str
    description: str = ""
    trigger: dict
    steps: list[dict]


@app.get("/workflows")
async def workflows_list(x_api_key: str | None = Header(default=None)):
    """Tanımlı workflow'ları listele."""
    _check_auth(x_api_key)
    try:
        from ARIA.automation.workflow_engine import load_workflows
        wfs = load_workflows()
        return {"workflows": [{
            "name": w.get("name"), "description": w.get("description", ""),
            "trigger": w.get("trigger", {}), "steps": len(w.get("steps", [])),
        } for w in wfs], "count": len(wfs)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/workflows")
async def workflow_create(wf: WorkflowCreate, x_api_key: str | None = Header(default=None)):
    """Yeni workflow oluştur."""
    _check_auth(x_api_key)
    try:
        from ARIA.automation.workflow_engine import save_workflow
        path = save_workflow(wf.model_dump())
        return {"success": True, "name": wf.name, "path": str(path)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/workflows/{name}/run")
async def workflow_run(name: str, x_api_key: str | None = Header(default=None)):
    """Workflow'u elle tetikle."""
    _check_auth(x_api_key)
    try:
        from ARIA.automation.workflow_engine import load_workflows, run_workflow
        wfs = {w.get("name"): w for w in load_workflows()}
        if name not in wfs:
            raise HTTPException(status_code=404, detail=f"Workflow bulunamadı: {name}")
        results = run_workflow(wfs[name])
        return {"name": name, "results": results}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.delete("/workflows/{name}")
async def workflow_delete(name: str, x_api_key: str | None = Header(default=None)):
    """Workflow'u sil."""
    _check_auth(x_api_key)
    try:
        from ARIA.automation.workflow_engine import delete_workflow
        ok = delete_workflow(name)
        return {"success": ok, "name": name}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Belge Q&A (RAG) ───────────────────────────────────────────────────────────

class DocumentQueryRequest(BaseModel):
    question: str
    file_name: str | None = None


@app.post("/documents/index")
async def document_index_endpoint(file_path: str, x_api_key: str | None = Header(default=None)):
    """Belgeyi RAG için indeksle."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.document_qa import document_index
        return document_index(file_path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/documents/query")
async def document_query_endpoint(req: DocumentQueryRequest, x_api_key: str | None = Header(default=None)):
    """İndekslenmiş belgelerden soruya cevap al."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.document_qa import document_query
        return document_query(req.question, req.file_name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/documents")
async def document_list_endpoint(x_api_key: str | None = Header(default=None)):
    """İndekslenmiş belgeleri listele."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.document_qa import document_list
        return document_list()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/documents/upload")
async def document_upload_endpoint(
    file: UploadFile = File(...),
    x_api_key: str | None = Header(default=None),
):
    """Frontend'den dosya yükle ve indeksle."""
    _check_auth(x_api_key)
    import tempfile, os
    from pathlib import Path
    allowed_exts = {".pdf", ".txt", ".md", ".csv", ".docx", ".json"}
    ext = Path(file.filename or "").suffix.lower()
    if ext not in allowed_exts:
        raise HTTPException(status_code=400, detail=f"Desteklenmeyen format: {ext}")
    try:
        content = await file.read()
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False, prefix="aria_upload_") as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        from ARIA.tools.document_qa import document_index
        result = document_index(tmp_path)
        os.unlink(tmp_path)
        result["original_filename"] = file.filename
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Hafıza ────────────────────────────────────────────────────────────────────

class MemoryAddRequest(BaseModel):
    text: str
    category: str = "genel"


@app.post("/memory")
async def memory_add_endpoint(req: MemoryAddRequest, x_api_key: str | None = Header(default=None)):
    """Semantik hafızaya not ekle."""
    _check_auth(x_api_key)
    try:
        from ARIA.memory.semantic_context import remember_fact
        ok = remember_fact(req.text, req.category)
        return {"success": ok}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/memory/search")
async def memory_search_endpoint(q: str, n: int = 5, x_api_key: str | None = Header(default=None)):
    """Semantik hafızada ara."""
    _check_auth(x_api_key)
    try:
        from ARIA.memory.vector_memory import memory_search
        return {"results": memory_search(q, n=n)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Email Zekası ──────────────────────────────────────────────────────────────

class EmailClassifyRequest(BaseModel):
    subject: str
    body: str
    sender: str = ""


class EmailDraftRequest(BaseModel):
    subject: str
    body: str
    sender: str
    tone: str = "profesyonel"


@app.post("/email/classify")
async def email_classify_endpoint(req: EmailClassifyRequest, x_api_key: str | None = Header(default=None)):
    """Maili sınıflandır ve öncelik belirle."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.email_intelligence import email_classify
        return email_classify(req.subject, req.body, req.sender)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/email/draft")
async def email_draft_endpoint(req: EmailDraftRequest, x_api_key: str | None = Header(default=None)):
    """Maile otomatik yanıt taslağı üret."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.email_intelligence import email_draft_reply
        return email_draft_reply(req.subject, req.body, req.sender, req.tone)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/email/smart-inbox")
async def smart_inbox_endpoint(count: int = 10, x_api_key: str | None = Header(default=None)):
    """Okunmamış mailleri akıllıca özetle ve önceliklendir."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.mail_control import get_unread_emails
        from ARIA.tools.email_intelligence import email_summarize
        raw = get_unread_emails(count)
        emails = raw if isinstance(raw, list) else []
        return email_summarize(emails)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Analitik ──────────────────────────────────────────────────────────────────

@app.get("/analytics/usage")
async def analytics_usage(x_api_key: str | None = Header(default=None)):
    """Kullanım istatistiklerini döndür."""
    _check_auth(x_api_key)
    try:
        import json
        from pathlib import Path
        tracker_file = Path.home() / ".aria" / "usage.json"
        if not tracker_file.exists():
            return {"agent_counts": {}, "total_messages": 0, "sessions": []}
        data = json.loads(tracker_file.read_text())

        # Son 7 günlük trend
        from datetime import datetime, timedelta
        cutoff = (datetime.now() - timedelta(days=7)).isoformat()
        recent = [s for s in data.get("sessions", []) if s.get("timestamp", "") >= cutoff]

        # Saatlik dağılım
        hourly = {}
        for s in recent:
            h = str(s.get("hour", 0))
            hourly[h] = hourly.get(h, 0) + 1

        # En aktif ajan
        top_agent = max(data.get("agent_counts", {}).items(), key=lambda x: x[1], default=("chat", 0))

        return {
            "total_messages": data.get("total_messages", 0),
            "agent_counts": data.get("agent_counts", {}),
            "last_7_days": len(recent),
            "hourly_distribution": hourly,
            "top_agent": {"name": top_agent[0], "count": top_agent[1]},
            "sessions": recent[-20:],
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/analytics/patterns")
async def analytics_patterns(x_api_key: str | None = Header(default=None)):
    """Kullanım pattern'larını döndür."""
    _check_auth(x_api_key)
    try:
        import json
        from pathlib import Path
        patterns_file = Path.home() / ".aria" / "patterns.json"
        if not patterns_file.exists():
            return {"patterns": {}}
        return json.loads(patterns_file.read_text())
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Akıllı Model Durumu ───────────────────────────────────────────────────────

@app.get("/models/smart-select")
async def smart_select_endpoint(query: str, x_api_key: str | None = Header(default=None)):
    """Sorgu için hangi modelin seçileceğini göster."""
    _check_auth(x_api_key)
    try:
        from ARIA.core.smart_router import classify_complexity, select_model
        models = engine.list_models()
        complexity = classify_complexity(query)
        selected = select_model(query, models, engine.config.model)
        return {"query": query, "complexity": complexity, "selected_model": selected, "available": models}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Pomodoro ─────────────────────────────────────────────────────────────────

class PomodoroStartRequest(BaseModel):
    work_minutes: int = 25
    break_minutes: int = 5
    long_break_minutes: int = 15
    cycles: int = 4


@app.post("/pomodoro/start")
async def pomodoro_start_endpoint(req: PomodoroStartRequest, x_api_key: str | None = Header(default=None)):
    """Pomodoro başlat."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.pomodoro import pomodoro_start
        return pomodoro_start(req.work_minutes, req.break_minutes, req.long_break_minutes, req.cycles)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/pomodoro/stop")
async def pomodoro_stop_endpoint(x_api_key: str | None = Header(default=None)):
    """Pomodoro durdur."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.pomodoro import pomodoro_stop
        return pomodoro_stop()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/pomodoro/status")
async def pomodoro_status_endpoint(x_api_key: str | None = Header(default=None)):
    """Pomodoro durumu."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.pomodoro import pomodoro_status
        return pomodoro_status()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── iMessage ─────────────────────────────────────────────────────────────────

class IMessageSendRequest(BaseModel):
    recipient: str
    message: str


@app.post("/imessage/send")
async def imessage_send_endpoint(req: IMessageSendRequest, x_api_key: str | None = Header(default=None)):
    """iMessage gönder."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.imessage import imessage_send
        return imessage_send(req.recipient, req.message)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/imessage/unread")
async def imessage_unread_endpoint(limit: int = 5, x_api_key: str | None = Header(default=None)):
    """Okunmamış iMessage'ları getir."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.imessage import imessage_get_unread
        return imessage_get_unread(limit)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Git Zekası ────────────────────────────────────────────────────────────────

@app.get("/git/log")
async def git_log_endpoint(path: str | None = None, count: int = 10, x_api_key: str | None = Header(default=None)):
    """Git commit geçmişini özetle."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.git_intelligence import git_log_summary
        return git_log_summary(path, count)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/git/status")
async def git_status_endpoint(path: str | None = None, x_api_key: str | None = Header(default=None)):
    """Git durumu."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.git_intelligence import git_status_summary
        return git_status_summary(path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/git/todos")
async def git_todos_endpoint(path: str | None = None, x_api_key: str | None = Header(default=None)):
    """TODO/FIXME tara."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.git_intelligence import git_todo_scan
        return git_todo_scan(path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Rapor ─────────────────────────────────────────────────────────────────────

@app.post("/reports/weekly")
async def weekly_report_endpoint(x_api_key: str | None = Header(default=None)):
    """Haftalık rapor üret."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.weekly_report import generate_weekly_report
        return generate_weekly_report(save=True)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/reports/list")
async def reports_list_endpoint(limit: int = 10, x_api_key: str | None = Header(default=None)):
    """Kayıtlı raporları listele."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.weekly_report import list_reports
        return list_reports(limit)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Apple Health ──────────────────────────────────────────────────────────────

@app.get("/health/summary")
async def health_summary_endpoint(x_api_key: str | None = Header(default=None)):
    """Sağlık özeti."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.health import health_summary
        return health_summary()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/health/steps")
async def health_steps_endpoint(days: int = 7, x_api_key: str | None = Header(default=None)):
    """Adım sayısı verisi."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.health import health_get_steps
        return health_get_steps(days)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Bağlam Farkındalığı ───────────────────────────────────────────────────────

@app.get("/context/suggest")
async def context_suggest_endpoint(x_api_key: str | None = Header(default=None)):
    """Mevcut bağlama göre öneri üret."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.context_awareness import context_suggest
        return context_suggest()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/context/frontmost-app")
async def context_app_endpoint(x_api_key: str | None = Header(default=None)):
    """Ön plandaki uygulamayı döndür."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.context_awareness import context_get_frontmost_app
        return context_get_frontmost_app()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/context/upcoming-meetings")
async def context_meetings_endpoint(minutes: int = 30, x_api_key: str | None = Header(default=None)):
    """Yaklaşan toplantıları döndür."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.context_awareness import context_upcoming_meetings
        return context_upcoming_meetings(minutes)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Wake Word Kontrolü ────────────────────────────────────────────────────────

@app.get("/wake-word/status")
async def wake_word_status_endpoint(x_api_key: str | None = Header(default=None)):
    """Wake word dinleme durumu."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.wake_word import is_listening
        return {"listening": is_listening()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Tam Konfigürasyon API'si ──────────────────────────────────────────────────

class ConfigUpdateRequest(BaseModel):
    model: str | None = None
    language: str | None = None
    tts_voice: str | None = None
    enable_tts: bool | None = None
    weather_city: str | None = None
    enable_speech_input: bool | None = None
    notification_enabled: bool | None = None
    conversation_history_limit: int | None = None
    temperature: float | None = None
    max_tokens: int | None = None


@app.get("/config")
async def config_get(x_api_key: str | None = Header(default=None)):
    """Tüm konfigürasyonu döndür."""
    _check_auth(x_api_key)
    try:
        from ARIA.core.config import load_config
        cfg = load_config()
        return {
            "model": cfg.model,
            "language": cfg.language,
            "tts_voice": cfg.tts_voice,
            "enable_tts": cfg.enable_tts,
            "weather_city": cfg.weather_city,
            "enable_speech_input": cfg.enable_speech_input,
            "notification_enabled": cfg.notification_enabled,
            "conversation_history_limit": cfg.conversation_history_limit,
            "temperature": cfg.temperature,
            "max_tokens": cfg.max_tokens,
            "cloud_fallback": cfg.cloud_fallback,
            "telemetry": cfg.telemetry,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.patch("/config")
async def config_update(req: ConfigUpdateRequest, x_api_key: str | None = Header(default=None)):
    """Konfigürasyonu güncelle (sadece verilen alanlar değişir)."""
    _check_auth(x_api_key)
    try:
        from ARIA.core.config import load_config, save_config
        cfg = load_config()
        updates = req.model_dump(exclude_none=True)
        for key, val in updates.items():
            if hasattr(cfg, key):
                setattr(cfg, key, val)
        save_config(cfg)
        return {"success": True, "updated": list(updates.keys())}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Voice Mode ───────────────────────────────────────────────────────────────

@app.post("/voice/start")
async def voice_start(x_api_key: str | None = Header(default=None)):
    """Sürekli ses konuşma modunu başlat."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.voice_mode import start_voice_mode
        return start_voice_mode()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/voice/stop")
async def voice_stop(x_api_key: str | None = Header(default=None)):
    """Voice mode'u durdur."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.voice_mode import stop_voice_mode
        return stop_voice_mode()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/voice/status")
async def voice_status(x_api_key: str | None = Header(default=None)):
    """Voice mode durumu."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.voice_mode import is_voice_active
        return {"active": is_voice_active()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Agent Zinciri ─────────────────────────────────────────────────────────────

class ChainRequest(BaseModel):
    message: str
    session_id: int | None = None


@app.post("/chain")
async def chain_run(req: ChainRequest, x_api_key: str | None = Header(default=None)):
    """Çok-ajan zinciri çalıştır."""
    _check_auth(x_api_key)
    try:
        from ARIA.agents.chain import run_chain
        result = run_chain(req.message)
        return {
            "success": result.success,
            "description": result.description,
            "final_output": result.final_output,
            "steps": [
                {"agent": s.agent, "task": s.task[:100], "success": s.success, "result": s.result[:500]}
                for s in result.steps
            ],
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Toplantı Asistanı ─────────────────────────────────────────────────────────

class MeetingStartRequest(BaseModel):
    title: str = ""


@app.post("/meeting/start")
async def meeting_start_endpoint(req: MeetingStartRequest, x_api_key: str | None = Header(default=None)):
    """Toplantı kaydını başlat."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.meeting_assistant import meeting_start
        return meeting_start(req.title)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/meeting/stop")
async def meeting_stop_endpoint(x_api_key: str | None = Header(default=None)):
    """Toplantıyı durdur, özet üret."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.meeting_assistant import meeting_stop
        return meeting_stop(save_to_notes=True)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/meeting/status")
async def meeting_status_endpoint(x_api_key: str | None = Header(default=None)):
    """Aktif toplantı durumu."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.meeting_assistant import meeting_status
        return meeting_status()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/meeting/list")
async def meeting_list_endpoint(limit: int = 10, x_api_key: str | None = Header(default=None)):
    """Kayıtlı toplantıları listele."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.meeting_assistant import meeting_list
        return meeting_list(limit)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Obsidian ─────────────────────────────────────────────────────────────────

class ObsidianNoteRequest(BaseModel):
    title: str
    content: str
    folder: str = ""
    tags: list[str] = []
    open_after: bool = False


class ObsidianDailyRequest(BaseModel):
    content: str
    heading: str = ""


class ObsidianSetupRequest(BaseModel):
    vault_path: str


@app.get("/obsidian/info")
async def obsidian_info(x_api_key: str | None = Header(default=None)):
    """Obsidian vault bilgisi."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.obsidian import obsidian_vault_info
        return obsidian_vault_info()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/obsidian/setup")
async def obsidian_setup_endpoint(req: ObsidianSetupRequest, x_api_key: str | None = Header(default=None)):
    """Obsidian vault yolunu ayarla."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.obsidian import obsidian_setup
        return obsidian_setup(req.vault_path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/obsidian/note")
async def obsidian_create_note_endpoint(req: ObsidianNoteRequest, x_api_key: str | None = Header(default=None)):
    """Obsidian'da yeni not oluştur."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.obsidian import obsidian_create_note
        return obsidian_create_note(req.title, req.content, req.folder, req.tags, req.open_after)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/obsidian/daily")
async def obsidian_daily_endpoint(req: ObsidianDailyRequest, x_api_key: str | None = Header(default=None)):
    """Daily note'a içerik ekle."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.obsidian import obsidian_append_daily
        return obsidian_append_daily(req.content, req.heading)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/obsidian/search")
async def obsidian_search_endpoint(q: str, limit: int = 10, x_api_key: str | None = Header(default=None)):
    """Obsidian vault'ta ara."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.obsidian import obsidian_search
        return obsidian_search(q, limit)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/obsidian/note")
async def obsidian_get_note_endpoint(title: str, x_api_key: str | None = Header(default=None)):
    """Obsidian notunu getir."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.obsidian import obsidian_get_note
        return obsidian_get_note(title)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Keychain ──────────────────────────────────────────────────────────────────

class KeychainSetRequest(BaseModel):
    key: str
    value: str
    account: str = "aria"


@app.post("/keychain/set")
async def keychain_set_endpoint(req: KeychainSetRequest, x_api_key: str | None = Header(default=None)):
    """Keychain'e güvenli değer kaydet."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.keychain import keychain_set
        return keychain_set(req.key, req.value, req.account)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/keychain/get")
async def keychain_get_endpoint(key: str, account: str = "aria", x_api_key: str | None = Header(default=None)):
    """Keychain'den değer oku."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.keychain import keychain_get
        return keychain_get(key, account)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.delete("/keychain/{key}")
async def keychain_delete_endpoint(key: str, account: str = "aria", x_api_key: str | None = Header(default=None)):
    """Keychain'den sil."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.keychain import keychain_delete
        return keychain_delete(key, account)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/keychain/list")
async def keychain_list_endpoint(x_api_key: str | None = Header(default=None)):
    """Kayıtlı anahtarları listele."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.keychain import keychain_list
        return keychain_list()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── iOS Shortcut Bridge ───────────────────────────────────────────────────────

class ShortcutRequest(BaseModel):
    message: str
    agent: str | None = None
    voice_response: bool = False  # TTS ile de seslendir
    format: str = "text"          # "text" | "json" | "brief"


@app.post("/shortcut")
async def shortcut_endpoint(req: ShortcutRequest, x_api_key: str | None = Header(default=None)):
    """iOS Shortcuts için optimize edilmiş basit endpoint.

    Siri Shortcut'tan çağrılmak üzere tasarlanmıştır.
    Yanıt her zaman düz metin veya kısa JSON döndürür.
    """
    _check_auth(x_api_key)
    try:
        response_text = orchestrator.dispatch(req.message)

        if req.voice_response:
            try:
                from ARIA.tools.tts import speak
                speak(response_text, lang="tr", block=False)
            except Exception:
                pass

        if req.format == "brief":
            # 280 karakter — tweet/bildirim boyutu
            return {"response": response_text[:280]}
        elif req.format == "json":
            return {"message": req.message, "response": response_text}
        else:
            # Düz metin — Shortcuts'ta en kolay
            from fastapi.responses import PlainTextResponse
            return PlainTextResponse(response_text)

    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/shortcut/brief")
async def shortcut_brief(x_api_key: str | None = Header(default=None)):
    """iOS Widget için sabah briefi — düz metin."""
    _check_auth(x_api_key)
    try:
        from ARIA.agents.brief import BriefAgent
        brief = BriefAgent().run(speak=False)
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(brief)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/shortcut/weather")
async def shortcut_weather(x_api_key: str | None = Header(default=None)):
    """iOS Widget için hava durumu — tek satır."""
    _check_auth(x_api_key)
    try:
        from ARIA.tools.weather import weather_current
        d = weather_current()
        if d.get("success"):
            text = f"{d['city']}: {d['temp_c']}°C, {d['desc']}"
        else:
            text = "Hava durumu alınamadı"
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(text)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    """aria-api entry point (pyproject.toml scripts)."""
    import uvicorn
    uvicorn.run("ARIA.api:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    main()
