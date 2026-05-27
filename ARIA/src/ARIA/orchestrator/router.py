# ARIA - Orchestrator (Ajan Koordinatörü)

from __future__ import annotations

import json
import logging
from typing import Optional

import ARIA.agents  # noqa: F401 — @register_agent decorator'larını tetikler
from ARIA.core.engine import ARIAEngine
from ARIA.core.config import load_config
from ARIA.core.registry import get_agent
from ARIA.learning.tracker import UsageTracker

ROUTER_SYSTEM_PROMPT = """Sen ARIA'nın Orkestratörüsün.
Kullanıcının mesajını analiz eder, hangi ajanın devreye gireceğine karar verirsin.

Ajanlar:
- brief: Sabah özeti, günlük plan
- researcher: Araştırma, analiz, bilgi toplama
- deep_research: Derin/kapsamlı araştırma, çoklu kaynak
- coder: Kod yazma, debug, teknik sorular
- monitor: İzleme, takip, alert
- analyst: Veri analizi, dosya okuma
- writer: İçerik üretme, haber, tweet, makale
- memory: Hafıza, not kaydetme, geçmiş sorgulama
- planner: Çok adımlı görev planlaması, otomasyon
- terminal: Shell komutları, sistem bilgisi
- chat: Genel sohbet, diğer ajanlarla çözülemeyen

SADECE şu JSON formatında cevap ver:
{"agent": "ajan_adı", "reason": "kısa neden"}"""


