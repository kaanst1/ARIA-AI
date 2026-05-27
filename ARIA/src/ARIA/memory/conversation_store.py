"""SQLite tabanlı oturum ve mesaj geçmişi deposu."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("aria.memory.conversation_store")

DB_PATH = Path.home() / ".aria" / "data" / "conversations.sqlite"


class ConversationStore:
    """Sohbet oturumlarını ve mesajlarını SQLite'ta saklar.

    Örnek kullanım::

        store = ConversationStore()
        sid = store.new_session("Proje planlaması")
        store.add_message(sid, "user", "Merhaba ARIA")
        store.add_message(sid, "assistant", "Merhaba! Nasıl yardımcı olabilirim?")
        messages = store.get_messages(sid)
    """

    def __init__(self, db_path: Path = DB_PATH) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    # ── Veritabanı kurulumu ───────────────────────────────────────────────────

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    title      TEXT    NOT NULL DEFAULT 'Yeni Sohbet',
                    created_at TEXT    NOT NULL,
                    updated_at TEXT    NOT NULL
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    role       TEXT    NOT NULL,   -- 'user' | 'assistant' | 'system'
                    content    TEXT    NOT NULL,
                    agent      TEXT,
                    created_at TEXT    NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_messages_session
                    ON messages(session_id, created_at);

                CREATE INDEX IF NOT EXISTS idx_sessions_updated
                    ON sessions(updated_at DESC);
            """)

    # ── Oturum işlemleri ──────────────────────────────────────────────────────

    def new_session(self, title: str = "Yeni Sohbet") -> int:
        """Yeni oturum oluştur ve ID'sini döndür."""
        now = _now()
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO sessions (title, created_at, updated_at) VALUES (?, ?, ?)",
                (title, now, now),
            )
            return cur.lastrowid  # type: ignore[return-value]

    def rename_session(self, session_id: int, title: str) -> None:
        """Oturum başlığını güncelle."""
        with self._conn() as conn:
            conn.execute(
                "UPDATE sessions SET title=?, updated_at=? WHERE id=?",
                (title, _now(), session_id),
            )

    def delete_session(self, session_id: int) -> bool:
        """Oturumu ve mesajlarını sil. Silinip silinmediğini döndür."""
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM sessions WHERE id=?", (session_id,))
            return cur.rowcount > 0

    def list_sessions(self, limit: int = 100) -> list[dict]:
        """Oturumları güncelleme tarihine göre azalan sırada listele."""
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT s.id, s.title, s.created_at, s.updated_at,
                       COUNT(m.id) AS message_count
                FROM sessions s
                LEFT JOIN messages m ON m.session_id = s.id
                GROUP BY s.id
                ORDER BY s.updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_session(self, session_id: int) -> Optional[dict]:
        """Tek oturum bilgisini döndür."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id, title, created_at, updated_at FROM sessions WHERE id=?",
                (session_id,),
            ).fetchone()
        return dict(row) if row else None

    # ── Mesaj işlemleri ───────────────────────────────────────────────────────

    def add_message(
        self,
        session_id: int,
        role: str,
        content: str,
        agent: Optional[str] = None,
    ) -> int:
        """Oturuma mesaj ekle ve mesaj ID'sini döndür."""
        now = _now()
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO messages (session_id, role, content, agent, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, role, content, agent, now),
            )
            # Oturum güncelleme zamanını da yenile
            conn.execute(
                "UPDATE sessions SET updated_at=? WHERE id=?",
                (now, session_id),
            )
            return cur.lastrowid  # type: ignore[return-value]

    def get_messages(self, session_id: int, limit: Optional[int] = None) -> list[dict]:
        """Bir oturumun tüm mesajlarını kronolojik sırayla döndür."""
        sql = """
            SELECT id, session_id, role, content, agent, created_at
            FROM messages
            WHERE session_id=?
            ORDER BY created_at ASC, id ASC
        """
        params: tuple = (session_id,)
        if limit is not None:
            sql += " LIMIT ?"
            params = (session_id, limit)

        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def get_context_messages(
        self,
        session_id: int,
        n: int = 20,
    ) -> list[dict[str, str]]:
        """LLM context için son N mesajı {'role', 'content'} formatında döndür."""
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT role, content
                FROM messages
                WHERE session_id=?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (session_id, n),
            ).fetchall()
        # Ters çevir — kronolojik sıra
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    def search_sessions(self, query: str, limit: int = 20) -> list[dict]:
        """Mesaj içeriğine göre oturum ara."""
        pattern = f"%{query}%"
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT s.id, s.title, s.created_at, s.updated_at
                FROM sessions s
                JOIN messages m ON m.session_id = s.id
                WHERE m.content LIKE ? OR s.title LIKE ?
                ORDER BY s.updated_at DESC
                LIMIT ?
                """,
                (pattern, pattern, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    # ── Oturum başlığını ilk mesajdan otomatik türet ──────────────────────────

    def auto_title_session(self, session_id: int, first_message: str) -> None:
        """Oturuma ilk kullanıcı mesajından kısa başlık ata."""
        title = first_message[:60].strip()
        if len(first_message) > 60:
            title += "…"
        self.rename_session(session_id, title)


# ── Yardımcı ─────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
