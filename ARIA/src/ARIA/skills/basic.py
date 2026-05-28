"""Basic built-in skills."""

from __future__ import annotations

from ARIA.skills.registry import register_skill


@register_skill("summarize")
def summarize_skill(text: str, max_chars: int = 400) -> str:
    clean = text.strip()
    if len(clean) <= max_chars:
        return clean
    return clean[:max_chars].rstrip() + "..."


@register_skill("echo")
def echo_skill(text: str) -> str:
    return text
