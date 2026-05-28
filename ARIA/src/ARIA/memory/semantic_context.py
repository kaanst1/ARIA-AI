"""Semantik hafıza — her orchestrator çağrısına otomatik bağlam enjekte eder."""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger("aria.memory.semantic_context")

_INJECT_AGENTS = {"chat", "researcher", "analyst", "writer", "planner", "brief"}
_MAX_MEMORIES = 3
_MIN_RELEVANCE = 0.35


def build_memory_context(query: str) -> str:
    """Sorguyla ilgili hafıza kayıtlarını string olarak döndür."""
    try:
        from ARIA.memory.vector_memory import _vector_memory
        if not _vector_memory.is_available():
            return ""
        results = _vector_memory.search(query, n=_MAX_MEMORIES)
        relevant = [r for r in results if r.get("relevance", 0) >= _MIN_RELEVANCE and "error" not in r]
        if not relevant:
            return ""
        lines = ["[Hafıza — ilgili geçmiş bilgiler]"]
        for r in relevant:
            content = r["content"][:300]
            ts = r.get("metadata", {}).get("timestamp", "")[:10]
            lines.append(f"• ({ts}) {content}")
        return "\n".join(lines)
    except Exception as exc:
        logger.debug("Hafıza bağlamı alınamadı: %s", exc)
        return ""


def inject_into_messages(messages: list[dict], query: str, agent: str) -> list[dict]:
    """Eğer agent uygunsa, system mesajına hafıza bağlamı ekle."""
    if agent not in _INJECT_AGENTS:
        return messages
    ctx = build_memory_context(query)
    if not ctx:
        return messages

    injected = list(messages)
    if injected and injected[0].get("role") == "system":
        injected[0] = {
            "role": "system",
            "content": injected[0]["content"] + f"\n\n{ctx}",
        }
    else:
        injected.insert(0, {"role": "system", "content": ctx})
    return injected


def save_exchange(user_msg: str, assistant_msg: str, agent: str = "chat") -> None:
    """Konuşmayı hem vektör hafızaya hem de kısa özet olarak kaydet."""
    try:
        from ARIA.memory.vector_memory import _vector_memory
        if not _vector_memory.is_available():
            return
        text = f"Kullanıcı: {user_msg[:400]}\nARIA: {assistant_msg[:400]}"
        _vector_memory.add_memory(text, metadata={"agent": agent, "type": "conversation"})
    except Exception as exc:
        logger.debug("Konuşma hafızaya kaydedilemedi: %s", exc)


def remember_fact(fact: str, category: str = "genel") -> bool:
    """Açık bir gerçeği / notu kalıcı hafızaya kaydet."""
    try:
        from ARIA.memory.vector_memory import _vector_memory
        return _vector_memory.add_memory(fact, metadata={"type": "fact", "category": category})
    except Exception:
        return False
