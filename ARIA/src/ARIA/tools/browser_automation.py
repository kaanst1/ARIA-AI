"""Browser Automation — Playwright ile gerçek tarayıcı kontrolü."""

from __future__ import annotations

import logging
from typing import Optional

from ARIA.core.registry import register_tool

logger = logging.getLogger("aria.tools.browser_auto")

try:
    from playwright.sync_api import sync_playwright, Page, Browser
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logger.warning("playwright kurulu değil — `playwright install chromium` çalıştır")


def _check() -> None:
    if not PLAYWRIGHT_AVAILABLE:
        raise RuntimeError("playwright kurulu değil. `uv run playwright install chromium` çalıştır.")


@register_tool("browser_scrape")
def browser_scrape(url: str, selector: Optional[str] = None, wait_for: Optional[str] = None) -> dict:
    """URL'den içerik çek (JavaScript gerektiren siteler dahil).

    Args:
        url: Hedef URL
        selector: CSS selector — sadece bu elementin metnini al (None = tüm sayfa)
        wait_for: Sayfanın yüklenmesini beklenecek CSS selector

    Returns:
        {'content': str, 'title': str, 'url': str}
    """
    _check()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_extra_http_headers({"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"})
            page.goto(url, wait_until="domcontentloaded", timeout=20000)

            if wait_for:
                page.wait_for_selector(wait_for, timeout=10000)

            title = page.title()

            if selector:
                elements = page.query_selector_all(selector)
                content = "\n".join(el.inner_text() for el in elements[:20])
            else:
                content = page.inner_text("body")[:8000]

            browser.close()
            return {"success": True, "url": url, "title": title, "content": content}
    except Exception as exc:
        logger.warning("Scrape hatası (%s): %s", url, exc)
        return {"success": False, "url": url, "error": str(exc), "content": ""}


@register_tool("browser_screenshot")
def browser_screenshot(url: str, output_path: Optional[str] = None) -> dict:
    """URL'nin ekran görüntüsünü al.

    Returns:
        {'success': bool, 'path': str}
    """
    _check()
    import tempfile, os
    from pathlib import Path

    if not output_path:
        output_path = str(Path.home() / ".aria" / "screenshots" / f"screenshot_{int(__import__('time').time())}.png")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.goto(url, wait_until="networkidle", timeout=20000)
            page.screenshot(path=output_path, full_page=False)
            browser.close()
        return {"success": True, "path": output_path, "url": url}
    except Exception as exc:
        return {"success": False, "error": str(exc), "path": ""}


@register_tool("browser_fill_form")
def browser_fill_form(url: str, fields: dict, submit_selector: Optional[str] = None) -> dict:
    """Web formunu doldur ve gönder.

    Args:
        url: Form sayfası URL'si
        fields: {css_selector: değer} — doldurulacak alanlar
        submit_selector: Gönder butonunun CSS selector'ı

    Returns:
        {'success': bool, 'result_url': str, 'result_title': str}
    """
    _check()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)  # Görünür — güvenlik için
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=15000)

            for selector, value in fields.items():
                el = page.query_selector(selector)
                if el:
                    el.fill(str(value))

            if submit_selector:
                page.click(submit_selector)
                page.wait_for_load_state("domcontentloaded")

            result_url = page.url
            result_title = page.title()
            browser.close()

            return {"success": True, "result_url": result_url, "result_title": result_title}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


@register_tool("browser_extract_links")
def browser_extract_links(url: str, filter_text: Optional[str] = None) -> dict:
    """Sayfadaki linkleri çıkar.

    Returns:
        {'links': list[dict], 'count': int}
    """
    _check()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
            links = page.evaluate("""() => {
                return Array.from(document.querySelectorAll('a[href]')).map(a => ({
                    text: a.innerText.trim().substring(0, 100),
                    href: a.href
                })).filter(l => l.href.startsWith('http'));
            }""")
            browser.close()

            if filter_text:
                ft = filter_text.lower()
                links = [l for l in links if ft in l["text"].lower() or ft in l["href"].lower()]

            return {"links": links[:50], "count": len(links), "success": True}
    except Exception as exc:
        return {"success": False, "error": str(exc), "links": []}


@register_tool("browser_run_script")
def browser_run_script(url: str, script: str) -> dict:
    """Sayfada JavaScript çalıştır ve sonucu döndür.

    Args:
        url: Hedef sayfa
        script: Çalıştırılacak JS (return ile değer döndür)

    Returns:
        {'result': any}
    """
    _check()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
            result = page.evaluate(script)
            browser.close()
            return {"success": True, "result": result}
    except Exception as exc:
        return {"success": False, "error": str(exc), "result": None}
