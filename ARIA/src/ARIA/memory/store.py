"""SQLite-backed memory store."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from ARIA.core.config import load_config


class MemoryStore:
    def __init__(self) -> None:
        config = load_config()
        data_dir = Path(config.data_dir)
        data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = data_dir / "memory.sqlite"
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    category TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memories_cat ON memories(category)"
            )
            conn.commit()

    def add(self, content: str, category: str, created_at: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO memories (content, category, created_at) VALUES (?, ?, ?)",
                (content, category, created_at),
            )
            conn.commit()

    def list_all(self) -> list[tuple]:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "SELECT id, content, category, created_at FROM memories ORDER BY id DESC"
            )
            return cur.fetchall()

    def search(self, query: str, limit: int = 10) -> list[tuple]:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                """
                SELECT id, content, category, created_at
                FROM memories
                WHERE content LIKE ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (f"%{query}%", limit),
            )
            return cur.fetchall()
