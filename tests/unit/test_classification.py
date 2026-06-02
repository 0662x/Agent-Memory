from __future__ import annotations

import json
from pathlib import Path

import pytest

from plugins.life_memory.classification import classify_candidate
from plugins.life_memory.models import MemoryClassification


@pytest.mark.parametrize(
    ("content", "expected", "reason_term"),
    [
        (
            "My Hermes runs on Mac, and Windows is connected through SSH.",
            MemoryClassification.TECHNICAL_MEMORY,
            "technical",
        ),
        (
            "Remember that I prefer to work late at night and usually think better after midnight.",
            MemoryClassification.LIFE_MEMORY,
            "life",
        ),
        (
            "From now on, when you generate English content for me, include Chinese translation below.",
            MemoryClassification.USER_PROFILE,
            "response",
        ),
        (
            "For this conversation, keep the current task context about the draft in mind.",
            MemoryClassification.TEMPORARY_WORKING_MEMORY,
            "temporary",
        ),
        (
            "I'm a bit tired today.",
            MemoryClassification.NO_SAVE,
            "temporary",
        ),
    ],
)
def test_boundary_classification(content: str, expected: MemoryClassification, reason_term: str) -> None:
    decision = classify_candidate(content)

    assert decision.classification is expected
    assert reason_term in decision.reason.lower()


def test_life_preference_gets_primary_category_and_tags() -> None:
    decision = classify_candidate(
        "Remember that I prefer to work late at night and usually think better after midnight."
    )

    assert decision.classification is MemoryClassification.LIFE_MEMORY
    assert decision.primary_category == "personal_preference"
    assert {"routine", "night", "work_style"}.issubset(set(decision.tags))
    assert decision.should_store is True


def test_personal_fact_gets_fact_category() -> None:
    decision = classify_candidate("Remember that my sister Maya lives in Brisbane.")

    assert decision.classification is MemoryClassification.LIFE_MEMORY
    assert decision.primary_category == "personal_fact"
    assert "family" in decision.tags


def test_repeated_pattern_candidate_stays_life_memory_until_supported() -> None:
    decision = classify_candidate(
        "I tend to reject over-engineered solutions and prefer MVP-first implementation.",
        evidence_count=1,
    )

    assert decision.classification is MemoryClassification.LIFE_MEMORY
    assert decision.primary_category == "personal_pattern"
    assert "pattern_candidate" in decision.tags


def test_supported_repeated_pattern_can_be_abstract_experience() -> None:
    decision = classify_candidate(
        "Across several sessions, the user rejects over-engineered solutions and prefers MVP-first implementation.",
        evidence_count=3,
    )

    assert decision.classification is MemoryClassification.ABSTRACT_EXPERIENCE
    assert decision.primary_category == "personal_pattern"
    assert decision.should_store is False


def test_no_save_becomes_recent_state_when_explicitly_requested() -> None:
    decision = classify_candidate("Remember that I am a bit tired today.", explicit_user_request=True)

    assert decision.classification is MemoryClassification.LIFE_MEMORY
    assert decision.primary_category == "personal_fact"
    assert "recent_state" in decision.tags


def test_mixed_language_preference_is_life_memory() -> None:
    decision = classify_candidate("这个可以长期记一下：我通常晚上十点以后 focus 更好，早上的例会会打断我。")

    assert decision.classification is MemoryClassification.LIFE_MEMORY
    assert decision.primary_category == "personal_pattern"
    assert {"routine", "night", "morning", "work_style"}.issubset(set(decision.tags))


def test_compact_chinese_food_preference_entry_is_life_memory() -> None:
    decision = classify_candidate("晚饭后喜欢喝茉莉茶。")

    assert decision.classification is MemoryClassification.LIFE_MEMORY
    assert decision.primary_category == "personal_preference"
    assert "food" in decision.tags


def test_life_preference_with_test_marker_is_not_technical_memory() -> None:
    decision = classify_candidate("晚饭后喜欢喝一款路由测试饮品，名字是 route_marker_123。")

    assert decision.classification is MemoryClassification.LIFE_MEMORY
    assert decision.primary_category == "personal_preference"


def test_compact_chinese_weekend_routine_summary_is_life_memory() -> None:
    decision = classify_candidate("周六下午慢跑完通常会买无糖豆浆。")

    assert decision.classification is MemoryClassification.LIFE_MEMORY
    assert decision.primary_category == "personal_pattern"
    assert {"routine", "food", "health"}.issubset(set(decision.tags))


def test_third_person_response_preference_is_user_profile() -> None:
    decision = classify_candidate("User prefers concise responses with concrete next steps.")

    assert decision.classification is MemoryClassification.USER_PROFILE


def test_long_term_career_goal_is_user_profile_even_when_explicit() -> None:
    decision = classify_candidate("记住：我希望以后做 agent 岗位。", explicit_user_request=True)

    assert decision.classification is MemoryClassification.USER_PROFILE
    assert decision.should_store is False


def test_chinese_do_not_store_temporary_state_is_not_life_memory() -> None:
    decision = classify_candidate("不要长期记这个，我今天有点焦虑。")

    assert decision.classification is MemoryClassification.TEMPORARY_WORKING_MEMORY
    assert decision.should_store is False


def test_evaluation_classification_fixtures_match_expected() -> None:
    fixture = Path(__file__).parents[1] / "fixtures" / "evaluation_cases.json"
    data = json.loads(fixture.read_text(encoding="utf-8"))

    cases = [case for case in data["cases"] if case["case_type"] == "classification"]
    assert cases

    for case in cases:
        expected = case["expected"]
        decision = classify_candidate(**case["input"])

        assert decision.classification.value == expected["classification"], case["case_id"]
        if "primary_category" in expected:
            assert decision.primary_category == expected["primary_category"], case["case_id"]
        reason = decision.reason.lower()
        assert all(term.lower() in reason for term in expected["reason_contains"]), case["case_id"]
