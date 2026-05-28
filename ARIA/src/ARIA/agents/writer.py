# ARIA - Writer Agent (İçerik Üretici)

from ARIA.core.engine import ARIAEngine
from ARIA.core.config import load_config
from ARIA.core.registry import register_agent

WRITER_SYSTEM_PROMPT = """Sen ARIA'nın İçerik Yazarı ajanısın.
Makale, haber, sosyal medya içeriği, rapor ve her türlü metin üretirsin.

Kurallar:
- İstenen formata sadık kal
- Ton: kullanıcının belirttiği (resmi/samimi/teknik)
- Spor haberi yazarken kaynak belirt, uydurma
- @holigrans için içerik yazarken Twitter formatına uy (280 karakter sınırı)
- Türkçe dil bilgisine dikkat et"""

CONTENT_TYPES = {
    "tweet": "Twitter/X için 280 karakter tweet",
    "haber": "Spor haberi makalesi",
    "rapor": "Detaylı rapor veya analiz",
    "makale": "Blog yazısı veya makale",
    "özet": "Kısa özet",
    "başlık": "Haber başlığı önerileri"
}

@register_agent("writer")
class WriterAgent:
    def __init__(self):
        self.engine = ARIAEngine()
        self.config = load_config()

    def write(self, content_type: str, topic: str, tone: str = "samimi", extra: str = "") -> str:
        """İçerik üret"""
        type_desc = CONTENT_TYPES.get(content_type, content_type)

        prompt = f"""İçerik türü: {type_desc}
Konu: {topic}
Ton: {tone}
{("Ek notlar: " + extra) if extra else ""}

İçeriği üret."""

        messages = [
            {"role": "system", "content": WRITER_SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ]

        return self.engine.chat(messages)

    def handle(self, user_input: str) -> str:
        return self.write("makale", user_input)

    def interactive(self):
        """İnteraktif yazı modu"""
        print("\n✍️ ARIA Yazar Modu — Çıkmak için 'quit'")
        print("=" * 40)
        print("İçerik türleri:", ", ".join(CONTENT_TYPES.keys()))

        while True:
            content_type = input("\nTür: ").strip().lower()
            if content_type in ["quit", "exit", "çıkış"]:
                break

            topic = input("Konu: ").strip()
            tone = input("Ton (samimi/resmi/teknik): ").strip() or "samimi"
            extra = input("Ek not (boş bırakabilirsin): ").strip()

            print("\n⏳ Yazılıyor...\n")
            result = self.write(content_type, topic, tone, extra)
            print(result)
            print("\n" + "=" * 40)


if __name__ == "__main__":
    import sys
    agent = WriterAgent()

    if len(sys.argv) > 2:
        content_type = sys.argv[1]
        topic = " ".join(sys.argv[2:])
        print(agent.write(content_type, topic))
    else:
        agent.interactive()