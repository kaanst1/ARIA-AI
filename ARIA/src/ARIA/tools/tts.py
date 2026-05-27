"""Offline text-to-speech utilities."""

from __future__ import annotations

import subprocess
from ARIA.core.config import load_config


def speak_text(text: str) -> None:
    config = load_config()
    if not config.enable_tts:
        return
    if config.tts_engine != "macos_say":
        raise ValueError("Desteklenmeyen TTS motoru")

    clean = text.strip()
    if not clean:
        return

    cmd = ["say"]
    if config.tts_voice:
        cmd.extend(["-v", config.tts_voice])
    cmd.append(clean)

    subprocess.run(cmd, check=False)
