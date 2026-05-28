"""Log dosyası analiz aracı — error pattern tespiti ve özet."""

from __future__ import annotations

import logging
import re
from collections import Counter
from pathlib import Path
from typing import Optional

from ARIA.core.registry import register_tool

logger = logging.getLogger("aria.tools.log_analyzer")

# Log seviye pattern'ları
_ERROR_PATTERNS = [
    re.compile(r'\bERROR\b', re.IGNORECASE),
    re.compile(r'\bCRITICAL\b', re.IGNORECASE),
    re.compile(r'\bFATAL\b', re.IGNORECASE),
    re.compile(r'Exception:', re.IGNORECASE),
    re.compile(r'Traceback \(most recent call last\)', re.IGNORECASE),
    re.compile(r'\bFAILED\b'),
    re.compile(r'\bPANIC\b', re.IGNORECASE),
]

_WARNING_PATTERNS = [
    re.compile(r'\bWARNING\b', re.IGNORECASE),
    re.compile(r'\bWARN\b', re.IGNORECASE),
    re.compile(r'\bDEPRECATED\b', re.IGNORECASE),
]

_TIMESTAMP_PATTERN = re.compile(
    r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}|\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}'
)


class LogAnalyzer:
    """Log dosyası analiz sınıfı."""

    def analyze(self, path: str, last_n: int = 200) -> dict:
        """Log dosyasını analiz et ve özet üret.

        Args:
            path: Log dosyası yolu.
            last_n: Analiz edilecek son satır sayısı.

        Returns:
            Analiz özeti dict.
        """
        fpath = Path(path).expanduser()

        if not fpath.exists():
            return {"error": f"Log dosyası bulunamadı: {path}"}

        if fpath.stat().st_size > 10 * 1024 * 1024:  # 10 MB limit
            return {"error": "Log dosyası çok büyük (max 10MB)"}

        try:
            with open(fpath, encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except Exception as exc:
            return {"error": f"Dosya okunamadı: {exc}"}

        total_lines = len(lines)
        analyzed_lines = lines[-last_n:] if len(lines) > last_n else lines

        # Hata sayımı
        error_lines = []
        warning_count = 0
        error_types: Counter = Counter()
        timestamps = []

        for i, line in enumerate(analyzed_lines):
            # Timestamp bul
            ts_match = _TIMESTAMP_PATTERN.search(line)
            if ts_match:
                timestamps.append(ts_match.group())

            # Error kontrol
            is_error = any(p.search(line) for p in _ERROR_PATTERNS)
            if is_error:
                error_lines.append({
                    "line_no": total_lines - last_n + i + 1 if len(lines) > last_n else i + 1,
                    "content": line.rstrip()[:200],
                })
                # Hata tipini çıkar
                for p in _ERROR_PATTERNS:
                    m = p.search(line)
                    if m:
                        error_types[m.group().upper()] += 1
                        break

            # Warning kontrol
            if any(p.search(line) for p in _WARNING_PATTERNS):
                warning_count += 1

        # Özet üret
        most_common_errors = error_types.most_common(5)
        first_ts = timestamps[0] if timestamps else None
        last_ts = timestamps[-1] if timestamps else None

        return {
            "file": str(fpath),
            "total_lines": total_lines,
            "analyzed_lines": len(analyzed_lines),
            "error_count": len(error_lines),
            "warning_count": warning_count,
            "most_common_errors": most_common_errors,
            "timestamp_range": {"first": first_ts, "last": last_ts},
            "recent_errors": error_lines[-10:],  # Son 10 hata
            "summary": self._generate_summary(
                fpath.name, len(error_lines), warning_count,
                most_common_errors, first_ts, last_ts
            ),
        }

    def _generate_summary(
        self,
        filename: str,
        error_count: int,
        warning_count: int,
        most_common: list,
        first_ts: Optional[str],
        last_ts: Optional[str],
    ) -> str:
        lines = [f"Log Analizi: {filename}"]
        lines.append(f"Hatalar: {error_count}, Uyarılar: {warning_count}")
        if most_common:
            lines.append("En sık hatalar: " + ", ".join(f"{t}({c})" for t, c in most_common))
        if first_ts and last_ts:
            lines.append(f"Zaman aralığı: {first_ts} → {last_ts}")
        if error_count == 0:
            lines.append("Kritik hata tespit edilmedi.")
        return " | ".join(lines)


_log_analyzer = LogAnalyzer()


@register_tool("analyze_log")
def analyze_log(path: str, last_n: int = 200) -> dict:
    """Log dosyasını analiz et, hata pattern'larını tespit et ve özet üret.

    Args:
        path: Analiz edilecek log dosyasının yolu.
        last_n: Analiz edilecek son satır sayısı (varsayılan 200).

    Returns:
        Analiz özeti.
    """
    return _log_analyzer.analyze(path, last_n=last_n)
