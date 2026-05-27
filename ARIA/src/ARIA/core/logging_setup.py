"""Logging configuration for ARIA."""

from __future__ import annotations

import logging
from pathlib import Path
from ARIA.core.config import load_config


def configure_logging() -> None:
    config = load_config()
    level = getattr(logging, config.log_level.upper(), logging.INFO)

    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if config.log_to_file:
        log_dir = Path(config.log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_dir / "aria.log"))

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
    )
