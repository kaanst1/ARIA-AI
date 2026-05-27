# ARIA - Monitor Agent (Scheduled İzleyici)

from __future__ import annotations

import json
import logging
import os
import subprocess
from datetime import datetime

from ARIA.core.engine import ARIAEngine
from ARIA.core.config import load_config
from ARIA.core.registry import register_agent

MONITOR_SYSTEM_PROMPT = """Sen ARIA'nın İzleme ajanısın.
Verilen kaynakları, konuları veya metrikleri periyodik olarak izler,
değişiklikleri tespit eder ve alert üretirsin.

Kurallar:
- Önemli değişiklikleri vurgula
- Trend analizi yap
- Alert seviyesi belirt: 🟢 Normal / 🟡 Dikkat / 🔴 Kritik
- Kısa ve net raporla"""

MONITORS_FILE = os.path.expanduser("~/.aria/monitors.json")

logger = logging.getLogger("aria.agents.monitor")


@register_agent("monitor")
class MonitorAgent:
    """Periyodik izleme ve alert üretimi yapan ajan."""

    def __init__(self) -> None:
        self.engine = ARIAEngine()
        self.config = load_config()
        self.monitors = self._load_monitors()

    # ── Yardımcı ─────────────────────────────────────────────────────────────

    def _load_monitors(self) -> list:
        os.makedirs(os.path.dirname(MONITORS_FILE), exist_ok=True)
        if os.path.exists(MONITORS_FILE):
            try:
                with open(MONITORS_FILE) as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def _save_monitors(self) -> None:
        with open(MONITORS_FILE, "w") as f:
            json.dump(self.monitors, f, indent=2, ensure_ascii=False)

    # ── macOS Bildirim ────────────────────────────────────────────────────────

    def _send_notification(self, title: str, message: str) -> None:
        """macOS desktop bildirimi gönder (osascript ile).

        Sadece notification_enabled=True olduğunda çalışır.
        Hata durumunda sessizce geçer.
        """
        if not self.config.notification_enabled:
            return
        try:
            script = (
                f'display notification "{_esc(message)}" '
                f'with title "ARIA — {_esc(title)}"'
            )
            subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                timeout=5,
            )
        except Exception as exc:
            logger.warning("Bildirim gönderilemedi: %s", exc)

    # ── Monitor işlemleri ─────────────────────────────────────────────────────

    def add_monitor(self, name: str, topic: str, frequency: str = "günlük") -> None:
        """Yeni izleme ekle."""
        monitor = {
            "id": len(self.monitors) + 1,
            "name": name,
            "topic": topic,
            "frequency": frequency,
            "created": datetime.now().isoformat(),
            "last_run": None,
        }
        self.monitors.append(monitor)
        self._save_monitors()
        print(f"✅ Monitor eklendi: {name}")

    def run_monitor(self, monitor: dict) -> str:
        """Tek bir monitörü çalıştır ve sonucu döndür.

        🔴 kritik alert varsa otomatik olarak macOS bildirimi ve TTS gönderir.
        """
        prompt = (
            f"İzleme konusu: {monitor['topic']}\n"
            f"Son kontrol: {monitor['last_run'] or 'İlk kontrol'}\n"
            f"Şu an: {datetime.now().strftime('%d %B %Y %H:%M')}\n\n"
            "Bu konuda güncel durum analizi yap ve önemli gelişmeleri raporla."
        )

        messages = [
            {"role": "system", "content": MONITOR_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        result = self.engine.chat(messages)

        # Kritik alert tespiti
        if "🔴" in result:
            monitor_name = monitor.get("name", "Monitor")
            # İlk satırı bildirim mesajı olarak kullan
            first_line = result.split("\n")[0][:120]
            logger.warning("Kritik alert: %s — %s", monitor_name, first_line)
            self._send_notification(f"Kritik: {monitor_name}", first_line)

            # TTS — kritik alertlerde sesli uyarı
            if self.config.enable_tts:
                try:
                    from ARIA.tools.tts import speak_text
                    speak_text(f"Kritik alert: {monitor_name}")
                except Exception as exc:
                    logger.warning("TTS hatası: %s", exc)

        return result

    def run_all(self) -> None:
        """Tüm monitörleri çalıştır."""
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

    def list_monitors(self) -> None:
        if not self.monitors:
            print("⚠️ Monitor yok.")
            return
        for m in self.monitors:
            print(f"[{m['id']}] {m['name']} — {m['frequency']} — Konu: {m['topic']}")

    def handle(self, user_input: str) -> str:
        """Kullanıcı girişine göre ad-hoc monitor çalıştır."""
        monitor = {
            "name": "ad-hoc",
            "topic": user_input,
            "last_run": None,
        }
        return self.run_monitor(monitor)


# ── Yardımcı ─────────────────────────────────────────────────────────────────

def _esc(text: str) -> str:
    """AppleScript için string'deki tırnak işaretlerini kaçır."""
    return text.replace('"', '\\"').replace("'", "\\'")


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
