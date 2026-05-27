"""Sistem kaynakları izleme — CPU, RAM, disk, GPU (M4), Ollama."""

from __future__ import annotations

import logging
import subprocess
from typing import Any, Optional

from ARIA.core.registry import register_tool

logger = logging.getLogger("aria.tools.system_monitor")

# ── Opsiyonel bağımlılık ──────────────────────────────────────────────────────
try:
    import psutil  # type: ignore
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    logger.warning("psutil yüklü değil — sistem istatistikleri sınırlı")


# ── Yardımcı fonksiyonlar ─────────────────────────────────────────────────────

def _get_cpu_info() -> dict[str, Any]:
    """CPU kullanım bilgisi."""
    if not PSUTIL_AVAILABLE:
        return {"available": False}
    try:
        return {
            "percent": psutil.cpu_percent(interval=0.5),
            "count_logical": psutil.cpu_count(logical=True),
            "count_physical": psutil.cpu_count(logical=False),
            "freq_mhz": round(psutil.cpu_freq().current, 1) if psutil.cpu_freq() else None,
        }
    except Exception as exc:
        logger.warning("CPU bilgisi alınamadı: %s", exc)
        return {"available": False, "error": str(exc)}


def _get_memory_info() -> dict[str, Any]:
    """RAM kullanım bilgisi."""
    if not PSUTIL_AVAILABLE:
        return {"available": False}
    try:
        vm = psutil.virtual_memory()
        return {
            "total_gb": round(vm.total / 1024 ** 3, 2),
            "used_gb": round(vm.used / 1024 ** 3, 2),
            "available_gb": round(vm.available / 1024 ** 3, 2),
            "percent": vm.percent,
        }
    except Exception as exc:
        logger.warning("RAM bilgisi alınamadı: %s", exc)
        return {"available": False, "error": str(exc)}


def _get_disk_info(path: str = "/") -> dict[str, Any]:
    """Disk kullanım bilgisi."""
    if not PSUTIL_AVAILABLE:
        return {"available": False}
    try:
        disk = psutil.disk_usage(path)
        return {
            "path": path,
            "total_gb": round(disk.total / 1024 ** 3, 1),
            "used_gb": round(disk.used / 1024 ** 3, 1),
            "free_gb": round(disk.free / 1024 ** 3, 1),
            "percent": disk.percent,
        }
    except Exception as exc:
        logger.warning("Disk bilgisi alınamadı: %s", exc)
        return {"available": False, "error": str(exc)}


def _get_m4_gpu_info() -> dict[str, Any]:
    """Apple Silicon GPU bilgisini system_profiler ile çek."""
    try:
        result = subprocess.run(
            ["system_profiler", "SPDisplaysDataType", "-json"],
            capture_output=True,
            text=True,
            timeout=8,
        )
        if result.returncode != 0:
            return {"available": False}

        import json
        data = json.loads(result.stdout)
        displays = data.get("SPDisplaysDataType", [])
        if not displays:
            return {"available": False}

        gpu = displays[0]
        info: dict[str, Any] = {
            "name": gpu.get("spdisplays_vendor", "Apple GPU"),
            "chipset": gpu.get("sppci_model", ""),
            "vram": gpu.get("spdisplays_vram", "Unified"),
            "metal": gpu.get("spdisplays_mtlgpufamilysupport", ""),
        }
        # Ekstra: core sayısı varsa ekle
        cores = gpu.get("spdisplays_gpu_core_count", "")
        if cores:
            info["gpu_cores"] = cores
        return info
    except FileNotFoundError:
        return {"available": False, "reason": "system_profiler bulunamadı"}
    except Exception as exc:
        logger.warning("GPU bilgisi alınamadı: %s", exc)
        return {"available": False, "error": str(exc)}


def _get_ollama_stats() -> dict[str, Any]:
    """Ollama process istatistikleri."""
    if not PSUTIL_AVAILABLE:
        return {"running": False, "reason": "psutil yok"}
    try:
        ollama_procs = [
            p for p in psutil.process_iter(["name", "pid", "cpu_percent", "memory_info"])
            if "ollama" in (p.info.get("name") or "").lower()
        ]
        if not ollama_procs:
            return {"running": False}

        total_rss_mb = sum(
            (p.info.get("memory_info").rss / 1024 ** 2 if p.info.get("memory_info") else 0)
            for p in ollama_procs
        )
        total_cpu = sum(p.info.get("cpu_percent") or 0 for p in ollama_procs)

        return {
            "running": True,
            "process_count": len(ollama_procs),
            "total_rss_mb": round(total_rss_mb, 1),
            "total_cpu_percent": round(total_cpu, 1),
            "pids": [p.info.get("pid") for p in ollama_procs],
        }
    except Exception as exc:
        logger.warning("Ollama istatistikleri alınamadı: %s", exc)
        return {"running": False, "error": str(exc)}


# ── Ana tool fonksiyonu ───────────────────────────────────────────────────────

@register_tool("system_stats")
def get_system_stats() -> dict[str, Any]:
    """Tüm sistem istatistiklerini toplu olarak döndür.

    Returns:
        cpu, memory, disk, gpu, ollama anahtarlarını içeren dict.
    """
    return {
        "cpu": _get_cpu_info(),
        "memory": _get_memory_info(),
        "disk": _get_disk_info(),
        "gpu": _get_m4_gpu_info(),
        "ollama": _get_ollama_stats(),
        "psutil_available": PSUTIL_AVAILABLE,
    }


def format_system_stats() -> str:
    """Sistem istatistiklerini okunabilir metin olarak döndür."""
    stats = get_system_stats()

    lines: list[str] = ["📊 Sistem Durumu\n"]

    cpu = stats.get("cpu", {})
    if cpu.get("percent") is not None:
        lines.append(f"  CPU      : %{cpu['percent']:.1f} ({cpu.get('count_physical', '?')} çekirdek)")

    mem = stats.get("memory", {})
    if mem.get("used_gb") is not None:
        lines.append(
            f"  RAM      : {mem['used_gb']:.1f} / {mem['total_gb']:.1f} GB (%{mem['percent']})"
        )

    disk = stats.get("disk", {})
    if disk.get("used_gb") is not None:
        lines.append(
            f"  Disk     : {disk['used_gb']:.0f} / {disk['total_gb']:.0f} GB (%{disk['percent']})"
        )

    gpu = stats.get("gpu", {})
    if gpu.get("name"):
        core_info = f" ({gpu['gpu_cores']} çekirdek)" if gpu.get("gpu_cores") else ""
        lines.append(f"  GPU      : {gpu['name']}{core_info}")

    ollama = stats.get("ollama", {})
    if ollama.get("running"):
        lines.append(
            f"  Ollama   : Aktif — {ollama['total_rss_mb']:.0f} MB RAM, "
            f"%{ollama['total_cpu_percent']} CPU"
        )
    else:
        lines.append("  Ollama   : Kapalı")

    return "\n".join(lines)
