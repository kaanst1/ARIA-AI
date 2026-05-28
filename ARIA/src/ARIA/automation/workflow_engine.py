"""ARIA Workflow Motoru — YAML tabanlı otomasyon kuralları.

Örnek kural dosyası (~/.aria/workflows/sabah.yaml):

    name: sabah_rutini
    trigger:
      type: schedule
      cron: "0 7 * * 1-5"   # Hafta içi 07:00
    steps:
      - action: brief
      - action: weather
        params: {city: Ankara}
      - action: tts
        params: {text: "Günaydın Meriç!"}

    name: mail_alert
    trigger:
      type: keyword
      keywords: ["acil mail", "önemli mail"]
    steps:
      - action: get_unread_emails
        params: {count: 3}
      - action: notify
        params: {title: "ARIA Mail", message: "{result}"}
"""

from __future__ import annotations

import json
import logging
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

logger = logging.getLogger("aria.automation.workflow")

_WORKFLOWS_DIR = Path.home() / ".aria" / "workflows"
_WORKFLOWS_DIR.mkdir(parents=True, exist_ok=True)

_running_jobs: dict[str, threading.Thread] = {}


# ── Yerleşik aksiyonlar ────────────────────────────────────────────────────────

def _action_brief(_params: dict) -> str:
    from ARIA.agents.brief import BriefAgent
    return BriefAgent().run(speak=_params.get("speak", False))


def _action_weather(params: dict) -> str:
    from ARIA.tools.weather import weather_current
    r = weather_current(params.get("city"))
    if r.get("success"):
        return f"{r['city']}: {r['temp_c']}°C, {r['desc']}"
    return "Hava durumu alınamadı"


def _action_tts(params: dict) -> str:
    from ARIA.tools.tts import speak
    speak(params.get("text", ""), lang="tr", block=False)
    return "TTS çalıştırıldı"


def _action_notify(params: dict) -> str:
    title = params.get("title", "ARIA")
    msg = params.get("message", "")
    script = f'display notification "{msg}" with title "{title}" sound name "Basso"'
    subprocess.run(["osascript", "-e", script], capture_output=True, timeout=5)
    return f"Bildirim gönderildi: {title}"


def _action_get_unread_emails(params: dict) -> str:
    from ARIA.tools.mail_control import get_unread_emails
    emails = get_unread_emails(params.get("count", 3))
    if not emails:
        return "Okunmamış mail yok"
    return "\n".join(f"• {e.get('subject','?')} — {e.get('from','?')}" for e in emails[:5])


def _action_chat(params: dict) -> str:
    from ARIA.orchestrator.router import Orchestrator
    return Orchestrator().dispatch(params.get("message", ""))


def _action_shell(params: dict) -> str:
    cmd = params.get("command", "")
    if not cmd:
        return "Komut belirtilmedi"
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
    return r.stdout.strip() or r.stderr.strip() or "Komut tamamlandı"


def _action_remember(params: dict) -> str:
    from ARIA.memory.semantic_context import remember_fact
    text = params.get("text", "")
    remember_fact(text, category=params.get("category", "workflow"))
    return f"Hafızaya kaydedildi: {text[:60]}"


_ACTION_MAP = {
    "brief": _action_brief,
    "weather": _action_weather,
    "tts": _action_tts,
    "notify": _action_notify,
    "get_unread_emails": _action_get_unread_emails,
    "chat": _action_chat,
    "shell": _action_shell,
    "remember": _action_remember,
}


# ── Workflow yürütme ──────────────────────────────────────────────────────────

def _interpolate(text: str, context: dict) -> str:
    """Şablon değişkenlerini doldur: {result}, {date} vb."""
    now = datetime.now()
    ctx = {
        "date": now.strftime("%d.%m.%Y"),
        "time": now.strftime("%H:%M"),
        "weekday": ["Pazartesi","Salı","Çarşamba","Perşembe","Cuma","Cumartesi","Pazar"][now.weekday()],
        **context,
    }
    try:
        return text.format(**ctx)
    except Exception:
        return text


def run_workflow(workflow: dict) -> list[dict]:
    """Bir workflow'u senkron olarak çalıştır, her adımın sonucunu döndür."""
    steps = workflow.get("steps", [])
    results = []
    last_result = ""

    for step in steps:
        action = step.get("action", "")
        params = {k: _interpolate(str(v), {"result": last_result}) if isinstance(v, str) else v
                  for k, v in step.get("params", {}).items()}

        fn = _ACTION_MAP.get(action)
        if not fn:
            results.append({"action": action, "success": False, "error": f"Bilinmeyen aksiyon: {action}"})
            continue

        try:
            result = fn(params)
            last_result = str(result)
            results.append({"action": action, "success": True, "result": last_result})
            logger.info("Workflow adımı tamamlandı: %s → %s", action, last_result[:60])
        except Exception as exc:
            last_result = ""
            results.append({"action": action, "success": False, "error": str(exc)})
            logger.warning("Workflow adımı başarısız: %s — %s", action, exc)

    return results


