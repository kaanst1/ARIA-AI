# ARIA - Web Search Tool

from duckduckgo_search import DDGS
from ARIA.core.config import load_config
from ARIA.core.registry import register_tool
import re

_SENSITIVE_PATTERNS = [
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    re.compile(r"\b\+?\d[\d\s\-\(\)]{7,}\d\b"),
    re.compile(r"(https?://|www\.)", re.IGNORECASE),
    re.compile(r"(/Users/|/home/|C:\\\\|~\/)", re.IGNORECASE),
]


def _is_sensitive(query: str) -> bool:
    return any(pattern.search(query) for pattern in _SENSITIVE_PATTERNS)

class WebSearch:
    def __init__(self):
        config = load_config()
        if not config.allow_network or not config.allow_web_search:
            raise PermissionError("Web search devre disi (offline mod)")
        self._allow_user_data = config.allow_web_search_user_data
        self.ddgs = DDGS()

    def _prepare_query(self, query: str) -> str:
        clean = query.strip()
        if not clean:
            raise ValueError("Arama sorgusu bos olamaz")
        if len(clean) > 120:
            raise PermissionError("Guvenlik: uzun sorgular disari cikamaz")
        if not self._allow_user_data and _is_sensitive(clean):
            raise PermissionError("Guvenlik: hassas veri web aramasina gonderilemez")
        return clean

    def search(self, query: str, max_results: int = 5) -> list:
        """Web'de ara, sonuçları döndür"""
        try:
            safe_query = self._prepare_query(query)
            results = list(self.ddgs.text(safe_query, max_results=max_results))
            return results
        except Exception as e:
            return [{"title": "Hata", "body": str(e), "href": ""}]

    def search_news(self, query: str, max_results: int = 5) -> list:
        """Haber ara"""
        try:
            safe_query = self._prepare_query(query)
            results = list(self.ddgs.news(safe_query, max_results=max_results))
            return results
        except Exception as e:
            return [{"title": "Hata", "body": str(e), "href": ""}]

    def format_results(self, results: list) -> str:
        """Sonuçları okunabilir formata çevir"""
        if not results:
            return "Sonuç bulunamadı."

        lines = []
        for i, r in enumerate(results, 1):
            title = r.get("title", "Başlık yok")
            body = r.get("body", r.get("excerpt", ""))
            url = r.get("href", r.get("url", ""))
            lines.append(f"{i}. {title}\n   {body}\n   {url}")

        return "\n\n".join(lines)


if __name__ == "__main__":
    ws = WebSearch()
    results = ws.search("Ankara hava durumu bugün")
    print(ws.format_results(results))


@register_tool("web_search")
def web_search_tool(query: str, max_results: int = 5) -> list:
    return WebSearch().search(query, max_results=max_results)