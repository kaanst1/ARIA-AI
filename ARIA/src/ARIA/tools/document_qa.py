"""Belge Q&A (RAG) — PDF, TXT, MD, CSV dosyalarını indeksle ve sorgula."""

from __future__ import annotations

import csv
import io
import logging
import os
from pathlib import Path
from typing import Optional

from ARIA.core.registry import register_tool

logger = logging.getLogger("aria.tools.document_qa")

_ARIA_DIR = Path.home() / ".aria"
_DOCS_DIR = _ARIA_DIR / "documents"
_DOCS_DIR.mkdir(parents=True, exist_ok=True)

_CHUNK_SIZE = 800
_CHUNK_OVERLAP = 100


def _chunk_text(text: str, size: int = _CHUNK_SIZE, overlap: int = _CHUNK_OVERLAP) -> list[str]:
    """Metni örtüşen parçalara böl."""
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        chunks.append(text[start:end].strip())
        start += size - overlap
    return [c for c in chunks if c]


def _extract_text(file_path: Path) -> str:
    """Dosya uzantısına göre metin çıkar."""
    suffix = file_path.suffix.lower()

    if suffix == ".pdf":
        try:
            import urllib.request
            # PyMuPDF veya pdfminer dene
            try:
                import fitz  # PyMuPDF
                doc = fitz.open(str(file_path))
                return "\n".join(page.get_text() for page in doc)
            except ImportError:
                pass
            try:
                from pdfminer.high_level import extract_text as pdf_extract
                return pdf_extract(str(file_path))
            except ImportError:
                return f"PDF okuma için 'pymupdf' veya 'pdfminer.six' gerekli: {file_path.name}"
        except Exception as exc:
            return f"PDF okunamadı: {exc}"

    elif suffix in (".txt", ".md", ".rst", ".log"):
        return file_path.read_text(errors="ignore")

    elif suffix == ".csv":
        rows = []
        with open(file_path, newline="", errors="ignore") as f:
            reader = csv.reader(f)
            for row in reader:
                rows.append(", ".join(row))
        return "\n".join(rows)

    elif suffix in (".json",):
        return file_path.read_text(errors="ignore")

    elif suffix in (".docx",):
        try:
            import docx
            doc = docx.Document(str(file_path))
            return "\n".join(p.text for p in doc.paragraphs)
        except ImportError:
            return "DOCX okuma için 'python-docx' gerekli"
        except Exception as exc:
            return f"DOCX okunamadı: {exc}"

    return f"Desteklenmeyen dosya tipi: {suffix}"


def _get_collection():
    """ChromaDB koleksiyonunu döndür (documents ayrı koleksiyon)."""
    try:
        import chromadb
        chroma_dir = _ARIA_DIR / "chroma"
        chroma_dir.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(path=str(chroma_dir))
        return client.get_or_create_collection(
            name="aria_documents",
            metadata={"hnsw:space": "cosine"},
        )
    except Exception as exc:
        raise RuntimeError(f"ChromaDB başlatılamadı: {exc}")


@register_tool("document_index")
def document_index(file_path: str) -> dict:
    """Dosyayı ChromaDB'ye indeksle (RAG için).

    Args:
        file_path: Dosyanın tam yolu veya ~/.aria/documents/ içindeki adı

    Returns:
        {'success': bool, 'chunks': int, 'file': str}
    """
    path = Path(file_path).expanduser()
    if not path.exists():
        # ~/.aria/documents/ içinde ara
        path = _DOCS_DIR / file_path
    if not path.exists():
        return {"success": False, "error": f"Dosya bulunamadı: {file_path}"}

    try:
        collection = _get_collection()
        text = _extract_text(path)
        if not text.strip():
            return {"success": False, "error": "Dosyadan metin çıkarılamadı"}

        chunks = _chunk_text(text)
        file_id = path.stem.replace(" ", "_")[:40]

        # Eski kayıtları sil
        try:
            existing = collection.get(where={"source": str(path)})
            if existing["ids"]:
                collection.delete(ids=existing["ids"])
        except Exception:
            pass

        ids = [f"{file_id}_{i}" for i in range(len(chunks))]
        metas = [{"source": str(path), "filename": path.name, "chunk": i} for i in range(len(chunks))]
        collection.add(documents=chunks, metadatas=metas, ids=ids)

        logger.info("Belge indekslendi: %s (%d parça)", path.name, len(chunks))
        return {"success": True, "file": path.name, "chunks": len(chunks)}

    except Exception as exc:
        logger.error("Belge indekslenemedi: %s", exc)
        return {"success": False, "error": str(exc)}


@register_tool("document_query")
def document_query(question: str, file_name: Optional[str] = None, n: int = 4) -> dict:
    """İndekslenmiş belgelerden soruya cevap üret (RAG).

    Args:
        question: Sorulacak soru
        file_name: Belirli bir dosyayla sınırla (None = tümü)
        n: Kaç parça kullanılacak

    Returns:
        {'answer': str, 'sources': list[str], 'context_used': int}
    """
    try:
        collection = _get_collection()
        if collection.count() == 0:
            return {"answer": "Henüz indekslenmiş belge yok. Önce 'document_index' kullan.", "sources": [], "context_used": 0}

        where = {"source": {"$contains": file_name}} if file_name else None
        results = collection.query(
            query_texts=[question],
            n_results=min(n, collection.count()),
            where=where,
        )

        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        sources = list({m.get("filename", "?") for m in metas})

        if not docs:
            return {"answer": "İlgili içerik bulunamadı.", "sources": [], "context_used": 0}

        context = "\n\n---\n\n".join(docs)
        prompt = (
            f"Aşağıdaki belge içeriğini kullanarak soruyu Türkçe yanıtla.\n"
            f"Bilmiyorsan 'Bu bilgi belgede yok' de.\n\n"
            f"Soru: {question}\n\n"
            f"Belge:\n{context[:3000]}"
        )

        from ARIA.core.engine import ARIAEngine
        answer = ARIAEngine().chat([{"role": "user", "content": prompt}])

        return {"answer": answer, "sources": sources, "context_used": len(docs)}

    except Exception as exc:
        logger.error("Belge sorgusu başarısız: %s", exc)
        return {"answer": f"Hata: {exc}", "sources": [], "context_used": 0}


@register_tool("document_list")
def document_list() -> dict:
    """İndekslenmiş belgeleri listele.

    Returns:
        {'documents': list[dict]}
    """
    try:
        collection = _get_collection()
        if collection.count() == 0:
            return {"documents": [], "count": 0, "success": True}
        all_items = collection.get()
        metas = all_items.get("metadatas", [])
        seen = {}
        for m in metas:
            fn = m.get("filename", "?")
            if fn not in seen:
                seen[fn] = {"filename": fn, "source": m.get("source", ""), "chunks": 0}
            seen[fn]["chunks"] += 1
        return {"documents": list(seen.values()), "count": len(seen), "success": True}
    except Exception as exc:
        return {"success": False, "error": str(exc), "documents": []}
