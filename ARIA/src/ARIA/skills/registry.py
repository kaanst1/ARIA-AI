"""Skill registry and execution helpers."""

from __future__ import annotations

from typing import Callable, Dict

SKILL_REGISTRY: Dict[str, Callable[..., str]] = {}


def register_skill(name: str) -> Callable[[Callable[..., str]], Callable[..., str]]:
    def decorator(func: Callable[..., str]) -> Callable[..., str]:
        SKILL_REGISTRY[name] = func
        return func

    return decorator


def list_skills() -> list[str]:
    return sorted(SKILL_REGISTRY.keys())


def run_skill(name: str, *args, **kwargs) -> str:
    skill = SKILL_REGISTRY.get(name)
    if not skill:
        raise ValueError(f"Skill bulunamadi: {name}")
    return skill(*args, **kwargs)
