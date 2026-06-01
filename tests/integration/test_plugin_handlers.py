from __future__ import annotations

import json
import time
from pathlib import Path

from plugins.life_memory.contracts import TOOL_NAMES
from plugins.life_memory.repository import LifeMemoryRepository
from plugins.life_memory.time_utils import content_hash, json_dumps, now_iso


def test_registers_all_life_memory_tools(registered_tools) -> None:
    assert set(registered_tools) == set(TOOL_NAMES)

    for name, entry in registered_tools.items():
        assert entry["name"] == name
        assert entry["toolset"] == "life_memory"
        assert entry["schema"]["name"] == name
        assert callable(entry["handler"])


def test_registered_handlers_return_contract_envelope(registered_tools) -> None:
    for name, entry in registered_tools.items():
        result = json.loads(entry["handler"]({}))

        assert isinstance(result["ok"], bool)
        assert isinstance(result["outcome"], str)
        assert result["message"]
        assert result["trace_id"].startswith("trace_")
        if result["ok"] is False:
            assert result.get("tool") in {name, None}


def test_store_declines_technical_memory_and_writes_trace(registered_tools, hermes_home: Path) -> None:
    result = json.loads(
        registered_tools["life_memory_store"]["handler"](
            {"content": "My Hermes runs on Mac, and Windows is connected through SSH."}
        )
    )

    assert result["ok"] is False
    assert result["outcome"] == "declined"
    assert result["classification"] == "technical_memory"
    assert result["trace_id"].startswith("trace_")

    repo = LifeMemoryRepository(hermes_home=hermes_home)
    trace = repo.fetch_one("SELECT * FROM memory_traces WHERE trace_id = ?", (result["trace_id"],))
    assert trace is not None
    assert trace["operation"] == "classify"
    assert trace["input_hash"]


def test_store_accepts_life_memory_and_persists_to_sqlite(registered_tools, hermes_home: Path) -> None:
    result = json.loads(
        registered_tools["life_memory_store"]["handler"](
            {
                "content": "Remember that I prefer to work late at night and usually think better after midnight.",
                "explicit_user_request": True,
            }
        )
    )

    assert result["ok"] is True
    assert result["outcome"] == "success"
    assert result["classification"] == "life_memory"
    assert result["primary_category"] == "personal_preference"
    assert {"routine", "night", "work_style"}.issubset(set(result["tags"]))

    repo = LifeMemoryRepository(hermes_home=hermes_home)
    memory = repo.fetch_one("SELECT * FROM life_memories WHERE memory_id = ?", (result["memory_id"],))
    assert memory is not None
    assert memory["status"] == "young"
    assert memory["content"]


def test_store_sensitive_content_returns_confirmation_without_write(registered_tools, hermes_home: Path) -> None:
    result = json.loads(
        registered_tools["life_memory_store"]["handler"](
            {
                "content": "Remember my bank account number is 123456789.",
                "explicit_user_request": False,
            }
        )
    )

    assert result["ok"] is False
    assert result["outcome"] == "needs_confirmation"
    assert result["sensitivity"] == "sensitive"

    repo = LifeMemoryRepository(hermes_home=hermes_home)
    count = repo.fetch_one("SELECT COUNT(*) AS count FROM life_memories")
    assert count is not None
    assert count["count"] == 0


def test_store_major_life_fact_fast_promotes_to_active(registered_tools, hermes_home: Path) -> None:
    result = json.loads(
        registered_tools["life_memory_store"]["handler"](
            {
                "content": "Remember that I moved to Sydney.",
                "explicit_user_request": True,
                "tags": ["major_life_fact"],
                "importance": 0.9,
                "confidence": 0.9,
            }
        )
    )

    assert result["ok"] is True
    assert result["status"] == "active"
    assert result["promotion_path"] == "major_life_fact"

    repo = LifeMemoryRepository(hermes_home=hermes_home)
    memory = repo.fetch_one("SELECT * FROM life_memories WHERE memory_id = ?", (result["memory_id"],))
    assert memory is not None
    assert memory["status"] == "active"
    assert memory["promotion_path"] == "major_life_fact"


