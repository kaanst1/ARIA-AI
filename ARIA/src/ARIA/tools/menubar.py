"""macOS Menu Bar entegrasyonu — rumps ile sistem tepsisi ikonu."""

from __future__ import annotations

import logging
import subprocess
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger("aria.tools.menubar")

_API_URL = "http://localhost:8000"
_menubar_thread: Optional[threading.Thread] = None
_menubar_app = None


def _run_menubar() -> None:
    try:
        import rumps

        class ARIAMenuBar(rumps.App):
            def __init__(self):
                super().__init__(
                    "ARIA",
                    icon=str(Path(__file__).parent.parent.parent.parent.parent / "frontend/public/icon-192.png"),
                    quit_button=None,
                )
                self.menu = [
                    rumps.MenuItem("Sabah Briefi", callback=self.morning_brief),
                    rumps.MenuItem("Hava Durumu", callback=self.weather),
                    rumps.MenuItem("Pomodoro Başlat", callback=self.start_pomodoro),
                    rumps.MenuItem("Pomodoro Durdur", callback=self.stop_pomodoro),
                    None,  # separator
                    rumps.MenuItem("ARIA'yı Aç", callback=self.open_aria),
                    rumps.MenuItem("Sistem Durumu", callback=self.system_status),
                    None,
                    rumps.MenuItem("Çıkış", callback=self.quit_app),
                ]

            def _api(self, endpoint: str, method: str = "GET", json_data=None) -> dict:
                import requests
                try:
                    if method == "POST":
                        r = requests.post(f"{_API_URL}{endpoint}", json=json_data or {}, timeout=10)
                    else:
                        r = requests.get(f"{_API_URL}{endpoint}", timeout=10)
                    return r.json()
                except Exception as exc:
                    return {"error": str(exc)}

            def morning_brief(self, _):
                data = self._api("/chat", "POST", {"message": "sabah briefi", "agent": "brief"})
                response = data.get("response", "Brief alınamadı")[:200]
                rumps.notification("ARIA Sabah Briefi", "", response)

            def weather(self, _):
                data = self._api("/weather")
                if data.get("success"):
                    msg = f"{data['city']}: {data['temp_c']}°C, {data['desc']}"
                    rumps.notification("ARIA Hava Durumu", "", msg)
                else:
                    rumps.notification("ARIA", "", "Hava durumu alınamadı")

            def start_pomodoro(self, _):
                data = self._api("/pomodoro/start", "POST")
                msg = data.get("message", "Pomodoro başlatıldı")
                rumps.notification("ARIA Pomodoro", "", msg)

            def stop_pomodoro(self, _):
                self._api("/pomodoro/stop", "POST")
                rumps.notification("ARIA Pomodoro", "", "Pomodoro durduruldu")

            def open_aria(self, _):
                subprocess.run(["open", "http://localhost:5173"], capture_output=True)

            def system_status(self, _):
                data = self._api("/status")
                model = data.get("model", "?")
                ollama = "✅" if data.get("ollama_running") else "❌"
                rumps.notification("ARIA Sistem", f"Model: {model}", f"Ollama: {ollama}")

            def quit_app(self, _):
                rumps.quit_application()

        app = ARIAMenuBar()
        app.run()

    except ImportError:
        logger.warning("rumps kurulu değil. Menu bar devre dışı. 'pip install rumps' ile kur.")
    except Exception as exc:
        logger.error("Menu bar başlatılamadı: %s", exc)


def start_menubar() -> bool:
    """Menu bar uygulamasını ayrı thread'de başlat.

    Returns:
        True if başlatıldı
    """
    global _menubar_thread
    try:
        import rumps
    except ImportError:
        logger.warning("rumps yok — menu bar devre dışı")
        return False

    if _menubar_thread and _menubar_thread.is_alive():
        return True

    _menubar_thread = threading.Thread(target=_run_menubar, daemon=True, name="aria-menubar")
    _menubar_thread.start()
    logger.info("Menu bar başlatıldı")
    return True
