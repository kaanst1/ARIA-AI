# ARIA - Learning Layer (Kullanım Takibi)

from datetime import datetime
import json
import os

TRACKER_FILE = os.path.expanduser("~/.aria/usage.json")

class UsageTracker:
    def __init__(self):
        self.data = self._load()

    def _load(self) -> dict:
        os.makedirs(os.path.dirname(TRACKER_FILE), exist_ok=True)
        if os.path.exists(TRACKER_FILE):
            with open(TRACKER_FILE) as f:
                return json.load(f)
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
            "response_len": response_len
        }
        self.data["sessions"].append(entry)
        self.data["agent_counts"][agent] = self.data["agent_counts"].get(agent, 0) + 1
        self.data["total_messages"] += 1
        self._save()

    def stats(self) -> str:
        """İstatistikleri göster"""
        if not self.data["sessions"]:
            return "⚠️ Henüz kullanım verisi yok."

        lines = [
            "\n📈 ARIA Kullanım İstatistikleri",
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


if __name__ == "__main__":
    t = UsageTracker()
    print(t.stats())