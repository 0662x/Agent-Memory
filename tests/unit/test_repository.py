from __future__ import annotations

from pathlib import Path

from plugins.life_memory import repository
from plugins.life_memory.classification import classify_candidate
from plugins.life_memory.models import EvidenceType, TraceOperation
from plugins.life_memory.repository import LifeMemoryRepository
from plugins.life_memory.time_utils import content_hash, json_dumps, now_iso


def _insert_memory(repo: LifeMemoryRepository, memory_id: str, content: str) -> None:
    now = now_iso()
    with repo.transaction() as conn:
        conn.execute(
            """
            INSERT INTO life_memories (
                memory_id, kind, classification, classification_reason,
                classification_confidence, content, content_hash, primary_category,
                tags_json, context_json, importance, confidence, feedback_score,
                source, source_ref, status, review_status, sensitivity,
                evidence_count, source_count, unique_query_count, days_seen_count,
                promotion_score, promotion_path, promotion_reason, decay_reason,
                last_confirmed_at, valid_from, valid_until, scope, authority,
                action_boundary, injection_risk, created_at, updated_at,
                last_accessed_at, access_count, deleted_at
            )
            VALUES (
                ?, 'direct', 'life_memory', 'test fixture', 0.9, ?, ?, 'personal_fact',
                ?, ?, 0.5, 0.8, 0, 'assistant_tool', NULL, 'young', 'pending', 'normal',
                0, 1, 0, 1, 0, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
                'assistant_tool', NULL, 0, ?, ?, NULL, 0, NULL
            )
            """,
            (memory_id, content, content_hash(content), json_dumps([]), json_dumps({}), now, now),
        )


def test_schema_creation_and_migration_are_idempotent(hermes_home: Path) -> None:
    repo = LifeMemoryRepository(hermes_home=hermes_home)
    repo.initialize()
    repo.initialize()

    assert repo.db_path == hermes_home / "life_memory.db"
    assert repo.get_schema_version() == repository.SCHEMA_VERSION

    rows = repo.connect().execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table', 'virtual table')"
    ).fetchall()
    table_names = {row["name"] for row in rows}
    assert {
        "schema_version",
        "life_memories",
        "memory_evidence",
        "memory_links",
        "memory_feedback",
        "memory_traces",
        "reflection_runs",
        "reflection_reports",
    }.issubset(table_names)

    version_count = repo.connect().execute("SELECT COUNT(*) AS count FROM schema_version").fetchone()
    assert version_count["count"] == 1


def test_append_trace_stores_hash_not_raw_input(hermes_home: Path) -> None:
    repo = LifeMemoryRepository(hermes_home=hermes_home)
    repo.initialize()

    trace_id = repo.append_trace(
        operation=TraceOperation.STORE,
        actor="plugin",
        reason="declined sensitive candidate",
        input_text="secret account number 123",
        after={"outcome": "declined"},
    )

    row = repo.fetch_one("SELECT * FROM memory_traces WHERE trace_id = ?", (trace_id,))
    assert row is not None
    assert row["operation"] == "store"
    assert row["reason"] == "declined sensitive candidate"
    assert row["input_hash"] == content_hash("secret account number 123")
    assert "secret account number 123" not in repr(row)


def test_evidence_and_memory_link_writes(hermes_home: Path) -> None:
    repo = LifeMemoryRepository(hermes_home=hermes_home)
    repo.initialize()
    _insert_memory(repo, "mem_a", "The user prefers late-night work.")
    _insert_memory(repo, "mem_b", "The user often starts deep work after midnight.")

    evidence_id = repo.write_evidence(
        memory_id="mem_a",
        evidence_type=EvidenceType.EXPLICIT_USER_STATEMENT,
        content="I prefer late-night work.",
        source_ref="session_1",
        weight=1.4,
    )
    link_id = repo.write_memory_link(
        from_memory_id="mem_b",
        to_memory_id="mem_a",
        relation="supports",
        reason="Both memories describe the same work routine.",
    )

    evidence = repo.fetch_one("SELECT * FROM memory_evidence WHERE evidence_id = ?", (evidence_id,))
    link = repo.fetch_one("SELECT * FROM memory_links WHERE link_id = ?", (link_id,))

    assert evidence is not None
    assert evidence["memory_id"] == "mem_a"
    assert evidence["weight"] == 1.0
    assert link is not None
    assert link["from_memory_id"] == "mem_b"
    assert link["to_memory_id"] == "mem_a"


def test_fts_fallback_does_not_block_initialization(hermes_home: Path, monkeypatch) -> None:
    monkeypatch.setattr(repository, "_sqlite_supports_fts5", lambda conn: False)

    repo = LifeMemoryRepository(hermes_home=hermes_home)
    repo.initialize()

    assert repo.fts_enabled is False
    row = repo.connect().execute(
        "SELECT name FROM sqlite_master WHERE name = 'life_memories_fts'"
    ).fetchone()
    assert row is None


