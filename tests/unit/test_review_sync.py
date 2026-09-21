from __future__ import annotations

from pathlib import Path

import pytest

from plugins.life_memory.review_sync import (
    ReviewSyncActionResult,
    ReviewSyncPlan,
    load_change_request_text,
    plan_review_sync,
    parse_review_change_requests,
)
from plugins.life_memory.repository import LifeMemoryRepository


def test_parse_life_memory_change_blocks_with_line_numbers() -> None:
    text = """
Intro text is ignored.

```life-memory-change
id: req-001
action: replace
memory_id: mem_old
replacement: I now buy unsweetened soy milk after Saturday runs.
reason: corrected
confirm: true
```
"""

    requests = parse_review_change_requests(text)

    assert len(requests) == 1
    request = requests[0]
    assert request.request_id == "req-001"
    assert request.action == "replace"
    assert request.target_memory_ids == ("mem_old",)
    assert request.replacement_content == "I now buy unsweetened soy milk after Saturday runs."
    assert request.confirm is True
    assert request.start_line == 4
    assert request.end_line == 11
    assert request.raw_hash
    assert request.errors == ()


def test_parse_detects_unsupported_duplicate_and_missing_action() -> None:
    text = """
```life-memory-change
id: req-dup
action: dance
memory_id: mem_a
```

```life-memory-change
id: req-dup
memory_id: mem_b
```
"""

    requests = parse_review_change_requests(text)

    assert len(requests) == 2
    assert "unsupported action: dance" in requests[0].errors
    assert "missing action" in requests[1].errors
    assert "duplicate request id: req-dup" in requests[1].errors


def test_parse_memory_ids_array() -> None:
    text = """
```life-memory-change
id: req-merge
action: merge
memory_ids: [mem_a, mem_b, "mem_c"]
merged_content: User buys soy milk after Saturday runs.
confirm: true
```
"""

    request = parse_review_change_requests(text)[0]

    assert request.target_memory_ids == ("mem_a", "mem_b", "mem_c")


def test_parse_respects_max_actions() -> None:
    text = "\n\n".join(
        f"""```life-memory-change
id: req-{index}
action: confirm
memory_id: mem_{index}
```"""
        for index in range(3)
    )

    requests = parse_review_change_requests(text, max_actions=2)

    assert [request.request_id for request in requests] == ["req-0", "req-1"]


def test_parse_large_change_request_file_is_bounded() -> None:
    text = "\n\n".join(
        f"""```life-memory-change
id: req-{index:03d}
action: confirm
memory_id: mem_{index:03d}
```"""
        for index in range(100)
    )

    requests = parse_review_change_requests(text, max_actions=100)

    assert len(requests) == 100
    assert requests[0].request_id == "req-000"
    assert requests[-1].request_id == "req-099"


def test_load_change_request_text_rejects_path_traversal(tmp_path: Path) -> None:
    review_dir = tmp_path / "life_memory_review"
    review_dir.mkdir()

    with pytest.raises(ValueError):
        load_change_request_text(review_dir=review_dir, source_file="../outside.md")


def test_load_change_request_text_supports_inline_text(tmp_path: Path) -> None:
    text, path = load_change_request_text(
        review_dir=tmp_path,
        change_requests_text="```life-memory-change\nid: req\naction: confirm\nmemory_id: mem\n```",
    )

    assert "life-memory-change" in text
    assert path is None


def test_stable_result_shapes() -> None:
    action = ReviewSyncActionResult(
        request_id="req-001",
        action="delete",
        outcome="planned",
        target_memory_ids=["mem_a"],
        warnings=["confirm required"],
    )
    plan = ReviewSyncPlan(
        apply=False,
        source_path=None,
        source_hash="hash",
        actions=[action],
        trace_id="trace_123",
    )

    assert action.to_dict()["target_memory_ids"] == ["mem_a"]
    assert plan.summary["planned"] == 1
    assert plan.to_dict()["outcome"] == "planned"
    assert plan.ok is True


def test_plan_review_sync_dry_run_returns_target_ids_without_mutation(tmp_path: Path) -> None:
    repo = LifeMemoryRepository(hermes_home=tmp_path)
    repo.initialize()
    created = repo.create_memory(
        content="Remember that I prefer focused work late at night.",
        classification="life_memory",
        classification_reason="unit test",
        classification_confidence=0.9,
        primary_category="personal_preference",
        tags=("preference",),
        context={},
        importance=0.5,
        confidence=0.8,
        source="test",
        source_ref=None,
        sensitivity="normal",
        injection_risk=0,
    )
    request = parse_review_change_requests(
        f"""```life-memory-change
id: req-delete
action: delete
memory_id: {created['memory_id']}
reason: wrong
confirm: true
```"""
    )[0]

    plan = plan_review_sync(
        repo,
        [request],
        apply=False,
        source_hash="hash",
        source_path=None,
    )

    assert plan.outcome == "planned"
    assert plan.actions[0].target_memory_ids == [created["memory_id"]]
    assert repo.get_memory(created["memory_id"])["status"] == "young"
