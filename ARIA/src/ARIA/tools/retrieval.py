"""Retrieval tool wrapper."""

from __future__ import annotations

from pathlib import Path
from ARIA.core.registry import register_tool
from ARIA.tools.retrieval_store import retrieve_memories


@register_tool("retrieval")
def retrieve(query: str, root: str | None = None, max_hits: int = 5) -> str:
    """Retrieve information for the given query."""
    # Varsayılan: ~/.aria — tüm home tarımak çok yavaş ve tehlikeli
    search_root = Path(root or Path.home() / ".aria")
    hits = []
    for path in search_root.rglob("*.txt"):
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if query.lower() in content.lower():
            hits.append(str(path))
        if len(hits) >= max_hits:
            break

    if not hits:
        return "Sonuc yok"
    file_hits = "\n".join(hits)
    memory_hits = retrieve_memories(query, limit=5)
    return f"Dosyalar:\n{file_hits}\n\nHafiza:\n{memory_hits}"
