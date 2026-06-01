from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .repository import default_hermes_home


@dataclass(frozen=True, slots=True)
class SessionMessage:
    role: str
    content: str
    source_ref: str | None = None


@dataclass(frozen=True, slots=True)
class SessionTranscript:
    session_ref: str | None
    source: str
    messages: tuple[SessionMessage, ...]

    @property
    def text(self) -> str:
        return "\n".join(f"{message.role}: {message.content}" for message in self.messages)

    @property
    def source_refs(self) -> tuple[str, ...]:
        return tuple(message.source_ref for message in self.messages if message.source_ref)


class SessionUnavailableError(RuntimeError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class HermesSessionAdapter:
    """Read-only adapter for Hermes session/state data.

    The plugin owns the normalization boundary here so reflection logic does not depend on
    any one Hermes state.db schema.
    """

    def __init__(
        self,
        *,
        hermes_home: str | Path | None = None,
        state_db_path: str | Path | None = None,
    ) -> None:
        home = Path(hermes_home).expanduser() if hermes_home is not None else default_hermes_home()
        self.hermes_home = home
        self.state_db_path = Path(state_db_path).expanduser() if state_db_path is not None else home / "state.db"

    def load(
        self,
        *,
        session_ref: str | None = None,
        transcript: Iterable[dict[str, Any] | str] | str | None = None,
    ) -> SessionTranscript:
        if transcript is not None:
            return self._from_explicit_transcript(session_ref=session_ref, transcript=transcript)
        if not session_ref:
            raise SessionUnavailableError("session_ref or transcript is required.")
        return self._from_state_db(session_ref)

    def _from_explicit_transcript(
        self,
        *,
        session_ref: str | None,
        transcript: Iterable[dict[str, Any] | str] | str,
    ) -> SessionTranscript:
        if isinstance(transcript, str):
            raw_items: Iterable[dict[str, Any] | str] = [{"role": "user", "content": transcript}]
        else:
            raw_items = transcript
        messages = _normalize_messages(raw_items)
        if not messages:
            raise SessionUnavailableError("explicit transcript did not contain readable messages.")
        return SessionTranscript(session_ref=session_ref, source="transcript", messages=messages)

    def _from_state_db(self, session_ref: str) -> SessionTranscript:
        if not self.state_db_path.exists():
            raise SessionUnavailableError(f"Hermes state database not found: {self.state_db_path}")
        uri = f"file:{self.state_db_path.as_posix()}?mode=ro"
        try:
            conn = sqlite3.connect(uri, uri=True)
            conn.row_factory = sqlite3.Row
        except sqlite3.Error as exc:
            raise SessionUnavailableError(f"Hermes state database is unavailable: {exc}") from exc
        try:
            messages = self._read_messages(conn, session_ref)
        finally:
            conn.close()
        if not messages:
            raise SessionUnavailableError(f"No readable transcript found for session_ref={session_ref}.")
        return SessionTranscript(session_ref=session_ref, source="state_db", messages=messages)

    def _read_messages(self, conn: sqlite3.Connection, session_ref: str) -> tuple[SessionMessage, ...]:
        tables = _table_names(conn)
        if "messages" in tables:
            messages = self._read_message_table(conn, session_ref)
            if messages:
                return messages
        if "session_messages" in tables:
            messages = self._read_named_message_table(conn, "session_messages", session_ref)
            if messages:
                return messages
        if "sessions" in tables:
            messages = self._read_sessions_table(conn, session_ref)
            if messages:
                return messages
        return ()

    def _read_message_table(self, conn: sqlite3.Connection, session_ref: str) -> tuple[SessionMessage, ...]:
        return self._read_named_message_table(conn, "messages", session_ref)

    def _read_named_message_table(
        self,
        conn: sqlite3.Connection,
        table: str,
        session_ref: str,
    ) -> tuple[SessionMessage, ...]:
        columns = _columns(conn, table)
        session_column = _first_existing(columns, ("session_id", "session_ref", "conversation_id", "thread_id"))
        content_column = _first_existing(columns, ("content", "text", "message", "body"))
        role_column = _first_existing(columns, ("role", "author", "speaker", "source"))
        order_column = _first_existing(columns, ("created_at", "timestamp", "idx", "position", "id"))
        if not session_column or not content_column:
            return ()
        select_role = role_column if role_column else "'unknown'"
        order_sql = f" ORDER BY {order_column}" if order_column else ""
        rows = conn.execute(
            f"SELECT rowid AS _rowid, {select_role} AS role, {content_column} AS content "
            f"FROM {table} WHERE {session_column} = ?{order_sql}",
            (session_ref,),
        ).fetchall()
        return _normalize_messages(
            (
                {
                    "role": row["role"],
                    "content": row["content"],
                    "source_ref": f"{table}:{row['_rowid']}",
                }
                for row in rows
            )
        )

    def _read_sessions_table(self, conn: sqlite3.Connection, session_ref: str) -> tuple[SessionMessage, ...]:
        columns = _columns(conn, "sessions")
        id_column = _first_existing(columns, ("session_id", "session_ref", "id", "conversation_id", "thread_id"))
        transcript_column = _first_existing(columns, ("transcript_json", "messages_json", "transcript", "messages", "content"))
        if not id_column or not transcript_column:
            return ()
        row = conn.execute(
            f"SELECT rowid AS _rowid, {transcript_column} AS transcript FROM sessions WHERE {id_column} = ?",
            (session_ref,),
        ).fetchone()
        if row is None:
            return ()
        return _messages_from_blob(row["transcript"], source_prefix=f"sessions:{row['_rowid']}")


def _normalize_messages(raw_items: Iterable[dict[str, Any] | str]) -> tuple[SessionMessage, ...]:
    messages: list[SessionMessage] = []
    for index, item in enumerate(raw_items):
        if isinstance(item, str):
            role = "user"
            content = item
            source_ref = f"transcript:{index}"
        else:
            role = str(item.get("role") or item.get("author") or item.get("speaker") or "unknown")
            content = str(item.get("content") or item.get("text") or item.get("message") or "").strip()
            source_ref_raw = item.get("source_ref") or item.get("id")
            source_ref = str(source_ref_raw) if source_ref_raw is not None else f"transcript:{index}"
        normalized = " ".join(content.split())
        if normalized:
            messages.append(SessionMessage(role=role.strip().lower() or "unknown", content=normalized, source_ref=source_ref))
    return tuple(messages)


def _messages_from_blob(value: Any, *, source_prefix: str) -> tuple[SessionMessage, ...]:
    if value is None:
        return ()
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    text = str(value)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return _normalize_messages([{"role": "unknown", "content": text, "source_ref": source_prefix}])
    if isinstance(parsed, list):
        return _normalize_messages(
            item if isinstance(item, dict) else {"content": str(item), "source_ref": f"{source_prefix}:item"}
            for item in parsed
        )
    if isinstance(parsed, dict):
        for key in ("messages", "transcript", "items"):
            nested = parsed.get(key)
            if isinstance(nested, list):
                return _normalize_messages(
                    item if isinstance(item, dict) else {"content": str(item), "source_ref": f"{source_prefix}:{key}"}
                    for item in nested
                )
        return _normalize_messages([{"role": "unknown", "content": json.dumps(parsed, ensure_ascii=False), "source_ref": source_prefix}])
    return ()


def _table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {str(row["name"]) for row in rows}


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row["name"]) for row in rows}


def _first_existing(columns: set[str], names: tuple[str, ...]) -> str | None:
    for name in names:
        if name in columns:
            return name
    return None
