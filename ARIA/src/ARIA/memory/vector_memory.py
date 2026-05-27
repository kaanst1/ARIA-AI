"""ChromaDB tabanlı vektör hafıza — semantik arama."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

try:
    import chromadb
    from chromadb.config import Settings
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False

from ARIA.core.registry import register_tool

logger = logging.getLogger("aria.memory.vector")

_ARIA_DIR = Path.home() / ".aria"
_CHROMA_DIR = _ARIA_DIR / "chroma"


class VectorMemory:
    """ChromaDB ile semantik hafıza."""

    def __init__(self) -> None:
        self._client: Optional[Any] = None
        self._collection: Optional[Any] = None

        if CHROMA_AVAILABLE:
            self._init_chroma()

    def _init_chroma(self) -> None:
        """ChromaDB'yi başlat."""
        try:
            _CHROMA_DIR.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(
                path=str(_CHROMA_DIR),
            )
            self._collection = self._client.get_or_create_collection(
                name="aria_memory",
                metadata={"hnsw:space": "cosine"},
            )
            logger.info("VectorMemory başlatıldı: %s", _CHROMA_DIR)
        except Exception as exc:
            logger.error("ChromaDB başlatma hatası: %s", exc)
            self._client = None
            self._collection = None

    def add_memory(self, text: str, metadata: Optional[dict] = None) -> bool:
        """Hafızaya ekle.

        Args:
            text: Kaydedilecek metin.
            metadata: Ek meta veri (isteğe bağlı).

        Returns:
            Başarılı ise True.
        """
        if not CHROMA_AVAILABLE or self._collection is None:
            return False

        try:
            doc_id = f"mem_{datetime.now().timestamp()}_{hash(text) % 100000}"
            meta = metadata or {}
            meta["timestamp"] = datetime.now().isoformat()
            meta["length"] = len(text)

            self._collection.add(
                documents=[text],
                metadatas=[meta],
                ids=[doc_id],
            )
            return True
        except Exception as exc:
            logger.error("Hafıza ekleme hatası: %s", exc)
            return False

    def search(self, query: str, n: int = 5) -> list[dict]:
        """Semantik arama yap.

        Args:
            query: Arama sorgusu.
            n: Kaç sonuç döndürülecek.

        Returns:
            En yakın hafıza kayıtlarının listesi.
        """
        if not CHROMA_AVAILABLE or self._collection is None:
            return [{"error": "ChromaDB mevcut değil veya başlatılamadı"}]

        try:
            results = self._collection.query(
                query_texts=[query],
                n_results=min(n, self._collection.count() or 1),
            )

            memories = []
            documents = results.get("documents", [[]])[0]
            metadatas = results.get("metadatas", [[]])[0]
            distances = results.get("distances", [[]])[0]

            for doc, meta, dist in zip(documents, metadatas, distances):
                memories.append({
                    "content": doc,
                    "metadata": meta,
                    "relevance": round(1 - dist, 3),  # cosine distance → similarity
                })
            return memories
        except Exception as exc:
            logger.error("Semantik arama hatası: %s", exc)
            return [{"error": str(exc)}]

    def get_count(self) -> int:
        """Toplam kayıt sayısını döndür."""
        if not CHROMA_AVAILABLE or self._collection is None:
            return 0
        try:
            return self._collection.count()
        except Exception:
            return 0

    def is_available(self) -> bool:
        """ChromaDB erişilebilir mi?"""
        return CHROMA_AVAILABLE and self._collection is not None


# Global instance
_vector_memory = VectorMemory()


@register_tool("memory_search")
def memory_search(query: str, n: int = 5) -> list[dict]:
    """Semantik hafızada arama yap.

    Args:
        query: Arama sorgusu.
        n: Döndürülecek sonuç sayısı.

    Returns:
        İlgili hafıza kayıtlarının listesi.
    """
    return _vector_memory.search(query, n=n)


@register_tool("memory_add")
def memory_add(text: str, metadata: Optional[dict] = None) -> dict:
    """Semantik hafızaya not ekle.

    Args:
        text: Kaydedilecek metin.
        metadata: Ek meta veri.

    Returns:
        {'success': bool}
    """
    success = _vector_memory.add_memory(text, metadata=metadata)
    return {
        "success": success,
        "count": _vector_memory.get_count(),
        "chroma_available": CHROMA_AVAILABLE,
    }


def auto_add_conversation(user_msg: str, assistant_msg: str, agent: str = "chat") -> None:
    """Her konuşmayı otomatik olarak hafızaya ekle."""
    if not CHROMA_AVAILABLE:
        return
    text = f"Kullanıcı: {user_msg}\nARIA: {assistant_msg}"
    _vector_memory.add_memory(text, metadata={"agent": agent, "type": "conversation"})
