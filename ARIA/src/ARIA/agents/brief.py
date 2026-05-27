# ARIA - Brief Agent (Sabah Özeti)

from ARIA.core.engine import ARIAEngine
from ARIA.core.config import load_config
from ARIA.core.registry import register_agent
from datetime import datetime

BRIEF_SYSTEM_PROMPT = """Sen ARIA'nın Sabah Özeti ajanısın.
Her sabah Meriç'e kısa, net, önemli bir günlük özet sunarsın.
Format:
- Tarih ve gün
- Öncelikli görevler
- Hatırlatmalar
- Kısa motivasyon

Gereksiz detay yok, direkt ve özlü ol."""

@register_agent("brief")
class BriefAgent:
    def __init__(self):
        self.engine = ARIAEngine()
        self.engine.config = load_config()

    def run(self, context: dict = {}) -> str:
        """Günlük brief üret"""
        from ARIA.tools.web_search import WebSearch

        now = datetime.now()
        tarih = now.strftime("%A, %d %B %Y %H:%M")

        ws = WebSearch()
        haberler = ws.search_news("Türkiye gündem bugün", max_results=3)
        haber_context = ws.format_results(haberler)

        prompt = f"""Bugün: {tarih}

Güncel haberler:
{haber_context}

Ek bağlam: {context if context else 'Yok'}

Meriç için kısa sabah briefi hazırla."""

        messages = [
            {"role": "system", "content": BRIEF_SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ]

        return self.engine.chat(messages)

    def handle(self, user_input: str) -> str:
        return self.run()

    def scheduled_run(self):
        """Scheduler tarafından çağrılır"""
        print("\n📋 ARIA Sabah Briefi")
        print("=" * 40)
        print(self.run())
        print("=" * 40)


if __name__ == "__main__":
    agent = BriefAgent()
    agent.scheduled_run()