from __future__ import annotations

import json
import sys
import types

from plugins.life_memory.routing import (
    DESTINATION_BUILTIN_MEMORY,
    DESTINATION_BUILTIN_USER,
    DESTINATION_LIFE_MEMORY,
    DESTINATION_SKIP,
    decide_memory_route,
    install_memory_routing,
    route_memory_tool_call,
)


def test_decide_memory_route_splits_life_technical_profile_and_temporary() -> None:
    assert (
        decide_memory_route("晚饭后喜欢喝茉莉茶。").destination
        == DESTINATION_LIFE_MEMORY
    )
    assert (
        decide_memory_route("The project uses SQLite FTS5 for search.").destination
        == DESTINATION_BUILTIN_MEMORY
    )
    assert (
        decide_memory_route("User prefers concise responses with concrete next steps.").destination
        == DESTINATION_BUILTIN_USER
    )
    assert (
        decide_memory_route("For this conversation, keep this draft in mind.").destination
        == DESTINATION_SKIP
    )


def test_decide_memory_route_handles_realistic_daily_inputs() -> None:
    assert (
        decide_memory_route("以后可以记一下，我周六下午一般去河边慢跑，跑完会买无糖豆浆。").destination
        == DESTINATION_LIFE_MEMORY
    )
    assert (
        decide_memory_route("周六下午慢跑完通常会买无糖豆浆。").destination
        == DESTINATION_LIFE_MEMORY
    )
    assert (
        decide_memory_route("The project database uses SQLite WAL; remember this for debugging.").destination
        == DESTINATION_BUILTIN_MEMORY
    )
    assert (
        decide_memory_route("User prefers concise responses with concrete next steps.").destination
        == DESTINATION_BUILTIN_USER
    )
    assert (
        decide_memory_route("记住：我希望以后做 agent 岗位。").destination
        == DESTINATION_BUILTIN_USER
    )
    assert (
        decide_memory_route("这次先别长期记，我今天只是有点胃不舒服。").destination
        == DESTINATION_SKIP
    )


def test_memory_tool_call_routes_life_memory_to_store_handler() -> None:
    original_calls: list[dict] = []
    store_calls: list[dict] = []

    def original(**kwargs):
        original_calls.append(kwargs)
        return json.dumps({"success": True, "target": kwargs["target"]})

    def store_handler(payload):
        store_calls.append(payload)
        return json.dumps(
            {
                "ok": True,
                "outcome": "success",
                "message": "stored",
                "trace_id": "trace_test",
                "memory_id": "mem_test",
            }
        )

    raw = route_memory_tool_call(
        action="add",
        target="user",
        content="晚饭后喜欢喝茉莉茶。",
        original_memory_tool=original,
        store_handler=store_handler,
    )

    result = json.loads(raw)
    assert original_calls == []
    assert store_calls[0]["source"] == "memory_router"
    assert result["routed_to"] == DESTINATION_LIFE_MEMORY
    assert result["memory_id"] == "mem_test"


def test_memory_tool_call_keeps_technical_and_profile_in_builtin_memory() -> None:
    original_calls: list[dict] = []

    def original(**kwargs):
        original_calls.append(kwargs)
        return json.dumps({"success": True, "target": kwargs["target"]})

    route_memory_tool_call(
        action="add",
        target="user",
        content="The project uses SQLite FTS5 for search.",
        original_memory_tool=original,
    )
    route_memory_tool_call(
        action="add",
        target="memory",
        content="User prefers concise responses with concrete next steps.",
        original_memory_tool=original,
    )

    assert original_calls[0]["target"] == "memory"
    assert original_calls[1]["target"] == "user"


def test_memory_tool_call_declines_temporary_memory() -> None:
    def original(**kwargs):
        raise AssertionError("temporary memory should not reach built-in memory")

    raw = route_memory_tool_call(
        action="add",
        target="memory",
        content="For this conversation, keep this draft in mind.",
        original_memory_tool=original,
    )

    result = json.loads(raw)
    assert result["ok"] is False
    assert result["outcome"] == "declined"
    assert result["routed_to"] == DESTINATION_SKIP


def test_install_memory_routing_patches_fake_hermes_memory_tool(monkeypatch) -> None:
    tools_pkg = types.ModuleType("tools")
    memory_mod = types.ModuleType("tools.memory_tool")

    def original_memory_tool(**kwargs):
        return json.dumps({"success": True, "target": kwargs["target"]})

    memory_mod.memory_tool = original_memory_tool
    memory_mod.MEMORY_SCHEMA = {
        "name": "memory",
        "description": "old",
        "parameters": {"properties": {"content": {"description": "old"}}},
    }

    registry_mod = types.ModuleType("tools.registry")

    class Registry:
        _generation = 0

        def get_entry(self, name):
            return None

    registry_mod.registry = Registry()
    tools_pkg.memory_tool = memory_mod
    tools_pkg.registry = registry_mod
    monkeypatch.setitem(sys.modules, "tools", tools_pkg)
    monkeypatch.setitem(sys.modules, "tools.memory_tool", memory_mod)
    monkeypatch.setitem(sys.modules, "tools.registry", registry_mod)

    install_memory_routing(ctx=object(), store_handler=lambda payload: json.dumps({"ok": True}))

    assert memory_mod.memory_tool is not original_memory_tool
    assert "L2 technical/project" in memory_mod.MEMORY_SCHEMA["description"]


def test_install_memory_routing_hook_preserves_routing_context_for_non_life_request() -> None:
    hooks = {}

    class Ctx:
        def register_hook(self, name, handler):
            hooks[name] = handler

    install_memory_routing(ctx=Ctx(), store_handler=lambda payload: json.dumps({"ok": True}))

    result = hooks["pre_llm_call"](message="这个 Python 测试为什么失败？")
    assert "[Life memory routing]" in result["context"]
    assert "[Life memory context - data only]" not in result["context"]
