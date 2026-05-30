"""Hava durumu — Open-Meteo API (açık kaynak, ücretsiz, buluta veri gitmiyor)."""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from functools import lru_cache
from typing import Optional

from ARIA.core.config import load_config
from ARIA.core.registry import register_tool

logger = logging.getLogger("aria.tools.weather")

# WMO Weather Code → Türkçe açıklama
_WMO_TR = {
    0: "açık", 1: "çoğunlukla açık", 2: "parçalı bulutlu", 3: "kapalı",
    45: "sisli", 48: "kırağılı sis",
    51: "hafif çiseleyen", 53: "orta çiseleyen", 55: "yoğun çiseleyen",
    61: "hafif yağmurlu", 63: "yağmurlu", 65: "kuvvetli yağmurlu",
    71: "hafif karlı", 73: "karlı", 75: "yoğun karlı",
    77: "kar taneli",
    80: "hafif sağanak", 81: "sağanak", 82: "kuvvetli sağanak",
    85: "hafif kar sağanağı", 86: "yoğun kar sağanağı",
    95: "gök gürültülü fırtına",
    96: "hafif dolu ile fırtına", 99: "dolu ile fırtına",
}


def _wmo_desc(code: int) -> str:
    return _WMO_TR.get(code, f"kod:{code}")


def _fetch_url(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "ARIA/1.0"})
    with urllib.request.urlopen(req, timeout=8) as resp:
        return json.loads(resp.read().decode())


@lru_cache(maxsize=32)
def _geocode(city: str) -> tuple[float, float]:
    """Şehir adını koordinata çevir (Open-Meteo Geocoding)."""
    url = (
        "https://geocoding-api.open-meteo.com/v1/search?"
        + urllib.parse.urlencode({"name": city, "count": 1, "language": "tr", "format": "json"})
    )
    data = _fetch_url(url)
    results = data.get("results", [])
    if not results:
        raise ValueError(f"Şehir bulunamadı: {city}")
    return float(results[0]["latitude"]), float(results[0]["longitude"])


@register_tool("weather_current")
def weather_current(city: Optional[str] = None) -> dict:
    """Anlık hava durumunu getir (Open-Meteo).

    Returns:
        {'city': str, 'temp_c': float, 'feels_like_c': float,
         'desc': str, 'humidity': int, 'wind_kmh': float, 'success': bool}
    """
    config = load_config()
    city = city or config.weather_city
    try:
        lat, lon = _geocode(city)
        url = (
            "https://api.open-meteo.com/v1/forecast?"
            + urllib.parse.urlencode({
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m",
                "timezone": "auto",
                "forecast_days": 1,
            })
        )
        data = _fetch_url(url)
        cur = data["current"]
        return {
            "city": city,
            "temp_c": round(cur["temperature_2m"], 1),
            "feels_like_c": round(cur["apparent_temperature"], 1),
            "desc": _wmo_desc(cur["weather_code"]),
            "humidity": int(cur["relative_humidity_2m"]),
            "wind_kmh": round(cur["wind_speed_10m"], 1),
            "success": True,
        }
    except Exception as exc:
        logger.warning("Hava durumu alınamadı (%s): %s", city, exc)
        return {"success": False, "error": str(exc), "city": city}


@register_tool("weather_forecast")
def weather_forecast(city: Optional[str] = None, days: int = 3) -> dict:
    """Önümüzdeki günlerin hava tahminini getir (Open-Meteo).

    Returns:
        {'city': str, 'forecast': list[dict], 'success': bool}
    """
    config = load_config()
    city = city or config.weather_city
    days = min(days, 7)
    try:
        lat, lon = _geocode(city)
        url = (
            "https://api.open-meteo.com/v1/forecast?"
            + urllib.parse.urlencode({
                "latitude": lat,
                "longitude": lon,
                "daily": "temperature_2m_max,temperature_2m_min,weather_code,precipitation_sum,wind_speed_10m_max",
                "timezone": "auto",
                "forecast_days": days,
            })
        )
        data = _fetch_url(url)
        daily = data["daily"]
        forecast = [
            {
                "date": daily["time"][i],
                "max_c": round(daily["temperature_2m_max"][i], 1),
                "min_c": round(daily["temperature_2m_min"][i], 1),
                "desc": _wmo_desc(daily["weather_code"][i]),
                "rain_mm": round(daily["precipitation_sum"][i] or 0, 1),
                "wind_kmh": round(daily["wind_speed_10m_max"][i], 1),
            }
            for i in range(len(daily["time"]))
        ]
        return {"city": city, "forecast": forecast, "success": True}
    except Exception as exc:
        logger.warning("Hava tahmini alınamadı (%s): %s", city, exc)
        return {"success": False, "error": str(exc), "city": city}
