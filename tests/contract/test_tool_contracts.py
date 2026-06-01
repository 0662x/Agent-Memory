from __future__ import annotations

import json
from pathlib import Path

from plugins.life_memory.contracts import OUTCOMES, TOOL_NAMES, TOOL_SCHEMAS, build_result


def test_tool_schemas_cover_all_life_memory_tools() -> None:
    assert set(TOOL_SCHEMAS) == set(TOOL_NAMES)

    for name in TOOL_NAMES:
        schema = TOOL_SCHEMAS[name]
        assert schema["name"] == name
        assert schema["description"]
        assert schema["parameters"]["type"] == "object"
        assert isinstance(schema["parameters"].get("properties", {}), dict)


def test_common_result_envelope_contains_required_fields() -> None:
    result = build_result(
        ok=True,
        outcome="success",
        message="Stored life memory.",
        trace_id="trace_test",
        memory_id="mem_test",
    )

    assert result["ok"] is True
    assert result["outcome"] in OUTCOMES
    assert result["message"] == "Stored life memory."
    assert result["trace_id"] == "trace_test"
    assert result["memory_id"] == "mem_test"


def test_store_schema_requires_content() -> None:
    schema = TOOL_SCHEMAS["life_memory_store"]["parameters"]

    assert schema["required"] == ["content"]
    assert schema["properties"]["importance"]["minimum"] == 0
    assert schema["properties"]["importance"]["maximum"] == 1


def test_store_success_declined_and_needs_confirmation_envelopes(registered_tools, hermes_home: Path) -> None:
    del hermes_home
    handler = registered_tools["life_memory_store"]["handler"]

    success = json.loads(
        handler(
            {
                "content": "Remember that I prefer focused work late at night.",
                "explicit_user_request": True,
            }
        )
    )
    declined = json.loads(handler({"content": "My Hermes runs on Mac and Windows connects over SSH."}))
    needs_confirmation = json.loads(handler({"content": "Remember my bank account number is 123456789."}))

    assert success["ok"] is True
    assert success["outcome"] == "success"
    assert success["memory_id"].startswith("mem_")
    assert success["classification"] == "life_memory"
    assert success["trace_id"].startswith("trace_")

    assert declined["ok"] is False
    assert declined["outcome"] == "declined"
    assert declined["classification"] == "technical_memory"
    assert declined["trace_id"].startswith("trace_")

    assert needs_confirmation["ok"] is False
    assert needs_confirmation["outcome"] == "needs_confirmation"
    assert needs_confirmation["sensitivity"] == "sensitive"
    assert needs_confirmation["trace_id"].startswith("trace_")


def test_forget_schema_requires_memory_id_or_query() -> None:
    schema = TOOL_SCHEMAS["life_memory_forget"]["parameters"]

    assert {"required": ["memory_id"]} in schema["anyOf"]
    assert {"required": ["query"]} in schema["anyOf"]


def test_recall_success_not_found_limit_and_result_shape(registered_tools, hermes_home: Path) -> None:
    del hermes_home
    store = registered_tools["life_memory_store"]["handler"]
    recall = registered_tools["life_memory_recall"]["handler"]
    stored = json.loads(
        store(
            {
                "content": "Remember that I prefer focused work late at night.",
                "explicit_user_request": True,
            }
        )
    )
    assert stored["ok"] is True

    success = json.loads(recall({"query": "late night focused work", "limit": 50}))
    not_found = json.loads(recall({"query": "favorite mountain trail", "limit": 5}))

    assert success["ok"] is True
    assert success["outcome"] == "success"
    assert len(success["results"]) <= 20
    result = success["results"][0]
    assert {
        "memory_id",
        "kind",
        "content",
        "primary_category",
        "tags",
        "status",
        "importance",
        "confidence",
        "relevance_score",
        "relevance_reason",
    }.issubset(result)
    assert success["trace_id"].startswith("trace_")

    assert not_found["ok"] is True
    assert not_found["outcome"] == "not_found"
    assert not_found["results"] == []


