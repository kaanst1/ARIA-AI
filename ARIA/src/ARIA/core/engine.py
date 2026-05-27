# ARIA - Engine Layer (Ollama / Metal)

from typing import Generator, Optional
from ARIA.core.config import ARIAConfig, load_config
from ARIA.engine.selector import get_engine

class ARIAEngine:
    def __init__(self, config: Optional[ARIAConfig] = None):
        self.config = config or load_config()
        self.engine = get_engine()

    def is_available(self) -> bool:
        """Ollama çalışıyor mu kontrol et"""
        return self.engine.is_available()

    def list_models(self) -> list:
        """Yüklü modelleri listele"""
        return self.engine.list_models()

    def chat(self, messages: list, stream: bool = False) -> str:
        """Modele mesaj gönder"""
        return self.engine.chat(messages, stream=stream)

    def stream_chat(self, messages: list) -> Generator[str, None, None]:
        """Modele streaming mesaj gönder"""
        yield from self.engine.stream_chat(messages)

    def switch_model(self, model_name: str):
        """Model değiştir"""
        available = self.list_models()
        if model_name in available:
            self.config.model = model_name
            print(f"Model değiştirildi: {model_name}")
        else:
            print(f"Model bulunamadı: {model_name}")
            print(f"Mevcut modeller: {available}")

    def doctor(self) -> dict:
        """Sistem durumunu kontrol et"""
        return {
            "engine": self.config.engine,
            "ollama_running": self.is_available(),
            "active_model": self.config.model,
            "available_models": self.list_models(),
            "base_url": self.config.base_url,
            "cloud_fallback": self.config.cloud_fallback,
        }