"""Local file read/write tools with path guards."""

from __future__ import annotations

from pathlib import Path
from ARIA.core.config import load_config
from ARIA.core.registry import register_tool


def _is_allowed(path: Path) -> bool:
    config = load_config()
    if not config.allow_file_access:
        return False
    resolved = path.expanduser().resolve()
    for base in config.allowed_file_paths:
        base_path = Path(base).expanduser().resolve()
        try:
            resolved.relative_to(base_path)
            return True
        except ValueError:
            continue
    return False


@register_tool("file_read")
def file_read(path: str) -> str:
    target = Path(path)
    if not _is_allowed(target):
        raise PermissionError("Dosya erisimi engellendi")
    return target.read_text(encoding="utf-8", errors="ignore")


@register_tool("file_write")
def file_write(path: str, content: str) -> str:
    target = Path(path)
    if not _is_allowed(target):
        raise PermissionError("Dosya erisimi engellendi")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return "OK"