def test_recall_sensitivity_flag_controls_sensitive_results(registered_tools, hermes_home: Path) -> None:
    del hermes_home
    store = registered_tools["life_memory_store"]["handler"]
    recall = registered_tools["life_memory_recall"]["handler"]

    stored = json.loads(
        store(
            {
                "content": "Remember my medical therapy schedule.",
                "explicit_user_request": True,
            }
        )
    )
    assert stored["ok"] is True
    assert stored["sensitivity"] == "sensitive"

    hidden = json.loads(recall({"query": "therapy schedule", "include_sensitive": False}))
    visible = json.loads(recall({"query": "therapy schedule", "include_sensitive": True}))

    assert hidden["outcome"] == "not_found"
    assert visible["outcome"] == "success"
    assert visible["results"][0]["sensitivity"] == "sensitive"


def test_feedback_and_forget_contract_outcomes(registered_tools, hermes_home: Path) -> None:
    del hermes_home
    store = registered_tools["life_memory_store"]["handler"]
    feedback = registered_tools["life_memory_feedback"]["handler"]
    forget = registered_tools["life_memory_forget"]["handler"]

    first = json.loads(
        store(
            {
                "content": "Remember that I prefer focused work late at night.",
                "explicit_user_request": True,
            }
        )
    )
    second = json.loads(
        store(
            {
                "content": "Remember that I prefer focused work in the morning.",
                "explicit_user_request": True,
            }
        )
    )

    useful = json.loads(feedback({"memory_id": first["memory_id"], "feedback_type": "useful"}))
    important = json.loads(feedback({"memory_id": first["memory_id"], "feedback_type": "important"}))
    wrong = json.loads(
        feedback(
            {
                "memory_id": first["memory_id"],
                "feedback_type": "wrong",
                "replacement_content": "Remember that I now prefer focused work in the morning.",
            }
        )
    )
    duplicate = json.loads(
        feedback(
            {
                "memory_id": second["memory_id"],
                "feedback_type": "duplicate",
                "target_memory_id": wrong["replacement_memory_id"],
            }
        )
    )
    merge = json.loads(
        feedback(
            {
                "memory_id": second["memory_id"],
                "feedback_type": "merge",
                "target_memory_id": wrong["replacement_memory_id"],
            }
        )
    )
    outdated = json.loads(feedback({"memory_id": second["memory_id"], "feedback_type": "outdated"}))
    delete = json.loads(feedback({"memory_id": second["memory_id"], "feedback_type": "delete"}))
    not_found = json.loads(feedback({"memory_id": "mem_missing", "feedback_type": "useful"}))
    ambiguous = json.loads(forget({"query": "focused work", "confirm": False}))

    assert useful["outcome"] == "success"
    assert important["outcome"] == "success"
    assert wrong["outcome"] == "success"
    assert wrong["replacement_memory_id"].startswith("mem_")
    assert duplicate["outcome"] == "duplicate"
    assert merge["outcome"] == "merged"
    assert outdated["outcome"] in {"archived", "success"}
    assert delete["outcome"] == "success"
    assert not_found["outcome"] == "not_found"
    assert ambiguous["outcome"] == "ambiguous"


def test_export_review_contract_default_archive_sensitive_and_read_only(
    registered_tools,
    hermes_home: Path,
) -> None:
    store = registered_tools["life_memory_store"]["handler"]
    export = registered_tools["life_memory_export_review"]["handler"]
    stored = json.loads(
        store(
            {
                "content": "Remember that I prefer focused work late at night.",
                "explicit_user_request": True,
                "importance": 0.8,
            }
        )
    )

    result = json.loads(export({"include_archive": True, "include_sensitive": "summary_only"}))

    assert result["ok"] is True
    assert result["outcome"] == "success"
    assert result["target_dir"] == str(hermes_home / "life_memory_review")
    assert "README.md" in result["files"]
    assert "memory-library/preferences.md" in result["files"]
    assert "archive.md" in result["files"]
    assert result["read_only"] is True
    assert result["trace_id"].startswith("trace_")

    repo = __import__("plugins.life_memory.repository", fromlist=["LifeMemoryRepository"]).LifeMemoryRepository(
        hermes_home=hermes_home
    )
    memory = repo.fetch_one("SELECT * FROM life_memories WHERE memory_id = ?", (stored["memory_id"],))
    assert memory is not None
    assert memory["status"] == stored["status"]
