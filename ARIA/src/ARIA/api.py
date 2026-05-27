# ARIA - FastAPI Backend

from fastapi import FastAPI, Header, HTTPException, status as http_status
from contextlib import asynccontextmanager
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from ARIA.orchestrator.router import Orchestrator
from ARIA.core.logging_setup import configure_logging
import logging
from ARIA.core.config import load_config
from ARIA.core.engine import ARIAEngine
from ARIA.telemetry.metrics import track_latency

configure_logging()
logger = logging.getLogger("aria.api")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    config = load_config()
    if config.warmup_on_start:
        try:
            # Global engine henüz bağlanmamış olabilir; doğrudan instance kullan
            _warmup_engine = ARIAEngine(config)
            _warmup_engine.chat([{"role": "user", "content": config.warmup_message}])
            logger.info("ARIA warm-up tamam")
        except Exception as exc:
            logger.warning("Warm-up hatasi: %s", exc)
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


def _check_auth(x_api_key: str | None) -> None:
    config = load_config()
    if not config.require_auth:
        return
    if not config.api_key or x_api_key != config.api_key:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="Gecersiz API anahtari",
        )



class ChatRequest(BaseModel):
    message: str
    agent: str = "chat"
    speak: bool = False

class ChatResponse(BaseModel):
    response: str
    agent: str


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest, x_api_key: str | None = Header(default=None)):
    """Orchestrator üzerinden routing yapıp streaming cevap döner."""
    _check_auth(x_api_key)
    from ARIA.tools.summarizer import summarize_text

    reduced = summarize_text(req.message)
    route = orchestrator.route(reduced)
    agent_name = route.get("agent", req.agent)

    def event_stream():
        try:
            for token in engine.stream_chat([{"role": "user", "content": reduced}]):
                yield f"data: {token}\n\n"
        except Exception as exc:
            yield f"data: [error] {exc}\n\n"

    logger.info("stream ajan: %s", agent_name)
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"X-ARIA-Agent": agent_name},
    )

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, x_api_key: str | None = Header(default=None)):
    _check_auth(x_api_key)
    from ARIA.tools.summarizer import summarize_text

    metrics: dict = {}
    try:
        with track_latency(metrics, "total_ms"):
            reduced = summarize_text(req.message)
            # dispatch_with_route: route+dispatch tek seferde, LLM 1x çağrılır
            response, route = orchestrator.dispatch_with_route(reduced)
            agent_name = route.get("agent", req.agent)
    except Exception as exc:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )
    if req.speak:
        from ARIA.tools.tts import speak_text

        try:
            speak_text(response)
        except Exception as exc:
            logger.warning("TTS hata: %s", exc)
    if metrics:
        logger.info("chat metrics: %s", metrics)
    return ChatResponse(
        response=response,
        agent=agent_name,
    )


@app.post("/v1/chat/completions")
async def openai_chat(payload: dict, x_api_key: str | None = Header(default=None)):
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

@app.get("/status")
async def get_status(x_api_key: str | None = Header(default=None)):
    _check_auth(x_api_key)
    return ARIAEngine().doctor()


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
        raise HTTPException(status_code=400, detail="Preset adi gerekli")
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

def main() -> None:
    """aria-api entry point (pyproject.toml scripts)."""
    import uvicorn

    uvicorn.run("ARIA.api:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    main()
