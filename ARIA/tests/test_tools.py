"""Yeni tool'lar için birim testleri."""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── Weather ───────────────────────────────────────────────────────────────────

def test_weather_current_offline():
    """Ağ yokken graceful fail döndürmeli."""
    with patch("urllib.request.urlopen", side_effect=Exception("no network")):
        from ARIA.tools.weather import weather_current
        result = weather_current("Ankara")
        assert result["success"] is False
        assert "error" in result


def test_weather_current_success():
    """Open-Meteo formatında sahte yanıt ile weather_current testi."""
    # Geocoding yanıtı
    geo_response = json.dumps({
        "results": [{"latitude": 39.92, "longitude": 32.85, "name": "Ankara"}]
    }).encode()
    # Forecast yanıtı
    forecast_response = json.dumps({
        "current": {
            "temperature_2m": 22.0,
            "apparent_temperature": 20.0,
            "relative_humidity_2m": 40,
            "weather_code": 1,
            "wind_speed_10m": 15.0,
        }
    }).encode()

    call_count = 0
    def fake_urlopen(req, timeout=None):
        nonlocal call_count
        call_count += 1
        mock = MagicMock()
        mock.__enter__ = lambda s: s
        mock.__exit__ = MagicMock(return_value=False)
        # İlk çağrı geocoding, ikinci çağrı forecast
        mock.read.return_value = geo_response if call_count == 1 else forecast_response
        return mock

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        from ARIA.tools import weather as weather_mod
        weather_mod._geocode.cache_clear()  # lru_cache temizle
        from ARIA.tools.weather import weather_current
        r = weather_current("Ankara")

    assert r["success"] is True
    assert r["temp_c"] == 22.0
    assert r["city"] == "Ankara"
    assert r["humidity"] == 40


# ── Smart Router ──────────────────────────────────────────────────────────────

def test_smart_router_classify_simple():
    from ARIA.core.smart_router import classify_complexity
    assert classify_complexity("merhaba") == "simple"
    assert classify_complexity("günaydın") == "simple"


def test_smart_router_classify_complex():
    from ARIA.core.smart_router import classify_complexity
    assert classify_complexity("derin araştır kuantum bilişim") == "complex"
    assert classify_complexity("bu kod neden hata veriyor debug") == "complex"


def test_smart_router_classify_medium():
    from ARIA.core.smart_router import classify_complexity
    assert classify_complexity("haber özetle") == "medium"


def test_smart_router_select_model():
    from ARIA.core.smart_router import select_model
    models = ["qwen2.5:3b", "qwen2.5:7b", "qwen2.5:14b"]
    assert select_model("günaydın", models, "qwen2.5:7b") == "qwen2.5:3b"
    assert select_model("derin araştır", models, "qwen2.5:7b") == "qwen2.5:14b"
    assert select_model("haberleri özetle", models, "qwen2.5:7b") == "qwen2.5:7b"


def test_smart_router_empty_models():
    from ARIA.core.smart_router import select_model
    result = select_model("merhaba", [], "qwen2.5:7b")
    assert result == "qwen2.5:7b"


# ── Email Intelligence ────────────────────────────────────────────────────────

def test_email_classify_urgent():
    from ARIA.tools.email_intelligence import email_classify
    r = email_classify("Acil: Sunucu çöktü!", "Hemen bakmanız lazım.", "dev@example.com")
    assert r["priority"] == "yüksek"
    assert "acil" in r["tags"]


def test_email_classify_meeting():
    from ARIA.tools.email_intelligence import email_classify
    r = email_classify("Toplantı daveti", "Zoom meeting yarın saat 14:00", "hr@example.com")
    assert r["is_meeting"] is True
    assert "toplantı" in r["tags"]


def test_email_classify_spam():
    from ARIA.tools.email_intelligence import email_classify
    r = email_classify("You won!", "Unsubscribe from this newsletter.", "spam@example.com")
    assert r["priority"] == "düşük"
    assert "spam" in r["tags"]


def test_email_extract_meeting():
    from ARIA.tools.email_intelligence import email_extract_meeting
    r = email_extract_meeting(
        "Zoom toplantısı",
        "https://zoom.us/j/123456789 Yarın 14:30'da görüşelim.",
    )
    assert r["found"] is True
    assert r["platform"] == "Zoom"


def test_email_summarize_empty():
    from ARIA.tools.email_intelligence import email_summarize
    r = email_summarize([])
    assert r["success"] is True
    assert r["urgent"] == []


# ── Semantic Context ──────────────────────────────────────────────────────────

def test_semantic_context_no_chroma():
    """ChromaDB yokken graceful davranmalı."""
    with patch("ARIA.memory.semantic_context.build_memory_context", return_value=""):
        from ARIA.memory.semantic_context import inject_into_messages
        messages = [{"role": "user", "content": "merhaba"}]
        result = inject_into_messages(messages, "merhaba", "chat")
        assert result == messages


def test_semantic_context_inject():
    with patch("ARIA.memory.semantic_context.build_memory_context", return_value="[Hafıza] Önceki bilgi"):
        from ARIA.memory.semantic_context import inject_into_messages
        messages = [{"role": "user", "content": "merhaba"}]
        result = inject_into_messages(messages, "merhaba", "chat")
        assert any("[Hafıza]" in m.get("content", "") for m in result)


# ── Clipboard History ─────────────────────────────────────────────────────────

