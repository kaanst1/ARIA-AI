"""Minimal skill benchmark runner."""

from __future__ import annotations

import time
from ARIA.skills.registry import list_skills, run_skill


def bench(text: str = "ornek", repeats: int = 3) -> str:
    results = []
    for name in list_skills():
        durations = []
        for _ in range(repeats):
            start = time.time()
            run_skill(name, text)
            durations.append((time.time() - start) * 1000)
        avg = sum(durations) / len(durations)
        results.append(f"{name}: {avg:.2f} ms")
    return "\n".join(results) if results else "Skill yok"
