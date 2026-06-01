from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture()
def hermes_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "hermes_home"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    return home


class RegisteredToolRecorder:
    def __init__(self) -> None:
        self.tools: dict[str, dict[str, Any]] = {}

    def register_tool(self, **kwargs: Any) -> None:
        name = kwargs["name"]
        self.tools[name] = kwargs


@pytest.fixture()
def plugin_module(hermes_home: Path):
    del hermes_home
    module = importlib.import_module("plugins.life_memory")
    return importlib.reload(module)


@pytest.fixture()
def registered_tools(plugin_module) -> dict[str, dict[str, Any]]:
    ctx = RegisteredToolRecorder()
    plugin_module.register(ctx)
    return ctx.tools


def decode_tool_result(raw: Any) -> dict[str, Any]:
    if isinstance(raw, str):
        return json.loads(raw)
    if isinstance(raw, dict):
        return raw
    raise TypeError(f"Unsupported tool result type: {type(raw)!r}")
