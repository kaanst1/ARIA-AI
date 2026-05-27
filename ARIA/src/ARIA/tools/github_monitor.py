"""GitHub izleme araçları — gh CLI kullanarak."""

from __future__ import annotations

import json
import logging
import subprocess
from typing import Optional

from ARIA.core.registry import register_tool

logger = logging.getLogger("aria.tools.github_monitor")


def _run_gh(args: list[str], timeout: int = 15) -> tuple[str, str, int]:
    """gh CLI komutunu çalıştır. (stdout, stderr, returncode) döndür."""
    try:
        result = subprocess.run(
            ["gh"] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout, result.stderr, result.returncode
    except FileNotFoundError:
        return "", "gh CLI bulunamadı. Kurulum: https://cli.github.com", -1
    except subprocess.TimeoutExpired:
        return "", f"Zaman aşımı ({timeout}s)", -1
    except Exception as exc:
        return "", str(exc), -1


def _parse_json_safe(text: str) -> Optional[list | dict]:
    try:
        return json.loads(text)
    except Exception:
        return None


def get_my_prs() -> list[dict]:
    """Kendi açık pull request'lerini al."""
    stdout, stderr, rc = _run_gh([
        "pr", "list",
        "--author", "@me",
        "--state", "open",
        "--json", "number,title,repository,url,createdAt,reviewDecision",
        "--limit", "20",
    ])
    if rc != 0:
        return [{"error": stderr or "gh komutu başarısız"}]
    data = _parse_json_safe(stdout)
    if data is None:
        return [{"error": "JSON parse hatası", "raw": stdout[:200]}]
    return data if isinstance(data, list) else [data]


def get_repo_issues(repo: str) -> list[dict]:
    """Bir repo'nun açık issue'larını al."""
    stdout, stderr, rc = _run_gh([
        "issue", "list",
        "--repo", repo,
        "--state", "open",
        "--json", "number,title,url,createdAt,labels",
        "--limit", "20",
    ])
    if rc != 0:
        return [{"error": stderr or f"{repo} issue'ları alınamadı"}]
    data = _parse_json_safe(stdout)
    if data is None:
        return [{"error": "JSON parse hatası"}]
    return data if isinstance(data, list) else [data]


def get_notifications() -> list[dict]:
    """GitHub bildirimlerini al."""
    stdout, stderr, rc = _run_gh([
        "api", "notifications",
        "--paginate",
        "-X", "GET",
        "-f", "per_page=20",
    ])
    if rc != 0:
        return [{"error": stderr or "Bildirimler alınamadı"}]
    data = _parse_json_safe(stdout)
    if data is None:
        return [{"error": "JSON parse hatası"}]
    # Sadece önemli alanları döndür
    if isinstance(data, list):
        return [
            {
                "id": n.get("id"),
                "type": n.get("subject", {}).get("type"),
                "title": n.get("subject", {}).get("title"),
                "repo": n.get("repository", {}).get("full_name"),
                "reason": n.get("reason"),
                "unread": n.get("unread"),
                "updated_at": n.get("updated_at"),
            }
            for n in data[:20]
        ]
    return []


def get_recent_commits(repo: str, n: int = 5) -> list[dict]:
    """Bir repo'nun son commitlerini al."""
    stdout, stderr, rc = _run_gh([
        "api", f"repos/{repo}/commits",
        "-X", "GET",
        "-f", f"per_page={n}",
    ])
    if rc != 0:
        return [{"error": stderr or f"{repo} commit'leri alınamadı"}]
    data = _parse_json_safe(stdout)
    if data is None:
        return [{"error": "JSON parse hatası"}]
    if isinstance(data, list):
        return [
            {
                "sha": c.get("sha", "")[:7],
                "message": c.get("commit", {}).get("message", "")[:100],
                "author": c.get("commit", {}).get("author", {}).get("name"),
                "date": c.get("commit", {}).get("author", {}).get("date"),
                "url": c.get("html_url"),
            }
            for c in data[:n]
        ]
    return []


@register_tool("github_prs")
def github_prs() -> list[dict]:
    """GitHub'da açık pull request'lerini listele.

    Returns:
        PR listesi.
    """
    return get_my_prs()


@register_tool("github_notifications")
def github_notifications() -> list[dict]:
    """GitHub bildirimlerini al.

    Returns:
        Bildirim listesi.
    """
    return get_notifications()


@register_tool("github_issues")
def github_issues(repo: str) -> list[dict]:
    """Bir repo'nun açık issue'larını listele.

    Args:
        repo: GitHub repo (owner/repo formatında).

    Returns:
        Issue listesi.
    """
    return get_repo_issues(repo)


@register_tool("github_commits")
def github_commits(repo: str, n: int = 5) -> list[dict]:
    """Bir repo'nun son commitlerini al.

    Args:
        repo: GitHub repo (owner/repo formatında).
        n: Kaç commit alınacak.

    Returns:
        Commit listesi.
    """
    return get_recent_commits(repo, n=n)
