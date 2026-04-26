from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


@dataclass(frozen=True)
class Profile:
    id: int
    name: str
    endpoint: str
    headers_json: str
    metadata_json: str
    tls_verify: bool
    ca_bundle_path: str
    client_cert_path: str
    client_key_path: str
    timeout_seconds: float
    protocol_version: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Profile":
        return cls(
            id=row["id"],
            name=row["name"],
            endpoint=row["endpoint"],
            headers_json=row["headers_json"] or "{}",
            metadata_json=row["metadata_json"] or "{}",
            tls_verify=bool(row["tls_verify"]),
            ca_bundle_path=row["ca_bundle_path"] or "",
            client_cert_path=row["client_cert_path"] or "",
            client_key_path=row["client_key_path"] or "",
            timeout_seconds=float(row["timeout_seconds"] or 60),
            protocol_version=row["protocol_version"] or "1.0",
        )


@dataclass(frozen=True)
class Conversation:
    id: int
    profile_id: int
    title: str
    context_id: str
    created_at: str
    updated_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Conversation":
        return cls(
            id=row["id"],
            profile_id=row["profile_id"],
            title=row["title"],
            context_id=row["context_id"] or "",
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.conn: sqlite3.Connection | None = None
        self.lock = threading.RLock()

    def connect(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")

    def close(self) -> None:
        if self.conn is not None:
            self.conn.close()
            self.conn = None

    @property
    def db(self) -> sqlite3.Connection:
        if self.conn is None:
            raise RuntimeError("Database is not connected")
        return self.conn

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self.lock:
            try:
                yield self.db
                self.db.commit()
            except Exception:
                self.db.rollback()
                raise

    def migrate(self) -> None:
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        if version < 1:
            self._migrate_v1()

    def _migrate_v1(self) -> None:
        with self.transaction() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    endpoint TEXT NOT NULL DEFAULT '',
                    headers_json TEXT NOT NULL DEFAULT '{}',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    tls_verify INTEGER NOT NULL DEFAULT 1,
                    ca_bundle_path TEXT NOT NULL DEFAULT '',
                    client_cert_path TEXT NOT NULL DEFAULT '',
                    client_key_path TEXT NOT NULL DEFAULT '',
                    timeout_seconds REAL NOT NULL DEFAULT 60,
                    protocol_version TEXT NOT NULL DEFAULT '1.0',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
                    title TEXT NOT NULL,
                    context_id TEXT NOT NULL DEFAULT '',
                    archived INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    task_id TEXT NOT NULL DEFAULT '',
                    role TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    text TEXT NOT NULL DEFAULT '',
                    raw_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS artifacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    task_id TEXT NOT NULL DEFAULT '',
                    name TEXT NOT NULL DEFAULT '',
                    mime_type TEXT NOT NULL DEFAULT '',
                    content_text TEXT NOT NULL DEFAULT '',
                    content_json TEXT NOT NULL DEFAULT '{}',
                    file_path TEXT NOT NULL DEFAULT '',
                    raw_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS http_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id INTEGER REFERENCES conversations(id) ON DELETE CASCADE,
                    profile_id INTEGER REFERENCES profiles(id) ON DELETE SET NULL,
                    jsonrpc_id TEXT NOT NULL DEFAULT '',
                    method TEXT NOT NULL DEFAULT '',
                    request_json TEXT NOT NULL DEFAULT '{}',
                    response_json TEXT NOT NULL DEFAULT '{}',
                    response_headers_json TEXT NOT NULL DEFAULT '{}',
                    status_code INTEGER,
                    latency_ms REAL,
                    error TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_conversations_profile
                    ON conversations(profile_id, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_messages_conversation
                    ON messages(conversation_id, created_at ASC, id ASC);
                CREATE INDEX IF NOT EXISTS idx_artifacts_conversation
                    ON artifacts(conversation_id, created_at ASC, id ASC);
                CREATE INDEX IF NOT EXISTS idx_http_events_conversation
                    ON http_events(conversation_id, created_at ASC, id ASC);

                PRAGMA user_version = 1;
                """
            )

    def ensure_default_profile(self) -> None:
        existing = self.db.execute("SELECT id FROM profiles LIMIT 1").fetchone()
        if existing:
            return
        self.create_profile(
            name="Local agent",
            endpoint="http://localhost:8000",
            headers={},
            metadata={},
        )

    def get_setting(self, key: str, default: str = "") -> str:
        row = self.db.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO app_settings(key, value)
                VALUES(?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )

    def list_profiles(self) -> list[Profile]:
        rows = self.db.execute("SELECT * FROM profiles ORDER BY name COLLATE NOCASE").fetchall()
        return [Profile.from_row(row) for row in rows]

    def get_profile(self, profile_id: int) -> Profile:
        row = self.db.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,)).fetchone()
        if not row:
            raise KeyError(f"Profile {profile_id} not found")
        return Profile.from_row(row)

    def create_profile(
        self,
        name: str,
        endpoint: str,
        headers: dict[str, Any],
        metadata: dict[str, Any],
    ) -> int:
        timestamp = now_iso()
        with self.transaction() as conn:
            cur = conn.execute(
                """
                INSERT INTO profiles(
                    name, endpoint, headers_json, metadata_json, created_at, updated_at
                )
                VALUES(?, ?, ?, ?, ?, ?)
                """,
                (name, endpoint, dumps(headers), dumps(metadata), timestamp, timestamp),
            )
        return int(cur.lastrowid)

    def update_profile(
        self,
        profile_id: int,
        *,
        name: str,
        endpoint: str,
        headers_json: str,
        metadata_json: str,
        tls_verify: bool,
        ca_bundle_path: str,
        client_cert_path: str,
        client_key_path: str,
        timeout_seconds: float,
        protocol_version: str,
    ) -> None:
        with self.transaction() as conn:
            conn.execute(
                """
                UPDATE profiles
                SET name = ?,
                    endpoint = ?,
                    headers_json = ?,
                    metadata_json = ?,
                    tls_verify = ?,
                    ca_bundle_path = ?,
                    client_cert_path = ?,
                    client_key_path = ?,
                    timeout_seconds = ?,
                    protocol_version = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    name,
                    endpoint,
                    headers_json,
                    metadata_json,
                    int(tls_verify),
                    ca_bundle_path,
                    client_cert_path,
                    client_key_path,
                    timeout_seconds,
                    protocol_version,
                    now_iso(),
                    profile_id,
                ),
            )

    def list_conversations(self, profile_id: int | None = None) -> list[Conversation]:
        if profile_id:
            rows = self.db.execute(
                """
                SELECT * FROM conversations
                WHERE archived = 0 AND profile_id = ?
                ORDER BY updated_at DESC, id DESC
                """,
                (profile_id,),
            ).fetchall()
        else:
            rows = self.db.execute(
                """
                SELECT * FROM conversations
                WHERE archived = 0
                ORDER BY updated_at DESC, id DESC
                """
            ).fetchall()
        return [Conversation.from_row(row) for row in rows]

    def get_conversation(self, conversation_id: int) -> Conversation:
        row = self.db.execute("SELECT * FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
        if not row:
            raise KeyError(f"Conversation {conversation_id} not found")
        return Conversation.from_row(row)

    def create_conversation(self, profile_id: int, title: str, context_id: str = "") -> int:
        timestamp = now_iso()
        with self.transaction() as conn:
            cur = conn.execute(
                """
                INSERT INTO conversations(profile_id, title, context_id, created_at, updated_at)
                VALUES(?, ?, ?, ?, ?)
                """,
                (profile_id, title, context_id, timestamp, timestamp),
            )
        return int(cur.lastrowid)

    def update_conversation_context(self, conversation_id: int, context_id: str) -> None:
        if not context_id:
            return
        with self.transaction() as conn:
            conn.execute(
                """
                UPDATE conversations
                SET context_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (context_id, now_iso(), conversation_id),
            )

    def touch_conversation(self, conversation_id: int) -> None:
        with self.transaction() as conn:
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (now_iso(), conversation_id),
            )

    def add_message(
        self,
        *,
        conversation_id: int,
        role: str,
        kind: str,
        text: str = "",
        raw_json: Any | None = None,
        task_id: str = "",
    ) -> int:
        with self.transaction() as conn:
            cur = conn.execute(
                """
                INSERT INTO messages(conversation_id, task_id, role, kind, text, raw_json, created_at)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    conversation_id,
                    task_id,
                    role,
                    kind,
                    text,
                    dumps(raw_json if raw_json is not None else {}),
                    now_iso(),
                ),
            )
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (now_iso(), conversation_id),
            )
        return int(cur.lastrowid)

    def list_messages(self, conversation_id: int) -> list[sqlite3.Row]:
        return self.db.execute(
            """
            SELECT * FROM messages
            WHERE conversation_id = ?
            ORDER BY created_at ASC, id ASC
            """,
            (conversation_id,),
        ).fetchall()

    def add_artifact(
        self,
        *,
        conversation_id: int,
        task_id: str = "",
        name: str = "",
        mime_type: str = "",
        content_text: str = "",
        content_json: Any | None = None,
        file_path: str = "",
        raw_json: Any | None = None,
    ) -> int:
        with self.transaction() as conn:
            cur = conn.execute(
                """
                INSERT INTO artifacts(
                    conversation_id, task_id, name, mime_type, content_text,
                    content_json, file_path, raw_json, created_at
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    conversation_id,
                    task_id,
                    name,
                    mime_type,
                    content_text,
                    dumps(content_json if content_json is not None else {}),
                    file_path,
                    dumps(raw_json if raw_json is not None else {}),
                    now_iso(),
                ),
            )
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (now_iso(), conversation_id),
            )
        return int(cur.lastrowid)

    def list_artifacts(self, conversation_id: int) -> list[sqlite3.Row]:
        return self.db.execute(
            """
            SELECT * FROM artifacts
            WHERE conversation_id = ?
            ORDER BY created_at ASC, id ASC
            """,
            (conversation_id,),
        ).fetchall()

    def add_http_event(
        self,
        *,
        conversation_id: int | None,
        profile_id: int | None,
        jsonrpc_id: str = "",
        method: str = "",
        request_json: Any | None = None,
        response_json: Any | None = None,
        response_headers_json: Any | None = None,
        status_code: int | None = None,
        latency_ms: float | None = None,
        error: str = "",
    ) -> int:
        with self.transaction() as conn:
            cur = conn.execute(
                """
                INSERT INTO http_events(
                    conversation_id, profile_id, jsonrpc_id, method, request_json,
                    response_json, response_headers_json, status_code, latency_ms,
                    error, created_at
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    conversation_id,
                    profile_id,
                    jsonrpc_id,
                    method,
                    dumps(request_json if request_json is not None else {}),
                    dumps(response_json if response_json is not None else {}),
                    dumps(response_headers_json if response_headers_json is not None else {}),
                    status_code,
                    latency_ms,
                    error,
                    now_iso(),
                ),
            )
        return int(cur.lastrowid)

    def list_http_events(self, conversation_id: int) -> list[sqlite3.Row]:
        return self.db.execute(
            """
            SELECT * FROM http_events
            WHERE conversation_id = ?
            ORDER BY created_at ASC, id ASC
            """,
            (conversation_id,),
        ).fetchall()
