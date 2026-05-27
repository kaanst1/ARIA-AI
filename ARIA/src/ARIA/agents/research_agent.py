"""Derin Araştırma Agent — çoklu arama, self-reflection, kapsamlı rapor."""

from __future__ import annotations

import logging
from typing import Optional

from ARIA.core.engine import ARIAEngine
from ARIA.core.registry import register_agent

logger = logging.getLogger("aria.agents.deep_research")

_QUERY_GEN_SYSTEM = """Sen bir araştırma sorgusu üreticisin.
Verilen konuyu araştırmak için 3-5 farklı, tamamlayıcı arama sorgusu üret.
Her sorgu farklı bir açıdan konuyu ele alsın.
Her satıra bir sorgu yaz, numara veya madde işareti koyma."""

_RESEARCH_SYSTEM = """Sen ARIA'nın Derin Araştırma Ajanısın.
Birden fazla kaynaktan toplanan verileri sentezleyerek kapsamlı, akademik kalitede raporlar üretirsin.

Rapor formatı:
## Araştırma Konusu: [başlık]

### Yönetici Özeti
[2-3 cümle özet]

### Temel Bulgular
[Önemli bulgular]

### Detaylı Analiz
[Kapsamlı analiz, alt başlıklar ile]

### Farklı Perspektifler
[Konuya farklı açılardan bakış]

### Sonuç ve Öneriler
[Pratik çıkarımlar]

### Kaynaklar
[Kullanılan kaynaklar]

Kurallar:
- Spekülatif bilgiyi işaretle
- Çelişkili bilgileri not et
- Teknik konularda derine in
- Önemli rakamları ve tarihleri vurgula"""

_REFLECTION_SYSTEM = """Sen bir araştırma kalite değerlendiricisin.
Verilen araştırma raporunu değerlendir:
1. Yeterli kapsamda mı?
2. Önemli eksik noktalar var mı?
3. Ek arama yapılması gerekiyor mu?

Yanıt formatı (JSON):
{"sufficient": true/false, "missing": ["eksik konu 1", ...], "additional_queries": ["sorgu 1", ...]}

Sadece JSON döndür."""


@register_agent("deep_research")
class DeepResearchAgent:
    """Çoklu arama, self-reflection döngüsü ile derin araştırma."""

    def __init__(self) -> None:
        self.engine = ARIAEngine()

    def _generate_queries(self, topic: str) -> list[str]:
        """Konudan 3-5 farklı arama sorgusu üret."""
        messages = [
            {"role": "system", "content": _QUERY_GEN_SYSTEM},
            {"role": "user", "content": f"Konu: {topic}"},
        ]
        response = self.engine.chat(messages)
        queries = [q.strip() for q in response.strip().split('\n') if q.strip()]
        # İlk konuyu da ekle
        if topic not in queries:
            queries.insert(0, topic)
        return queries[:5]

    def _search_all(self, queries: list[str]) -> list[dict]:
        """Tüm sorgular için web araması yap."""
        try:
            from ARIA.tools.web_search import WebSearch
            ws = WebSearch()
        except ImportError:
            return [{"title": "Hata", "body": "web_search kullanılamıyor", "href": ""}]

        all_results = []
        seen_urls = set()

        for query in queries:
            try:
                results = ws.search(query, max_results=5)
                for r in results:
                    url = r.get("href", "")
                    if url not in seen_urls:
                        seen_urls.add(url)
                        all_results.append(r)
            except Exception as exc:
                logger.warning("Arama hatası (%s): %s", query, exc)

        return all_results

    def _reflect(self, topic: str, draft_report: str) -> dict:
        """Raporu değerlendir, eksikleri tespit et."""
        import json
        messages = [
            {"role": "system", "content": _REFLECTION_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"Araştırma konusu: {topic}\n\n"
                    f"Hazırlanan rapor (ilk 2000 karakter):\n{draft_report[:2000]}"
                ),
            },
        ]
        response = self.engine.chat(messages)
        try:
            clean = response.strip()
            if "{" in clean and "}" in clean:
                clean = clean[clean.index("{"):clean.rindex("}") + 1]
            return json.loads(clean)
        except Exception:
            return {"sufficient": True, "missing": [], "additional_queries": []}

    def _build_report(self, topic: str, all_results: list[dict], queries: list[str]) -> str:
        """Araştırma sonuçlarından kapsamlı rapor üret."""
        # Sonuçları formatla
        formatted_results = []
        for i, r in enumerate(all_results[:15], 1):
            title = r.get("title", "")
            body = r.get("body", r.get("snippet", ""))[:500]
            url = r.get("href", r.get("url", ""))
            formatted_results.append(f"{i}. **{title}**\n{body}\nKaynak: {url}\n")

        results_text = "\n".join(formatted_results) if formatted_results else "Arama sonucu bulunamadı."

        prompt = (
            f"Araştırma konusu: {topic}\n\n"
            f"Kullanılan arama sorguları:\n" + "\n".join(f"- {q}" for q in queries) + "\n\n"
            f"Toplanan veriler ({len(all_results)} kaynak):\n{results_text}\n\n"
            "Yukarıdaki verileri kullanarak kapsamlı araştırma raporu hazırla."
        )

        messages = [
            {"role": "system", "content": _RESEARCH_SYSTEM},
            {"role": "user", "content": prompt},
        ]
        return self.engine.chat(messages)

    def handle(self, user_input: str) -> str:
        """Derin araştırma yap ve rapor üret."""
        logger.info("DeepResearch başlıyor: %s", user_input)

        # 1. Sorguları oluştur
        queries = self._generate_queries(user_input)
        logger.info("Oluşturulan sorgular: %s", queries)

        # 2. Tüm aramaları yap
        all_results = self._search_all(queries)
        logger.info("%d benzersiz sonuç toplandı", len(all_results))

        # 3. İlk raporu oluştur
        draft_report = self._build_report(user_input, all_results, queries)

        # 4. Self-reflection: yeterli mi?
        reflection = self._reflect(user_input, draft_report)

        if not reflection.get("sufficient", True) and reflection.get("additional_queries"):
            # Eksik konuları ara
            additional = reflection["additional_queries"][:2]
            logger.info("Ek araştırma yapılıyor: %s", additional)
            extra_results = self._search_all(additional)

            if extra_results:
                all_results.extend(extra_results)
                # Son raporu yeniden üret
                draft_report = self._build_report(user_input, all_results, queries + additional)

        return draft_report
