from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS collections (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, description TEXT NOT NULL DEFAULT '',
  is_default INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS one_default ON collections(is_default) WHERE is_default=1;
CREATE TABLE IF NOT EXISTS selections (
  id INTEGER PRIMARY KEY, collection_id INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
  relative_path TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('file','folder')),
  UNIQUE(collection_id, relative_path)
);
CREATE TABLE IF NOT EXISTS schedules (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', color TEXT NOT NULL DEFAULT '#7c3aed',
  collection_id INTEGER NOT NULL REFERENCES collections(id) ON DELETE RESTRICT,
  starts_at TEXT NOT NULL, ends_at TEXT NOT NULL, rrule TEXT, exdates TEXT NOT NULL DEFAULT '[]',
  enabled INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS trash (
  id INTEGER PRIMARY KEY, trash_name TEXT NOT NULL UNIQUE, original_path TEXT NOT NULL,
  deleted_at TEXT NOT NULL, purge_after TEXT NOT NULL, is_folder INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS app_state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit (
  id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, username TEXT, action TEXT NOT NULL,
  target TEXT, outcome TEXT NOT NULL, detail TEXT
);
"""


class Database:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def initialize(self) -> None:
        with self.connect() as db:
            db.executescript(SCHEMA)
            db.execute(
                "INSERT OR IGNORE INTO collections(name,is_default,created_at) VALUES(?,?,?)",
                ("Default", 1, datetime.now(UTC).isoformat()),
            )

    def state(self, key: str, default: str = "") -> str:
        with self.connect() as db:
            row = db.execute("SELECT value FROM app_state WHERE key=?", (key,)).fetchone()
            return row["value"] if row else default

    def set_state(self, key: str, value: str) -> None:
        with self.connect() as db:
            db.execute("INSERT INTO app_state(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))

    def audit(self, action: str, target: str | None, outcome: str, username: str | None = None, detail: str | None = None) -> None:
        with self.connect() as db:
            db.execute(
                "INSERT INTO audit(created_at,username,action,target,outcome,detail) VALUES(?,?,?,?,?,?)",
                (datetime.now(UTC).isoformat(), username, action, target, outcome, detail),
            )

    @staticmethod
    def decode_exdates(value: str) -> list[str]:
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []

