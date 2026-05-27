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


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    """aria-api entry point (pyproject.toml scripts)."""
    import uvicorn
    uvicorn.run("ARIA.api:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    main()
