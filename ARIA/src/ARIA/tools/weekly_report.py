"""Haftalık / günlük otomatik rapor üreteci — Markdown + macOS bildirimi."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from ARIA.core.registry import register_tool

logger = logging.getLogger("aria.tools.weekly_report")

_ARIA_DIR = Path.home() / ".aria"
_REPORTS_DIR = _ARIA_DIR / "reports"
_REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def _load_usage(days: int = 7) -> dict:
    tracker_file = _ARIA_DIR / "usage.json"
    if not tracker_file.exists():
        return {"sessions": [], "agent_counts": {}, "total_messages": 0}
    data = json.loads(tracker_file.read_text())
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    data["sessions"] = [s for s in data.get("sessions", []) if s.get("timestamp", "") >= cutoff]
    return data


def _load_patterns() -> dict:
    patterns_file = _ARIA_DIR / "patterns.json"
    if not patterns_file.exists():
        return {}
    return json.loads(patterns_file.read_text())


@register_tool("generate_weekly_report")
def generate_weekly_report(save: bool = True) -> dict:
    """Haftalık kullanım raporunu üret ve kaydet.

    Returns:
        {'report': str, 'path': str, 'success': bool}
    """
    data = _load_usage(7)
    patterns = _load_patterns()
    now = datetime.now()
    week_start = (now - timedelta(days=7)).strftime("%d.%m.%Y")
    week_end = now.strftime("%d.%m.%Y")

    sessions = data.get("sessions", [])
    agent_counts = data.get("agent_counts", {})
    total = len(sessions)

    # Saatlik dağılım
    hourly: dict[int, int] = {}
    for s in sessions:
        h = s.get("hour", 0)
        hourly[h] = hourly.get(h, 0) + 1
    peak_hour = max(hourly.items(), key=lambda x: x[1])[0] if hourly else 0

    # En aktif ajan
    top_agents = sorted(agent_counts.items(), key=lambda x: -x[1])[:5]

    # Ortalama yanıt uzunluğu
    avg_resp = int(sum(s.get("response_len", 0) for s in sessions) / max(total, 1))

    # LLM ile yorum
    stats_text = (
        f"Bu hafta {total} mesaj, en çok {top_agents[0][0] if top_agents else '?'} ajanı kullanıldı, "
        f"en yoğun saat {peak_hour}:00, ortalama yanıt {avg_resp} karakter."
    )
    try:
        from ARIA.core.engine import ARIAEngine
        insight = ARIAEngine().chat([{
            "role": "user",
            "content": f"Bu haftalık ARIA kullanım özetini Türkçe 2-3 cümle ile yorumla ve öneri ver:\n{stats_text}"
        }])
    except Exception:
        insight = "Kullanım verisi analiz edildi."

    # Markdown raporu
    lines = [
        f"# ARIA Haftalık Rapor",
        f"**Dönem:** {week_start} — {week_end}",
        f"**Oluşturuldu:** {now.strftime('%d.%m.%Y %H:%M')}",
        "",
        "## Özet İstatistikler",
        f"- Toplam mesaj: **{total}**",
        f"- En yoğun saat: **{peak_hour}:00**",
        f"- Ort. yanıt uzunluğu: **{avg_resp} karakter**",
        "",
        "## Ajan Kullanımı",
    ]
    for agent, count in top_agents:
        lines.append(f"- `{agent}`: {count} kullanım")

    lines += [
        "",
        "## Saatlik Dağılım",
    ]
    for h in sorted(hourly.keys()):
        bar = "█" * min(hourly[h], 20)
        lines.append(f"- {h:02d}:00  {bar} ({hourly[h]})")

    lines += [
        "",
        "## ARIA Yorumu",
        insight,
        "",
        "---",
        f"*ARIA Haftalık Rapor — {now.strftime('%Y-%m-%d')}*",
    ]

    report = "\n".join(lines)

    path = ""
    if save:
        fname = f"weekly_{now.strftime('%Y-%m-%d')}.md"
        report_path = _REPORTS_DIR / fname
        report_path.write_text(report, encoding="utf-8")
        path = str(report_path)
        logger.info("Haftalık rapor kaydedildi: %s", path)

    return {"report": report, "path": path, "success": True, "total_messages": total}


@register_tool("generate_daily_report")
def generate_daily_report(save: bool = True) -> dict:
    """Günlük kullanım raporunu üret.

    Returns:
        {'report': str, 'path': str, 'success': bool}
    """
    data = _load_usage(1)
    now = datetime.now()
    sessions = data.get("sessions", [])
    agent_counts: dict[str, int] = {}
    for s in sessions:
        a = s.get("agent", "chat")
        agent_counts[a] = agent_counts.get(a, 0) + 1

    top = sorted(agent_counts.items(), key=lambda x: -x[1])

    lines = [
        f"# ARIA Günlük Rapor — {now.strftime('%d.%m.%Y')}",
        f"**Toplam mesaj:** {len(sessions)}",
        "",
        "## Ajan Dağılımı",
    ]
    for agent, count in top:
        lines.append(f"- `{agent}`: {count}")

    report = "\n".join(lines)

    path = ""
    if save:
        fname = f"daily_{now.strftime('%Y-%m-%d')}.md"
        report_path = _REPORTS_DIR / fname
        report_path.write_text(report, encoding="utf-8")
        path = str(report_path)

    return {"report": report, "path": path, "success": True}


@register_tool("list_reports")
def list_reports(limit: int = 10) -> dict:
    """Kayıtlı raporları listele.

    Returns:
        {'reports': list[dict]}
    """
    reports = sorted(_REPORTS_DIR.glob("*.md"), reverse=True)[:limit]
    return {
        "reports": [{"name": p.stem, "path": str(p), "size_kb": round(p.stat().st_size / 1024, 1)} for p in reports],
        "count": len(reports),
        "success": True,
    }