# ── YAML yönetimi ─────────────────────────────────────────────────────────────

def load_workflows() -> list[dict]:
    """~/.aria/workflows/ dizininden tüm YAML workflow'larını yükle."""
    if not YAML_AVAILABLE:
        return []
    workflows = []
    for path in _WORKFLOWS_DIR.glob("*.yaml"):
        try:
            data = yaml.safe_load(path.read_text())
            if isinstance(data, list):
                workflows.extend(data)
            elif isinstance(data, dict):
                workflows.append(data)
        except Exception as exc:
            logger.warning("Workflow yüklenemedi (%s): %s", path.name, exc)
    return workflows


def save_workflow(workflow: dict) -> Path:
    """Workflow'u YAML olarak kaydet."""
    name = workflow.get("name", f"workflow_{int(time.time())}")
    path = _WORKFLOWS_DIR / f"{name}.yaml"
    if YAML_AVAILABLE:
        path.write_text(yaml.dump(workflow, allow_unicode=True, default_flow_style=False))
    else:
        path.write_text(json.dumps(workflow, ensure_ascii=False, indent=2))
    return path


def delete_workflow(name: str) -> bool:
    path = _WORKFLOWS_DIR / f"{name}.yaml"
    if path.exists():
        path.unlink()
        return True
    return False


def list_workflow_names() -> list[str]:
    return [p.stem for p in _WORKFLOWS_DIR.glob("*.yaml")]


# ── Keyword tetikleyici ────────────────────────────────────────────────────────

def check_keyword_triggers(user_input: str) -> Optional[dict]:
    """Kullanıcı girdisinde keyword trigger'ı olan workflow var mı kontrol et."""
    text = user_input.lower()
    for wf in load_workflows():
        trigger = wf.get("trigger", {})
        if trigger.get("type") == "keyword":
            keywords = trigger.get("keywords", [])
            if any(k.lower() in text for k in keywords):
                return wf
    return None


# ── Zamanlı scheduler entegrasyonu ────────────────────────────────────────────

def start_workflow_scheduler() -> None:
    """Schedule trigger'ı olan workflow'ları cron ile başlat."""
    try:
        import schedule as sched

        def _make_job(wf):
            def job():
                logger.info("Workflow başlatıldı (schedule): %s", wf.get("name"))
                run_workflow(wf)
            return job

        for wf in load_workflows():
            trigger = wf.get("trigger", {})
            if trigger.get("type") == "schedule":
                cron_str = trigger.get("cron", "")
                # Basit cron parse: "0 7 * * 1-5" → her gün 07:00
                parts = cron_str.split()
                if len(parts) >= 2:
                    minute, hour = parts[0], parts[1]
                    time_str = f"{hour.zfill(2)}:{minute.zfill(2)}"
                    sched.every().day.at(time_str).do(_make_job(wf))
                    logger.info("Workflow zamanlandı: %s @ %s", wf.get("name"), time_str)

        def _run_loop():
            while True:
                sched.run_pending()
                time.sleep(30)

        t = threading.Thread(target=_run_loop, daemon=True, name="workflow-scheduler")
        t.start()
        logger.info("Workflow scheduler başlatıldı")
    except Exception as exc:
        logger.warning("Workflow scheduler başlatılamadı: %s", exc)


# ── Varsayılan workflow'ları oluştur ──────────────────────────────────────────

def ensure_default_workflows() -> None:
    """İlk çalıştırmada örnek workflow'ları oluştur."""
    sabah_path = _WORKFLOWS_DIR / "sabah_rutini.yaml"
    if not sabah_path.exists() and YAML_AVAILABLE:
        sabah = {
            "name": "sabah_rutini",
            "description": "Her sabah 07:30'da özet + hava durumu",
            "trigger": {"type": "schedule", "cron": "30 7 * * 1-5"},
            "steps": [
                {"action": "weather", "params": {}},
                {"action": "brief", "params": {"speak": True}},
            ],
        }
        save_workflow(sabah)
        logger.info("Varsayılan sabah rutini workflow'u oluşturuldu")
