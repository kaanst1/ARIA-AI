# ARIA - Analyst Agent (Veri Analisti)

from ARIA.core.engine import ARIAEngine
from ARIA.core.config import load_config
from ARIA.core.registry import register_agent

ANALYST_SYSTEM_PROMPT = """Sen ARIA'nın Veri Analisti ajanısın.
Dosya, tablo, metin veya ham veri alır, analiz eder ve içgörü üretirsin.

Format:
## Veri Özeti
## Ana Bulgular
## Trendler ve Patterns
## Öneriler

Kurallar:
- Sayısal verilerde yüzde ve karşılaştırma kullan
- Grafiği metin olarak ifade et (ASCII veya açıklama)
- Varsayım yapıyorsan belirt
- Somut aksiyon önerileri ver"""

@register_agent("analyst")
class AnalystAgent:
    def __init__(self):
        self.engine = ARIAEngine()
        self.config = load_config()

    def analyze_text(self, data: str, question: str = "") -> str:
        """Metin veya veri analiz et"""
        prompt = f"""Analiz edilecek veri:
{data}

{"Soru: " + question if question else "Genel analiz yap."}"""

        messages = [
            {"role": "system", "content": ANALYST_SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ]

        return self.engine.chat(messages)

    def handle(self, user_input: str) -> str:
        return self.analyze_text(user_input)

    def analyze_file(self, filepath: str, question: str = "") -> str:
        """Dosya oku ve analiz et"""
        try:
            from ARIA.tools.file_tools import file_read

            data = file_read(filepath)
            print(f"📂 Dosya okundu: {filepath} ({len(data)} karakter)")
            return self.analyze_text(data, question)
        except Exception as e:
            return f"❌ Dosya okunamadı: {e}"

    def interactive(self):
        """İnteraktif analiz modu"""
        print("\n📊 ARIA Analiz Modu — Çıkmak için 'quit'")
        print("=" * 40)

        while True:
            print("\n1. Metin/veri yapıştır")
            print("2. Dosya analiz et")
            print("3. Çıkış")
            
            choice = input("\nSeçim: ").strip()
            
            if choice == "1":
                print("Veriyi yapıştır (bitirmek için boş satır + Enter):")
                lines = []
                while True:
                    line = input()
                    if line == "":
                        break
                    lines.append(line)
                data = "\n".join(lines)
                question = input("Soru (boş bırakabilirsin): ").strip()
                print("\n⏳ Analiz ediliyor...\n")
                print(self.analyze_text(data, question))

            elif choice == "2":
                filepath = input("Dosya yolu: ").strip()
                question = input("Soru (boş bırakabilirsin): ").strip()
                print("\n⏳ Analiz ediliyor...\n")
                print(self.analyze_file(filepath, question))

            elif choice in ["3", "quit", "çıkış"]:
                print("Analiz modu kapatılıyor...")
                break


if __name__ == "__main__":
    agent = AnalystAgent()
    agent.interactive()