# ARIA - Monitor Agent (Scheduled İzleyici)

from ARIA.core.engine import ARIAEngine
from ARIA.core.config import load_config
from ARIA.core.registry import register_agent
from datetime import datetime
import json
import os

MONITOR_SYSTEM_PROMPT = """Sen ARIA'nın İzleme ajanısın.
Verilen kaynakları, konuları veya metrikleri periyodik olarak izler,
değişiklikleri tespit eder ve alert üretirsin.

Kurallar:
- Önemli değişiklikleri vurgula
- Trend analizi yap
- Alert seviyesi belirt: 🟢 Normal / 🟡 Dikkat / 🔴 Kritik
- Kısa ve net raporla"""

MONITORS_FILE = os.path.expanduser("~/.aria/monitors.json")

@register_agent("monitor")
class MonitorAgent:
    def __init__(self):
        self.engine = ARIAEngine()
        self.config = load_config()
        self.monitors = self._load_monitors()

    def _load_monitors(self) -> list:
        os.makedirs(os.path.dirname(MONITORS_FILE), exist_ok=True)
        if os.path.exists(MONITORS_FILE):
            with open(MONITORS_FILE) as f:
                return json.load(f)
        return []

    def _save_monitors(self):
        with open(MONITORS_FILE, "w") as f:
            json.dump(self.monitors, f, indent=2, ensure_ascii=False)

    def add_monitor(self, name: str, topic: str, frequency: str = "günlük"):
        """Yeni izleme ekle"""
        monitor = {
            "id": len(self.monitors) + 1,
            "name": name,
            "topic": topic,
            "frequency": frequency,
            "created": datetime.now().isoformat(),
            "last_run": None
        }
        self.monitors.append(monitor)
        self._save_monitors()
        print(f"✅ Monitor eklendi: {name}")

    def run_monitor(self, monitor: dict) -> str:
        """Tek bir monitörü çalıştır"""
        prompt = f"""İzleme konusu: {monitor['topic']}
Son kontrol: {monitor['last_run'] or 'İlk kontrol'}
Şu an: {datetime.now().strftime('%d %B %Y %H:%M')}

Bu konuda güncel durum analizi yap ve önemli gelişmeleri raporla."""

        messages = [
            {"role": "system", "content": MONITOR_SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ]

        return self.engine.chat(messages)

    def run_all(self):
        """Tüm monitörleri çalıştır"""
        if not self.monitors:
            print("⚠️ Henüz monitor tanımlanmamış.")
            return

        print(f"\n📡 ARIA Monitor — {datetime.now().strftime('%d %B %Y %H:%M')}")
        print("=" * 40)

        for monitor in self.monitors:
            print(f"\n🔍 {monitor['name']}")
            result = self.run_monitor(monitor)
            print(result)
            monitor["last_run"] = datetime.now().isoformat()

        self._save_monitors()
        print("\n" + "=" * 40)

    def list_monitors(self):
        if not self.monitors:
            print("⚠️ Monitor yok.")
            return
        for m in self.monitors:
            print(f"[{m['id']}] {m['name']} — {m['frequency']} — Konu: {m['topic']}")

    def handle(self, user_input: str) -> str:
        monitor = {
            "name": "ad-hoc",
            "topic": user_input,
            "last_run": None,
        }
        return self.run_monitor(monitor)


if __name__ == "__main__":
    import sys
    agent = MonitorAgent()

    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "add":
            name = input("Monitor adı: ")
            topic = input("İzlenecek konu: ")
            freq = input("Sıklık (günlük/saatlik): ") or "günlük"
            agent.add_monitor(name, topic, freq)
        elif cmd == "list":
            agent.list_monitors()
        elif cmd == "run":
            agent.run_all()
    else:
        agent.run_all()