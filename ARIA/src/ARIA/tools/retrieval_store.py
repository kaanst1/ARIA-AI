"""Simple retrieval store using sqlite memory."""

from __future__ import annotations

from ARIA.memory.store import MemoryStore


def retrieve_memories(query: str, limit: int = 5) -> str:
    store = MemoryStore()
    rows = store.search(query, limit=limit)
    if not rows:
        return "Sonuc yok"
    lines = []
    for _id, content, category, created_at in rows:
        lines.append(f"[{created_at[:10]}] [{category}] {content}")
    return "\n".join(lines)
