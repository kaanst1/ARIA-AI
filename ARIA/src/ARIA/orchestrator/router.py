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

        # ── Günaydın / sabah briefi tespiti ──────────────────────────────────
        morning_triggers = [
            "günaydın", "gunaydin", "iyi sabahlar", "sabah briefi",
            "sabahın hayırlı", "sabah özeti", "briefi ver", "briefi başlat",
            "günaydın aria", "good morning",
        ]
        if any(k in text for k in morning_triggers):
            return {"agent": "brief", "reason": "sabah selamlaşma / brief talebi"}

        # ── Alarm / timer özel tespiti ───────────────────────────────────────
        alarm_triggers = [
            "alarm kur", "alarm ayarla", "alarm set", "saat", "da alarm",
            "de alarm", "da çal", "de çal", "timer", "dakika sonra",
            "saat sonra", "hatırlat", "hatırlatıcı", "zil", "uyandır",
        ]
        if any(k in text for k in alarm_triggers):
            return {"agent": "chat", "reason": "alarm/timer komutu"}

        # ── WhatsApp özel tespiti ─────────────────────────────────────────────
        if "whatsapp" in text or (
            ("mesaj" in text or "yaz" in text) and
            any(k in text for k in ["gönder", "at", "söyle", "ilet"])
        ):
            return {"agent": "chat", "reason": "whatsapp mesaj komutu"}

        # ── Reminders özel tespiti ────────────────────────────────────────────
        reminder_triggers = [
            "reminder", "hatırlatıcı ekle", "hatırlatıcı", "reminders",
            "görev ekle", "yapılacak ekle", "not ekle reminder",
        ]
        if any(k in text for k in reminder_triggers):
            return {"agent": "chat", "reason": "reminder komutu"}

        # ── Spotify özel tespiti ──────────────────────────────────────────────
        spotify_triggers = [
            "spotify", "müzik çal", "şarkı çal", "müzik aç",
            "sıradaki", "sıradaki parça", "müziği durdur",
            "müziği durdur", "şarkıyı atla", "ses seviyesi",
        ]
        if any(k in text for k in spotify_triggers):
            return {"agent": "chat", "reason": "spotify müzik komutu"}

        # ── Mail özel tespiti ─────────────────────────────────────────────────
        mail_triggers = [
            "mail gönder", "e-posta", "e-posta gönder", "mail at",
            "gelen kutusu", "okunmamış mail", "okunmamış e-posta",
        ]
        if any(k in text for k in mail_triggers):
            return {"agent": "chat", "reason": "e-posta komutu"}

        # ── Ekran analizi özel tespiti ────────────────────────────────────────
        screen_triggers = [
            "ekrana bak", "ekranı analiz", "ekranda ne var", "screenshot",
            "ekran görüntüsü", "ekranı incele",
        ]
        if any(k in text for k in screen_triggers):
            return {"agent": "chat", "reason": "ekran analizi komutu"}

        # ── Hava durumu tespiti ───────────────────────────────────────────────
        weather_triggers = [
            "hava durumu", "hava nasıl", "bugün hava", "yarın hava",
            "yağmur", "sıcaklık", "nem", "rüzgar", "tahmin",
        ]
        if any(k in text for k in weather_triggers):
            return {"agent": "chat", "reason": "hava durumu komutu"}

        # ── Apple Notes tespiti ───────────────────────────────────────────────
        notes_triggers = [
            "notes a ekle", "notlara ekle", "not oluştur", "nota ekle",
            "notlarım", "notes'ta ara", "notlarda ara",
        ]
        if any(k in text for k in notes_triggers):
            return {"agent": "chat", "reason": "apple notes komutu"}

        # ── Uygulama kontrol tespiti ──────────────────────────────────────────
        app_triggers = [
            "uygulamayı aç", "uygulamayı kapat", "aç ", "kapat ",
            "çalışan uygulamalar", "hangi uygulamalar açık",
        ]
        if any(k in text for k in app_triggers) and any(
            k in text for k in ["chrome", "safari", "spotify", "terminal", "finder",
                                  "slack", "discord", "notion", "vscode", "xcode", "arc"]
        ):
            return {"agent": "chat", "reason": "uygulama kontrol komutu"}

        # ── Kişiler tespiti ───────────────────────────────────────────────────
        contacts_triggers = [
            "kişiyi bul", "rehberde ara", "telefon numarası", "e-posta adresi",
            "kişi ara", "kontakt",
        ]
        if any(k in text for k in contacts_triggers):
            return {"agent": "chat", "reason": "rehber komutu"}

        # ── Odak modu tespiti ─────────────────────────────────────────────────
        focus_triggers = [
            "odak modu", "rahatsız etme", "dnd aç", "dnd kapat",
            "bildirimler kapat", "focus modu", "do not disturb",
        ]
        if any(k in text for k in focus_triggers):
            return {"agent": "chat", "reason": "odak modu komutu"}

        # ── Tarayıcı kontrol tespiti ──────────────────────────────────────────
        browser_triggers = [
            "tarayıcıda aç", "chrome'da aç", "safari'de aç", "sitesine git",
            "web'de ara", "sekme aç", "tarayıcıda ara",
        ]
        if any(k in text for k in browser_triggers):
            return {"agent": "chat", "reason": "tarayıcı komutu"}

        # ── Dosya/Spotlight arama tespiti ─────────────────────────────────────
        spotlight_triggers = [
            "dosya bul", "dosyayı bul", "spotlightta ara", "bilgisayarda ara",
            "dosya ara", "nerede bu dosya",
        ]
        if any(k in text for k in spotlight_triggers):
            return {"agent": "chat", "reason": "spotlight arama komutu"}

        # ── Pomodoro tespiti ──────────────────────────────────────────────────
        if any(k in text for k in ["pomodoro", "odaklanma modu", "çalışma zamanlayıcı", "timer başlat"]):
            return {"agent": "chat", "reason": "pomodoro komutu"}

        # ── iMessage tespiti ──────────────────────────────────────────────────
        if any(k in text for k in ["imessage", "i message", "sms gönder", "kısa mesaj"]):
            return {"agent": "chat", "reason": "imessage komutu"}

        # ── Git/kod tespiti ───────────────────────────────────────────────────
        if any(k in text for k in ["git log", "commit özeti", "todo tara", "git durumu", "diff özetle"]):
            return {"agent": "chat", "reason": "git intelligence komutu"}

        # ── Sağlık verisi tespiti ─────────────────────────────────────────────
        if any(k in text for k in ["adım sayısı", "uyku kalitesi", "sağlık özeti", "health", "kaç adım"]):
            return {"agent": "chat", "reason": "health komutu"}

        # ── Haftalık/günlük rapor tespiti ─────────────────────────────────────
        if any(k in text for k in ["haftalık rapor", "günlük rapor", "rapor oluştur", "haftanın özeti"]):
            return {"agent": "chat", "reason": "rapor komutu"}

        # ── Bağlam önerisi tespiti ────────────────────────────────────────────
        if any(k in text for k in ["ne önerirsin", "şu an ne yapayım", "bağlam önerisi"]):
            return {"agent": "chat", "reason": "bağlam önerisi"}

        # ── Agent zinciri tespiti ─────────────────────────────────────────────
        chain_triggers = [
            "önce araştır sonra", "araştır ve yaz", "araştır ve özetle",
            "sonra tweet", "ve makale yaz", "ardından", "sırayla yap",
            "birden fazla adım", "zincir",
        ]
        if any(k in text for k in chain_triggers):
            return {"agent": "chain", "reason": "çok-adım zincir"}

        # ── Voice mode tespiti ────────────────────────────────────────────────
        if any(k in text for k in ["voice mode aç", "ses modunu aç", "dinlemeye başla", "sürekli dinle"]):
            return {"agent": "chat", "reason": "voice mode komutu"}

        # ── Toplantı asistanı tespiti ─────────────────────────────────────────
        if any(k in text for k in ["toplantı başlat", "toplantı kaydı", "toplantıyı kaydet", "meeting start"]):
            return {"agent": "chat", "reason": "toplantı asistanı komutu"}
        if any(k in text for k in ["toplantıyı bitir", "toplantı bitti", "meeting stop", "kaydı bitir"]):
            return {"agent": "chat", "reason": "toplantı bitir komutu"}

        # ── Obsidian tespiti ──────────────────────────────────────────────────
        if any(k in text for k in ["obsidian", "vault'a", "vault a", "daily note", "not oluştur obsidian"]):
            return {"agent": "chat", "reason": "obsidian komutu"}

        # ── Keychain tespiti ──────────────────────────────────────────────────
        if any(k in text for k in ["keychain", "api key kaydet", "şifre kaydet", "credential"]):
            return {"agent": "chat", "reason": "keychain komutu"}

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

        # ── Workflow keyword tetikleyicisini kontrol et ───────────────────────
        try:
            from ARIA.automation.workflow_engine import check_keyword_triggers, run_workflow
            wf = check_keyword_triggers(user_input)
            if wf:
                self.logger.info("Workflow tetiklendi: %s", wf.get("name"))
                results = run_workflow(wf)
                last = next((r["result"] for r in reversed(results) if r.get("success")), "Workflow tamamlandı")
                tracker.log("workflow", user_input, len(last))
                return last, {"agent": "workflow", "reason": wf.get("name", "keyword")}
        except Exception as exc:
            self.logger.warning("Workflow kontrolü başarısız: %s", exc)

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
            response = agent_cls().handle(user_input)
        else:
            messages: list[dict] = []
            if context_messages:
                messages.extend(context_messages)
            messages.append({"role": "user", "content": user_input})

            # Semantik hafıza bağlamını enjekte et
            try:
                from ARIA.memory.semantic_context import inject_into_messages
                messages = inject_into_messages(messages, user_input, agent_name)
            except Exception:
                pass

            # Akıllı model seçimi
            try:
                from ARIA.core.smart_router import SmartEngine
                response = SmartEngine().chat(messages, query_hint=user_input)
            except Exception:
                response = self.engine.chat(messages)

        # ── Self-reflection ──────────────────────────────────────────────────
        try:
            from ARIA.core.reflector import get_reflector
            reflector = get_reflector()
            response = reflector.reflect(user_input, response)
        except Exception as exc:
            self.logger.warning("Self-reflection hatası: %s", exc)

        # ── Konuşmayı semantik hafızaya kaydet ───────────────────────────────
        try:
            from ARIA.memory.semantic_context import save_exchange
            save_exchange(user_input, response, agent=agent_name)
        except Exception:
            pass

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
