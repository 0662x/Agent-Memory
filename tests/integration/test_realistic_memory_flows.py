from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from plugins.life_memory.repository import LifeMemoryRepository


FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "realistic_transcripts.json"


def _fixture() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_realistic_transcript_pack_extracts_signal_without_saving_noise(
    registered_tools,
    hermes_home: Path,
) -> None:
    reflect = registered_tools["life_memory_reflect"]["handler"]
    recall = registered_tools["life_memory_recall"]["handler"]
    repo = LifeMemoryRepository(hermes_home=hermes_home)

    for case in _fixture()["transcript_cases"]:
        result = json.loads(
            reflect(
                {
                    "mode": "session",
                    "apply": True,
                    "session_ref": case["case_id"],
                    "transcript": case["transcript"],
                }
            )
        )
        expected = case["expected"]
        stored_ids = result.get("stored_memory_ids") or []
        stored_rows = [repo.get_memory(memory_id) for memory_id in stored_ids]
        combined = "\n".join(row["content"] for row in stored_rows if row is not None)

        assert result["ok"] is True, case["case_id"]
        assert len(stored_ids) >= expected["min_stored"], case["case_id"]
        assert result["declined_candidate_count"] >= expected.get("min_declined", 0), case["case_id"]
        for term in expected.get("stored_terms", []):
            assert term.lower() in combined.lower(), case["case_id"]
        for term in expected.get("not_stored_terms", []):
            assert term.lower() not in combined.lower(), case["case_id"]

        for query in expected.get("recall_queries", []):
            recalled = json.loads(recall({"query": query["query"], "limit": 5}))
            assert recalled["outcome"] == "success", case["case_id"]
            recalled_text = "\n".join(item["content"] for item in recalled["results"])
            assert query["must_include"].lower() in recalled_text.lower(), case["case_id"]


def test_realistic_chinese_family_schedule_extracts_and_recalls(
    registered_tools,
    hermes_home: Path,
) -> None:
    reflect = registered_tools["life_memory_reflect"]["handler"]
    recall = registered_tools["life_memory_recall"]["handler"]
    repo = LifeMemoryRepository(hermes_home=hermes_home)

    result = json.loads(
        reflect(
            {
                "mode": "session",
                "apply": True,
                "session_ref": "zh_family_schedule",
                "transcript": [
                    {
                        "role": "user",
                        "content": (
                            "这次对话只是整理 migration draft，不要长期记这个。"
                            "我周三晚上通常要接侄女 Ava 下芭蕾课，所以不安排晚会议。"
                            "我希望以后做 agent 岗位。"
                        ),
                        "source_ref": "zh_family_1",
                    }
                ],
            }
        )
    )
    stored_rows = [repo.get_memory(memory_id) for memory_id in result["stored_memory_ids"]]
    stored_text = "\n".join(row["content"] for row in stored_rows if row is not None)
    recalled = json.loads(recall({"query": "周三 Ava 芭蕾", "limit": 5}))
    recalled_text = "\n".join(item["content"] for item in recalled.get("results", []))

    assert result["ok"] is True
    assert result["stored_memory_ids"]
    assert "侄女 Ava" in stored_text
    assert "migration draft" not in stored_text
    assert "agent 岗位" not in stored_text
    assert recalled["outcome"] == "success"
    assert "Ava" in recalled_text


def test_realistic_boundary_cases_do_not_create_durable_memories(
    registered_tools,
    hermes_home: Path,
) -> None:
    store = registered_tools["life_memory_store"]["handler"]
    repo = LifeMemoryRepository(hermes_home=hermes_home)
    repo.initialize()

    for case in _fixture()["store_boundary_cases"]:
        before = repo.fetch_one("SELECT COUNT(*) AS count FROM life_memories")
        result = json.loads(store({"content": case["content"], "explicit_user_request": False}))
        after = repo.fetch_one("SELECT COUNT(*) AS count FROM life_memories")

        assert result["ok"] is False, case["case_id"]
        assert result["outcome"] == case["expected"]["outcome"], case["case_id"]
        if case["expected"]["durable_write"] is False:
            assert after["count"] == before["count"], case["case_id"]