def test_store_recent_state_assigns_fourteen_day_ttl(registered_tools, hermes_home: Path) -> None:
    result = json.loads(
        registered_tools["life_memory_store"]["handler"](
            {
                "content": "Remember that I am a bit tired today.",
                "explicit_user_request": True,
            }
        )
    )

    assert result["ok"] is True
    assert "recent_state" in result["tags"]
    assert result["valid_until"]

    repo = LifeMemoryRepository(hermes_home=hermes_home)
    memory = repo.fetch_one("SELECT * FROM life_memories WHERE memory_id = ?", (result["memory_id"],))
    assert memory is not None
    assert memory["valid_until"] == result["valid_until"]


def test_recall_targeted_query_updates_access_count(registered_tools, hermes_home: Path) -> None:
    store = registered_tools["life_memory_store"]["handler"]
    recall = registered_tools["life_memory_recall"]["handler"]
    stored = json.loads(
        store(
            {
                "content": "Remember that I prefer focused work late at night.",
                "explicit_user_request": True,
                "importance": 0.8,
            }
        )
    )
    json.loads(
        store(
            {
                "content": "Remember that my sister Maya lives in Brisbane.",
                "explicit_user_request": True,
            }
        )
    )

    result = json.loads(recall({"query": "late night focused work", "limit": 5}))

    assert result["ok"] is True
    assert result["outcome"] == "success"
    assert result["results"][0]["memory_id"] == stored["memory_id"]
    assert all("sister" not in item["content"].lower() for item in result["results"])

    repo = LifeMemoryRepository(hermes_home=hermes_home)
    memory = repo.fetch_one("SELECT * FROM life_memories WHERE memory_id = ?", (stored["memory_id"],))
    assert memory is not None
    assert memory["access_count"] == 1
    assert memory["last_accessed_at"] is not None


def test_recall_broad_abstention_returns_not_found(registered_tools) -> None:
    store = registered_tools["life_memory_store"]["handler"]
    recall = registered_tools["life_memory_recall"]["handler"]
    json.loads(
        store(
            {
                "content": "Remember that I prefer focused work late at night.",
                "explicit_user_request": True,
            }
        )
    )

    result = json.loads(recall({"query": "favorite mountain trail", "limit": 5}))

    assert result["ok"] is True
    assert result["outcome"] == "not_found"
    assert result["results"] == []


def test_feedback_correction_replaces_and_excludes_old_memory(registered_tools) -> None:
    store = registered_tools["life_memory_store"]["handler"]
    feedback = registered_tools["life_memory_feedback"]["handler"]
    recall = registered_tools["life_memory_recall"]["handler"]
    old = json.loads(
        store(
            {
                "content": "Remember that I prefer focused work late at night.",
                "explicit_user_request": True,
            }
        )
    )

    correction = json.loads(
        feedback(
            {
                "memory_id": old["memory_id"],
                "feedback_type": "wrong",
                "replacement_content": "Remember that I now prefer focused work in the morning.",
            }
        )
    )
    recalled = json.loads(recall({"query": "focused work morning", "limit": 5}))

    assert correction["ok"] is True
    assert correction["replacement_memory_id"].startswith("mem_")
    assert correction["relation"] == "superseded_by"
    assert recalled["outcome"] == "success"
    assert correction["replacement_memory_id"] in [item["memory_id"] for item in recalled["results"]]
    assert old["memory_id"] not in [item["memory_id"] for item in recalled["results"]]


def test_feedback_outdated_demotes_memory(registered_tools, hermes_home: Path) -> None:
    store = registered_tools["life_memory_store"]["handler"]
    feedback = registered_tools["life_memory_feedback"]["handler"]
    stored = json.loads(
        store(
            {
                "content": "Remember that I currently prefer late-night work.",
                "explicit_user_request": True,
            }
        )
    )

    result = json.loads(
        feedback(
            {
                "memory_id": stored["memory_id"],
                "feedback_type": "outdated",
                "note": "This is no longer current.",
            }
        )
    )

    assert result["ok"] is True
    assert result["outcome"] == "archived"
    repo = LifeMemoryRepository(hermes_home=hermes_home)
    memory = repo.fetch_one("SELECT * FROM life_memories WHERE memory_id = ?", (stored["memory_id"],))
    assert memory is not None
    assert memory["status"] == "archived"
    assert memory["decay_reason"] == "outdated"


