from __future__ import annotations

from pathlib import Path

from plugins.life_memory.models import LifecycleStatus
from plugins.life_memory.reflection import run_reflection
from plugins.life_memory.repository import LifeMemoryRepository


def _memory(
    repo: LifeMemoryRepository,
    content: str,
    *,
    primary_category: str = "personal_preference",
    tags: tuple[str, ...] = (),
    status: str = "young",
    confidence: float = 0.82,
    valid_until: str | None = None,
) -> str:
    record = repo.create_memory(
        content=content,
        classification="life_memory",
        classification_reason="test fixture",
        classification_confidence=0.9,
        primary_category=primary_category,
        tags=tags,
        context={},
        importance=0.6,
        confidence=confidence,
        source="assistant_tool",
        source_ref=None,
        sensitivity="normal",
        injection_risk=0,
        status=status,
        valid_until=valid_until,
    )
    return record["memory_id"]


def test_light_reflection_dry_run_proposes_without_archiving(hermes_home: Path) -> None:
    repo = LifeMemoryRepository(hermes_home=hermes_home)
    repo.initialize()
    memory_id = _memory(
        repo,
        "Remember that I am a bit tired today.",
        tags=("recent_state",),
        valid_until="2000-01-01T00:00:00+00:00",
    )

    result = run_reflection(repo, mode="light", apply=False)

    assert result["ok"] is True
    assert any(candidate["action"] == "archive_recent_state" for candidate in result["candidates"])
    assert repo.get_memory(memory_id)["status"] == LifecycleStatus.YOUNG.value


def test_light_reflection_apply_archives_recent_state_and_links_duplicates(hermes_home: Path) -> None:
    repo = LifeMemoryRepository(hermes_home=hermes_home)
    repo.initialize()
    expired_id = _memory(
        repo,
        "Remember that I am a bit tired today.",
        tags=("recent_state",),
        valid_until="2000-01-01T00:00:00+00:00",
    )
    _memory(repo, "Remember that I prefer focused work late at night.", tags=("work_style", "night"))
    _memory(repo, "I usually prefer focused work late at night.", tags=("work_style", "night"))

    result = run_reflection(repo, mode="light", apply=True)

    assert result["applied_count"] >= 2
    assert any(candidate["action"] == "duplicate_candidate" for candidate in result["candidates"])
    assert repo.get_memory(expired_id)["status"] == LifecycleStatus.ARCHIVED.value
    duplicate_link = repo.fetch_one("SELECT * FROM memory_links WHERE relation = 'duplicate_candidate'")
    assert duplicate_link is not None


def test_session_reflection_extracts_candidates_without_fabricating_memory(hermes_home: Path) -> None:
    repo = LifeMemoryRepository(hermes_home=hermes_home)
    repo.initialize()

    result = run_reflection(
        repo,
        mode="session",
        apply=False,
        transcript=[{"role": "user", "content": "I prefer quiet morning routines.", "source_ref": "msg_1"}],
    )

    assert result["ok"] is True
    assert result["applied_count"] == 0
    assert result["candidates"][0]["action"] == "session_extract_candidate"
    count = repo.fetch_one("SELECT COUNT(*) AS count FROM life_memories")
    assert count["count"] == 0


def test_deep_reflection_promotes_low_risk_pattern_with_supporting_ids(hermes_home: Path) -> None:
    repo = LifeMemoryRepository(hermes_home=hermes_home)
    repo.initialize()
    pattern_id = _memory(
        repo,
        "The user tends to prefer quiet implementation plans before broad refactors.",
        primary_category="personal_pattern",
        tags=("pattern_candidate", "work_style"),
        status=LifecycleStatus.PATTERN_CANDIDATE.value,
        confidence=0.86,
    )
    with repo.transaction() as conn:
        conn.execute(
            """
            UPDATE life_memories
            SET evidence_count = 4,
                source_count = 2,
                days_seen_count = 3,
                promotion_score = 0.9
            WHERE memory_id = ?
            """,
            (pattern_id,),
        )

    result = run_reflection(repo, mode="deep", apply=True)

    assert result["ok"] is True
    assert result["reflected_memory_ids"]
    reflected = repo.get_memory(result["reflected_memory_ids"][0])
    assert reflected["kind"] == "reflected"
    assert reflected["classification"] == "abstract_experience"
    assert pattern_id in reflected["context"]["supporting_memory_ids"]


def test_daily_reflection_is_report_only_and_preserves_promotion_score(hermes_home: Path) -> None:
    repo = LifeMemoryRepository(hermes_home=hermes_home)
    repo.initialize()
    memory_id = _memory(repo, "Remember that I prefer focused work late at night.")
    before = repo.get_memory(memory_id)
    before_count = repo.fetch_one("SELECT COUNT(*) AS count FROM life_memories")

    result = run_reflection(repo, mode="daily", apply=True)

    after = repo.get_memory(memory_id)
    after_count = repo.fetch_one("SELECT COUNT(*) AS count FROM life_memories")
    report = repo.fetch_one("SELECT * FROM reflection_reports WHERE report_id = ?", (result["reports"][0],))
    assert result["report_only"] is True
    assert result["applied_count"] == 0
    assert before_count["count"] == after_count["count"]
    assert before["promotion_score"] == after["promotion_score"]
    assert report is not None
    assert report["report_type"] == "daily"
