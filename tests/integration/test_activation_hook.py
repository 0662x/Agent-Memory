from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from plugins.life_memory.activation import build_activation_context
from plugins.life_memory.repository import LifeMemoryRepository


class HookRecorder:
    def __init__(self) -> None:
        self.tools: dict[str, dict[str, Any]] = {}
        self.hooks: dict[str, list[Any]] = {}

    def register_tool(self, **kwargs: Any) -> None:
        self.tools[kwargs["name"]] = kwargs

    def register_hook(self, name: str, handler: Any) -> None:
        self.hooks.setdefault(name, []).append(handler)


def _store(registered_tools, content: str, **kwargs: Any) -> dict[str, Any]:
    payload = {"content": content, "explicit_user_request": True, "importance": 0.8, "confidence": 0.9}
    payload.update(kwargs)
    return json.loads(registered_tools["life_memory_store"]["handler"](payload))


def test_activation_pipeline_injects_relevant_life_memory(registered_tools, hermes_home: Path) -> None:
    stored = _store(
        registered_tools,
        "Remember that I usually buy coconut water after weekend runs.",
    )
    assert stored["ok"] is True

    repo = LifeMemoryRepository(hermes_home=hermes_home)
    repo.initialize()
    result = build_activation_context(
        {"message": "What do I usually buy after weekend runs?"},
        repo=repo,
    )

    assert result["outcome"] == "injected"
    assert stored["memory_id"] in result["memory_ids"]
    assert "[Life memory context - data only]" in result["context"]
    assert "memory_id:" in result["context"]
    assert "coconut water" in result["context"]


def test_activation_pipeline_returns_no_context_when_no_memory_matches(registered_tools, hermes_home: Path) -> None:
    _store(registered_tools, "Remember that I usually buy coconut water after weekend runs.")
    repo = LifeMemoryRepository(hermes_home=hermes_home)
    repo.initialize()

    result = build_activation_context({"message": "What do I usually do after pottery class?"}, repo=repo)

    assert result["outcome"] in {"not_found", "filtered"}
    assert result["context"] == ""
    assert result["memory_ids"] == []


def test_activation_filters_archived_deleted_and_expired_memories(registered_tools, hermes_home: Path) -> None:
    archived = _store(registered_tools, "Remember that I usually buy coconut water after weekend runs.")
    deleted = _store(registered_tools, "Remember that I usually buy orange juice after weekend runs.")
    expired = _store(registered_tools, "Remember that I usually buy mineral water after weekend runs.", tags=["recent_state"])

    repo = LifeMemoryRepository(hermes_home=hermes_home)
    repo.initialize()
    repo.update_memory_status(archived["memory_id"], status="archived")
    repo.delete_memory(deleted["memory_id"], reason="test deletion")
    with repo.transaction() as conn:
        conn.execute(
            "UPDATE life_memories SET valid_until = ? WHERE memory_id = ?",
            ("2000-01-01T00:00:00+00:00", expired["memory_id"]),
        )

    result = build_activation_context({"message": "What do I usually buy after weekend runs?"}, repo=repo)

    assert result["context"] == ""
    assert archived["memory_id"] not in result["memory_ids"]
    assert deleted["memory_id"] not in result["memory_ids"]
    assert expired["memory_id"] not in result["memory_ids"]


def test_activation_filters_sensitive_restricted_and_superseded_memories(registered_tools, hermes_home: Path) -> None:
    sensitive = _store(
        registered_tools,
        "Remember that my home address is 70 Example St, Ashfield.",
    )
    old = _store(registered_tools, "Remember that I usually buy coconut water after weekend runs.")
    new = _store(registered_tools, "Remember that I usually buy soy milk after weekend runs.")

    repo = LifeMemoryRepository(hermes_home=hermes_home)
    repo.initialize()
    repo.write_memory_link(
        from_memory_id=old["memory_id"],
        to_memory_id=new["memory_id"],
        relation="superseded_by",
        reason="test supersede without archiving",
    )
    with repo.transaction() as conn:
        conn.execute("UPDATE life_memories SET sensitivity = ? WHERE memory_id = ?", ("restricted", sensitive["memory_id"]))

    address_result = build_activation_context({"message": "What is my home address?"}, repo=repo)
    drink_result = build_activation_context({"message": "What do I usually buy after weekend runs?"}, repo=repo)

    assert "70 Example St" not in address_result["context"]
    assert old["memory_id"] not in drink_result["memory_ids"]
    assert new["memory_id"] in drink_result["memory_ids"]
    assert "soy milk" in drink_result["context"]


