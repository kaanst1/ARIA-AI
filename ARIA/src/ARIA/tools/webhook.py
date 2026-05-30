"""Webhook Köprüsü — dış sistemlerden ARIA'yı tetikle."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from ARIA.core.registry import register_tool

logger = logging.getLogger("aria.tools.webhook")

_ARIA_DIR = Path.home() / ".aria"
_WEBHOOKS_FILE = _ARIA_DIR / "webhooks.json"
_WEBHOOK_LOG = _ARIA_DIR / "webhook_events.json"


def _load_webhooks() -> dict:
    if _WEBHOOKS_FILE.exists():
        try:
            return json.loads(_WEBHOOKS_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_webhooks(webhooks: dict) -> None:
    _WEBHOOKS_FILE.write_text(json.dumps(webhooks, ensure_ascii=False, indent=2))


def _log_event(webhook_id: str, payload: dict, result: str) -> None:
    events = []
    if _WEBHOOK_LOG.exists():
        try:
            events = json.loads(_WEBHOOK_LOG.read_text())
        except Exception:
            pass
    events.insert(0, {
        "webhook_id": webhook_id,
        "received_at": datetime.now().isoformat(),
        "payload_keys": list(payload.keys()),
        "result_preview": result[:100],
    })
    _WEBHOOK_LOG.write_text(json.dumps(events[:100], ensure_ascii=False, indent=2))


@register_tool("webhook_register")
def webhook_register(
    webhook_id: str,
    action: str,
    message_template: str = "",
    secret: str = "",
    description: str = "",
) -> dict:
    """Webhook kaydı oluştur.

    Args:
        webhook_id: Benzersiz webhook ID (URL'de kullanılır: /webhook/{webhook_id})
        action: Tetiklenecek aksiyon — 'chat', 'brief', 'notify', 'workflow'
        message_template: Chat için mesaj şablonu — {payload.field} kullanılabilir
        secret: HMAC imza doğrulama için gizli anahtar (opsiyonel)
        description: Açıklama

    Returns:
        {'webhook_id': str, 'url': str}
    """
    webhooks = _load_webhooks()
    webhooks[webhook_id] = {
        "id": webhook_id,
        "action": action,
        "message_template": message_template,
        "secret": secret,
        "description": description,
        "created_at": datetime.now().isoformat(),
        "trigger_count": 0,
    }
    _save_webhooks(webhooks)
    return {
        "success": True,
        "webhook_id": webhook_id,
        "url": f"http://localhost:8000/webhook/{webhook_id}",
        "description": description,
    }


@register_tool("webhook_list")
def webhook_list() -> dict:
    """Kayıtlı webhook'ları listele.

    Returns:
        {'webhooks': list[dict]}
    """
    webhooks = _load_webhooks()
    return {
        "webhooks": [
            {"id": k, "action": v["action"], "description": v.get("description", ""),
             "trigger_count": v.get("trigger_count", 0)}
            for k, v in webhooks.items()
        ],
        "count": len(webhooks),
        "success": True,
    }


@register_tool("webhook_delete")
def webhook_delete(webhook_id: str) -> dict:
    """Webhook'u sil."""
    webhooks = _load_webhooks()
    if webhook_id not in webhooks:
        return {"success": False, "error": f"Bulunamadı: {webhook_id}"}
    del webhooks[webhook_id]
    _save_webhooks(webhooks)
    return {"success": True, "deleted": webhook_id}


def process_webhook(webhook_id: str, payload: dict, signature: str = "") -> dict:
    """Webhook'u işle — API endpoint'ten çağrılır."""
    webhooks = _load_webhooks()
    wh = webhooks.get(webhook_id)
    if not wh:
        return {"success": False, "error": f"Bilinmeyen webhook: {webhook_id}"}

    # HMAC doğrulama
    if wh.get("secret") and signature:
        expected = hmac.new(
            wh["secret"].encode(),
            json.dumps(payload, sort_keys=True).encode(),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return {"success": False, "error": "İmza doğrulama başarısız"}

    action = wh["action"]
    template = wh.get("message_template", "")

    # Şablonu doldur
    def _fill(text: str) -> str:
        for key, val in payload.items():
            text = text.replace(f"{{{key}}}", str(val))
            text = text.replace(f"{{payload.{key}}}", str(val))
        return text

    result = ""

    try:
        if action == "chat":
            message = _fill(template) if template else json.dumps(payload)
            from ARIA.orchestrator.router import Orchestrator
            result = Orchestrator().dispatch(message)

        elif action == "brief":
            from ARIA.agents.brief import BriefAgent
            result = BriefAgent().run(speak=False)

        elif action == "notify":
            title = _fill(wh.get("notify_title", "ARIA Webhook"))
            message = _fill(template or json.dumps(payload)[:200])
            import subprocess
            subprocess.run(
                ["osascript", "-e", f'display notification "{message}" with title "{title}"'],
                capture_output=True, timeout=5,
            )
            result = f"Bildirim gönderildi: {message}"

        elif action == "workflow":
            workflow_name = wh.get("workflow_name", "")
            if workflow_name:
                from ARIA.automation.workflow_engine import load_workflows, run_workflow
                wfs = {w.get("name"): w for w in load_workflows()}
                if workflow_name in wfs:
                    steps = run_workflow(wfs[workflow_name])
                    result = "; ".join(s.get("result", "")[:50] for s in steps if s.get("success"))
                else:
                    result = f"Workflow bulunamadı: {workflow_name}"

        elif action == "tts":
            message = _fill(template or "Webhook tetiklendi")
            from ARIA.tools.tts import speak
            speak(message, lang="tr", block=False)
            result = f"TTS: {message}"

        else:
            result = f"Bilinmeyen aksiyon: {action}"

    except Exception as exc:
        logger.error("Webhook işleme hatası: %s", exc)
        result = f"Hata: {exc}"

    # İstatistik güncelle
    webhooks[webhook_id]["trigger_count"] = webhooks[webhook_id].get("trigger_count", 0) + 1
    webhooks[webhook_id]["last_triggered"] = datetime.now().isoformat()
    _save_webhooks(webhooks)

    _log_event(webhook_id, payload, result)
    return {"success": True, "webhook_id": webhook_id, "result": result}
