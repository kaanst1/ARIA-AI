"""Alarm ve timer — macOS `at` komutu + osascript bildirim + TTS + sabah briefi."""

from __future__ import annotations

import logging
import re
import subprocess
from datetime import datetime, timedelta
from typing import Optional

from ARIA.core.registry import register_tool

logger = logging.getLogger("aria.tools.alarm")

# Sabah alarmlarında otomatik brief tetiklensin mi? (True = tetikle)
MORNING_BRIEF_ON_ALARM = True


def _now() -> datetime:
    return datetime.now()


def _parse_time(time_str: str) -> Optional[datetime]:
    """'10:00', '10', '10:30', '22:00' gibi formatları parse et."""
    time_str = time_str.strip().replace(".", ":")

    # HH:MM
    m = re.match(r"^(\d{1,2}):(\d{2})$", time_str)
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        target = _now().replace(hour=h, minute=mi, second=0, microsecond=0)
        if target <= _now():
            target += timedelta(days=1)
        return target

    # Sadece saat (10 → 10:00)
    m = re.match(r"^(\d{1,2})$", time_str)
    if m:
        h = int(m.group(1))
        target = _now().replace(hour=h, minute=0, second=0, microsecond=0)
        if target <= _now():
            target += timedelta(days=1)
        return target

    return None


def _is_morning_alarm(target: datetime) -> bool:
    """Alarm sabah saatinde mi? (05:00–12:00)"""
    return 5 <= target.hour <= 12


def _trigger_morning_brief() -> None:
    """Sabah briefini arka planda başlat — takvim + sistem + seslendir."""
    try:
        logger.info("Sabah briefi tetikleniyor")
        from ARIA.agents.brief import BriefAgent
        agent = BriefAgent()
        agent.run(speak=True)
    except Exception as exc:
        logger.error("Sabah briefi başlatılamadı: %s", exc)


def _schedule_with_at(target: datetime, message: str, morning_brief: bool = False) -> dict:
    """macOS `at` komutu ile belirli saatte script çalıştır."""
    at_time = target.strftime("%H:%M")

    safe_msg = message.replace('"', '\\"').replace("'", "\\'")

    # Temel alarm: bildirim + TTS
    script_parts = [
        f'osascript -e \'display notification "{safe_msg}" with title "◈ ARIA ALARM" sound name "Glass"\'',
        f'say -v Yelda "{safe_msg}"',
    ]

    # Sabah alarmı: brief de tetikle (curl ile API'ye istek)
    if morning_brief and MORNING_BRIEF_ON_ALARM:
        script_parts.append(
            "sleep 3 && curl -s -X POST http://localhost:8000/brief/morning > /dev/null 2>&1"
        )

    script = " ; ".join(script_parts)

    try:
        proc = subprocess.run(
            ["at", at_time],
            input=script,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode == 0 or "job" in (proc.stderr or "").lower():
            return {
                "success": True,
                "time": at_time,
                "message": message,
                "detail": proc.stderr.strip() or "Alarm kuruldu",
                "morning_brief": morning_brief,
            }
        else:
            # at başarısız → threading ile fallback
            return _schedule_with_threading(target, message, morning_brief=morning_brief)
    except Exception as exc:
        logger.warning("at komutu başarısız: %s, threading'e geçiliyor", exc)
        return _schedule_with_threading(target, message, morning_brief=morning_brief)


def _schedule_with_threading(
    target: datetime, message: str, morning_brief: bool = False
) -> dict:
    """threading.Timer ile alarm — API süresince geçerli."""
    import threading

    delay = (target - _now()).total_seconds()
    if delay < 0:
        return {"success": False, "error": "Geçmiş zaman"}

    def fire():
        # 1. Bildirim
        safe_msg = message.replace('"', '\\"')
        subprocess.run(
            ["osascript", "-e",
             f'display notification "{safe_msg}" with title "◈ ARIA ALARM" sound name "Glass"'],
            capture_output=True,
        )
        # 2. Yelda TTS
        subprocess.run(["say", "-v", "Yelda", message], capture_output=True)
        logger.info("Alarm çaldı: %s", message)

        # 3. Sabah briefi
        if morning_brief and MORNING_BRIEF_ON_ALARM:
            import time
            time.sleep(3)  # TTS bitsin
            brief_thread = threading.Thread(target=_trigger_morning_brief, daemon=True)
            brief_thread.start()

    t = threading.Timer(delay, fire)
    t.daemon = True
    t.start()

    return {
        "success": True,
        "time": target.strftime("%H:%M"),
        "message": message,
        "detail": f"Alarm kuruldu (threading, {int(delay//60)} dakika sonra)",
        "morning_brief": morning_brief,
    }


def set_alarm(
    time_str: str,
    message: str = "Günaydın! ARIA sabah alarmı.",
    morning_brief: bool = False,
) -> dict:
    """Belirtilen saatte macOS bildirimi + Yelda sesiyle alarm kur.

    Args:
        time_str: Saat (örn: '10:00', '10', '22:30')
        message: Alarm mesajı
        morning_brief: True → alarm çalınca sabah briefi de başlat
    """
    target = _parse_time(time_str)
    if not target:
        return {"success": False, "error": f"Saat formatı anlaşılamadı: {time_str}"}

    # Sabah saatiyse morning_brief otomatik True
    if _is_morning_alarm(target):
        morning_brief = True

    minutes_left = int((target - _now()).total_seconds() / 60)
    logger.info(
        "Alarm: %s için '%s' (%d dk sonra, brief=%s)",
        target.strftime("%H:%M"), message, minutes_left, morning_brief,
    )

    result = _schedule_with_at(target, message, morning_brief=morning_brief)
    result["minutes_left"] = minutes_left
    return result


def set_timer(minutes: int, message: str = "Süre doldu!") -> dict:
    """Şu andan itibaren N dakika sonra alarm kur."""
    if minutes <= 0:
        return {"success": False, "error": "Süre 0'dan büyük olmalı"}

    target = _now() + timedelta(minutes=minutes)
    result = _schedule_with_threading(target, message, morning_brief=False)
    result["minutes_left"] = minutes
    return result


def list_alarms() -> dict:
    """Kurulu `at` alarm'larını listele."""
    try:
        proc = subprocess.run(["atq"], capture_output=True, text=True, timeout=5)
        jobs = proc.stdout.strip()
        return {
            "success": True,
            "jobs": jobs if jobs else "(Alarm yok)",
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def cancel_alarm(job_id: int) -> dict:
    """at alarm'ını iptal et."""
    try:
        proc = subprocess.run(["atrm", str(job_id)], capture_output=True, text=True, timeout=5)
        return {"success": proc.returncode == 0}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


# ── Tool kayıtları ────────────────────────────────────────────────────────────

@register_tool("set_alarm")
def set_alarm_tool(time_str: str, message: str = "Günaydın! ARIA sabah alarmı.") -> dict:
    """Belirtilen saatte alarm kur (örn: '10:00'). Sabah saatlerinde otomatik brief tetikler."""
    return set_alarm(time_str, message)


@register_tool("set_timer")
def set_timer_tool(minutes: int, message: str = "Süre doldu!") -> dict:
    """N dakika sonra alarm kur."""
    return set_timer(minutes, message)


@register_tool("list_alarms")
def list_alarms_tool() -> dict:
    """Kurulu alarm'ları listele."""
    return list_alarms()
