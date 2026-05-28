"""macOS Spotlight ile dosya arama — mdfind tabanlı."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Optional

from ARIA.core.registry import register_tool

logger = logging.getLogger("aria.tools.spotlight")

_HOME = Path.home()


@register_tool("spotlight_search")
def spotlight_search(
    query: str,
    kind: Optional[str] = None,
    limit: int = 10,
    scope: Optional[str] = None,
) -> dict:
    """Spotlight (mdfind) ile dosya ara.

    Args:
        query: Arama metni
        kind: 'pdf', 'image', 'video', 'audio', 'document', 'code', None (hepsi)
        limit: Maksimum sonuç sayısı
        scope: Arama dizini (None = tüm disk)

    Returns:
        {'results': list[dict], 'count': int}
    """
    kind_map = {
        "pdf": "kMDItemContentType == 'com.adobe.pdf'",
        "image": "kMDItemContentTypeTree == 'public.image'",
        "video": "kMDItemContentTypeTree == 'public.movie'",
        "audio": "kMDItemContentTypeTree == 'public.audio'",
        "document": "kMDItemContentTypeTree == 'public.text'",
        "code": "kMDItemContentTypeTree == 'public.source-code'",
    }

    cmd = ["mdfind"]

    if scope:
        cmd += ["-onlyin", str(scope)]
    else:
        cmd += ["-onlyin", str(_HOME)]

    if kind and kind.lower() in kind_map:
        mdfind_query = f'({kind_map[kind.lower()]}) && kMDItemFSName == "*{query}*"cdw'
    else:
        mdfind_query = query

    cmd.append(mdfind_query)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        lines = [l.strip() for l in result.stdout.splitlines() if l.strip()][:limit]
        results = []
        for path_str in lines:
            p = Path(path_str)
            results.append({
                "name": p.name,
                "path": path_str,
                "ext": p.suffix.lower(),
                "parent": str(p.parent),
            })
        return {"results": results, "count": len(results), "success": True, "query": query}
    except Exception as exc:
        logger.warning("Spotlight arama hatası: %s", exc)
        return {"success": False, "error": str(exc), "results": [], "count": 0}


@register_tool("spotlight_find_app")
def spotlight_find_app(app_name: str) -> dict:
    """Spotlight ile uygulama bul.

    Args:
        app_name: Uygulama adı

    Returns:
        {'path': str, 'found': bool}
    """
    cmd = [
        "mdfind",
        "-onlyin", "/Applications",
        f'kMDItemContentType == "com.apple.application-bundle" && kMDItemFSName == "*{app_name}*"cdw',
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        lines = [l.strip() for l in result.stdout.splitlines() if l.strip()]
        if lines:
            return {"path": lines[0], "name": Path(lines[0]).stem, "found": True, "success": True}
        return {"found": False, "success": True, "path": ""}
    except Exception as exc:
        return {"success": False, "error": str(exc), "found": False, "path": ""}
