from __future__ import annotations

from typing import Any

from .models import ToolOutcome
from .time_utils import json_dumps


TOOL_NAMES = (
    "life_memory_store",
    "life_memory_recall",
    "life_memory_feedback",
    "life_memory_forget",
    "life_memory_reflect",
    "life_memory_export_review",
    "life_memory_sync_review",
)

OUTCOMES = tuple(outcome.value for outcome in ToolOutcome)


def _schema(name: str, description: str, parameters: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "parameters": parameters,
    }


TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "life_memory_store": _schema(
        "life_memory_store",
        (
            "Classify and store an L4 life memory candidate: non-technical personal routines, "
            "habits, food/lifestyle preferences, relationships, life events, and repeated "
            "personal patterns. Do not use for technical/project memory or stable response-profile "
            "instructions; those belong in Hermes built-in memory."
        ),
        {
            "type": "object",
            "required": ["content"],
            "properties": {
                "content": {"type": "string"},
                "explicit_user_request": {"type": "boolean", "default": False},
                "category_hint": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}, "default": []},
                "importance": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.5},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.7},
                "source": {"type": "string", "default": "assistant_tool"},
                "source_ref": {"type": "string"},
                "context": {"type": "object", "additionalProperties": True},
            },
        },
    ),
    "life_memory_recall": _schema(
        "life_memory_recall",
        "Retrieve bounded, relevant L4 life memories for a query, excluding technical/project memory.",
        {
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5},
                "candidate_limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 30},
                "categories": {"type": "array", "items": {"type": "string"}, "default": []},
                "include_archived": {"type": "boolean", "default": False},
                "include_sensitive": {"type": "boolean", "default": False},
                "include_traces": {"type": "boolean", "default": False},
                "recall_mode": {"type": "string", "enum": ["lexical", "hybrid", "auto"], "default": "hybrid"},
                "semantic": {"type": "boolean", "default": True},
                "historical_mode": {"type": "boolean", "default": False},
            },
        },
    ),
    "life_memory_feedback": _schema(
        "life_memory_feedback",
        "Apply feedback, correction, duplicate, merge, or deletion intent to a life memory.",
        {
            "type": "object",
            "required": ["memory_id", "feedback_type"],
            "properties": {
                "memory_id": {"type": "string"},
                "feedback_type": {
                    "type": "string",
                    "enum": ["useful", "wrong", "outdated", "important", "duplicate", "delete", "merge"],
                },
                "note": {"type": "string"},
                "replacement_content": {"type": "string"},
                "target_memory_id": {"type": "string"},
            },
        },
    ),
    "life_memory_forget": _schema(
        "life_memory_forget",
        "Forget an unambiguous life memory by id or confirmed query.",
        {
            "type": "object",
            "anyOf": [{"required": ["memory_id"]}, {"required": ["query"]}],
            "properties": {
                "memory_id": {"type": "string"},
                "query": {"type": "string"},
                "confirm": {"type": "boolean", "default": False},
                "reason": {"type": "string"},
            },
        },
    ),
    "life_memory_reflect": _schema(
        "life_memory_reflect",
        "Run dry-run or applied memory maintenance and reflection.",
        {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["light", "rem", "deep", "session", "daily", "dedupe", "merge", "decay", "archive", "patterns", "all"],
                    "default": "all",
                },
                "apply": {"type": "boolean", "default": False},
                "session_ref": {"type": "string"},
                "transcript": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                "time_window": {"type": "object"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
            },
        },
    ),
    "life_memory_export_review": _schema(
        "life_memory_export_review",
        "Export a read-only Markdown review view of stored life memories.",
        {
            "type": "object",
            "properties": {
                "target_dir": {"type": "string"},
                "include_archive": {"type": "boolean", "default": True},
                "include_sensitive": {"type": "string", "enum": ["none", "summary_only"], "default": "summary_only"},
            },
        },
    ),
    "life_memory_sync_review": _schema(
        "life_memory_sync_review",
        (
            "Explicitly parse and optionally apply structured life-memory review change requests "
            "from change-requests.md. Defaults to dry-run and ignores arbitrary exported Markdown edits."
        ),
        {
            "type": "object",
            "properties": {
                "apply": {"type": "boolean", "default": False},
                "confirm_apply": {"type": "boolean", "default": False},
                "review_dir": {"type": "string"},
                "source_file": {"type": "string", "default": "change-requests.md"},
                "change_requests_text": {"type": "string"},
                "max_actions": {"type": "integer", "minimum": 1, "maximum": 200, "default": 50},
            },
        },
    ),
}


def build_result(
    *,
    ok: bool,
    outcome: str | ToolOutcome,
    message: str,
    trace_id: str | None,
    **fields: Any,
) -> dict[str, Any]:
    outcome_value = outcome.value if isinstance(outcome, ToolOutcome) else outcome
    result = {
        "ok": bool(ok),
        "outcome": outcome_value,
        "message": message,
        "trace_id": trace_id,
    }
    result.update(fields)
    return result


def result_json(**kwargs: Any) -> str:
    return json_dumps(build_result(**kwargs))
