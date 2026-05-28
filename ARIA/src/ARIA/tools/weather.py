"""Hava durumu — wttr.in JSON API (lokalde, buluta veri gitmiyor)."""

from __future__ import annotations

import logging
import urllib.request
import json

from ARIA.core.config import load_config
from ARIA.core.registry import register_tool

logger = logging.getLogger("aria.tools.weather")


def _fetch(city: str) -> dict:
    url = f"https://wttr.in/{urllib.parse.quote(city)}?format=j1"
    req = urllib.request.Request(url, headers={"User-Agent": "ARIA/1.0"})
    with urllib.request.urlopen(req, timeout=8) as resp:
        return json.loads(resp.read().decode())


import urllib.parse


@register_tool("weather_current")
def weather_current(city: str | None = None) -> dict:
    """Anlık hava durumunu getir.

    Returns:
        {'city': str, 'temp_c': int, 'feels_like_c': int,
         'desc': str, 'humidity': int, 'wind_kmh': int}
    """
    config = load_config()
    city = city or config.weather_city
    try:
        data = _fetch(city)
        cur = data["current_condition"][0]
        desc = cur["lang_tr"][0]["value"] if cur.get("lang_tr") else cur["weatherDesc"][0]["value"]
        return {
            "city": city,
            "temp_c": int(cur["temp_C"]),
            "feels_like_c": int(cur["FeelsLikeC"]),
            "desc": desc,
            "humidity": int(cur["humidity"]),
            "wind_kmh": int(cur["windspeedKmph"]),
            "success": True,
        }
    except Exception as exc:
        logger.warning("Hava durumu alınamadı (%s): %s", city, exc)
        return {"success": False, "error": str(exc), "city": city}


@register_tool("weather_forecast")
def weather_forecast(city: str | None = None, days: int = 3) -> dict:
    """Önümüzdeki günlerin hava tahminini getir.

    Returns:
        {'city': str, 'forecast': list[dict]}
    """
    config = load_config()
    city = city or config.weather_city
    days = min(days, 3)
    try:
        data = _fetch(city)
        forecast = []
        for day_data in data["weather"][:days]:
            desc_list = day_data["hourly"][4].get("lang_tr") or day_data["hourly"][4].get("weatherDesc", [{}])
            desc = desc_list[0].get("value", "") if desc_list else ""
            forecast.append({
                "date": day_data["date"],
                "max_c": int(day_data["maxtempC"]),
                "min_c": int(day_data["mintempC"]),
                "desc": desc,
                "rain_mm": float(day_data["hourly"][4].get("precipMM", 0)),
            })
        return {"city": city, "forecast": forecast, "success": True}
    except Exception as exc:
        logger.warning("Hava tahmini alınamadı (%s): %s", city, exc)
        return {"success": False, "error": str(exc), "city": city}
