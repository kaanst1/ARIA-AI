# ARIA - Orchestrator (Ajan Koordinatörü)

from ARIA.core.engine import ARIAEngine
from ARIA.core.config import load_config
from ARIA.core.registry import get_agent
from ARIA.learning.tracker import UsageTracker
import logging
import json

ROUTER_SYSTEM_PROMPT = """Sen ARIA'nın Orkestratörüsün.
Kullanıcının mesajını analiz eder, hangi ajanın devreye gireceğine karar verirsin.

Ajanlar:
- brief: Sabah özeti, günlük plan
- researcher: Araştırma, analiz, bilgi toplama
- coder: Kod yazma, debug, teknik sorular
- monitor: İzleme, takip, alert
- analyst: Veri analizi, dosya okuma
- writer: İçerik üretme, haber, tweet, makale
- memory: Hafıza, not kaydetme, geçmiş sorgulama
- chat: Genel sohbet, diğer ajanlarla çözülemeyen

SADECE şu JSON formatında cevap ver:
{"agent": "ajan_adı", "reason": "kısa neden"}"""

class Orchestrator:
    def __init__(self):
        self.engine = ARIAEngine()
        self.config = load_config()
        self.logger = logging.getLogger("aria.orchestrator")

    def _rule_route(self, user_input: str) -> dict | None:
        text = user_input.lower()
        rules = [
            ("brief", ["brief", "sabah", "günlük özet", "gunluk ozet"]),
            ("monitor", ["izle", "monitor", "takip", "alert"]),
            ("memory", ["hafıza", "memory", "not", "hatırla", "hatirla"]),
            ("researcher", ["araştır", "arastir", "kaynak", "literatür", "literatur"]),
            ("analyst", ["analiz", "veri", "tablo", "raporla"]),
            ("coder", ["kod", "debug", "hata", "exception", "stack trace"]),
            ("writer", ["yaz", "makale", "tweet", "rapor", "haber"]),
        ]
        for agent, keys in rules:
            if any(k in text for k in keys):
                return {"agent": agent, "reason": "kural eslesmesi"}
        return None

    def route(self, user_input: str) -> dict:
        """Mesajı analiz et, uygun ajanı seç"""
        rule_pick = self._rule_route(user_input)
        if rule_pick:
            return rule_pick

        messages = [
            {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
            {"role": "user", "content": f"Kullanıcı mesajı: {user_input}\n\nSadece JSON döndür, başka hiçbir şey yazma."}
        ]

        response = self.engine.chat(messages)

        try:
            clean = response.strip()
            if "```json" in clean:
                clean = clean.split("```json")[1].split("```")[0].strip()
            elif "```" in clean:
                clean = clean.split("```")[1].strip()
            if "{" in clean and "}" in clean:
                clean = clean[clean.index("{"):clean.rindex("}")+1]
            return json.loads(clean)
        except:
            return {"agent": "chat", "reason": "parse hatası"}

    def dispatch(self, user_input: str) -> str:
        """Routing yap ve ilgili ajanı çalıştır"""
        tracker = UsageTracker()
        route = self.route(user_input)
        agent_name = route.get("agent", "chat")

        self.logger.info("Ajan: %s — %s", agent_name, route.get("reason", ""))

        agent_cls = get_agent(agent_name)
        if agent_cls:
            response = agent_cls().handle(user_input)
        else:
            messages = [{"role": "user", "content": user_input}]
            response = self.engine.chat(messages)

        tracker.log(agent_name, user_input, len(response))
        return response

    def interactive(self):
        """ARIA ana modu — tüm ajanlar aktif"""
        print("\n🤖 ARIA — Tüm Sistemler Aktif")
        print("=" * 40)

        while True:
            user_input = input("\nSen: ").strip()
            if user_input.lower() in ["quit", "exit", "çıkış"]:
                print("ARIA kapatılıyor...")
                break
            if not user_input:
                continue

            response = self.dispatch(user_input)
            print(f"\nARIA: {response}")


if __name__ == "__main__":
    o = Orchestrator()
    o.interactive()