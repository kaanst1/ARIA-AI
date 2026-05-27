# ARIA - Learning Layer (Kullanım Takibi + Pattern Tracker)

from datetime import datetime
from pathlib import Path
import json
import os
from typing import Optional

TRACKER_FILE = os.path.expanduser("~/.aria/usage.json")
PATTERNS_FILE = os.path.expanduser("~/.aria/patterns.json")

# Sabah saatleri (07:00 - 10:00)
_MORNING_HOURS = range(7, 11)


class UsageTracker:
    def __init__(self):
        self.data = self._load()

    def _load(self) -> dict:
        os.makedirs(os.path.dirname(TRACKER_FILE), exist_ok=True)
        if os.path.exists(TRACKER_FILE):
            try:
                with open(TRACKER_FILE) as f:
                    return json.load(f)
            except Exception:
                pass
        return {"sessions": [], "agent_counts": {}, "total_messages": 0}

    def _save(self):
        with open(TRACKER_FILE, "w") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    def log(self, agent: str, user_input: str, response_len: int):
        """Kullanım kaydı tut"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "agent": agent,
            "input_len": len(user_input),
            "response_len": response_len,
            "hour": datetime.now().hour,
        }
        self.data["sessions"].append(entry)
        self.data["agent_counts"][agent] = self.data["agent_counts"].get(agent, 0) + 1
        self.data["total_messages"] += 1
        self._save()
        # Pattern güncelle
        PatternTracker().update(agent, datetime.now().hour)

    def stats(self) -> str:
        """İstatistikleri göster"""
        if not self.data["sessions"]:
            return "Henüz kullanım verisi yok."

        lines = [
            "\nARIA Kullanım İstatistikleri",
            "=" * 40,
            f"Toplam mesaj : {self.data['total_messages']}",
            "\nAjan kullanımı:"
        ]

        for agent, count in sorted(self.data["agent_counts"].items(), key=lambda x: -x[1]):
            lines.append(f"  {agent:15} : {count} kez")

        if self.data["sessions"]:
            last = self.data["sessions"][-1]
            lines.append(f"\nSon kullanım : {last['timestamp'][:16]}")

        lines.append("=" * 40)
        return "\n".join(lines)


class PatternTracker:
    """Kullanıcı davranış pattern'larını takip eder ve öneri üretir."""

    def __init__(self) -> None:
        Path(PATTERNS_FILE).parent.mkdir(parents=True, exist_ok=True)
        self.patterns = self._load()

    def _load(self) -> dict:
        if os.path.exists(PATTERNS_FILE):
            try:
                with open(PATTERNS_FILE, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "agent_by_hour": {},   # {"brief": {"8": 15, "9": 3, ...}, ...}
            "total_by_agent": {},
            "first_messages": [],  # İlk günlük mesajın agent'ı
        }

    def _save(self) -> None:
        with open(PATTERNS_FILE, "w", encoding="utf-8") as f:
            json.dump(self.patterns, f, ensure_ascii=False, indent=2)

    def update(self, agent: str, hour: int) -> None:
        """Pattern güncelle."""
        hour_str = str(hour)

        # Agent by hour
        if agent not in self.patterns["agent_by_hour"]:
            self.patterns["agent_by_hour"][agent] = {}
        agent_hours = self.patterns["agent_by_hour"][agent]
        agent_hours[hour_str] = agent_hours.get(hour_str, 0) + 1

        # Total by agent
        self.patterns["total_by_agent"][agent] = (
            self.patterns["total_by_agent"].get(agent, 0) + 1
        )

        # Sabah ilk mesaj takibi
        if hour in _MORNING_HOURS:
            today = datetime.now().strftime("%Y-%m-%d")
            today_entries = [e for e in self.patterns["first_messages"] if e.get("date") == today]
            if not today_entries:
                self.patterns["first_messages"].append({"date": today, "agent": agent})
                # Son 30 günü tut
                self.patterns["first_messages"] = self.patterns["first_messages"][-30:]

        self._save()

    def most_used_agents(self, top_n: int = 5) -> list[tuple[str, int]]:
        """En çok kullanılan agent'ları döndür."""
        counts = self.patterns.get("total_by_agent", {})
        return sorted(counts.items(), key=lambda x: -x[1])[:top_n]

    def suggest_shortcut(self, user_input: str) -> Optional[str]:
        """Kullanım pattern'larına göre kısayol önerisi üret."""
        suggestions = []
        hour = datetime.now().hour

        # Sabah pattern kontrolü
        if hour in _MORNING_HOURS:
            morning_firsts = self.patterns.get("first_messages", [])
            if len(morning_firsts) >= 5:
                # Son 5 sabah ilk mesajının en sık agent'ını bul
                from collections import Counter
                recent = [e["agent"] for e in morning_firsts[-5:]]
                most_common = Counter(recent).most_common(1)
                if most_common and most_common[0][1] >= 3:
                    agent_name = most_common[0][0]
                    suggestions.append(
                        f"Sabah ilk mesajınız genellikle '{agent_name}' oluyor. "
                        f"Direkt başlatılsın mı?"
                    )

        # Belirli saatlerde yoğun kullanım
        for agent, hours_data in self.patterns.get("agent_by_hour", {}).items():
            hour_str = str(hour)
            if hours_data.get(hour_str, 0) >= 5:
                suggestions.append(
                    f"Bu saatlerde '{agent}' kullanımınız yüksek. "
                    f"Otomatik hazırlanmamı ister misiniz?"
                )
                break

        return suggestions[0] if suggestions else None


if __name__ == "__main__":
    t = UsageTracker()
    print(t.stats())
    pt = PatternTracker()
    print("En çok kullanılan:", pt.most_used_agents())