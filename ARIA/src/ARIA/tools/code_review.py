"""Code Review Pipeline — git diff → ARIA inceleme → GitHub PR yorumu."""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Optional

from ARIA.core.registry import register_tool

logger = logging.getLogger("aria.tools.code_review")

_CODE_REVIEW_PROMPT = """Sen deneyimli bir kod inceleyicisisin.
Aşağıdaki git diff'i incele ve Türkçe olarak şunları belirt:

**Sorunlar:** Hata, güvenlik açığı, bug riski
**İyileştirmeler:** Performans, okunabilirlik, best practice
**Pozitifler:** İyi yapılmış şeyler (varsa)

Kısa ve net ol. Madde madde listele. Kritik sorunları 🔴, önerileri 🟡, iyi şeyleri 🟢 ile işaretle."""


def _run(cmd: list[str], cwd: Optional[str] = None, timeout: int = 30) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd)
    return r.stdout.strip()


def _find_git_root(path: Optional[str] = None) -> Optional[str]:
    cwd = path or "."
    r = subprocess.run(["git", "-C", cwd, "rev-parse", "--show-toplevel"],
                       capture_output=True, text=True, timeout=5)
    return r.stdout.strip() if r.returncode == 0 else None


def _get_github_token() -> Optional[str]:
    """Keychain veya env'den GitHub token al."""
    try:
        from ARIA.tools.keychain import keychain_get
        r = keychain_get("github_token")
        if r["success"]:
            return r["value"]
    except Exception:
        pass
    import os
    return os.environ.get("GITHUB_TOKEN")


@register_tool("code_review_diff")
def code_review_diff(
    path: Optional[str] = None,
    base: str = "HEAD",
    compare: str = "",
    max_lines: int = 300,
) -> dict:
    """Git diff'i ARIA ile incele.

    Args:
        path: Repo yolu (None = mevcut)
        base: Karşılaştırma tabanı (varsayılan: HEAD)
        compare: Karşılaştırılacak branch/commit (boş = staged/unstaged)
        max_lines: Maksimum diff satırı

    Returns:
        {'review': str, 'diff_lines': int, 'issues': int}
    """
    cwd = _find_git_root(path) or path or "."

    if compare:
        diff = _run(["git", "diff", base, compare, "--", "*.py", "*.ts", "*.tsx", "*.js", "*.go"], cwd=cwd)
    else:
        diff = _run(["git", "diff", "HEAD"], cwd=cwd)
        if not diff:
            diff = _run(["git", "diff", "--cached"], cwd=cwd)

    if not diff.strip():
        return {"success": True, "review": "İncelenecek değişiklik yok.", "diff_lines": 0, "issues": 0}

    lines = diff.splitlines()
    if len(lines) > max_lines:
        diff = "\n".join(lines[:max_lines]) + f"\n... ({len(lines) - max_lines} satır daha)"

    prompt = f"{_CODE_REVIEW_PROMPT}\n\n```diff\n{diff}\n```"

    try:
        from ARIA.core.engine import ARIAEngine
        review = ARIAEngine().chat([{"role": "user", "content": prompt}])
    except Exception as exc:
        return {"success": False, "error": str(exc)}

    issues = review.count("🔴")
    warnings = review.count("🟡")

    return {
        "success": True,
        "review": review,
        "diff_lines": len(lines),
        "issues": issues,
        "warnings": warnings,
        "repo": cwd,
    }


@register_tool("code_review_file")
def code_review_file(file_path: str) -> dict:
    """Tek dosyayı incele.

    Returns:
        {'review': str}
    """
    p = Path(file_path).expanduser()
    if not p.exists():
        return {"success": False, "error": f"Dosya bulunamadı: {file_path}"}

    content = p.read_text(errors="ignore")[:6000]
    prompt = f"{_CODE_REVIEW_PROMPT}\n\nDosya: {p.name}\n\n```\n{content}\n```"

    try:
        from ARIA.core.engine import ARIAEngine
        review = ARIAEngine().chat([{"role": "user", "content": prompt}])
        return {"success": True, "review": review, "file": str(p), "issues": review.count("🔴")}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


@register_tool("code_review_pr")
def code_review_pr(owner: str, repo: str, pr_number: int) -> dict:
    """GitHub PR'ını incele ve yorum bırak.

    Args:
        owner: GitHub kullanıcı/org adı
        repo: Repo adı
        pr_number: PR numarası

    Returns:
        {'review': str, 'comment_posted': bool}
    """
    token = _get_github_token()
    if not token:
        return {
            "success": False,
            "error": "GitHub token bulunamadı. `POST /keychain/set {key: 'github_token', value: 'ghp_...'}`"
        }

    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}

    try:
        import urllib.request, urllib.parse

        # PR diff'ini çek
        diff_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
        req = urllib.request.Request(diff_url, headers={**headers, "Accept": "application/vnd.github.v3.diff"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            diff = resp.read().decode()[:8000]

        if not diff.strip():
            return {"success": False, "error": "PR diff alınamadı"}

        # ARIA ile incele
        prompt = f"{_CODE_REVIEW_PROMPT}\n\nPR: {owner}/{repo}#{pr_number}\n\n```diff\n{diff}\n```"
        from ARIA.core.engine import ARIAEngine
        review = ARIAEngine().chat([{"role": "user", "content": prompt}])

        # PR'a yorum bırak
        comment_url = f"https://api.github.com/repos/{owner}/{repo}/issues/{pr_number}/comments"
        body = f"## 🤖 ARIA Code Review\n\n{review}\n\n---\n*ARIA tarafından otomatik oluşturuldu*"
        payload = json.dumps({"body": body}).encode()

        req = urllib.request.Request(
            comment_url, data=payload,
            headers={**headers, "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            comment_posted = resp.status == 201

        return {
            "success": True,
            "review": review,
            "comment_posted": comment_posted,
            "pr": f"{owner}/{repo}#{pr_number}",
            "issues": review.count("🔴"),
        }

    except Exception as exc:
        logger.error("PR review hatası: %s", exc)
        return {"success": False, "error": str(exc)}


@register_tool("code_review_setup_github")
def code_review_setup_github(token: str) -> dict:
    """GitHub token'ını Keychain'e kaydet.

    Args:
        token: GitHub Personal Access Token (ghp_... veya github_pat_...)

    Returns:
        {'success': bool}
    """
    try:
        from ARIA.tools.keychain import keychain_set
        return keychain_set("github_token", token)
    except Exception as exc:
        return {"success": False, "error": str(exc)}
