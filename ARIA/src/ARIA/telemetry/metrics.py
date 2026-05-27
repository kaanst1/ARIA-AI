"""Simple latency and token metrics."""

from __future__ import annotations

import time
from contextlib import contextmanager


@contextmanager
def track_latency(metrics: dict, key: str):
    start = time.time()
    try:
        yield
    finally:
        metrics[key] = round((time.time() - start) * 1000, 2)
