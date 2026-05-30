"""Gerçek zamanlı uptime / API health izleme — çöktüğünde bildirim at."""

from __future__ import annotations

import json
import logging
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

from ARIA.core.registry import register_tool

logger = logging.getLogger("aria.tools.uptime")

_ARIA_DIR = Path.home() / ".aria"
_MONITORS_FILE = _ARIA_DIR / "uptime_monitors.json"
_STATUS_FILE = _ARIA_DIR / "uptime_status.json"
_ARIA_DIR.mkdir(parents=True, exist_ok=True)

_monitor_thread: Optional[threading.Thread] = None
_running = False


def _load_monitors() -> list[dict]:
    if _MONITORS_FILE.exists():
        try:
            return json.loads(_MONITORS_FILE.read_text())
        except Exception:
            pass
    return []


def _save_monitors(monitors: list[dict]) -> None:
    _MONITORS_FILE.write_text(json.dumps(monitors, ensure_ascii=False, indent=2))


def _load_status() -> dict:
    if _STATUS_FILE.exists():
        try:
            return json.loads(_STATUS_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_status(status: dict) -> None:
    _STATUS_FILE.write_text(json.dumps(status, ensure_ascii=False, indent=2))


def _notify(title: str, message: str, sound: str = "Basso") -> None:
    script = f'display notification "{message}" with title "{title}" sound name "{sound}"'
    try:
        subprocess.run(["osascript", "-e", script], capture_output=True, timeout=5)
    except Exception:
        pass


def _check_endpoint(monitor: dict) -> dict:
    """Tek bir endpoint'i kontrol et."""
    url = monitor["url"]
    timeout = monitor.get("timeout", 10)
    expected_status = monitor.get("expected_status", 200)
    keyword = monitor.get("keyword")  # Yanıtta bu metin olmalı

    result = {
        "url": url,
        "name": monitor.get("name", url),
        "checked_at": datetime.now().isoformat(),
        "up": False,
        "status_code": None,
        "response_ms": None,
        "error": None,
    }

    try:
        start = time.time()
        resp = requests.get(url, timeout=timeout, allow_redirects=True)
        elapsed = int((time.time() - start) * 1000)

        result["status_code"] = resp.status_code
        result["response_ms"] = elapsed
        result["up"] = (resp.status_code == expected_status)

        if keyword and keyword not in resp.text:
            result["up"] = False
            result["error"] = f"Keyword bulunamadı: '{keyword}'"

    except requests.exceptions.ConnectionError:
        result["error"] = "Bağlantı reddedildi"
    except requests.exceptions.Timeout:
        result["error"] = f"{timeout}s timeout"
    except Exception as exc:
        result["error"] = str(exc)

    return result


def _monitor_loop() -> None:
    global _running
    status = _load_status()
    logger.info("Uptime monitor başladı")

    while _running:
        monitors = _load_monitors()
        now_status = {}

        for monitor in monitors:
            url = monitor["url"]
            name = monitor.get("name", url)
            interval = monitor.get("interval_sec", 60)
            prev = status.get(url, {})

            # Kontrol zamanı geldi mi?
            last_check = prev.get("checked_at", "")
            if last_check:
                elapsed = (datetime.now() - datetime.fromisoformat(last_check)).total_seconds()
                if elapsed < interval:
                    now_status[url] = prev
                    continue

            result = _check_endpoint(monitor)
            was_up = prev.get("up", True)

            # Durum değişti mi?
            if was_up and not result["up"]:
                error = result.get("error") or f"HTTP {result.get('status_code')}"
                _notify(f"⛔ {name} ÇÖKTÜ", error, sound="Sosumi")
                logger.warning("DOWN: %s — %s", name, error)
            elif not was_up and result["up"]:
                ms = result.get("response_ms", "?")
                _notify(f"✅ {name} DÜZELDI", f"{ms}ms yanıt süresi", sound="Glass")
                logger.info("UP: %s — %sms", name, ms)

            now_status[url] = result

        status = now_status
        _save_status(status)
        time.sleep(10)  # Her 10 saniyede interval kontrolü


def start_uptime_monitor() -> bool:
    global _monitor_thread, _running
    if _monitor_thread and _monitor_thread.is_alive():
        return True
    _running = True
    _monitor_thread = threading.Thread(target=_monitor_loop, daemon=True, name="aria-uptime")
    _monitor_thread.start()
    logger.info("Uptime monitor başlatıldı")
    return True


def stop_uptime_monitor() -> None:
    global _running
    _running = False


@register_tool("uptime_add")
def uptime_add(
    url: str,
    name: str = "",
    interval_sec: int = 60,
    expected_status: int = 200,
    keyword: Optional[str] = None,
) -> dict:
    """İzlenecek endpoint ekle.

    Args:
        url: İzlenecek URL
        name: Tanımlayıcı isim
        interval_sec: Kontrol aralığı (saniye)
        expected_status: Beklenen HTTP durum kodu
        keyword: Yanıtta bulunması gereken metin

    Returns:
        {'success': bool, 'name': str, 'url': str}
    """
    monitors = _load_monitors()
    if any(m["url"] == url for m in monitors):
        return {"success": False, "error": f"{url} zaten izleniyor"}

    monitor = {
        "url": url,
        "name": name or url,
        "interval_sec": interval_sec,
        "expected_status": expected_status,
        "added_at": datetime.now().isoformat(),
    }
    if keyword:
        monitor["keyword"] = keyword

    monitors.append(monitor)
    _save_monitors(monitors)
    return {"success": True, "name": monitor["name"], "url": url}


@register_tool("uptime_remove")
def uptime_remove(url: str) -> dict:
    """İzlemeyi kaldır.

    Returns:
        {'success': bool}
    """
    monitors = _load_monitors()
    new = [m for m in monitors if m["url"] != url]
    if len(new) == len(monitors):
        return {"success": False, "error": "Bulunamadı"}
    _save_monitors(new)
    return {"success": True, "removed": url}


@register_tool("uptime_status")
def uptime_status() -> dict:
    """Tüm monitörlerin mevcut durumunu döndür.

    Returns:
        {'monitors': list[dict], 'up': int, 'down': int}
    """
    status = _load_status()
    monitors = _load_monitors()
    results = []

    for m in monitors:
        url = m["url"]
        s = status.get(url, {"up": None, "checked_at": None})
        results.append({
            "name": m.get("name", url),
            "url": url,
            "up": s.get("up"),
            "response_ms": s.get("response_ms"),
            "last_checked": s.get("checked_at", "")[:19],
            "error": s.get("error"),
        })

    up = sum(1 for r in results if r["up"] is True)
    down = sum(1 for r in results if r["up"] is False)
    return {"monitors": results, "up": up, "down": down, "total": len(results), "success": True}


@register_tool("uptime_check_now")
def uptime_check_now(url: str) -> dict:
    """Belirli bir URL'yi hemen kontrol et.

    Returns:
        {'up': bool, 'response_ms': int, 'status_code': int}
    """
    monitors = _load_monitors()
    monitor = next((m for m in monitors if m["url"] == url), {"url": url, "name": url})
    return _check_endpoint(monitor)
