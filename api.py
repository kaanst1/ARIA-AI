"""Compatibility wrapper for running the API from the repo root."""

from __future__ import annotations

import os
import sys


def _ensure_src_on_path() -> None:
    repo_root = os.path.dirname(__file__)
    src_path = os.path.join(repo_root, "ARIA", "src")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)


def main() -> None:
    """Run the FastAPI application."""
    _ensure_src_on_path()
    from ARIA.api import main as api_main  # type: ignore[import-not-found]

    api_main()


if __name__ == "__main__":
    main()