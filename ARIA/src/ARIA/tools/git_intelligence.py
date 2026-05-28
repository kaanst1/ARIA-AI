"""Git / kod zekası — commit özeti, PR analizi, TODO tarama."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Optional

from ARIA.core.registry import register_tool

logger = logging.getLogger("aria.tools.git")


def _run(cmd: list[str], cwd: Optional[str] = None, timeout: int = 20) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd)
        return r.stdout.strip()
    except Exception as exc:
        return f"Hata: {exc}"


def _find_git_root(path: Optional[str] = None) -> Optional[str]:
    start = path or str(Path.home())
    result = subprocess.run(
        ["git", "-C", start, "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, timeout=5,
    )
    return result.stdout.strip() if result.returncode == 0 else None


@register_tool("git_log_summary")
def git_log_summary(path: Optional[str] = None, count: int = 10) -> dict:
    """Son commit'leri özetle.

    Args:
        path: Git repo yolu (None = mevcut dizin)
        count: Kaç commit

    Returns:
        {'summary': str, 'commits': list[dict]}
    """
    cwd = _find_git_root(path) or path
    if not cwd:
        return {"success": False, "error": "Git repo bulunamadı", "commits": []}

    raw = _run(["git", "log", f"-{count}", "--pretty=format:%h|%an|%ar|%s", "--no-merges"], cwd=cwd)
    commits = []
    for line in raw.splitlines():
        parts = line.split("|", 3)
        if len(parts) == 4:
            commits.append({"hash": parts[0], "author": parts[1], "when": parts[2], "message": parts[3]})

    if not commits:
        return {"success": True, "commits": [], "summary": "Commit bulunamadı."}

    # LLM özeti
    log_text = "\n".join(f"• {c['when']}: {c['message']} ({c['author']})" for c in commits)
    prompt = f"Aşağıdaki git commit geçmişini kısaca Türkçe özetle (3-5 cümle):\n\n{log_text}"
    try:
        from ARIA.core.engine import ARIAEngine
        summary = ARIAEngine().chat([{"role": "user", "content": prompt}])
    except Exception:
        summary = log_text

    return {"success": True, "commits": commits, "summary": summary, "repo": cwd}


@register_tool("git_status_summary")
def git_status_summary(path: Optional[str] = None) -> dict:
    """Git durumunu özetle.

    Returns:
        {'status': str, 'changed_files': list, 'branch': str, 'ahead': int}
    """
    cwd = _find_git_root(path) or path
    if not cwd:
        return {"success": False, "error": "Git repo bulunamadı"}

    branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd)
    status_raw = _run(["git", "status", "--short"], cwd=cwd)
    changed = [l.strip() for l in status_raw.splitlines() if l.strip()]

    ahead_raw = _run(["git", "rev-list", "--count", f"origin/{branch}..HEAD"], cwd=cwd)
    try:
        ahead = int(ahead_raw)
    except ValueError:
        ahead = 0

    status_parts = []
    if changed:
        status_parts.append(f"{len(changed)} değişiklik var")
    if ahead > 0:
        status_parts.append(f"{ahead} commit push edilmedi")
    status = ", ".join(status_parts) or "Temiz — değişiklik yok"

    return {
        "success": True,
        "branch": branch,
        "status": status,
        "changed_files": changed[:20],
        "ahead_of_origin": ahead,
        "repo": cwd,
    }


@register_tool("git_todo_scan")
def git_todo_scan(path: Optional[str] = None, extensions: Optional[list] = None) -> dict:
    """Kod tabanında TODO, FIXME, HACK gibi yorumları tara.

    Returns:
        {'todos': list[dict], 'count': int}
    """
    cwd = _find_git_root(path) or path or str(Path.home())
    exts = extensions or ["py", "ts", "tsx", "js", "jsx", "go", "rs", "swift"]
    ext_args = []
    for ext in exts:
        ext_args += ["--include", f"*.{ext}"]

    patterns = ["TODO", "FIXME", "HACK", "XXX", "BUG", "NOQA"]
    pattern_arg = "|".join(patterns)

    try:
        result = subprocess.run(
            ["grep", "-rn", "--color=never", "-E", pattern_arg] + ext_args + ["."],
            capture_output=True, text=True, timeout=15, cwd=cwd,
        )
        lines = result.stdout.splitlines()[:50]
        todos = []
        for line in lines:
            parts = line.split(":", 2)
            if len(parts) >= 3:
                todos.append({"file": parts[0], "line": parts[1], "text": parts[2].strip()})

        return {"success": True, "todos": todos, "count": len(todos), "repo": cwd}
    except Exception as exc:
        return {"success": False, "error": str(exc), "todos": []}


@register_tool("git_diff_summary")
def git_diff_summary(path: Optional[str] = None) -> dict:
    """Staged ve unstaged değişiklikleri LLM ile özetle.

    Returns:
        {'summary': str, 'diff_lines': int}
    """
    cwd = _find_git_root(path) or path
    if not cwd:
        return {"success": False, "error": "Git repo bulunamadı"}

    diff = _run(["git", "diff", "HEAD"], cwd=cwd)
    if not diff.strip():
        return {"success": True, "summary": "Değişiklik yok.", "diff_lines": 0}

    diff_short = diff[:3000]
    prompt = f"Aşağıdaki git diff'i Türkçe kısaca özetle — ne değişti, neden önemli:\n\n{diff_short}"
    try:
        from ARIA.core.engine import ARIAEngine
        summary = ARIAEngine().chat([{"role": "user", "content": prompt}])
    except Exception:
        summary = f"{len(diff.splitlines())} satır değişiklik"

    return {"success": True, "summary": summary, "diff_lines": len(diff.splitlines())}
