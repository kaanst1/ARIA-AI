# ARIA - Coder Agent (Kod Asistanı)

from ARIA.core.engine import ARIAEngine
from ARIA.core.config import load_config
from ARIA.core.registry import register_agent

CODER_SYSTEM_PROMPT = """Sen ARIA'nın Kod ajanısın.
Kod yazar, debug eder, açıklarsın.

Kurallar:
- Çalışan kod yaz, teorik kalma
- Her zaman kod bloğu kullan
- Hataları açıkla, sadece düzeltme yapma
- Dil ve framework'ü kullanıcıdan al
- Performans ve güvenliği göz önünde tut
- Türkçe açıkla, kod İngilizce olabilir"""

@register_agent("coder")
class CoderAgent:
    def __init__(self):
        self.engine = ARIAEngine()
        self.config = load_config()
        self.messages = [
            {"role": "system", "content": CODER_SYSTEM_PROMPT}
        ]

    def run(self, prompt: str) -> str:
        """Kod sorusu yanıtla"""
        self.messages.append({"role": "user", "content": prompt})
        response = self.engine.chat(self.messages)
        self.messages.append({"role": "assistant", "content": response})
        return response

    def handle(self, user_input: str) -> str:
        return self.run(user_input)

    def interactive(self):
        """İnteraktif kod asistanı modu"""
        print("\n💻 ARIA Kod Asistanı — Çıkmak için 'quit'")
        print("=" * 40)

        while True:
            user_input = input("\nSen: ").strip()
            if user_input.lower() in ["quit", "exit", "çıkış"]:
                print("Kod asistanı kapatılıyor...")
                break
            if not user_input:
                continue

            print("\n⏳ Düşünüyor...\n")
            response = self.run(user_input)
            print(f"ARIA: {response}")


if __name__ == "__main__":
    agent = CoderAgent()
    agent.interactive()