"""Spotify Desktop kontrolü — osascript (AppleScript) üzerinden."""

from __future__ import annotations

import logging
import subprocess
from typing import Optional

from ARIA.core.registry import register_tool

logger = logging.getLogger("aria.tools.spotify")


def _run_applescript(script: str) -> str:
    """AppleScript çalıştır ve çıktısını döndür."""
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "AppleScript hatası")
    return result.stdout.strip()


def _spotify_running() -> bool:
    """Spotify'ın çalışıp çalışmadığını kontrol et."""
    try:
        out = subprocess.run(
            ["osascript", "-e", 'tell application "System Events" to (name of processes) contains "Spotify"'],
            capture_output=True, text=True, timeout=5,
        )
        return "true" in out.stdout.lower()
    except Exception:
        return False


def _ensure_spotify() -> None:
    """Spotify açık değilse başlat."""
    if not _spotify_running():
        subprocess.Popen(["open", "-a", "Spotify"])
        import time
        time.sleep(2)


@register_tool("spotify_play")
def spotify_play(query: Optional[str] = None) -> dict:
    """Spotify'da çal. query varsa ara ve çal, yoksa mevcut çalmaya devam et.

    Args:
        query: Aranacak şarkı/sanatçı/albüm adı (opsiyonel)
    """
    try:
        _ensure_spotify()
        if query:
            # Spotify URI araması — önce search URL ile aç
            import urllib.parse
            encoded = urllib.parse.quote(query)
            # Spotify'ın search'ünü URI ile tetikle
            script = f"""
tell application "Spotify"
    activate
    search "{query}"
    play
end tell
"""
            try:
                _run_applescript(script)
            except Exception:
                # Fallback: sadece play
                _run_applescript('tell application "Spotify" to play')
        else:
            _run_applescript('tell application "Spotify" to play')

        current = spotify_current()
        return {"success": True, "action": "play", "query": query, **current}
    except Exception as exc:
        logger.error("Spotify play hatası: %s", exc)
        return {"success": False, "error": str(exc)}


@register_tool("spotify_pause")
def spotify_pause() -> dict:
    """Spotify'ı durdur/devam ettir."""
    try:
        _ensure_spotify()
        _run_applescript('tell application "Spotify" to pause')
        return {"success": True, "action": "pause"}
    except Exception as exc:
        logger.error("Spotify pause hatası: %s", exc)
        return {"success": False, "error": str(exc)}


@register_tool("spotify_next")
def spotify_next() -> dict:
    """Spotify'da bir sonraki şarkıya geç."""
    try:
        _ensure_spotify()
        _run_applescript('tell application "Spotify" to next track')
        import time
        time.sleep(0.5)
        current = spotify_current()
        return {"success": True, "action": "next", **current}
    except Exception as exc:
        logger.error("Spotify next hatası: %s", exc)
        return {"success": False, "error": str(exc)}


@register_tool("spotify_previous")
def spotify_previous() -> dict:
    """Spotify'da bir önceki şarkıya geç."""
    try:
        _ensure_spotify()
        _run_applescript('tell application "Spotify" to previous track')
        import time
        time.sleep(0.5)
        current = spotify_current()
        return {"success": True, "action": "previous", **current}
    except Exception as exc:
        logger.error("Spotify previous hatası: %s", exc)
        return {"success": False, "error": str(exc)}


@register_tool("spotify_current")
def spotify_current() -> dict:
    """Spotify'da şu an çalan şarkının bilgilerini döndür."""
    try:
        if not _spotify_running():
            return {"success": False, "error": "Spotify çalışmıyor", "state": "stopped"}

        script = """
tell application "Spotify"
    set trackName to name of current track
    set artistName to artist of current track
    set albumName to album of current track
    set playerState to player state as string
    set vol to sound volume
    return trackName & "|||" & artistName & "|||" & albumName & "|||" & playerState & "|||" & (vol as string)
end tell
"""
        raw = _run_applescript(script)
        parts = raw.split("|||")
        if len(parts) >= 5:
            return {
                "success": True,
                "track": parts[0],
                "artist": parts[1],
                "album": parts[2],
                "state": parts[3],  # "playing" / "paused" / "stopped"
                "volume": int(parts[4]) if parts[4].isdigit() else 50,
            }
        return {"success": False, "error": "Şarkı bilgisi alınamadı"}
    except Exception as exc:
        logger.error("Spotify current hatası: %s", exc)
        return {"success": False, "error": str(exc), "state": "unknown"}


@register_tool("spotify_volume")
def spotify_volume(level: int) -> dict:
    """Spotify ses seviyesini ayarla (0-100).

    Args:
        level: Ses seviyesi (0-100)
    """
    try:
        level = max(0, min(100, int(level)))
        _ensure_spotify()
        _run_applescript(f'tell application "Spotify" to set sound volume to {level}')
        return {"success": True, "volume": level}
    except Exception as exc:
        logger.error("Spotify volume hatası: %s", exc)
        return {"success": False, "error": str(exc)}
