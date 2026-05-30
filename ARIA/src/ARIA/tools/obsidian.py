"""Obsidian vault entegrasyonu — not oluştur, ara, daily note'a ekle."""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from ARIA.core.registry import register_tool

logger = logging.getLogger("aria.tools.obsidian")

_CONFIG_FILE = Path.home() / ".aria" / "obsidian_config.json"


def _load_vault_path() -> Optional[Path]:
    """Obsidian vault yolunu config'den veya otomatik bul."""
    # Config dosyasından
    if _CONFIG_FILE.exists():
        try:
            data = json.loads(_CONFIG_FILE.read_text())
            p = Path(data.get("vault_path", ""))
            if p.exists():
                return p
        except Exception:
            pass

    # Obsidian'ın kendi config'inden bul
    obsidian_config = Path.home() / "Library" / "Application Support" / "obsidian" / "obsidian.json"
    if obsidian_config.exists():
        try:
            data = json.loads(obsidian_config.read_text())
            vaults = data.get("vaults", {})
            for vault_id, vault_data in vaults.items():
                vault_path = vault_data.get("path", "")
                if vault_path and Path(vault_path).exists():
                    return Path(vault_path)
        except Exception:
            pass

    # Yaygın yerler
    for candidate in [
        Path.home() / "Documents" / "Obsidian",
        Path.home() / "Obsidian",
        Path.home() / "Documents" / "vault",
        Path.home() / "vault",
    ]:
        if candidate.exists() and (candidate / ".obsidian").exists():
            return candidate

    return None


def _vault() -> Path:
    v = _load_vault_path()
    if not v:
        raise RuntimeError(
            "Obsidian vault bulunamadı. "
            "aria-obsidian-setup <vault_yolu> komutuyla ayarla."
        )
    return v


def _sanitize_title(title: str) -> str:
    """Dosya adına uygun başlık yap."""
    return re.sub(r'[\\/:*?"<>|]', "-", title).strip()


def _open_in_obsidian(file_path: Path) -> None:
    """Obsidian'da dosyayı aç."""
    try:
        vault = _vault()
        rel = file_path.relative_to(vault)
        uri = f"obsidian://open?vault={vault.name}&file={rel}"
        subprocess.run(["open", uri], capture_output=True, timeout=5)
    except Exception:
        pass


@register_tool("obsidian_create_note")
def obsidian_create_note(
    title: str,
    content: str,
    folder: str = "",
    tags: Optional[list] = None,
    open_after: bool = False,
) -> dict:
    """Obsidian vault'ta yeni not oluştur.

    Args:
        title: Not başlığı
        content: Not içeriği (Markdown)
        folder: Alt klasör (boş = vault kökü)
        tags: Etiket listesi
        open_after: Oluşturduktan sonra Obsidian'da aç

    Returns:
        {'success': bool, 'path': str, 'title': str}
    """
    try:
        vault = _vault()
        safe_title = _sanitize_title(title)

        target_dir = vault / folder if folder else vault
        target_dir.mkdir(parents=True, exist_ok=True)
        file_path = target_dir / f"{safe_title}.md"

        # Frontmatter
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        tag_str = "\n".join(f"  - {t}" for t in (tags or []))
        frontmatter = f"---\ncreated: {now}\n"
        if tags:
            frontmatter += f"tags:\n{tag_str}\n"
        frontmatter += "---\n\n"

        file_path.write_text(frontmatter + content, encoding="utf-8")

        if open_after:
            _open_in_obsidian(file_path)

        logger.info("Obsidian notu oluşturuldu: %s", file_path)
        return {
            "success": True,
            "path": str(file_path),
            "title": title,
            "relative": str(file_path.relative_to(vault)),
        }
    except Exception as exc:
        logger.warning("Obsidian notu oluşturulamadı: %s", exc)
        return {"success": False, "error": str(exc)}


