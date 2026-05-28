"""Ekran yakalama ve LLM vision analizi — macOS screencapture + Ollama.

Bu dosya screen_capture.py'nin düzeltilmiş implementasyonudur.
screencapture komutunun flag uyumluluğu için fallback mekanizması içerir.
"""

from __future__ import annotations

import base64
import logging
import os
import subprocess
import tempfile
from typing import Optional

from ARIA.core.registry import register_tool

logger = logging.getLogger("aria.tools.screen_capture")

# Vision için tercih edilen modeller (öncelik sırasıyla)
VISION_MODELS = ["llava", "llava:7b", "llava:13b", "qwen2-vl", "moondream"]


def _get_ollama_models() -> list[str]:
    """Mevcut Ollama modellerini listele."""
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True, text=True, timeout=10,
        )
        lines = result.stdout.strip().splitlines()
        models = []
        for line in lines[1:]:  # header satırını atla
            parts = line.split()
            if parts:
                models.append(parts[0])
                base = parts[0].split(":")[0]
                if base not in models:
                    models.append(base)
        return models
    except Exception:
        return []


def _find_vision_model() -> Optional[str]:
    """Yüklü vision modeli bul."""
    available = _get_ollama_models()
    for preferred in VISION_MODELS:
        for m in available:
            if preferred in m:
                return m
    return None


def _take_screenshot(tmp_path: str, region: Optional[str] = None) -> bool:
    """Ekran görüntüsü al — birden fazla yöntem dene."""
    cmds = []

    if region:
        try:
            parts = [int(p.strip()) for p in region.split(",")]
            if len(parts) == 4:
                x, y, w, h = parts
                cmds.append(["screencapture", "-R", f"{x},{y},{w},{h}", tmp_path])
        except ValueError:
            pass

    # Yöntem 1: temel screencapture
    cmds.append(["screencapture", tmp_path])
    # Yöntem 2: -D 1 bayrağıyla (display 1)
    cmds.append(["screencapture", "-D", "1", tmp_path])
    # Yöntem 3: -x sessiz mod (ses yok)
    cmds.append(["screencapture", "-x", tmp_path])

    for cmd in cmds:
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=15)
            if result.returncode == 0 and os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
                return True
        except Exception:
            pass

    return False


@register_tool("capture_screen")
def capture_screen(region: Optional[str] = None) -> dict:
    """macOS ekranını yakala.

    Args:
        region: Opsiyonel bölge "x,y,width,height" formatında (None → tüm ekran)

    Returns:
        {"path": "/tmp/aria_screen_xxx.png", "success": True}
    """
    try:
        tmp_fd, tmp_path = tempfile.mkstemp(prefix="aria_screen_", suffix=".png")
        os.close(tmp_fd)

        success = _take_screenshot(tmp_path, region)
        if not success:
            return {"success": False, "error": "Ekran görüntüsü alınamadı (tüm yöntemler başarısız)"}

        size = os.path.getsize(tmp_path)
        logger.info("Ekran görüntüsü alındı: %s (%d bytes)", tmp_path, size)
        return {"success": True, "path": tmp_path, "size": size}

    except Exception as exc:
        logger.error("capture_screen hatası: %s", exc)
        return {"success": False, "error": str(exc)}


@register_tool("analyze_screen")
def analyze_screen(question: str = "Ekranda ne var?") -> dict:
    """Ekranı yakala ve LLM vision ile analiz et.

    Args:
        question: Ekran hakkında sorulacak soru

    Returns:
        {"success": True, "analysis": "...", "model": "llava"}
    """
    img_path = None
    try:
        # 1. Ekranı yakala
        capture_result = capture_screen()
        if not capture_result.get("success"):
            return {
                "success": False,
                "error": capture_result.get("error", "Ekran yakalanamadı"),
            }

        img_path = capture_result["path"]

        # 2. Vision modeli bul
        vision_model = _find_vision_model()
        if not vision_model:
            return {
                "success": False,
                "error": (
                    "llava modeli yüklü değil. "
                    "'ollama pull llava' komutu ile yükleyebilirsin."
                ),
            }

        # 3. PNG'yi base64'e çevir
        with open(img_path, "rb") as f:
            img_data = f.read()
        b64 = base64.b64encode(img_data).decode("utf-8")

        # 4. Ollama vision API'ye gönder
        import json
        import urllib.request

        payload = {
            "model": vision_model,
            "messages": [
                {
                    "role": "user",
                    "content": question,
                    "images": [b64],
                }
            ],
            "stream": False,
        }

        req = urllib.request.Request(
            "http://localhost:11434/api/chat",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=60) as resp:
            result_data = json.loads(resp.read().decode())

        analysis = result_data.get("message", {}).get("content", "")
        return {
            "success": True,
            "analysis": analysis,
            "model": vision_model,
            "question": question,
        }

    except Exception as exc:
        logger.error("analyze_screen hatası: %s", exc)
        return {"success": False, "error": str(exc)}
    finally:
        # Geçici dosyayı temizle
        if img_path and os.path.exists(img_path):
            try:
                os.unlink(img_path)
            except Exception:
                pass