def test_realistic_daily_usage_store_and_recall_natural_language(registered_tools) -> None:
    store = registered_tools["life_memory_store"]["handler"]
    recall = registered_tools["life_memory_recall"]["handler"]
    scenarios = [
        {
            "content": "我晚饭后通常会泡一杯茉莉茶，睡前就不喝咖啡了。",
            "explicit_user_request": False,
            "query": "我晚饭后一般喝什么放松？",
            "must_include": "茉莉茶",
        },
        {
            "content": (
                "I usually pick up my niece Ava after ballet on Wednesdays, "
                "so I avoid late meetings then."
            ),
            "explicit_user_request": False,
            "query": "Wednesday ballet pickup",
            "must_include": "Ava",
        },
        {
            "content": "我周六下午一般去河边慢跑，跑完会买无糖豆浆。",
            "explicit_user_request": False,
            "query": "周末运动后的饮品是什么？",
            "must_include": "无糖豆浆",
        },
    ]

    for scenario in scenarios:
        stored = json.loads(
            store(
                {
                    "content": scenario["content"],
                    "explicit_user_request": scenario["explicit_user_request"],
                    "source": "realistic_daily_test",
                }
            )
        )
        recalled = json.loads(recall({"query": scenario["query"], "limit": 5}))
        recalled_text = "\n".join(item["content"] for item in recalled.get("results", []))

        assert stored["ok"] is True, scenario["content"]
        assert recalled["outcome"] == "success", scenario["query"]
        assert scenario["must_include"] in recalled_text, scenario["query"]


def test_realistic_cross_session_correction_excludes_superseded_memory(
    registered_tools,
) -> None:
    reflect = registered_tools["life_memory_reflect"]["handler"]
    feedback = registered_tools["life_memory_feedback"]["handler"]
    recall = registered_tools["life_memory_recall"]["handler"]

    extracted = json.loads(
        reflect(
            {
                "mode": "session",
                "apply": True,
                "session_ref": "correction_session_1",
                "transcript": [
                    {
                        "role": "user",
                        "content": "Remember that I prefer late-night planning sessions.",
                        "source_ref": "correction_msg_1",
                    }
                ],
            }
        )
    )
    old_memory_id = extracted["stored_memory_ids"][0]
    correction = json.loads(
        feedback(
            {
                "memory_id": old_memory_id,
                "feedback_type": "wrong",
                "replacement_content": "Remember that I now prefer morning planning sessions.",
                "note": "Realistic correction after the user's routine changed.",
            }
        )
    )
    recalled = json.loads(recall({"query": "morning planning sessions", "limit": 5}))
    old_recall = json.loads(recall({"query": "late-night planning sessions", "limit": 5}))

    assert correction["ok"] is True
    assert correction["replacement_memory_id"].startswith("mem_")
    assert correction["replacement_memory_id"] in [item["memory_id"] for item in recalled["results"]]
    assert old_memory_id not in [item["memory_id"] for item in old_recall.get("results", [])]


def test_realistic_multi_session_pattern_can_promote_to_reflected_memory(
    registered_tools,
    hermes_home: Path,
) -> None:
    reflect = registered_tools["life_memory_reflect"]["handler"]
    repo = LifeMemoryRepository(hermes_home=hermes_home)
    transcripts = [
        "I usually prefer concise implementation plans before changing code.",
        "I often ask for implementation checklists before starting work.",
        "I tend to reject broad work refactors unless there is a small first step.",
    ]

    for index, content in enumerate(transcripts):
        extracted = json.loads(
            reflect(
                {
                    "mode": "session",
                    "apply": True,
                    "session_ref": f"pattern_session_{index}",
                    "transcript": [{"role": "user", "content": content, "source_ref": f"pattern_msg_{index}"}],
                }
            )
        )
        assert extracted["stored_memory_ids"]

    rem = json.loads(reflect({"mode": "rem", "apply": True}))
    deep = json.loads(reflect({"mode": "deep", "apply": True}))

    assert rem["candidate_count"] >= 1
    assert deep["reflected_memory_ids"]
    reflected_rows = [repo.get_memory(memory_id) for memory_id in deep["reflected_memory_ids"]]
    assert any(
        row is not None
        and row["kind"] == "reflected"
        and row["classification"] == "abstract_experience"
        and len(row["context"].get("supporting_memory_ids", [])) >= 3
        for row in reflected_rows
    )
