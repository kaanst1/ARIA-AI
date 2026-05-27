"""Self Reflection — cevap kalitesini LLM ile iyileştirme."""

from __future__ import annotations

import logging

logger = logging.getLogger("aria.core.reflector")

_REFLECTION_SYSTEM = """Sen bir kalite değerlendirici ve iyileştiricisin.
Verilen soru ve taslak cevabı analiz et:

1. Cevap soruyu tam olarak yanıtlıyor mu?
2. Eksik önemli bilgi var mı?
3. Yanlış veya yanıltıcı bilgi var mı?
4. Daha açık veya kapsamlı yapılabilir mi?

Eğer cevap yeterliyse, aynısını döndür.
Eğer eksikse veya hatalıysa, geliştirilmiş versiyonu yaz.

SADECE geliştirilmiş cevabı döndür, değerlendirme metni yazma."""

# Yansıma tetikleyici eşik değerleri
_MIN_LENGTH_FOR_REFLECTION = 200  # karakter
_COMPLEX_KEYWORDS = [
    "neden", "nasıl", "açıkla", "karşılaştır", "analiz et",
    "detaylı", "kapsamlı", "araştır", "why", "how", "explain",
    "compare", "analyze", "detailed", "comprehensive",
]


def _should_reflect(question: str, answer: str) -> bool:
    """Yansıma gerekip gerekmediğine karar ver."""
    # Kısa cevaplar için yansıma gerekmez
    if len(answer) < _MIN_LENGTH_FOR_REFLECTION:
        return False

    # Karmaşık sorular için yansıma yap
    q_lower = question.lower()
    return any(kw in q_lower for kw in _COMPLEX_KEYWORDS)


class SelfReflector:
    """LLM cevaplarını self-reflection ile iyileştirir."""

    def __init__(self) -> None:
        self._engine = None

    def _get_engine(self):
        if self._engine is None:
            from ARIA.core.engine import ARIAEngine
            self._engine = ARIAEngine()
        return self._engine

    def reflect(self, question: str, draft_answer: str) -> str:
        """Taslak cevabı değerlendir ve iyileştir.

        Args:
            question: Kullanıcının sorusu.
            draft_answer: LLM'in ilk cevabı.

        Returns:
            İyileştirilmiş cevap (veya orijinal, yeterliyse).
        """
        if not _should_reflect(question, draft_answer):
            return draft_answer

        try:
            engine = self._get_engine()
            messages = [
                {"role": "system", "content": _REFLECTION_SYSTEM},
                {
                    "role": "user",
                    "content": (
                        f"Orijinal soru:\n{question}\n\n"
                        f"Taslak cevap:\n{draft_answer}\n\n"
                        "Geliştirilmiş cevabı yaz:"
                    ),
                },
            ]
            improved = engine.chat(messages)
            if improved and len(improved) > 50:
                logger.info(
                    "Self-reflection uygulandı: %d → %d karakter",
                    len(draft_answer), len(improved)
                )
                return improved
            return draft_answer
        except Exception as exc:
            logger.warning("Self-reflection hatası: %s", exc)
            return draft_answer


# Singleton
_reflector = SelfReflector()


def get_reflector() -> SelfReflector:
    return _reflector
