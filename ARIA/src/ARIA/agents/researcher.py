# ARIA - Researcher Agent (Derin Araştırma)

from ARIA.core.engine import ARIAEngine
from ARIA.core.config import load_config
from ARIA.core.registry import register_agent

RESEARCHER_SYSTEM_PROMPT = """Sen ARIA'nın Araştırma ajanısın.
Verilen konuyu derinlemesine araştırır, analiz eder ve rapor üretirsin.

Format:
## Konu: [başlık]
### Özet
### Ana Bulgular
### Detaylı Analiz
### Sonuç ve Öneriler

Kurallar:
- Kaynak belirt (bilmiyorsan belirt)
- Spekülatif bilgiyi işaretle
- Teknik konularda derine in
- Kısa değil, kapsamlı ol"""

@register_agent("researcher")
class ResearcherAgent:
    def __init__(self):
        self.engine = ARIAEngine()
        self.config = load_config()

    def run(self, topic: str, depth: str = "normal") -> str:
        """Konu araştır ve rapor üret"""
        from ARIA.tools.web_search import WebSearch

        ws = WebSearch()
        search_results = ws.search(topic, max_results=5)
        news_results = ws.search_news(topic, max_results=3)

        web_context = ws.format_results(search_results)
        news_context = ws.format_results(news_results)

        # Arama başarısız olduysa (hata nesnesi döndüyse) yerel retrieval'a fall back et
        search_failed = not search_results or search_results[0].get("title") == "Hata"
        if search_failed:
            from ARIA.tools.retrieval import retrieve

            web_context = retrieve(topic)

        depth_instruction = {
            "hızlı": "Hızlı tarama yap, 3-5 dakikada okunabilir özet.",
            "normal": "Kapsamlı analiz yap, tüm açılardan ele al.",
            "derin": "Maksimum derinlikte araştır, akademik seviyede detay ver."
        }.get(depth, "normal")

        prompt = f"""Araştırma konusu: {topic}

Web arama sonuçları:
{web_context}

Son haberler:
{news_context}

Derinlik: {depth_instruction}

Bu verileri kullanarak kapsamlı bir araştırma raporu hazırla."""

        messages = [
            {"role": "system", "content": RESEARCHER_SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ]

        return self.engine.chat(messages)

    def handle(self, user_input: str) -> str:
        return self.run(user_input)

    def ask(self, topic: str):
        """İnteraktif araştırma modu"""
        print(f"\n🔬 ARIA Araştırma Modu: {topic}")
        print("=" * 40)

        depth = input("Derinlik (hızlı/normal/derin): ").strip() or "normal"

        print("\n⏳ Araştırılıyor...\n")
        result = self.run(topic, depth)
        print(result)
        print("\n" + "=" * 40)


if __name__ == "__main__":
    import sys
    agent = ResearcherAgent()

    if len(sys.argv) > 1:
        topic = " ".join(sys.argv[1:])
        agent.ask(topic)
    else:
        topic = input("Araştırma konusu: ").strip()
        agent.ask(topic)