def test_forget_by_id_tombstones_and_recall_excludes_deleted(registered_tools, hermes_home: Path) -> None:
    store = registered_tools["life_memory_store"]["handler"]
    forget = registered_tools["life_memory_forget"]["handler"]
    recall = registered_tools["life_memory_recall"]["handler"]
    stored = json.loads(
        store(
            {
                "content": "Remember that I prefer focused work late at night.",
                "explicit_user_request": True,
            }
        )
    )

    result = json.loads(forget({"memory_id": stored["memory_id"], "reason": "User requested deletion."}))
    recalled = json.loads(recall({"query": "late night focused work"}))

    assert result["ok"] is True
    assert result["outcome"] == "success"
    assert result["status"] == "deleted"
    assert recalled["outcome"] == "not_found"

    repo = LifeMemoryRepository(hermes_home=hermes_home)
    memory = repo.fetch_one("SELECT * FROM life_memories WHERE memory_id = ?", (stored["memory_id"],))
    assert memory is not None
    assert memory["status"] == "deleted"
    assert "late night" not in memory["content"].lower()


def test_forget_by_query_requires_disambiguation_for_multiple_matches(registered_tools) -> None:
    store = registered_tools["life_memory_store"]["handler"]
    forget = registered_tools["life_memory_forget"]["handler"]
    json.loads(
        store(
            {
                "content": "Remember that I prefer focused work late at night.",
                "explicit_user_request": True,
            }
        )
    )
    json.loads(
        store(
            {
                "content": "Remember that I prefer focused work in the morning.",
                "explicit_user_request": True,
            }
        )
    )

    result = json.loads(forget({"query": "focused work", "confirm": True}))

    assert result["ok"] is False
    assert result["outcome"] == "ambiguous"
    assert len(result["candidates"]) >= 2


def test_reflect_session_dry_run_apply_and_no_fabrication(
    registered_tools,
    hermes_home: Path,
) -> None:
    reflect = registered_tools["life_memory_reflect"]["handler"]
    transcript = [{"role": "user", "content": "I prefer quiet morning routines.", "source_ref": "msg_1"}]

    dry_run = json.loads(reflect({"mode": "session", "apply": False, "transcript": transcript}))
    repo = LifeMemoryRepository(hermes_home=hermes_home)
    count_after_dry_run = repo.fetch_one("SELECT COUNT(*) AS count FROM life_memories")
    applied = json.loads(reflect({"mode": "session", "apply": True, "transcript": transcript}))
    unavailable = json.loads(reflect({"mode": "session", "apply": True, "session_ref": "missing"}))

    assert dry_run["ok"] is True
    assert dry_run["applied_count"] == 0
    assert dry_run["candidates"][0]["action"] == "session_extract_candidate"
    assert count_after_dry_run["count"] == 0

    assert applied["ok"] is True
    assert applied["stored_memory_ids"]
    stored = repo.fetch_one("SELECT * FROM life_memories WHERE memory_id = ?", (applied["stored_memory_ids"][0],))
    assert stored is not None
    assert stored["source"] == "session_extract"

    assert unavailable["ok"] is False
    assert unavailable["outcome"] == "not_found"
    assert "unavailable" in unavailable["message"] or "not found" in unavailable["message"]


