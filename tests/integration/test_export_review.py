from __future__ import annotations

import json
from pathlib import Path

from plugins.life_memory.models import LifecycleStatus, ReviewStatus
from plugins.life_memory.repository import LifeMemoryRepository


def _store(handler, content: str, **kwargs):
    payload = {"content": content, "explicit_user_request": True}
    payload.update(kwargs)
    result = json.loads(handler(payload))
    assert result["ok"] is True
    return result


def test_export_review_writes_expected_markdown_files_and_redacts_sensitive(
    registered_tools,
    hermes_home: Path,
) -> None:
    store = registered_tools["life_memory_store"]["handler"]
    export = registered_tools["life_memory_export_review"]["handler"]
    fact = _store(store, "Remember that my sister Maya lives in Brisbane.")
    pref = _store(store, "Remember that I prefer focused work late at night.")
    pattern = _store(
        store,
        "Remember that I tend to prefer quiet morning routines.",
        category_hint="personal_pattern",
    )
    sensitive = _store(store, "Remember my medical therapy schedule.")
    address = _store(store, "Remember that my home address is 70 Example St, Ashfield.")

    repo = LifeMemoryRepository(hermes_home=hermes_home)
    repo.update_memory_status(fact["memory_id"], status=LifecycleStatus.ACTIVE)
    repo.update_memory_status(pref["memory_id"], status=LifecycleStatus.REINFORCED)
    repo.update_memory_status(pattern["memory_id"], status=LifecycleStatus.PATTERN_CANDIDATE)
    repo.update_memory_status(sensitive["memory_id"], status=LifecycleStatus.ACTIVE)
    repo.update_memory_status(address["memory_id"], status=LifecycleStatus.ACTIVE)

    result = json.loads(export({"include_archive": True, "include_sensitive": "summary_only"}))

    assert result["ok"] is True
    files = set(result["files"])
    assert {
        "README.md",
        "memory-journal/README.md",
        "memory-library/facts.md",
        "memory-library/preferences.md",
        "memory-library/patterns.md",
        "review-needed.md",
        "change-requests.md",
        "archive.md",
    }.issubset(files)

    target = Path(result["target_dir"])
    facts = (target / "memory-library" / "facts.md").read_text(encoding="utf-8")
    preferences = (target / "memory-library" / "preferences.md").read_text(encoding="utf-8")
    patterns = (target / "memory-library" / "patterns.md").read_text(encoding="utf-8")
    change_requests = (target / "change-requests.md").read_text(encoding="utf-8")

    assert "Maya lives in Brisbane" in facts
    assert fact["memory_id"] in facts
    assert "focused work late at night" in preferences
    assert "quiet morning routines" in patterns
    assert "medical therapy schedule" not in facts + preferences + patterns
    assert "70 Example St" not in facts + preferences + patterns
    assert "Ashfield" not in facts + preferences + patterns
    assert "Sensitive" in facts + preferences + patterns
    assert "life_memory_sync_review" in change_requests
    assert "```life-memory-change" in change_requests
    assert "Supported actions" in change_requests


def test_export_review_archive_flag_and_sensitive_none(
    registered_tools,
    hermes_home: Path,
) -> None:
    store = registered_tools["life_memory_store"]["handler"]
    export = registered_tools["life_memory_export_review"]["handler"]
    archived = _store(store, "Remember that I used to prefer late-night work.")
    sensitive = _store(store, "Remember my medical therapy schedule.")

    repo = LifeMemoryRepository(hermes_home=hermes_home)
    repo.update_memory_status(archived["memory_id"], status=LifecycleStatus.ARCHIVED)
    repo.update_memory_status(sensitive["memory_id"], status=LifecycleStatus.ACTIVE)

    result = json.loads(export({"include_archive": False, "include_sensitive": "none"}))

    assert result["ok"] is True
    assert "archive.md" not in result["files"]
    target = Path(result["target_dir"])
    combined = "\n".join(path.read_text(encoding="utf-8") for path in target.rglob("*.md"))
    assert "used to prefer late-night work" not in combined
    assert "medical therapy schedule" not in combined
    assert sensitive["memory_id"] not in combined


def test_export_review_is_read_only_except_export_trace(registered_tools, hermes_home: Path) -> None:
    store = registered_tools["life_memory_store"]["handler"]
    export = registered_tools["life_memory_export_review"]["handler"]
    stored = _store(store, "Remember that I prefer focused work late at night.")

    repo = LifeMemoryRepository(hermes_home=hermes_home)
    before = repo.fetch_one("SELECT * FROM life_memories WHERE memory_id = ?", (stored["memory_id"],))
    assert before is not None
    before_trace_count = repo.fetch_one("SELECT COUNT(*) AS count FROM memory_traces")
    assert before_trace_count is not None

    result = json.loads(export({}))

    after = repo.fetch_one("SELECT * FROM life_memories WHERE memory_id = ?", (stored["memory_id"],))
    after_trace_count = repo.fetch_one("SELECT COUNT(*) AS count FROM memory_traces")
    trace = repo.fetch_one("SELECT * FROM memory_traces WHERE trace_id = ?", (result["trace_id"],))

    assert after is not None
    assert before["status"] == after["status"]
    assert before["promotion_score"] == after["promotion_score"]
    assert before["content"] == after["content"]
    assert after_trace_count is not None
    assert after_trace_count["count"] == before_trace_count["count"] + 1
    assert trace is not None
    assert trace["operation"] == "export_review"


def test_export_review_includes_review_needed_file(
    registered_tools,
    hermes_home: Path,
) -> None:
    store = registered_tools["life_memory_store"]["handler"]
    export = registered_tools["life_memory_export_review"]["handler"]
    stored = _store(store, "Remember that I may prefer quiet mornings.")

    repo = LifeMemoryRepository(hermes_home=hermes_home)
    repo.update_memory_status(
        stored["memory_id"],
        status=LifecycleStatus.YOUNG,
        review_status=ReviewStatus.NEEDS_REVIEW,
    )

    result = json.loads(export({}))
    target = Path(result["target_dir"])
    review_needed = (target / "review-needed.md").read_text(encoding="utf-8")

    assert stored["memory_id"] in review_needed
    assert "quiet mornings" in review_needed
