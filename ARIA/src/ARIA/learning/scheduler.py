# ARIA - Scheduler (Zamanlanmış Görevler)

import schedule
import time
import threading
from datetime import datetime

class ARIAScheduler:
    def __init__(self):
        self.jobs = []
        self.running = False

    def add_daily_brief(self, hour: int = 8, minute: int = 0):
        """Her gün belirli saatte brief çalıştır"""
        from ARIA.agents.brief import BriefAgent
        
        def run_brief():
            print(f"\n⏰ Zamanlanmış Brief — {datetime.now().strftime('%H:%M')}")
            BriefAgent().scheduled_run()

        time_str = f"{hour:02d}:{minute:02d}"
        schedule.every().day.at(time_str).do(run_brief)
        print(f"✅ Sabah briefi ayarlandı: {time_str}")

    def add_monitor_check(self, interval_hours: int = 6):
        """Periyodik monitor kontrolü"""
        from ARIA.agents.monitor import MonitorAgent

        def run_monitors():
            print(f"\n📡 Monitor Kontrolü — {datetime.now().strftime('%H:%M')}")
            MonitorAgent().run_all()

        schedule.every(interval_hours).hours.do(run_monitors)
        print(f"✅ Monitor kontrolü ayarlandı: her {interval_hours} saatte")

    def start(self, background: bool = True):
        """Scheduler'ı başlat"""
        self.running = True
        print("🕐 ARIA Scheduler başlatıldı")

        def run():
            while self.running:
                schedule.run_pending()
                time.sleep(30)

        if background:
            t = threading.Thread(target=run, daemon=True)
            t.start()
        else:
            run()

    def stop(self):
        self.running = False
        print("🛑 Scheduler durduruldu")


_scheduler_singleton: ARIAScheduler | None = None


def get_scheduler() -> ARIAScheduler:
    global _scheduler_singleton
    if _scheduler_singleton is None:
        _scheduler_singleton = ARIAScheduler()
    return _scheduler_singleton


if __name__ == "__main__":
    scheduler = ARIAScheduler()
    scheduler.add_daily_brief(hour=8, minute=0)
    scheduler.add_monitor_check(interval_hours=6)
    scheduler.start(background=False)