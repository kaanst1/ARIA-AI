"""Registries for agents and tools."""

from __future__ import annotations

from typing import Callable, Dict, Type

AGENT_REGISTRY: Dict[str, Type] = {}
TOOL_REGISTRY: Dict[str, Callable] = {}


def register_agent(name: str) -> Callable[[Type], Type]:
    def decorator(cls: Type) -> Type:
        AGENT_REGISTRY[name] = cls
        return cls

    return decorator


def get_agent(name: str) -> Type | None:
    return AGENT_REGISTRY.get(name)


def register_tool(name: str) -> Callable[[Callable], Callable]:
    def decorator(func: Callable) -> Callable:
        TOOL_REGISTRY[name] = func
        return func

    return decorator