def test_create_memory_defaults_and_source_metadata(hermes_home: Path) -> None:
    repo = LifeMemoryRepository(hermes_home=hermes_home)
    repo.initialize()
    decision = classify_candidate("Remember that I prefer focused work late at night.")

    record = repo.create_memory(
        content="Remember that I prefer focused work late at night.",
        classification=decision.classification.value,
        classification_reason=decision.reason,
        classification_confidence=decision.confidence,
        primary_category=decision.primary_category or "personal_preference",
        tags=decision.tags,
        context={"channel": "test"},
        importance=0.7,
        confidence=0.8,
        source="assistant_tool",
        source_ref="session_123",
        sensitivity="normal",
        injection_risk=0,
    )

    memory = repo.fetch_one("SELECT * FROM life_memories WHERE memory_id = ?", (record["memory_id"],))
    evidence = repo.fetch_one("SELECT * FROM memory_evidence WHERE evidence_id = ?", (record["evidence_id"],))
    trace = repo.fetch_one("SELECT * FROM memory_traces WHERE trace_id = ?", (record["trace_id"],))

    assert memory is not None
    assert memory["status"] == "young"
    assert memory["review_status"] == "pending"
    assert memory["source"] == "assistant_tool"
    assert memory["source_ref"] == "session_123"
    assert memory["evidence_count"] == 1
    assert evidence is not None
    assert evidence["memory_id"] == record["memory_id"]
    assert trace is not None
    assert trace["operation"] == "store"


def test_create_memory_promotion_and_validity_window(hermes_home: Path) -> None:
    repo = LifeMemoryRepository(hermes_home=hermes_home)
    repo.initialize()
    decision = classify_candidate("Remember that I moved to Sydney.")

    record = repo.create_memory(
        content="Remember that I moved to Sydney.",
        classification=decision.classification.value,
        classification_reason=decision.reason,
        classification_confidence=decision.confidence,
        primary_category=decision.primary_category or "personal_fact",
        tags=("major_life_fact",),
        context={},
        importance=0.9,
        confidence=0.9,
        source="assistant_tool",
        source_ref=None,
        sensitivity="normal",
        injection_risk=0,
        status="active",
        promotion_path="major_life_fact",
        promotion_reason="Explicit stable major life fact.",
        valid_until="2026-06-15T00:00:00+00:00",
    )

    memory = repo.fetch_one("SELECT * FROM life_memories WHERE memory_id = ?", (record["memory_id"],))
    assert memory is not None
    assert memory["status"] == "active"
    assert memory["promotion_path"] == "major_life_fact"
    assert memory["valid_until"] == "2026-06-15T00:00:00+00:00"


def test_feedback_rows_score_and_supersede_links_are_recorded(hermes_home: Path) -> None:
    repo = LifeMemoryRepository(hermes_home=hermes_home)
    repo.initialize()
    _insert_memory(repo, "mem_old", "The user prefers late-night work.")
    _insert_memory(repo, "mem_new", "The user prefers morning work.")

    feedback_id = repo.record_feedback(
        memory_id="mem_old",
        feedback_type="wrong",
        note="Corrected by user.",
        replacement_content="The user prefers morning work.",
        target_memory_id="mem_new",
    )
    repo.adjust_feedback_score("mem_old", -0.4)
    repo.supersede_memory("mem_old", "mem_new", reason="User supplied replacement.")

    feedback = repo.fetch_one("SELECT * FROM memory_feedback WHERE feedback_id = ?", (feedback_id,))
    old = repo.fetch_one("SELECT * FROM life_memories WHERE memory_id = 'mem_old'")
    forward = repo.fetch_one(
        "SELECT * FROM memory_links WHERE from_memory_id = 'mem_old' AND to_memory_id = 'mem_new'"
    )
    reverse = repo.fetch_one(
        "SELECT * FROM memory_links WHERE from_memory_id = 'mem_new' AND to_memory_id = 'mem_old'"
    )

    assert feedback is not None
    assert feedback["feedback_type"] == "wrong"
    assert old is not None
    assert old["feedback_score"] == 0.0
    assert old["status"] == "archived"
    assert forward is not None
    assert forward["relation"] == "superseded_by"
    assert reverse is not None
    assert reverse["relation"] == "supersedes"


def test_tombstone_redaction_preserves_id_hash_and_excludes_content(hermes_home: Path) -> None:
    repo = LifeMemoryRepository(hermes_home=hermes_home)
    repo.initialize()
    _insert_memory(repo, "mem_delete", "The user prefers late-night work.")
    before = repo.fetch_one("SELECT * FROM life_memories WHERE memory_id = 'mem_delete'")
    assert before is not None

    trace_id = repo.delete_memory("mem_delete", reason="User asked to forget.")

    after = repo.fetch_one("SELECT * FROM life_memories WHERE memory_id = 'mem_delete'")
    trace = repo.fetch_one("SELECT * FROM memory_traces WHERE trace_id = ?", (trace_id,))
    assert after is not None
    assert after["memory_id"] == "mem_delete"
    assert after["content_hash"] == before["content_hash"]
    assert after["status"] == "deleted"
    assert "late-night" not in after["content"]
    assert after["content"].startswith("[deleted")
    assert after["deleted_at"] is not None
    assert trace is not None
    assert trace["operation"] == "forget"


def test_deleted_memory_is_excluded_from_repository_search(hermes_home: Path) -> None:
    repo = LifeMemoryRepository(hermes_home=hermes_home)
    repo.initialize()
    _insert_memory(repo, "mem_delete", "The user prefers late-night work.")
    repo.delete_memory("mem_delete", reason="User asked to forget.")

    results = repo.search_memories(query="late night work")

    assert results == []