def test_clipboard_history_load_empty(tmp_path):
    with patch("ARIA.tools.clipboard_history._HISTORY_FILE", tmp_path / "clipboard.json"):
        from ARIA.tools.clipboard_history import clipboard_history_get
        r = clipboard_history_get(10)
        assert r["success"] is True
        assert r["count"] == 0


def test_clipboard_history_search(tmp_path):
    history_file = tmp_path / "clipboard.json"
    history_file.write_text(json.dumps([
        {"ts": "2026-01-01T10:00:00", "content": "merhaba dünya", "length": 13},
        {"ts": "2026-01-01T11:00:00", "content": "başka içerik", "length": 12},
    ]))
    with patch("ARIA.tools.clipboard_history._HISTORY_FILE", history_file):
        from ARIA.tools.clipboard_history import clipboard_history_search
        r = clipboard_history_search("merhaba")
        assert r["success"] is True
        assert r["count"] == 1


# ── Workflow Engine ───────────────────────────────────────────────────────────

def test_workflow_run_notify():
    """notify aksiyonu subprocess çağırmalı."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        from ARIA.automation.workflow_engine import run_workflow
        wf = {
            "name": "test",
            "steps": [{"action": "notify", "params": {"title": "Test", "message": "Merhaba"}}],
        }
        results = run_workflow(wf)
        assert results[0]["success"] is True
        assert results[0]["action"] == "notify"


def test_workflow_unknown_action():
    from ARIA.automation.workflow_engine import run_workflow
    wf = {"name": "test", "steps": [{"action": "bilinmeyen_aksiyon", "params": {}}]}
    results = run_workflow(wf)
    assert results[0]["success"] is False
    assert "Bilinmeyen" in results[0]["error"]


def test_workflow_interpolate():
    from ARIA.automation.workflow_engine import _interpolate
    result = _interpolate("Sonuç: {result}", {"result": "test123"})
    assert "test123" in result


# ── Pomodoro ──────────────────────────────────────────────────────────────────

def test_pomodoro_double_start():
    """İkinci başlatma hata vermeli."""
    import ARIA.tools.pomodoro as pom
    pom._active = True  # Simüle
    from ARIA.tools.pomodoro import pomodoro_start
    r = pomodoro_start()
    assert r["success"] is False
    pom._active = False


def test_pomodoro_stop_inactive():
    import ARIA.tools.pomodoro as pom
    pom._active = False
    from ARIA.tools.pomodoro import pomodoro_stop
    r = pomodoro_stop()
    assert r["success"] is False


# ── Git Intelligence ──────────────────────────────────────────────────────────

def test_git_no_repo():
    """Git root bulunamazsa ve path de None ise success False dönmeli."""
    with patch("ARIA.tools.git_intelligence._find_git_root", return_value=None):
        from ARIA.tools.git_intelligence import git_status_summary
        r = git_status_summary(None)
        assert r["success"] is False


def test_git_todo_scan_empty(tmp_path):
    (tmp_path / "test.py").write_text("# normal code\nprint('hello')\n")
    with patch("ARIA.tools.git_intelligence._find_git_root", return_value=str(tmp_path)):
        from ARIA.tools.git_intelligence import git_todo_scan
        r = git_todo_scan(str(tmp_path))
        assert r["success"] is True
        assert r["count"] == 0


def test_git_todo_scan_found(tmp_path):
    (tmp_path / "app.py").write_text("# TODO: bunu düzelt\nx = 1\n# FIXME: bug var\n")
    from ARIA.tools.git_intelligence import git_todo_scan
    r = git_todo_scan(str(tmp_path))
    assert r["success"] is True
    assert r["count"] >= 1


# ── Weekly Report ─────────────────────────────────────────────────────────────

def test_weekly_report_no_data(tmp_path):
    with (
        patch("ARIA.tools.weekly_report._ARIA_DIR", tmp_path),
        patch("ARIA.tools.weekly_report._REPORTS_DIR", tmp_path / "reports"),
        patch("ARIA.tools.weekly_report._load_usage", return_value={"sessions": [], "agent_counts": {}}),
        patch("ARIA.core.engine.ARIAEngine.chat", return_value="İyi haftalar!"),
    ):
        from ARIA.tools.weekly_report import generate_weekly_report
        r = generate_weekly_report(save=False)
        assert r["success"] is True
        assert "ARIA Haftalık Rapor" in r["report"]


# ── Context Awareness ─────────────────────────────────────────────────────────

def test_context_suggest_no_meetings():
    with (
        patch("ARIA.tools.context_awareness.context_upcoming_meetings", return_value={"next": None, "meetings": []}),
        patch("ARIA.tools.context_awareness.context_get_frontmost_app", return_value={"app": "Finder", "window_title": ""}),
    ):
        from ARIA.tools.context_awareness import context_suggest
        r = context_suggest()
        assert r["success"] is True


def test_context_suggest_with_meeting():
    with (
        patch("ARIA.tools.context_awareness.context_upcoming_meetings", return_value={
            "next": {"title": "Ekip Toplantısı", "minutes_until": 10},
            "meetings": [{"title": "Ekip Toplantısı", "minutes_until": 10}],
        }),
        patch("ARIA.tools.context_awareness.context_get_frontmost_app", return_value={"app": "Finder", "window_title": ""}),
    ):
        from ARIA.tools.context_awareness import context_suggest
        r = context_suggest()
        assert "toplantı" in r["suggestion"].lower() or "Toplantı" in r["suggestion"]
