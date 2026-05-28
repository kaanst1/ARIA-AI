# ARIA - Memory Agent (Kişisel Hafıza)

from ARIA.core.engine import ARIAEngine
from ARIA.core.config import load_config
from ARIA.core.registry import register_agent
from datetime import datetime
from ARIA.memory.store import MemoryStore


MEMORY_SYSTEM_PROMPT = """Sen ARIA'nın Hafıza ajanısın.
Meriç'in geçmiş kararlarını, tercihlerini ve notlarını saklarsın.
Diğer ajanlara bağlam sağlarsın.

Kurallar:
- Kişisel bilgileri gizli tut, asla dışarı çıkarma
- İlgili hafızaları özetle
- Çelişen bilgileri işaretle
- Tarihe göre sırala"""

@register_agent("memory")
class MemoryAgent:
    def __init__(self):
        self.engine = ARIAEngine()
        self.config = load_config()
        self.store = MemoryStore()

    def add(self, content: str, category: str = "genel") -> str:
        """Hafızaya ekle"""
        created_at = datetime.now().isoformat()
        self.store.add(content, category, created_at)
        return f"✅ Hafızaya eklendi: [{category}] {content}"

    def search(self, query: str) -> str:
        """Hafızada ara"""
        rows = self.store.search(query, limit=10)
        if not rows:
            return "⚠️ Hafıza boş."

        memory_text = "\n".join(
            f"[{created_at[:10]}] [{category}] {content}"
            for _, content, category, created_at in rows
        )

        prompt = f"""Hafıza kayıtları:
{memory_text}

Arama sorgusu: {query}

İlgili hafızaları bul ve özetle."""

        messages = [
            {"role": "system", "content": MEMORY_SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ]

        return self.engine.chat(messages)

    def list_all(self):
        """Tüm hafızaları listele"""
        rows = self.store.list_all()
        if not rows:
            print("⚠️ Hafıza boş.")
            return
        for _id, content, category, created_at in rows:
            print(f"[{_id}] [{created_at[:10]}] [{category}] {content}")

    def interactive(self):
        """İnteraktif hafıza modu"""
        print("\n🧠 ARIA Hafıza Modu — Çıkmak için 'quit'")
        print("=" * 40)

        while True:
            print("\n1. Hafızaya ekle")
            print("2. Hafızada ara")
            print("3. Tümünü listele")
            print("4. Çıkış")

            choice = input("\nSeçim: ").strip()

            if choice == "1":
                content = input("Not: ").strip()
                category = input("Kategori (genel/iş/spor/kişisel): ").strip() or "genel"
                print(self.add(content, category))

            elif choice == "2":
                query = input("Arama: ").strip()
                print("\n⏳ Aranıyor...\n")
                print(self.search(query))

            elif choice == "3":
                self.list_all()

            elif choice in ["4", "quit", "çıkış"]:
                print("Hafıza modu kapatılıyor...")
                break

    def handle(self, user_input: str) -> str:
        return self.search(user_input)


if __name__ == "__main__":
    agent = MemoryAgent()
    agent.interactive()