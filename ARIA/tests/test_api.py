"""Basic API tests."""

from __future__ import annotations

from fastapi.testclient import TestClient
from ARIA.api import app


client = TestClient(app)


def test_status():
    resp = client.get("/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "engine" in data


def test_chat_openai():
    payload = {
        "messages": [{"role": "user", "content": "Merhaba"}]
    }
    resp = client.post("/v1/chat/completions", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "choices" in data
