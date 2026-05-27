"""Engine selector and model catalog."""

from __future__ import annotations

import platform
from ARIA.core.config import load_config
from ARIA.engine.ollama_engine import OllamaEngine


def detect_hardware() -> dict:
    return {
        "system": platform.system(),
        "machine": platform.machine(),
        "processor": platform.processor(),
    }


def get_engine():
    config = load_config()
    if config.engine == "ollama":
        return OllamaEngine(config)
    return OllamaEngine(config)


def list_models() -> list:
    engine = get_engine()
    return engine.list_models()
