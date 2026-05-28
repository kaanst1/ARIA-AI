"""Model karmaşıklık yönlendirmesi — sorgunun zorluğuna göre model seç."""

from __future__ import annotations

import logging
import re

logger = logging.getLogger("aria.core.smart_router")

# Basit sorgular → küçük/hızlı model
_SIMPLE_PATTERNS = [
    r"^(merhaba|günaydın|selam|nasılsın|iyi misin|ne haber)",
    r"^(saat kaç|bugün ne|hava nasıl)",
    r"^(evet|hayır|tamam|ok|tamamdır)",
    r"^\w{1,3}\?*$",  # çok kısa tek kelime
]

# Araştırma / derin analiz → büyük model
_COMPLEX_PATTERNS = [
    r"(araştır|analiz|detaylı|kapsamlı|karşılaştır|incele)",
    r"(makale|rapor|akademik|literatür|kaynak)",
    r"(neden|nasıl çalışır|açıkla|anlat|fark nedir)",
    r"(kod yaz|implement|geliştir|debug|hata)",
    r"(plan yap|strateji|adım adım|workflow)",
]

# Haberdar — orta model
_MEDIUM_PATTERNS = [
    r"(haber|güncel|son dakika|bugün ne oldu)",
    r"(özetle|özet|kısaca|kısa)",
    r"(hatırla|kaydet|not al)",
]


def classify_complexity(query: str) -> str:
    """Sorgu karmaşıklığını sınıflandır: 'simple' | 'medium' | 'complex'."""
    text = query.lower().strip()

    for pat in _SIMPLE_PATTERNS:
        if re.search(pat, text):
            return "simple"

    for pat in _COMPLEX_PATTERNS:
        if re.search(pat, text):
            return "complex"

    for pat in _MEDIUM_PATTERNS:
        if re.search(pat, text):
            return "medium"

    # Uzunluğa göre fallback
    words = len(text.split())
    if words <= 5:
        return "simple"
    if words >= 25:
        return "complex"
    return "medium"


def select_model(query: str, available_models: list[str], default: str) -> str:
    """Sorgu karmaşıklığına göre en uygun modeli seç.

    Strateji:
    - simple  → en küçük/hızlı model (qwen2.5:3b, phi3, gemma:2b)
    - medium  → orta model (qwen2.5:7b, llama3.2)
    - complex → en büyük model (qwen2.5:14b, llama3.1:8b, mistral)
    """
    if not available_models:
        return default

    complexity = classify_complexity(query)
    logger.debug("Sorgu karmaşıklığı: %s — '%s'", complexity, query[:50])

    # Model tercih sıraları (küçükten büyüğe)
    _SMALL = ["qwen2.5:3b", "phi3:mini", "phi3", "gemma:2b", "gemma2:2b", "tinyllama"]
    _MEDIUM = ["qwen2.5:7b", "llama3.2:3b", "llama3.2", "mistral:7b", "gemma2:9b"]
    _LARGE = ["qwen2.5:14b", "qwen2.5:32b", "llama3.1:8b", "llama3.1", "mixtral", "command-r"]

    def _pick(candidates: list[str]) -> str | None:
        for c in candidates:
            for m in available_models:
                if c in m.lower():
                    return m
        return None

    if complexity == "simple":
        return _pick(_SMALL) or _pick(_MEDIUM) or default
    elif complexity == "complex":
        return _pick(_LARGE) or _pick(_MEDIUM) or default
    else:
        return _pick(_MEDIUM) or default


class SmartEngine:
    """ARIAEngine wrapper — her çağrıda otomatik model seçimi yapar."""

    def __init__(self):
        from ARIA.core.engine import ARIAEngine
        self._engine = ARIAEngine()
        self._available: list[str] = []
        self._refresh_models()

    def _refresh_models(self) -> None:
        try:
            self._available = self._engine.list_models()
        except Exception:
            self._available = []

    def chat(self, messages: list[dict], query_hint: str = "") -> str:
        """Sorguya göre model seçerek yanıtla."""
        if not self._available:
            self._refresh_models()

        default = self._engine.config.model
        query = query_hint or next(
            (m["content"] for m in reversed(messages) if m.get("role") == "user"), ""
        )
        best_model = select_model(query, self._available, default)

        if best_model != self._engine.engine.model:
            logger.debug("Model seçildi: %s (karmaşıklık: %s)", best_model, classify_complexity(query))
            self._engine.engine.model = best_model

        return self._engine.chat(messages)

    def stream_chat(self, messages: list[dict], query_hint: str = ""):
        query = query_hint or next(
            (m["content"] for m in reversed(messages) if m.get("role") == "user"), ""
        )
        best_model = select_model(query, self._available or [], self._engine.config.model)
        if best_model != self._engine.engine.model:
            self._engine.engine.model = best_model
        yield from self._engine.stream_chat(messages)
