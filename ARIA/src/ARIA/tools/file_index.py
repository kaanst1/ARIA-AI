"""Dosya index ve arama — ~/.aria/file_index.json'da JSON index."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from ARIA.core.registry import register_tool

logger = logging.getLogger("aria.tools.file_index")

# Güvenli okunabilir uzantılar
_SAFE_EXTENSIONS = {".txt", ".md", ".py", ".json", ".csv", ".log", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".sh", ".rs", ".js", ".ts", ".html", ".css"}
_MAX_FILE_SIZE = 50 * 1024  # 50 KB

# Varsayılan index dizinleri
_DEFAULT_DIRS = [
    Path.home() / "Documents",
    Path.home() / "Desktop",
    Path.home() / "Downloads",
]

_ARIA_DIR = Path.home() / ".aria"
_INDEX_PATH = _ARIA_DIR / "file_index.json"


class FileIndexer:
    """Dosya sistemi indexleyici."""

    def __init__(self) -> None:
        _ARIA_DIR.mkdir(parents=True, exist_ok=True)
        self.index: list[dict] = self._load_index()

    def _load_index(self) -> list[dict]:
        if _INDEX_PATH.exists():
            try:
                with open(_INDEX_PATH, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def _save_index(self) -> None:
        with open(_INDEX_PATH, "w", encoding="utf-8") as f:
            json.dump(self.index, f, ensure_ascii=False, indent=2)

    def build_index(self, dirs: Optional[list[Path]] = None) -> int:
        """Belirtilen dizinleri tara ve index oluştur."""
        search_dirs = dirs or _DEFAULT_DIRS
        entries = []

        for search_dir in search_dirs:
            if not search_dir.exists():
                continue
            try:
                for root, _, files in os.walk(str(search_dir)):
                    for fname in files:
                        fpath = Path(root) / fname
                        try:
                            stat = fpath.stat()
                            entries.append({
                                "name": fname,
                                "path": str(fpath),
                                "size": stat.st_size,
                                "ext": fpath.suffix.lower(),
                                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                                "dir": str(fpath.parent),
                            })
                        except (PermissionError, OSError):
                            continue
            except (PermissionError, OSError) as exc:
                logger.warning("Dizin okunamadı %s: %s", search_dir, exc)

        self.index = entries
        self._save_index()
        return len(entries)

    def search(self, query: str, limit: int = 20) -> list[dict]:
        """Dosya adı veya path'te query'i ara."""
        query_lower = query.lower()
        results = []
        for entry in self.index:
            if (query_lower in entry["name"].lower() or
                    query_lower in entry["path"].lower()):
                results.append(entry)
                if len(results) >= limit:
                    break
        return results

    def read_file_safe(self, path: str) -> str:
        """Güvenli dosya okuma — sadece izin verilen uzantılar, max 50KB."""
        fpath = Path(path).expanduser()

        if not fpath.exists():
            return f"Hata: Dosya bulunamadı — {path}"

        if fpath.suffix.lower() not in _SAFE_EXTENSIONS:
            return f"Hata: İzin verilmeyen dosya uzantısı — {fpath.suffix}"

        if fpath.stat().st_size > _MAX_FILE_SIZE:
            return f"Hata: Dosya çok büyük (max {_MAX_FILE_SIZE // 1024}KB) — {fpath.stat().st_size // 1024}KB"

        try:
            with open(fpath, encoding="utf-8", errors="replace") as f:
                return f.read()
        except PermissionError:
            return f"Hata: Dosyaya erişim izni yok — {path}"
        except Exception as exc:
            return f"Hata: {exc}"


_indexer = FileIndexer()


@register_tool("search_files")
def search_files(query: str) -> list[dict]:
    """Dosya sisteminde dosya ara.

    Args:
        query: Aranacak dosya adı veya path parçası.

    Returns:
        Eşleşen dosyaların listesi.
    """
    # Index yoksa veya boşsa, önce build et
    if not _indexer.index:
        logger.info("Dosya index'i yeniden oluşturuluyor...")
        _indexer.build_index()
    return _indexer.search(query)


@register_tool("read_file")
def read_file(path: str) -> str:
    """Dosya içeriğini güvenli şekilde oku (max 50KB, güvenli uzantılar).

    Args:
        path: Okunacak dosyanın yolu.

    Returns:
        Dosya içeriği veya hata mesajı.
    """
    return _indexer.read_file_safe(path)


@register_tool("index_files")
def index_files(dirs: Optional[list[str]] = None) -> dict:
    """Dosya index'ini yenile.

    Args:
        dirs: Taranacak dizinler (None ise varsayılan dizinler).

    Returns:
        {'indexed': int, 'message': str}
    """
    dir_paths = [Path(d).expanduser() for d in dirs] if dirs else None
    count = _indexer.build_index(dirs=dir_paths)
    return {"indexed": count, "message": f"{count} dosya indexlendi"}
