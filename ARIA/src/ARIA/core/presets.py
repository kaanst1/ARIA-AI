"""Preset management for ARIA config."""

from __future__ import annotations

import json
from pathlib import Path
from ARIA.core.config import ARIAConfig, load_config, save_config


PRESET_DIR = Path(__file__).resolve().parents[2] / "presets"


def list_presets() -> list[str]:
    if not PRESET_DIR.exists():
        return []
    return sorted(p.stem for p in PRESET_DIR.glob("*.json"))


def load_preset(name: str) -> ARIAConfig:
    preset_path = PRESET_DIR / f"{name}.json"
    if not preset_path.exists():
        raise FileNotFoundError(f"Preset bulunamadi: {name}")
    data = json.loads(preset_path.read_text(encoding="utf-8"))
    return ARIAConfig(**data)


def apply_preset(name: str) -> ARIAConfig:
    config = load_preset(name)
    save_config(config)
    return config


def merge_preset(name: str) -> ARIAConfig:
    current = load_config()
    preset = load_preset(name)
    merged = ARIAConfig(**{**current.__dict__, **preset.__dict__})
    save_config(merged)
    return merged
