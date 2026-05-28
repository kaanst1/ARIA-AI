"""RSS/Atom feed okuyucu — feedparser tabanlı."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    import feedparser
    FEEDPARSER_AVAILABLE = True
except ImportError:
    FEEDPARSER_AVAILABLE = False

from ARIA.core.registry import register_tool

logger = logging.getLogger("aria.tools.rss_reader")

_ARIA_DIR = Path.home() / ".aria"
_FEEDS_PATH = _ARIA_DIR / "feeds.json"

# Varsayılan feed'ler
_DEFAULT_FEEDS = {
    "bbc_turkce": "https://feeds.bbci.co.uk/turkce/rss.xml",
    "techcrunch": "https://techcrunch.com/feed/",
    "hn_top": "https://hnrss.org/frontpage",
    "arxiv_cs": "https://export.arxiv.org/rss/cs.AI",
}


class FeedManager:
    """RSS feed yöneticisi."""

    def __init__(self) -> None:
        _ARIA_DIR.mkdir(parents=True, exist_ok=True)
        self.feeds: dict[str, str] = self._load_feeds()

    def _load_feeds(self) -> dict[str, str]:
        if _FEEDS_PATH.exists():
            try:
                with open(_FEEDS_PATH, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        # Varsayılan feed'leri yaz
        self._save_feeds(_DEFAULT_FEEDS)
        return dict(_DEFAULT_FEEDS)

    def _save_feeds(self, feeds: dict) -> None:
        with open(_FEEDS_PATH, "w", encoding="utf-8") as f:
            json.dump(feeds, f, ensure_ascii=False, indent=2)

    def add_feed(self, name: str, url: str) -> bool:
        self.feeds[name] = url
        self._save_feeds(self.feeds)
        return True

    def remove_feed(self, name: str) -> bool:
        if name in self.feeds:
            del self.feeds[name]
            self._save_feeds(self.feeds)
            return True
        return False

    def get_latest(self, name: str, n: int = 5) -> list[dict]:
        """Belirli feed'den son n haberi al."""
        if not FEEDPARSER_AVAILABLE:
            return [{"error": "feedparser yüklü değil"}]

        url = self.feeds.get(name)
        if not url:
            return [{"error": f"Feed bulunamadı: {name}. Mevcut: {list(self.feeds.keys())}"}]

        try:
            feed = feedparser.parse(url)
            items = []
            for entry in feed.entries[:n]:
                items.append({
                    "title": getattr(entry, "title", "Başlık yok"),
                    "link": getattr(entry, "link", ""),
                    "summary": getattr(entry, "summary", "")[:300],
                    "published": getattr(entry, "published", ""),
                    "feed": name,
                })
            return items
        except Exception as exc:
            logger.error("Feed okuma hatası %s: %s", name, exc)
            return [{"error": str(exc), "feed": name}]

    def get_all_latest(self, n: int = 3) -> list[dict]:
        """Tüm kayıtlı feed'lerden son n haberi al."""
        if not FEEDPARSER_AVAILABLE:
            return [{"error": "feedparser yüklü değil"}]

        all_items = []
        for name in self.feeds:
            items = self.get_latest(name, n=n)
            all_items.extend(items)
        return all_items

    def list_feeds(self) -> dict[str, str]:
        return dict(self.feeds)


_feed_manager = FeedManager()


@register_tool("rss_latest")
def rss_latest(name: str = "all", n: int = 5) -> list[dict]:
    """RSS feed'den son haberleri al.

    Args:
        name: Feed adı veya "all" (tüm feed'ler).
        n: Her feed'den kaç haber alınacak.

    Returns:
        Haber listesi.
    """
    if name == "all":
        return _feed_manager.get_all_latest(n=n)
    return _feed_manager.get_latest(name, n=n)


@register_tool("rss_add")
def rss_add(name: str, url: str) -> dict:
    """Yeni RSS feed ekle.

    Args:
        name: Feed adı (unique).
        url: RSS feed URL'si.

    Returns:
        {'success': bool, 'message': str}
    """
    success = _feed_manager.add_feed(name, url)
    return {"success": success, "message": f"Feed eklendi: {name}" if success else "Feed eklenemedi"}


@register_tool("rss_list")
def rss_list() -> dict:
    """Kayıtlı tüm RSS feed'lerini listele."""
    return {"feeds": _feed_manager.list_feeds()}
