"""Tarayıcı kontrolü — Safari ve Chrome AppleScript."""

from __future__ import annotations

import logging
import subprocess
from typing import Optional

from ARIA.core.registry import register_tool

logger = logging.getLogger("aria.tools.browser")


def _run_applescript(script: str) -> str:
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "AppleScript hatası")
    return result.stdout.strip()


def _detect_browser() -> str:
    """Hangi tarayıcının açık olduğunu tespit et."""
    for browser in ["Google Chrome", "Arc", "Safari", "Firefox"]:
        result = subprocess.run(
            ["pgrep", "-x", browser.split()[0]],
            capture_output=True, timeout=3,
        )
        if result.returncode == 0:
            return browser
    return "Safari"


@register_tool("browser_open_url")
def browser_open_url(url: str, browser: Optional[str] = None) -> dict:
    """Tarayıcıda URL aç.

    Args:
        url: Açılacak URL (https:// ile başlamalı)
        browser: 'chrome', 'safari', 'arc' (varsayılan: otomatik tespit)

    Returns:
        {'success': bool, 'url': str, 'browser': str}
    """
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    resolved = {
        "chrome": "Google Chrome",
        "safari": "Safari",
        "arc": "Arc",
        "firefox": "Firefox",
    }.get((browser or "").lower(), browser or _detect_browser())

    try:
        subprocess.run(["open", "-a", resolved, url], check=True, timeout=10)
        return {"success": True, "url": url, "browser": resolved}
    except Exception as exc:
        return {"success": False, "url": url, "browser": resolved, "error": str(exc)}


@register_tool("browser_get_current_tab")
def browser_get_current_tab(browser: Optional[str] = None) -> dict:
    """Aktif sekmede açık sayfanın URL ve başlığını getir.

    Returns:
        {'title': str, 'url': str, 'browser': str}
    """
    detected = browser or _detect_browser()

    if "Chrome" in detected or "Arc" in detected:
        script = f'''
tell application "{detected}"
    set t to title of active tab of front window
    set u to URL of active tab of front window
    return t & "||" & u
end tell
'''
    else:
        script = '''
tell application "Safari"
    set t to name of current tab of front window
    set u to URL of current tab of front window
    return t & "||" & u
end tell
'''
    try:
        raw = _run_applescript(script)
        parts = raw.split("||", 1)
        return {
            "title": parts[0].strip(),
            "url": parts[1].strip() if len(parts) > 1 else "",
            "browser": detected,
            "success": True,
        }
    except Exception as exc:
        return {"success": False, "error": str(exc), "title": "", "url": "", "browser": detected}


@register_tool("browser_search")
def browser_search(query: str, engine: str = "google") -> dict:
    """Tarayıcıda arama yap.

    Args:
        query: Arama sorgusu
        engine: 'google', 'duckduckgo', 'bing'

    Returns:
        {'success': bool, 'url': str}
    """
    import urllib.parse
    encoded = urllib.parse.quote_plus(query)
    urls = {
        "google": f"https://www.google.com/search?q={encoded}",
        "duckduckgo": f"https://duckduckgo.com/?q={encoded}",
        "bing": f"https://www.bing.com/search?q={encoded}",
    }
    url = urls.get(engine.lower(), urls["google"])
    return browser_open_url(url)


@register_tool("browser_new_tab")
def browser_new_tab(url: str = "about:blank", browser: Optional[str] = None) -> dict:
    """Yeni sekme aç.

    Returns:
        {'success': bool}
    """
    detected = browser or _detect_browser()
    if not url.startswith(("http://", "https://", "about:")):
        url = "https://" + url

    if "Chrome" in detected or "Arc" in detected:
        script = f'''
tell application "{detected}"
    tell front window
        make new tab with properties {{URL:"{url}"}}
    end tell
    activate
end tell
'''
    else:
        script = f'''
tell application "Safari"
    tell front window
        make new tab with properties {{URL:"{url}"}}
    end tell
    activate
end tell
'''
    try:
        _run_applescript(script)
        return {"success": True, "url": url, "browser": detected}
    except Exception as exc:
        return {"success": False, "error": str(exc)}
