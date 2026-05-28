# ARIA - Brief Agent (Sabah Özeti) — Takvim + Sistem Entegrasyonu

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from ARIA.core.engine import ARIAEngine
from ARIA.core.config import load_config
from ARIA.core.registry import register_agent

logger = logging.getLogger("aria.agents.brief")

BRIEF_SYSTEM_PROMPT = """Sen ARIA'nın Sabah Özeti ajanısın.
Meriç'e her sabah kişisel, net ve motive edici bir günlük brifing sunarsın.

Kurallar:
- Bugünün takvim etkinliklerini zaman sırasıyla listele
- Haftanın önemli etkinliklerini vurgula
- Kısa ama etkili yaz — bullet point'ler kullan
- Türkçe konuş, samimi ama profesyonel
- Asla boş, genel kalıp cümleler yazma
- Etkinlik yoksa "bugün boş, verimli çalışma günü" de
- Sabah saatine uygun selamlama kullan
- Sistem durumunu kısaca belirt (CPU/RAM)
- Motive edici bir kapanış cümlesi ekle"""


def _get_calendar_data() -> tuple[list[dict], list[dict]]:
    """Bugünkü ve haftanın takvim verilerini çek."""
    try:
        from ARIA.tools.calendar_tools import get_today_events, get_week_events
        today = get_today_events()
        week = get_week_events()
        # Bugünküleri haftalık listeden çıkar (mükerrer olmasın)
        today_titles = {e["title"] for e in today}
        week_rest = [e for e in week if e["title"] not in today_titles]
        return today, week_rest
    except Exception as exc:
        logger.warning("Takvim verisi alınamadı: %s", exc)
        return [], []


def _get_system_stats() -> Optional[dict]:
    """CPU ve RAM durumunu çek."""
    try:
        from ARIA.tools.system_monitor import get_system_stats, PSUTIL_AVAILABLE
        if not PSUTIL_AVAILABLE:
            return None
        stats = get_system_stats()
        return {
            "cpu": stats["cpu"].get("percent", 0),
            "ram_used": stats["memory"].get("used_gb", 0),
            "ram_total": stats["memory"].get("total_gb", 0),
            "ram_pct": stats["memory"].get("percent", 0),
            "ollama": stats["ollama"].get("running", False),
        }
    except Exception as exc:
        logger.warning("Sistem istatistikleri alınamadı: %s", exc)
        return None


def _format_calendar_section(today_events: list[dict], week_events: list[dict]) -> str:
    """Takvim bölümünü formatla."""
    now = datetime.now()
    today_str = now.strftime("%-d %B %Y, %A")
    lines: list[str] = []

    # Bugün
    lines.append(f"📅 BUGÜN — {today_str}")
    if today_events:
        for ev in today_events:
            loc = f" @ {ev['location']}" if ev.get("location") else ""
            cal = f"[{ev['calendar']}]" if ev.get("calendar") else ""
            lines.append(f"  • {ev['start']} - {ev['end']}  {ev['title']}{loc}  {cal}".rstrip())
    else:
        lines.append("  • Bugün takvimde etkinlik yok — odaklanmak için ideal gün!")

    # Bu hafta (kalan)
    if week_events:
        lines.append(f"\n📆 BU HAFTA GELENLER — {len(week_events)} etkinlik")
        for ev in week_events[:5]:  # max 5
            loc = f" @ {ev['location']}" if ev.get("location") else ""
            lines.append(f"  • {ev['start']}  {ev['title']}{loc}")
        if len(week_events) > 5:
            lines.append(f"  … ve {len(week_events) - 5} etkinlik daha")

    return "\n".join(lines)


def _format_system_section(stats: Optional[dict]) -> str:
    """Sistem durumunu formatla."""
    if not stats:
        return ""
    ollama_icon = "✅" if stats["ollama"] else "⚠️"
    return (
        f"🖥️  SİSTEM — CPU: %{stats['cpu']:.0f}  |  "
        f"RAM: {stats['ram_used']:.1f}/{stats['ram_total']:.0f} GB (%{stats['ram_pct']:.0f})  |  "
        f"Ollama: {ollama_icon}"
    )


@register_agent("brief")
class BriefAgent:
    """Sabah özeti ajanı — takvim + sistem + LLM brief."""

    def __init__(self):
        self.engine = ARIAEngine()
        self.engine.config = load_config()

    def run(self, speak: bool = False) -> str:
        """Takvim destekli sabah briefi üret."""
        now = datetime.now()
        tarih = now.strftime("%-d %B %Y, %A")
        saat = now.strftime("%H:%M")

        # Takvim ve sistem verisi
        today_events, week_events = _get_calendar_data()
        sys_stats = _get_system_stats()

        cal_section = _format_calendar_section(today_events, week_events)
        sys_section = _format_system_section(sys_stats)

        prompt = f"""Tarih: {tarih}  |  Saat: {saat}

{cal_section}

{sys_section}

Yukarıdaki verileri kullanarak Meriç için kısa ve etkili bir sabah briefi yaz.
Takvim etkinliklerini Türkçe olarak özetle, günün nasıl geçeceğini yorumla.
Sistem durumu normalse söyleme, anormal ise dikkat çek.
Motivasyon cümlesiyle bitir."""

        messages = [
            {"role": "system", "content": BRIEF_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        brief_text = self.engine.chat(messages)

        # TTS — isterse seslendir
        if speak:
            try:
                from ARIA.tools.tts import speak as tts_speak
                tts_speak(brief_text, lang="tr", block=False)
            except Exception as exc:
                logger.warning("TTS hatası: %s", exc)

        return brief_text

    def handle(self, user_input: str) -> str:
        """Orchestrator çağrısı — brief üret ve seslendir."""
        text = user_input.lower()
        # "günaydın", "iyi sabahlar", "sabah briefi" → seslendirerek üret
        should_speak = any(k in text for k in [
            "günaydın", "gunaydin", "iyi sabahlar", "sabah briefi",
            "günaydın", "morning", "briefi ver", "briefi başlat",
        ])
        return self.run(speak=should_speak)

    def scheduled_run(self):
        """ProactiveScheduler tarafından çağrılır."""
        logger.info("Sabah briefi üretiliyor (scheduled)")
        brief = self.run(speak=True)
        logger.info("Sabah briefi tamamlandı: %d karakter", len(brief))
        return brief