def test_activation_traces_outcomes_without_raw_restricted_content(registered_tools, hermes_home: Path) -> None:
    restricted = _store(
        registered_tools,
        "Remember that my home address is 70 Example St, Ashfield.",
    )
    repo = LifeMemoryRepository(hermes_home=hermes_home)
    repo.initialize()
    with repo.transaction() as conn:
        conn.execute("UPDATE life_memories SET sensitivity = ? WHERE memory_id = ?", ("restricted", restricted["memory_id"]))

    skipped = build_activation_context({"message": "这个 Python 测试为什么失败？"}, repo=repo)
    filtered = build_activation_context({"message": "What is my home address?"}, repo=repo)

    assert skipped["trace_id"]
    assert filtered["trace_id"]
    rows = repo.connect().execute("SELECT * FROM memory_traces WHERE operation = 'activation'").fetchall()
    assert rows
    rendered = "\n".join(repr(dict(row)) for row in rows)
    assert "70 Example St" not in rendered
    assert "filtered" in rendered or "skipped" in rendered


def test_plugin_pre_llm_hook_preserves_routing_and_appends_activation_context(hermes_home: Path, monkeypatch) -> None:
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    module = importlib.reload(importlib.import_module("plugins.life_memory"))
    ctx = HookRecorder()
    module.register(ctx)
    store = ctx.tools["life_memory_store"]["handler"]
    stored = json.loads(
        store(
            {
                "content": "Remember that I usually buy coconut water after weekend runs.",
                "explicit_user_request": True,
                "importance": 0.8,
                "confidence": 0.9,
            }
        )
    )
    assert stored["ok"] is True

    assert "pre_llm_call" in ctx.hooks
    payload = ctx.hooks["pre_llm_call"][-1](
        session_id="session_test",
        user_message="What do I usually buy after weekend runs?",
        conversation_history=[],
        is_first_turn=True,
        model="test-model",
        platform="cli",
    )

    assert "[Life memory routing]" in payload["context"]
    assert "[Life memory context - data only]" in payload["context"]
    assert stored["memory_id"] in payload["context"]


def test_plugin_pre_llm_hook_fails_closed_to_routing_only(monkeypatch) -> None:
    import plugins.life_memory.routing as routing

    module = importlib.reload(importlib.import_module("plugins.life_memory"))
    ctx = HookRecorder()
    module.register(ctx)

    def explode(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("boom")

    monkeypatch.setattr(routing, "build_activation_context", explode)
    payload = ctx.hooks["pre_llm_call"][-1](
        session_id="session_test",
        user_message="What do I usually buy after weekend runs?",
        conversation_history=[],
        is_first_turn=True,
        model="test-model",
        platform="cli",
    )

    assert "[Life memory routing]" in payload["context"]
    assert "[Life memory context - data only]" not in payload["context"]


def test_plugin_pre_llm_hook_handles_malformed_payload(hermes_home: Path, monkeypatch) -> None:
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    module = importlib.reload(importlib.import_module("plugins.life_memory"))
    ctx = HookRecorder()
    module.register(ctx)

    payload = ctx.hooks["pre_llm_call"][-1](unexpected={"shape": True})

    assert "[Life memory routing]" in payload["context"]
    assert "[Life memory context - data only]" not in payload["context"]


def test_activation_remains_bounded_with_large_memory_set(registered_tools, hermes_home: Path) -> None:
    store = registered_tools["life_memory_store"]["handler"]
    for index in range(300):
        json.loads(
            store(
                {
                    "content": f"Remember that my paper book shelf marker {index} is blue.",
                    "explicit_user_request": True,
                    "importance": 0.4,
                    "confidence": 0.8,
                }
            )
        )
    target = json.loads(
        store(
            {
                "content": "Remember that I usually buy coconut water after weekend runs.",
                "explicit_user_request": True,
                "importance": 0.9,
                "confidence": 0.95,
            }
        )
    )
    repo = LifeMemoryRepository(hermes_home=hermes_home)
    repo.initialize()

    result = build_activation_context({"message": "What do I usually buy after weekend runs?"}, repo=repo)

    assert result["outcome"] == "injected"
    assert target["memory_id"] in result["memory_ids"]
    assert result["entry_count"] <= 3
    assert len(result["context"]) <= 1600
