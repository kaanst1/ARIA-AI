"""Proaktif Scheduler — zamanlanmış görevler ve bildirimler."""

from __future__ import annotations

import json
import logging
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    import schedule
    SCHEDULE_AVAILABLE = True
except ImportError:
    SCHEDULE_AVAILABLE = False

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

logger = logging.getLogger("aria.scheduler.proactive")

_ARIA_DIR = Path.home() / ".aria"
_REPORTS_DIR = _ARIA_DIR / "reports"


def _send_macos_notification(title: str, message: str) -> None:
    """macOS bildirimi gönder."""
    try:
        script = f'''display notification "{message}" with title "{title}" sound name "Basso"'''
        subprocess.run(["osascript", "-e", script], capture_output=True, timeout=5)
    except Exception as exc:
        logger.warning("Bildirim gönderilemedi: %s", exc)


def _check_system_resources() -> None:
    """CPU ve RAM kullanımını kontrol et, yüksekse uyar."""
    if not PSUTIL_AVAILABLE:
        return
    try:
        cpu = psutil.cpu_percent(interval=1)
        ram = psutil.virtual_memory().percent
        if cpu > 90:
            _send_macos_notification("ARIA Uyarı", f"CPU kullanımı yüksek: %{cpu:.0f}")
        if ram > 90:
            _send_macos_notification("ARIA Uyarı", f"RAM kullanımı yüksek: %{ram:.0f}")
    except Exception as exc:
        logger.error("Sistem kontrolü hatası: %s", exc)


def _morning_brief() -> None:
    """Sabah briefi üret ve bildir."""
    try:
        from ARIA.agents.brief import BriefAgent
        agent = BriefAgent()
        brief = agent.run()
        _send_macos_notification("ARIA Sabah Briefi", brief[:200])
        logger.info("Sabah briefi gönderildi")
    except Exception as exc:
        logger.error("Sabah briefi hatası: %s", exc)


def _daily_summary() -> None:
    """Günlük özet üret ve kaydet."""
    try:
        _REPORTS_DIR.mkdir(parents=True, exist_ok=True)

        from ARIA.core.engine import ARIAEngine
        from ARIA.learning.tracker import UsageTracker

        tracker = UsageTracker()
        stats = tracker.stats()

        engine = ARIAEngine()
        messages = [
            {
                "role": "system",
                "content": "Sen bir günlük rapor asistanısın. Kısa, öz günlük özet yaz.",
            },
            {
                "role": "user",
                "content": (
                    f"Bugün {datetime.now().strftime('%d %B %Y')}\n"
                    f"Kullanım istatistikleri:\n{stats}\n\n"
                    "Kısa günlük özet hazırla."
                ),
            },
        ]
        summary = engine.chat(messages)

        # Dosyaya kaydet
        date_str = datetime.now().strftime("%Y-%m-%d")
        report_path = _REPORTS_DIR / f"{date_str}.md"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(f"# ARIA Günlük Raporu — {date_str}\n\n")
            f.write(summary)
            f.write(f"\n\n---\n*Oluşturulma: {datetime.now().isoformat()}*\n")

        _send_macos_notification("ARIA", "Günlük rapor hazırlandı")
        logger.info("Günlük rapor kaydedildi: %s", report_path)
    except Exception as exc:
        logger.error("Günlük özet hatası: %s", exc)


def _check_rss_feeds() -> None:
    """RSS feed'lerini kontrol et, yeni içerik varsa bildir."""
    try:
        from ARIA.tools.rss_reader import _feed_manager
        items = _feed_manager.get_all_latest(n=2)
        if items and not items[0].get("error"):
            count = len([i for i in items if not i.get("error")])
            if count > 0:
                first = items[0]
                title = first.get("title", "Yeni haber")[:60]
                _send_macos_notification("ARIA — Yeni İçerik", f"{count} yeni haber: {title}")
    except Exception as exc:
        logger.warning("RSS kontrolü hatası: %s", exc)


class ProactiveScheduler:
    """Arka planda çalışan zamanlanmış görevler."""

    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        self._running = False

    def _setup_jobs(self) -> None:
        """Zamanlanmış görevleri tanımla."""
        if not SCHEDULE_AVAILABLE:
            logger.warning("schedule kütüphanesi yüklü değil")
            return

        # Sabah 08:00 — brief
        schedule.every().day.at("08:00").do(_morning_brief)

        # Her 5 dakika — kaynak kontrolü
        schedule.every(5).minutes.do(_check_system_resources)

        # Her gece 21:00 — günlük rapor
        schedule.every().day.at("21:00").do(_daily_summary)

        # Her saat — RSS feed kontrolü
        schedule.every(1).hours.do(_check_rss_feeds)

        logger.info("Proaktif zamanlayıcı görevleri kuruldu")

    def _run_loop(self) -> None:
        """Ana çalışma döngüsü."""
        if not SCHEDULE_AVAILABLE:
            return

        import time
        self._setup_jobs()
        logger.info("ProactiveScheduler çalışmaya başladı")

        while self._running:
            try:
                schedule.run_pending()
            except Exception as exc:
                logger.error("Zamanlayıcı döngüsü hatası: %s", exc)
            time.sleep(30)  # 30 saniyede bir kontrol

    def start_background(self) -> None:
        """Daemon thread olarak başlat."""
        if self._thread and self._thread.is_alive():
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop,
            daemon=True,
            name="aria-proactive-scheduler",
        )
        self._thread.start()
        logger.info("ProactiveScheduler arka planda başlatıldı")

    def stop(self) -> None:
        """Durdur."""
        self._running = False
        if SCHEDULE_AVAILABLE:
            schedule.clear()
        logger.info("ProactiveScheduler durduruldu")

    def get_daily_report(self) -> Optional[str]:
        """Son günlük raporu döndür."""
        _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        reports = sorted(_REPORTS_DIR.glob("*.md"), reverse=True)
        if not reports:
            return None
        try:
            with open(reports[0], encoding="utf-8") as f:
                return f.read()
        except Exception:
            return None
