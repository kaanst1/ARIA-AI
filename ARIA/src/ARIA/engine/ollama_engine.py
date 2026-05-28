"""Ollama engine implementation."""

from __future__ import annotations

import json
import requests
from typing import Generator, Optional
from urllib.parse import urlparse
from ARIA.core.config import ARIAConfig, load_config, ARIA_SYSTEM_PROMPT


class OllamaEngine:
    def __init__(self, config: Optional[ARIAConfig] = None):
        self.config = config or load_config()
        self.base_url = self.config.base_url
        self.model = self.config.model
        self._enforce_base_url()

    def _enforce_base_url(self) -> None:
        parsed = urlparse(self.base_url)
        host = parsed.hostname or ""
        if host not in self.config.allowed_base_hosts:
            raise ValueError(
                "Guvenlik: base_url sadece lokal hostlara izinli. "
                f"Mevcut host: {host}"
            )

    def is_available(self) -> bool:
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=3)
            return r.status_code == 200
        except Exception:
            return False

    def list_models(self) -> list:
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=3)
            data = r.json()
            return [m["name"] for m in data.get("models", [])]
        except Exception:
            return []

    def chat(self, messages: list, stream: bool = False) -> str:
        system_message = {"role": "system", "content": ARIA_SYSTEM_PROMPT}
        full_messages = [system_message] + messages

        payload = {
            "model": self.model,
            "messages": full_messages,
            "stream": stream,
            "options": {
                "temperature": self.config.temperature,
                "num_predict": self.config.max_tokens,
            },
        }

        if stream:
            return "".join(self.stream_chat(messages))

        r = requests.post(
            f"{self.base_url}/api/chat",
            json=payload,
            timeout=120,
        )

        if r.status_code != 200:
            raise Exception(f"Engine hatasi: {r.status_code} - {r.text}")

        return r.json()["message"]["content"]

    def stream_chat(self, messages: list) -> Generator[str, None, None]:
        system_message = {"role": "system", "content": ARIA_SYSTEM_PROMPT}
        full_messages = [system_message] + messages

        payload = {
            "model": self.model,
            "messages": full_messages,
            "stream": True,
            "options": {
                "temperature": self.config.temperature,
                "num_predict": self.config.max_tokens,
            },
        }

        r = requests.post(
            f"{self.base_url}/api/chat",
            json=payload,
            timeout=120,
            stream=True,
        )

        if r.status_code != 200:
            raise Exception(f"Engine hatasi: {r.status_code} - {r.text}")

        for line in r.iter_lines(decode_unicode=True):
            if not line:
                continue
            data = json.loads(line)
            if data.get("done"):
                break
            token = data.get("message", {}).get("content", "")
            if token:
                yield token