class Orchestrator:
    """Gelen mesajları uygun ajanlara yönlendiren koordinatör."""

    def __init__(self) -> None:
        self.engine = ARIAEngine()
        self.config = load_config()
        self.logger = logging.getLogger("aria.orchestrator")

    # ── Kural tabanlı yönlendirme ─────────────────────────────────────────────

    def _rule_route(self, user_input: str) -> Optional[dict]:
        """Hızlı prefix/keyword eşleştirmesi ile ajan seç.

        Öncelik sırası: daha spesifik kurallar önce.
        """
        text = user_input.lower().strip()

        # ── Prefix tabanlı hızlı komutlar ────────────────────────────────────
        prefix_rules: list[tuple[str, str]] = [
            ("sabah briefi", "brief"),
            ("sabah özeti", "brief"),
            ("araştır ", "researcher"),
            ("kod yaz", "coder"),
            ("kodla", "coder"),
            ("hatırlat", "memory"),
            ("not al", "memory"),
            ("izle ", "monitor"),
            ("takip et", "monitor"),
            ("analiz et", "analyst"),
            ("yaz ", "writer"),
            ("whatsapp", "chat"),     # whatsapp → chat agent + whatsapp_tool
            ("mesaj gönder", "chat"),
        ]
        for prefix, agent in prefix_rules:
            if text.startswith(prefix):
                return {"agent": agent, "reason": f"prefix: {prefix}"}

        # ── Keyword kuralları ─────────────────────────────────────────────────
        keyword_rules: list[tuple[str, list[str]]] = [
            ("brief", ["brief", "günlük özet", "gunluk ozet", "sabah planı", "sabah briefi"]),
            ("monitor", ["monitor", "alert", "izle", "takip"]),
            ("memory", ["hafıza", "memory", "not", "hatırla", "hatirla", "kaydet"]),
            ("planner", [
                "planla", "plan yap", "adım adım", "otomatik yap",
                "sırayla yap", "workflow", "pipeline", "görev listesi",
            ]),
            ("terminal", [
                "terminal", "komut", "shell", "çalıştır", "bash",
                "hangi işlem", "işlem listesi", "disk kullanımı",
                "klasör içeriği", "dosya listesi",
            ]),
            ("deep_research", [
                "derin araştır", "detaylı araştır", "kapsamlı araştır",
                "derinlemesine", "her açıdan", "akademik",
            ]),
            ("researcher", [
                "araştır", "arastir", "kaynak", "literatür", "literatur",
                "hava durumu", "haber", "güncel", "son dakika", "bugün ne",
                "videoya bak", "podcast özeti", "youtube",
            ]),
            ("analyst", ["analiz", "veri", "tablo", "raporla", "istatistik"]),
            ("coder", ["kod", "debug", "hata", "exception", "stack trace", "fonksiyon", "class"]),
            ("writer", ["makale", "tweet", "rapor", "haber", "içerik"]),
        ]

        # ── WhatsApp özel tespiti ─────────────────────────────────────────────
        if "whatsapp" in text or (
            ("mesaj" in text or "yaz" in text) and
            any(k in text for k in ["gönder", "at", "söyle", "ilet"])
        ):
            return {"agent": "chat", "reason": "whatsapp mesaj komutu"}
        for agent, keys in keyword_rules:
            if any(k in text for k in keys):
                return {"agent": agent, "reason": "keyword eşleşmesi"}

        return None

    # ── LLM tabanlı yönlendirme ───────────────────────────────────────────────

    def route(self, user_input: str) -> dict:
        """Mesajı analiz et, uygun ajanı seç."""
        rule_pick = self._rule_route(user_input)
        if rule_pick:
            return rule_pick

        messages = [
            {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Kullanıcı mesajı: {user_input}\n\n"
                    "Sadece JSON döndür, başka hiçbir şey yazma."
                ),
            },
        ]

        response = self.engine.chat(messages)

        try:
            clean = response.strip()
            if "```json" in clean:
                clean = clean.split("```json")[1].split("```")[0].strip()
            elif "```" in clean:
                clean = clean.split("```")[1].strip()
            if "{" in clean and "}" in clean:
                clean = clean[clean.index("{"):clean.rindex("}") + 1]
            return json.loads(clean)
        except Exception:
            return {"agent": "chat", "reason": "parse hatası"}

    # ── Dispatch ──────────────────────────────────────────────────────────────

    def dispatch(self, user_input: str, session_id: Optional[int] = None) -> str:
        """Routing yap ve ilgili ajanı çalıştır."""
        response, _ = self.dispatch_with_route(user_input, session_id=session_id)
        return response

    def dispatch_with_route(
        self,
        user_input: str,
        session_id: Optional[int] = None,
    ) -> tuple[str, dict]:
        """Routing yap, ajanı çalıştır; (cevap, route) döndür.

        session_id verilirse ConversationStore'dan son N mesajı alıp
        engine.chat() çağrısına context olarak ekler.
        """
        tracker = UsageTracker()
        route = self.route(user_input)
        agent_name = route.get("agent", "chat")

        self.logger.info("Ajan: %s — %s", agent_name, route.get("reason", ""))

        # ── Konuşma context'ini hazırla ───────────────────────────────────────
        context_messages: list[dict] = []
        if session_id is not None:
            try:
                from ARIA.memory.conversation_store import ConversationStore
                store = ConversationStore()
                limit = self.config.conversation_history_limit
                context_messages = store.get_context_messages(session_id, n=limit)
            except Exception as exc:
                self.logger.warning("Context yüklenemedi: %s", exc)

        # ── Ajan çalıştır ─────────────────────────────────────────────────────
        agent_cls = get_agent(agent_name)
        if agent_cls:
            # Ajan varsa handle() çağır — basit bir string döner
            response = agent_cls().handle(user_input)
        else:
            # Doğrudan LLM — context mesajlarını ekle
            messages: list[dict] = []
            if context_messages:
                messages.extend(context_messages)
            messages.append({"role": "user", "content": user_input})
            response = self.engine.chat(messages)

        # ── Self-reflection ──────────────────────────────────────────────────
        try:
            from ARIA.core.reflector import get_reflector
            reflector = get_reflector()
            response = reflector.reflect(user_input, response)
        except Exception as exc:
            self.logger.warning("Self-reflection hatası: %s", exc)

        tracker.log(agent_name, user_input, len(response))
        return response, route

    # ── İnteraktif mod ───────────────────────────────────────────────────────

    def interactive(self) -> None:
        """ARIA ana modu — tüm ajanlar aktif."""
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
