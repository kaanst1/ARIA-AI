"""Apple Health entegrasyonu — Shortcuts export veya HealthKit CSV."""

from __future__ import annotations

import csv
import json
import logging
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from ARIA.core.registry import register_tool

logger = logging.getLogger("aria.tools.health")

_ARIA_DIR = Path.home() / ".aria"
_HEALTH_DIR = _ARIA_DIR / "health"
_HEALTH_DIR.mkdir(parents=True, exist_ok=True)
_HEALTH_CACHE = _HEALTH_DIR / "health_cache.json"


def _load_cache() -> dict:
    if _HEALTH_CACHE.exists():
        try:
            return json.loads(_HEALTH_CACHE.read_text())
        except Exception:
            pass
    return {}


def _save_cache(data: dict) -> None:
    _HEALTH_CACHE.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def _run_shortcut(name: str) -> str:
    """Apple Shortcuts ile sağlık verisi çek."""
    try:
        r = subprocess.run(
            ["shortcuts", "run", name],
            capture_output=True, text=True, timeout=15,
        )
        return r.stdout.strip()
    except Exception:
        return ""


@register_tool("health_get_steps")
def health_get_steps(days: int = 7) -> dict:
    """Adım sayısı verisini getir (Apple Shortcuts entegrasyonu).

    Kullanım: Apple Shortcuts'ta 'ARIA Health Steps' adlı bir shortcut oluştur,
    Health app'ten adım sayısını JSON olarak döndürsün.

    Returns:
        {'today': int, 'average_7d': int, 'data': list[dict]}
    """
    # Önce cache'i dene
    cache = _load_cache()
    today_str = datetime.now().strftime("%Y-%m-%d")

    if cache.get("steps", {}).get("date") == today_str:
        return {**cache["steps"], "success": True, "source": "cache"}

    # Shortcuts dene
    raw = _run_shortcut("ARIA Health Steps")
    if raw:
        try:
            data = json.loads(raw)
            cache["steps"] = {**data, "date": today_str}
            _save_cache(cache)
            return {**data, "success": True, "source": "shortcuts"}
        except Exception:
            pass

    # CSV dosyasından oku (Apple Health Export)
    export_path = Path.home() / "Downloads" / "apple_health_export" / "export.csv"
    if export_path.exists():
        return _parse_health_csv(export_path, "HKQuantityTypeIdentifierStepCount", days)

    return {
        "success": False,
        "error": "Sağlık verisi alınamadı. 'ARIA Health Steps' shortcut'ı oluştur veya Apple Health export yap.",
        "today": 0,
        "average_7d": 0,
    }


def _parse_health_csv(path: Path, metric: str, days: int) -> dict:
    """Apple Health export CSV'sinden metrik çıkar."""
    try:
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        daily: dict[str, float] = {}

        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("type") == metric and row.get("startDate", "") >= cutoff:
                    date = row["startDate"][:10]
                    daily[date] = daily.get(date, 0) + float(row.get("value", 0))

        if not daily:
            return {"success": True, "today": 0, "average_7d": 0, "data": [], "source": "csv"}

        today_str = datetime.now().strftime("%Y-%m-%d")
        today_val = int(daily.get(today_str, 0))
        avg = int(sum(daily.values()) / len(daily))
        data = [{"date": d, "value": int(v)} for d, v in sorted(daily.items())]

        return {"success": True, "today": today_val, "average_7d": avg, "data": data[-days:], "source": "csv"}
    except Exception as exc:
        return {"success": False, "error": str(exc), "today": 0, "average_7d": 0}


@register_tool("health_summary")
def health_summary() -> dict:
    """Günlük sağlık özetini döndür (adım + uyku eğer mevcut ise).

    Returns:
        {'summary': str, 'data': dict}
    """
    cache = _load_cache()
    today_str = datetime.now().strftime("%Y-%m-%d")

    steps_data = health_get_steps(1)
    steps_today = steps_data.get("today", 0)
    steps_avg = steps_data.get("average_7d", 0)

    parts = []
    data = {}

    if steps_today:
        pct = int(steps_today / max(steps_avg, 1) * 100) if steps_avg else 0
        icon = "🟢" if steps_today >= 8000 else ("🟡" if steps_today >= 5000 else "🔴")
        parts.append(f"{icon} Adım: {steps_today:,} (7 günlük ort: {steps_avg:,})")
        data["steps"] = steps_today

    # Uyku — cache'den
    sleep = cache.get("sleep", {})
    if sleep.get("date") == today_str:
        hours = sleep.get("hours", 0)
        parts.append(f"😴 Uyku: {hours:.1f} saat")
        data["sleep_hours"] = hours

    if not parts:
        return {
            "summary": "Sağlık verisi mevcut değil. Apple Health Export'u indir veya shortcut oluştur.",
            "data": {},
            "success": False,
        }

    return {"summary": " | ".join(parts), "data": data, "success": True}


@register_tool("health_save_manual")
def health_save_manual(metric: str, value: float, unit: str = "") -> dict:
    """Sağlık verisini elle kaydet (shortcut veya export yoksa).

    Args:
        metric: 'steps', 'sleep_hours', 'weight_kg', 'heart_rate'
        value: Değer
        unit: Birim (opsiyonel)

    Returns:
        {'success': bool}
    """
    cache = _load_cache()
    today_str = datetime.now().strftime("%Y-%m-%d")

    if metric not in cache:
        cache[metric] = {}
    cache[metric] = {"date": today_str, "value": value, "unit": unit}
    _save_cache(cache)
    return {"success": True, "metric": metric, "value": value}