def test_reflect_light_rem_deep_daily_modes(
    registered_tools,
    hermes_home: Path,
) -> None:
    store = registered_tools["life_memory_store"]["handler"]
    reflect = registered_tools["life_memory_reflect"]["handler"]
    recent = json.loads(
        store(
            {
                "content": "Remember that I am a bit tired today.",
                "explicit_user_request": True,
            }
        )
    )
    first = json.loads(
        store(
            {
                "content": "Remember that I prefer focused implementation plans.",
                "explicit_user_request": True,
            }
        )
    )
    second = json.loads(
        store(
            {
                "content": "Remember that I usually prefer focused implementation reviews.",
                "explicit_user_request": True,
            }
        )
    )
    third = json.loads(
        store(
            {
                "content": "Remember that I often prefer focused implementation checklists.",
                "explicit_user_request": True,
            }
        )
    )
    repo = LifeMemoryRepository(hermes_home=hermes_home)
    with repo.transaction() as conn:
        conn.execute(
            "UPDATE life_memories SET valid_until = ? WHERE memory_id = ?",
            ("2000-01-01T00:00:00+00:00", recent["memory_id"]),
        )

    light = json.loads(reflect({"mode": "light", "apply": True}))
    rem = json.loads(reflect({"mode": "rem", "apply": True}))
    pattern_ids = rem.get("pattern_candidate_memory_ids") or [first["memory_id"], second["memory_id"], third["memory_id"]]
    with repo.transaction() as conn:
        conn.execute(
            """
            UPDATE life_memories
            SET status = 'pattern_candidate',
                evidence_count = 4,
                source_count = 2,
                days_seen_count = 3,
                promotion_score = 0.9,
                confidence = 0.86
            WHERE memory_id = ?
            """,
            (pattern_ids[0],),
        )
    before_daily = repo.fetch_one("SELECT COUNT(*) AS count FROM life_memories")
    deep = json.loads(reflect({"mode": "deep", "apply": True}))
    daily = json.loads(reflect({"mode": "daily", "apply": True}))
    after_daily = repo.fetch_one("SELECT COUNT(*) AS count FROM life_memories")

    archived = repo.fetch_one("SELECT * FROM life_memories WHERE memory_id = ?", (recent["memory_id"],))
    assert light["ok"] is True
    assert archived["status"] == "archived"
    assert rem["ok"] is True
    assert rem["candidate_count"] >= 1
    assert deep["ok"] is True
    assert deep["reflected_memory_ids"]
    assert daily["ok"] is True
    assert daily["report_only"] is True
    assert after_daily["count"] == before_daily["count"] + len(deep["reflected_memory_ids"])


def test_store_and_recall_are_bounded_with_ten_thousand_rows(
    registered_tools,
    hermes_home: Path,
) -> None:
    repo = LifeMemoryRepository(hermes_home=hermes_home)
    repo.initialize()
    _seed_many_memories(repo, row_count=10_000)
    store = registered_tools["life_memory_store"]["handler"]
    recall = registered_tools["life_memory_recall"]["handler"]

    store_started = time.perf_counter()
    stored = json.loads(
        store(
            {
                "content": "Remember that I prefer zephyr midnight focus blocks.",
                "explicit_user_request": True,
                "importance": 0.9,
            }
        )
    )
    store_elapsed = time.perf_counter() - store_started

    recall_started = time.perf_counter()
    recalled = json.loads(recall({"query": "zephyr midnight focus", "limit": 5}))
    recall_elapsed = time.perf_counter() - recall_started

    assert stored["ok"] is True
    assert store_elapsed < 2.0
    assert recalled["ok"] is True
    assert recalled["outcome"] == "success"
    assert recall_elapsed < 2.0
    assert len(recalled["results"]) <= 5
    assert recalled["results"][0]["memory_id"] == stored["memory_id"]


def _seed_many_memories(repo: LifeMemoryRepository, *, row_count: int) -> None:
    now = now_iso()
    rows = []
    fts_rows = []
    for index in range(row_count):
        memory_id = f"mem_perf_{index:05d}"
        content = f"Remember that the user has a calm walking routine marker_{index:05d}."
        tags = ["routine", "performance_fixture"]
        rows.append(
            (
                memory_id,
                "direct",
                "life_memory",
                "performance fixture",
                0.9,
                content,
                content_hash(content),
                "personal_pattern",
                json_dumps(tags),
                json_dumps({"fixture": "performance"}),
                0.4,
                0.8,
                0,
                "test_fixture",
                None,
                "active",
                "pending",
                "normal",
                1,
                1,
                0,
                1,
                0,
                None,
                None,
                None,
                now,
                now,
                None,
                None,
                "test_fixture",
                None,
                0,
                now,
                now,
                None,
                0,
                None,
            )
        )
        fts_rows.append((memory_id, content, "personal_pattern", " ".join(tags)))
    with repo.transaction() as conn:
        conn.executemany(
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
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            rows,
        )
        if repo.fts_enabled:
            conn.executemany(
                """
                INSERT INTO life_memories_fts (memory_id, content, primary_category, tags)
                VALUES (?, ?, ?, ?)
                """,
                fts_rows,
            )