@register_tool("obsidian_append_daily")
def obsidian_append_daily(content: str, heading: str = "") -> dict:
    """Bugünün daily note'una içerik ekle (yoksa oluştur).

    Args:
        content: Eklenecek metin
        heading: İçeriğin altına ekleneceği başlık (boş = en alta)

    Returns:
        {'success': bool, 'path': str}
    """
    try:
        vault = _vault()
        today = datetime.now().strftime("%Y-%m-%d")
        daily_dir = vault / "Daily Notes"
        daily_dir.mkdir(parents=True, exist_ok=True)
        file_path = daily_dir / f"{today}.md"

        if not file_path.exists():
            file_path.write_text(f"# {today}\n\n", encoding="utf-8")

        existing = file_path.read_text(encoding="utf-8")
        ts = datetime.now().strftime("%H:%M")

        if heading and f"## {heading}" in existing:
            # Başlığın altına ekle
            parts = existing.split(f"## {heading}")
            after = parts[1]
            next_h = re.search(r'\n## ', after)
            insert_at = next_h.start() if next_h else len(after)
            new_content = (
                parts[0] + f"## {heading}" +
                after[:insert_at] + f"\n- [{ts}] {content}\n" +
                after[insert_at:]
            )
        else:
            # En alta ekle
            new_content = existing.rstrip() + f"\n\n- [{ts}] {content}\n"

        file_path.write_text(new_content, encoding="utf-8")
        return {"success": True, "path": str(file_path), "date": today}
    except Exception as exc:
        logger.warning("Daily note güncellenemedi: %s", exc)
        return {"success": False, "error": str(exc)}


@register_tool("obsidian_search")
def obsidian_search(query: str, limit: int = 10) -> dict:
    """Vault'ta metin ara (grep tabanlı).

    Returns:
        {'results': list[dict], 'count': int}
    """
    try:
        vault = _vault()
        result = subprocess.run(
            ["grep", "-rli", "--include=*.md", query, str(vault)],
            capture_output=True, text=True, timeout=15,
        )
        files = [l.strip() for l in result.stdout.splitlines() if l.strip()][:limit]
        results = []
        for f in files:
            p = Path(f)
            try:
                text = p.read_text(encoding="utf-8")
                # İlk eşleşen satırı bul
                match_line = next(
                    (l.strip() for l in text.splitlines() if query.lower() in l.lower()),
                    ""
                )
                results.append({
                    "title": p.stem,
                    "path": f,
                    "preview": match_line[:150],
                    "relative": str(p.relative_to(vault)),
                })
            except Exception:
                pass
        return {"results": results, "count": len(results), "success": True}
    except Exception as exc:
        return {"success": False, "error": str(exc), "results": []}


@register_tool("obsidian_get_note")
def obsidian_get_note(title: str) -> dict:
    """Başlığa göre Obsidian notu getir.

    Returns:
        {'content': str, 'path': str, 'found': bool}
    """
    try:
        vault = _vault()
        # Tam eşleşme ara
        matches = list(vault.rglob(f"{_sanitize_title(title)}.md"))
        if not matches:
            # Kısmi eşleşme
            matches = [p for p in vault.rglob("*.md") if title.lower() in p.stem.lower()]

        if not matches:
            return {"found": False, "content": "", "path": ""}

        p = matches[0]
        content = p.read_text(encoding="utf-8")
        return {"found": True, "content": content, "path": str(p), "title": p.stem, "success": True}
    except Exception as exc:
        return {"success": False, "error": str(exc), "found": False, "content": ""}


@register_tool("obsidian_setup")
def obsidian_setup(vault_path: str) -> dict:
    """Obsidian vault yolunu kaydet.

    Args:
        vault_path: Obsidian vault'unun tam yolu

    Returns:
        {'success': bool, 'vault': str}
    """
    p = Path(vault_path).expanduser()
    if not p.exists():
        return {"success": False, "error": f"Yol bulunamadı: {vault_path}"}

    _CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    _CONFIG_FILE.write_text(json.dumps({"vault_path": str(p)}, indent=2))
    return {"success": True, "vault": str(p)}


@register_tool("obsidian_vault_info")
def obsidian_vault_info() -> dict:
    """Vault bilgilerini döndür.

    Returns:
        {'vault': str, 'note_count': int, 'found': bool}
    """
    try:
        vault = _vault()
        notes = list(vault.rglob("*.md"))
        return {
            "found": True,
            "vault": str(vault),
            "name": vault.name,
            "note_count": len(notes),
            "success": True,
        }
    except Exception as exc:
        return {"found": False, "error": str(exc), "success": False}
