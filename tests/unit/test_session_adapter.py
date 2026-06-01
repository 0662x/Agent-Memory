from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from plugins.life_memory.session_adapter import HermesSessionAdapter, SessionUnavailableError


def test_session_adapter_reads_state_db_without_writes(hermes_home: Path) -> None:
    db_path = hermes_home / "state.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE messages (
            id INTEGER PRIMARY KEY,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
        ("session_1", "user", "Remember that I prefer quiet morning routines.", "2026-06-02T00:00:00+00:00"),
    )
    conn.commit()
    conn.close()

    transcript = HermesSessionAdapter(hermes_home=hermes_home).load(session_ref="session_1")

    assert transcript.source == "state_db"
    assert transcript.session_ref == "session_1"
    assert transcript.messages[0].role == "user"
    assert transcript.messages[0].content == "Remember that I prefer quiet morning routines."
    assert not (hermes_home / "state.db-wal").exists()


def test_session_adapter_unavailable_state_raises_clear_error(hermes_home: Path) -> None:
    adapter = HermesSessionAdapter(hermes_home=hermes_home)

    with pytest.raises(SessionUnavailableError) as exc:
        adapter.load(session_ref="missing_session")

    assert "state database not found" in exc.value.reason


def test_session_adapter_uses_explicit_transcript_fallback(hermes_home: Path) -> None:
    transcript = HermesSessionAdapter(hermes_home=hermes_home).load(
        session_ref="manual_session",
        transcript=[
            {"role": "user", "content": "I usually focus better after midnight.", "source_ref": "msg_1"},
            {"role": "assistant", "content": "Noted."},
        ],
    )

    assert transcript.source == "transcript"
    assert transcript.session_ref == "manual_session"
    assert [message.role for message in transcript.messages] == ["user", "assistant"]
    assert transcript.source_refs == ("msg_1", "transcript:1")
