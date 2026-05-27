"""Local summarization helpers to keep context short."""

from __future__ import annotations

from ARIA.core.config import load_config
from ARIA.core.engine import ARIAEngine


def summarize_text(text: str) -> str:
    config = load_config()
    if not config.enable_summarization:
        return text

    if len(text) < config.summary_trigger_chars:
        return text

    engine = ARIAEngine()
    prompt = (
        "Azdaki metni Turkce, kisa ve net sekilde ozetle. "
        "Ozet en fazla {max_chars} karakter olsun.\n\n".format(
            max_chars=config.summary_max_chars
        )
        + text
    )

    response = engine.chat([
        {"role": "user", "content": prompt}
    ])

    return response[: config.summary_max_chars].strip()
