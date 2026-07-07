"""История транскрипций: SQLite в %APPDATA%/SteadyTranscribe/history.db.

Поведение как FileTranscriptionHistoryStore из FluidVoice:
лимит записей, пустой текст не сохраняется, новые записи сверху.
"""
import os
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime

from .settings import app_data_dir


@dataclass
class Entry:
    id: str
    timestamp: str          # iso8601
    file_name: str
    duration: float
    processing_time: float
    confidence: float
    text: str
    model: str = ""
    language: str = ""

    @property
    def preview_text(self) -> str:
        clean = " ".join(self.text.split())
        return clean[:77] + "..." if len(clean) > 80 else clean

    @property
    def dt(self) -> datetime:
        return datetime.fromisoformat(self.timestamp)


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(os.path.join(app_data_dir(), "history.db"))
    conn.execute("""CREATE TABLE IF NOT EXISTS entries (
        id TEXT PRIMARY KEY, timestamp TEXT NOT NULL, file_name TEXT NOT NULL,
        duration REAL, processing_time REAL, confidence REAL,
        text TEXT NOT NULL, model TEXT, language TEXT)""")
    return conn


def add(file_name: str, duration: float, processing_time: float,
        confidence: float, text: str, model: str, language: str,
        limit: int = 50) -> Entry | None:
    if not text.strip():
        return None
    entry = Entry(str(uuid.uuid4()), datetime.now().isoformat(timespec="seconds"),
                  file_name, duration, processing_time, confidence, text, model, language)
    with _connect() as conn:
        conn.execute("INSERT INTO entries VALUES (?,?,?,?,?,?,?,?,?)",
                     (entry.id, entry.timestamp, entry.file_name, entry.duration,
                      entry.processing_time, entry.confidence, entry.text,
                      entry.model, entry.language))
        conn.execute("""DELETE FROM entries WHERE id NOT IN
                        (SELECT id FROM entries ORDER BY timestamp DESC LIMIT ?)""", (limit,))
    return entry


def list_entries() -> list[Entry]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM entries ORDER BY timestamp DESC").fetchall()
    return [Entry(*row) for row in rows]


def delete(entry_id: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM entries WHERE id = ?", (entry_id,))


def clear() -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM entries")
