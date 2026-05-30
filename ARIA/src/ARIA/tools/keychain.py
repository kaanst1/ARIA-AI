"""macOS Keychain entegrasyonu — güvenli credential yönetimi."""

from __future__ import annotations

import logging
import subprocess
from typing import Optional

from ARIA.core.registry import register_tool

logger = logging.getLogger("aria.tools.keychain")

_SERVICE = "ARIA"


def _run(cmd: list[str]) -> tuple[str, int]:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    return r.stdout.strip(), r.returncode


@register_tool("keychain_set")
def keychain_set(key: str, value: str, account: str = "aria") -> dict:
    """macOS Keychain'e güvenli değer kaydet.

    Args:
        key: Anahtar adı (örn: 'openai_api_key')
        value: Saklanacak değer
        account: Hesap adı (varsayılan: 'aria')

    Returns:
        {'success': bool, 'key': str}
    """
    # Önce sil (varsa üzerine yaz)
    subprocess.run(
        ["security", "delete-generic-password", "-s", f"{_SERVICE}_{key}", "-a", account],
        capture_output=True, timeout=5,
    )
    out, rc = _run([
        "security", "add-generic-password",
        "-s", f"{_SERVICE}_{key}",
        "-a", account,
        "-w", value,
    ])
    if rc == 0:
        logger.info("Keychain'e kaydedildi: %s", key)
        return {"success": True, "key": key}
    return {"success": False, "error": out or "Keychain hatası", "key": key}


@register_tool("keychain_get")
def keychain_get(key: str, account: str = "aria") -> dict:
    """macOS Keychain'den değer oku.

    Args:
        key: Anahtar adı
        account: Hesap adı

    Returns:
        {'success': bool, 'key': str, 'value': str}
    """
    out, rc = _run([
        "security", "find-generic-password",
        "-s", f"{_SERVICE}_{key}",
        "-a", account,
        "-w",  # sadece şifreyi döndür
    ])
    if rc == 0 and out:
        return {"success": True, "key": key, "value": out}
    return {"success": False, "key": key, "value": "", "error": "Bulunamadı"}


@register_tool("keychain_delete")
def keychain_delete(key: str, account: str = "aria") -> dict:
    """Keychain'den değeri sil.

    Returns:
        {'success': bool, 'key': str}
    """
    _, rc = _run([
        "security", "delete-generic-password",
        "-s", f"{_SERVICE}_{key}",
        "-a", account,
    ])
    return {"success": rc == 0, "key": key}


@register_tool("keychain_list")
def keychain_list(account: str = "aria") -> dict:
    """ARIA'nın Keychain'de sakladığı anahtarları listele (değerler gösterilmez).

    Returns:
        {'keys': list[str]}
    """
    out, rc = _run([
        "security", "dump-keychain",
    ])
    keys = []
    if rc == 0:
        import re
        # ARIA_ ile başlayan service'leri bul
        matches = re.findall(rf'"svce"<blob>="{_SERVICE}_([^"]+)"', out)
        keys = list(set(matches))
    return {"keys": keys, "count": len(keys), "success": True}


def get_credential(key: str) -> Optional[str]:
    """Credential'ı Keychain'den çek; bulamazsa None döndür (programatik kullanım)."""
    result = keychain_get(key)
    return result["value"] if result["success"] else None


def set_credential(key: str, value: str) -> bool:
    """Credential'ı Keychain'e kaydet (programatik kullanım)."""
    return keychain_set(key, value)["success"]
