"""Runtime routing between Hermes built-in memory and life memory.

This module intentionally lives inside the user plugin. It patches runtime
objects after Hermes imports them, without editing Hermes source files.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .activation import build_activation_context
from .classification import classify_candidate
from .models import MemoryClassification
from .time_utils import json_dumps, make_id

logger = logging.getLogger(__name__)

ROUTER_NAME = "life_memory_router"

DESTINATION_LIFE_MEMORY = "life_memory"
DESTINATION_BUILTIN_MEMORY = "builtin_memory"
DESTINATION_BUILTIN_USER = "builtin_user"
DESTINATION_SKIP = "skip"

_STORE_HANDLER: Callable[[dict[str, Any]], str] | None = None
_ORIGINAL_MEMORY_TOOL: Callable[..., str] | None = None
_ORIGINAL_MEMORY_MANAGER_ON_WRITE: Callable[..., Any] | None = None
_ORIGINAL_HOLOGRAPHIC_FACT_STORE: Callable[..., str] | None = None
_ORIGINAL_HOLOGRAPHIC_SYSTEM_PROMPT: Callable[..., str] | None = None

_EXPLICIT_SAVE_RE = re.compile(
    r"\b(remember|save|store|keep this|note this)\b|记住|记一下|长期记|保存",
    re.I,
)

_PROJECT_DECISION_PATTERNS = (
    re.compile(r"\bwe\s+(?:decided|agreed|chose)\s+(?:to\s+)?(.+)", re.I),
    re.compile(r"\bthe\s+project\s+(?:uses|needs|requires)\s+(.+)", re.I),
    re.compile(r"(项目|工程|仓库).{0,20}(使用|需要|依赖|选择|决定)"),
)

ROUTING_CONTEXT = (
    "[Life memory routing]\n"
    "- Use life_memory_store for L4 non-technical life memories: routines, habits, "
    "food/lifestyle preferences, relationships, life events, and repeated personal patterns.\n"
    "- Use the built-in memory tool only for L2 technical/project/environment memories "
    "or L3 stable user-profile instructions such as response style, language, name, role, and timezone.\n"
    "- Sensitive life details such as precise home address may be saved for this personal agent only "
    "through life_memory_store, with explicit confirmation and sensitive metadata.\n"
    "- If a memory tool returns needs_confirmation or declined, do not retry through another memory route. "
    "Ask the user what to save: do_not_store, store_summary, or store_full.\n"
    "- Do not save temporary task state, one-off emotions, task progress logs, or trivial facts."
)

BUILTIN_MEMORY_DESCRIPTION = (
    "Save durable technical/project memory or stable user-profile instructions that survive "
    "across sessions. This built-in memory is for L2 technical/project/environment facts "
    "and L3 profile facts only.\n\n"
    "ROUTING RULES:\n"
    "- Use target='memory' for technical/project/environment facts: codebase structure, "
    "runtime setup, dependencies, debugging history, workflows, tool quirks, project decisions.\n"
    "- Use target='user' for stable user profile: name, role, timezone, response style, "
    "language preference, formatting requirements, long-term working preferences.\n"
    "- Do NOT use this tool for L4 life memories such as daily routines, food/lifestyle "
    "preferences, relationships, life events, sleep/exercise habits, or personal patterns. "
    "Use life_memory_store for those.\n"
    "- Do NOT save temporary task state, completed-work logs, one-off emotions, or trivial facts.\n\n"
    "If sensitive life information needs confirmation or is declined by life_memory_store, do not "
    "retry it through this built-in memory tool. Ask the user for explicit confirmation instead.\n\n"
    "If you accidentally call this tool with a life-memory candidate, the installed "
    "life_memory router will divert it to life_memory_store."
)


@dataclass(frozen=True, slots=True)
class MemoryRouteDecision:
    classification: MemoryClassification
    destination: str
    target: str | None
    reason: str
    confidence: float

    @property
    def should_use_builtin(self) -> bool:
        return self.destination in {DESTINATION_BUILTIN_MEMORY, DESTINATION_BUILTIN_USER}


def decide_memory_route(content: str, *, target: str = "memory") -> MemoryRouteDecision:
    """Classify a memory write and choose its storage destination."""
    decision = classify_candidate(
        content,
        explicit_user_request=_has_explicit_save_intent(content),
    )
    classification = decision.classification
    if classification is MemoryClassification.TECHNICAL_MEMORY:
        return MemoryRouteDecision(
            classification=classification,
            destination=DESTINATION_BUILTIN_MEMORY,
            target="memory",
            reason=decision.reason,
            confidence=decision.confidence,
        )
    if classification is MemoryClassification.USER_PROFILE:
        return MemoryRouteDecision(
            classification=classification,
            destination=DESTINATION_BUILTIN_USER,
            target="user",
            reason=decision.reason,
            confidence=decision.confidence,
        )
    if classification is MemoryClassification.LIFE_MEMORY:
        return MemoryRouteDecision(
            classification=classification,
            destination=DESTINATION_LIFE_MEMORY,
            target=None,
            reason=decision.reason,
            confidence=decision.confidence,
        )
    return MemoryRouteDecision(
        classification=classification,
        destination=DESTINATION_SKIP,
        target=target if target in {"memory", "user"} else None,
        reason=decision.reason,
        confidence=decision.confidence,
    )


def route_memory_tool_call(
    *,
    action: str,
    target: str = "memory",
    content: str | None = None,
    old_text: str | None = None,
    store: Any = None,
    original_memory_tool: Callable[..., str],
    store_handler: Callable[[dict[str, Any]], str] | None = None,
) -> str:
    """Route a built-in memory tool call without changing Hermes core code."""
    if action not in {"add", "replace"} or not content:
        return original_memory_tool(
            action=action,
            target=target,
            content=content,
            old_text=old_text,
            store=store,
        )

    route = decide_memory_route(content, target=target)
    if route.destination == DESTINATION_LIFE_MEMORY:
        return _route_to_life_memory_store(
            content,
            route=route,
            store_handler=store_handler,
            source="memory_router",
            source_ref="built_in_memory_tool",
        )
    if route.destination == DESTINATION_SKIP:
        return _declined_tool_result(route)

    return original_memory_tool(
        action=action,
        target=route.target or target,
        content=content,
        old_text=old_text,
        store=store,
    )


def install_memory_routing(ctx: Any, store_handler: Callable[[dict[str, Any]], str]) -> dict[str, bool]:
    """Install all available runtime routing patches.

    Failures are logged and treated as no-op so the plugin remains usable even
    if a future Hermes release moves an internal module.
    """
    global _STORE_HANDLER
    _STORE_HANDLER = store_handler
    installed = {
        "prompt_hook": _install_prompt_hook(ctx),
        "memory_schema": _patch_builtin_memory_schema(),
        "memory_tool": _patch_builtin_memory_tool(),
        "memory_manager": _patch_memory_manager_mirror(),
        "holographic": _patch_holographic_provider(),
        "background_review": _patch_background_review_prompt(),
    }
    return installed


def _install_prompt_hook(ctx: Any) -> bool:
    if not hasattr(ctx, "register_hook"):
        return False

    def inject_routing_context(**kwargs: Any) -> dict[str, str]:
        context = ROUTING_CONTEXT
        try:
            activation = build_activation_context(kwargs)
            activation_context = activation.get("context") if isinstance(activation, dict) else ""
            if activation_context:
                context = f"{context}\n\n{activation_context}"
        except Exception as exc:
            logger.debug("life memory activation hook failed closed: %s", exc)
        return {"context": context}

    try:
        ctx.register_hook("pre_llm_call", inject_routing_context)
        return True
    except Exception as exc:
        logger.debug("life memory routing prompt hook unavailable: %s", exc)
        return False


def _patch_builtin_memory_schema() -> bool:
    try:
        from tools import memory_tool as memory_mod
        from tools.registry import registry
    except Exception as exc:
        logger.debug("Hermes memory schema unavailable for routing patch: %s", exc)
        return False

    try:
        schema = getattr(memory_mod, "MEMORY_SCHEMA", None)
        if isinstance(schema, dict):
            schema["description"] = BUILTIN_MEMORY_DESCRIPTION
            props = schema.get("parameters", {}).get("properties", {})
            if isinstance(props, dict) and isinstance(props.get("content"), dict):
                props["content"]["description"] = (
                    "Entry content. Required for add/replace. The life_memory router "
                    "will divert L4 life-memory candidates away from built-in memory."
                )

        entry = registry.get_entry("memory")
        if entry is not None and isinstance(schema, dict):
            entry.schema = schema
            entry.description = BUILTIN_MEMORY_DESCRIPTION
            try:
                registry._generation += 1
            except Exception:
                pass
        _clear_model_tool_cache()
        return True
    except Exception as exc:
        logger.debug("Failed to patch Hermes memory schema: %s", exc)
        return False


def _patch_builtin_memory_tool() -> bool:
    global _ORIGINAL_MEMORY_TOOL
    try:
        from tools import memory_tool as memory_mod
    except Exception as exc:
        logger.debug("Hermes memory tool unavailable for routing patch: %s", exc)
        return False

    current = getattr(memory_mod, "memory_tool", None)
    if current is None:
        return False
    if getattr(current, "_life_memory_router_installed", False):
        return True

    _ORIGINAL_MEMORY_TOOL = current

    def routed_memory_tool(
        action: str,
        target: str = "memory",
        content: str | None = None,
        old_text: str | None = None,
        store: Any = None,
    ) -> str:
        original = _ORIGINAL_MEMORY_TOOL
        if original is None:
            return _error_result("Original Hermes memory tool is unavailable.")
        return route_memory_tool_call(
            action=action,
            target=target,
            content=content,
            old_text=old_text,
            store=store,
            original_memory_tool=original,
            store_handler=_STORE_HANDLER,
        )

    routed_memory_tool._life_memory_router_installed = True  # type: ignore[attr-defined]
    routed_memory_tool._life_memory_router_original = current  # type: ignore[attr-defined]
    memory_mod.memory_tool = routed_memory_tool
    return True


def _patch_memory_manager_mirror() -> bool:
    global _ORIGINAL_MEMORY_MANAGER_ON_WRITE
    try:
        from agent.memory_manager import MemoryManager
    except Exception as exc:
        logger.debug("Hermes MemoryManager unavailable for routing patch: %s", exc)
        return False

    current = getattr(MemoryManager, "on_memory_write", None)
    if current is None:
        return False
    if getattr(current, "_life_memory_router_installed", False):
        return True

    _ORIGINAL_MEMORY_MANAGER_ON_WRITE = current

    def routed_on_memory_write(
        self: Any,
        action: str,
        target: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> Any:
        if action in {"add", "replace"} and content:
            route = decide_memory_route(content, target=target)
            if route.destination in {DESTINATION_LIFE_MEMORY, DESTINATION_SKIP}:
                logger.debug(
                    "Skipping external memory mirror for %s classified as %s",
                    route.destination,
                    route.classification.value,
                )
                return None
        original = _ORIGINAL_MEMORY_MANAGER_ON_WRITE
        if original is None:
            return None
        return original(self, action, target, content, metadata=metadata)

    routed_on_memory_write._life_memory_router_installed = True  # type: ignore[attr-defined]
    routed_on_memory_write._life_memory_router_original = current  # type: ignore[attr-defined]
    MemoryManager.on_memory_write = routed_on_memory_write
    return True


def _patch_holographic_provider() -> bool:
    global _ORIGINAL_HOLOGRAPHIC_FACT_STORE, _ORIGINAL_HOLOGRAPHIC_SYSTEM_PROMPT
    try:
        from plugins.memory import holographic as holographic_mod
    except Exception as exc:
        logger.debug("Holographic memory provider unavailable for routing patch: %s", exc)
        return False

    provider_cls = getattr(holographic_mod, "HolographicMemoryProvider", None)
    if provider_cls is None:
        return False

    patched_any = False

    current_fact_store = getattr(provider_cls, "_handle_fact_store", None)
    if current_fact_store is not None and not getattr(current_fact_store, "_life_memory_router_installed", False):
        _ORIGINAL_HOLOGRAPHIC_FACT_STORE = current_fact_store

        def routed_fact_store(self: Any, args: dict[str, Any]) -> str:
            action = args.get("action")
            content = str(args.get("content") or "").strip()
            if action == "add" and content:
                route = decide_memory_route(content, target="memory")
                if route.destination == DESTINATION_LIFE_MEMORY:
                    return _route_to_life_memory_store(
                        content,
                        route=route,
                        store_handler=_STORE_HANDLER,
                        source="memory_router",
                        source_ref="holographic_fact_store",
                    )
                if route.destination == DESTINATION_SKIP:
                    return _declined_tool_result(route)
            original = _ORIGINAL_HOLOGRAPHIC_FACT_STORE
            if original is None:
                return _error_result("Original holographic fact_store handler is unavailable.")
            return original(self, args)

        routed_fact_store._life_memory_router_installed = True  # type: ignore[attr-defined]
        routed_fact_store._life_memory_router_original = current_fact_store  # type: ignore[attr-defined]
        provider_cls._handle_fact_store = routed_fact_store
        patched_any = True

    current_auto = getattr(provider_cls, "_auto_extract_facts", None)
    if current_auto is not None and not getattr(current_auto, "_life_memory_router_installed", False):

        def routed_auto_extract(self: Any, messages: list[dict[str, Any]]) -> None:
            _auto_extract_project_facts_only(self, messages)

        routed_auto_extract._life_memory_router_installed = True  # type: ignore[attr-defined]
        routed_auto_extract._life_memory_router_original = current_auto  # type: ignore[attr-defined]
        provider_cls._auto_extract_facts = routed_auto_extract
        patched_any = True

    current_prompt = getattr(provider_cls, "system_prompt_block", None)
    if current_prompt is not None and not getattr(current_prompt, "_life_memory_router_installed", False):
        _ORIGINAL_HOLOGRAPHIC_SYSTEM_PROMPT = current_prompt

        def routed_system_prompt(self: Any) -> str:
            original = _ORIGINAL_HOLOGRAPHIC_SYSTEM_PROMPT
            text = original(self) if original else ""
            if not text:
                return text
            return (
                text.replace(
                    "Use fact_store(action='add') to store durable structured facts about people, projects, preferences, decisions.",
                    "Use fact_store(action='add') for durable technical/project/profile facts. Use life_memory_store for ordinary life preferences, routines, relationships, and lifestyle context.",
                )
                .replace(
                    "Use fact_store to search, probe entities, reason across entities, or add facts.",
                    "Use fact_store to search, probe entities, reason across entities, or add technical/project/profile facts. Use life_memory_store for L4 life memories.",
                )
            )

        routed_system_prompt._life_memory_router_installed = True  # type: ignore[attr-defined]
        routed_system_prompt._life_memory_router_original = current_prompt  # type: ignore[attr-defined]
        provider_cls.system_prompt_block = routed_system_prompt
        patched_any = True

    _patch_holographic_schemas(holographic_mod)
    return patched_any


def _patch_holographic_schemas(holographic_mod: Any) -> None:
    schema = getattr(holographic_mod, "FACT_STORE_SCHEMA", None)
    if not isinstance(schema, dict):
        return
    schema["description"] = (
        "Deep structured memory for technical/project/profile facts. "
        "Use fact_store for project decisions, environment facts, tool configuration, "
        "workflow facts, and stable user-profile facts. Do not use it for ordinary "
        "life memories such as routines, food/lifestyle preferences, relationships, "
        "life events, or personal behavior patterns; use life_memory_store for those."
    )


def _patch_background_review_prompt() -> bool:
    prompt = (
        "Review the conversation above and consider saving durable memory if appropriate.\n\n"
        "Use the layered routing policy:\n"
        "1. L2 technical/project/environment facts and L3 stable user-profile instructions may be saved through the memory tool.\n"
        "2. L4 life memories such as routines, habits, relationships, non-technical preferences, life events, and personal patterns must be routed to life memory; if only the memory tool is available, call memory with the compact candidate and the installed router will divert it.\n"
        "3. Sensitive L4 details such as precise home address may be saved for this personal agent only after explicit confirmation and must not be routed around life_memory_store.\n"
        "4. If a memory write returns needs_confirmation or declined, ask the user for confirmation instead of retrying through another memory route.\n"
        "5. Do not save temporary task state, completed-work logs, one-off emotions, or trivial facts.\n\n"
        "If nothing is worth saving, just say 'Nothing to save.' and stop."
    )
    patched = False
    try:
        from agent import background_review as background_review_mod

        background_review_mod._MEMORY_REVIEW_PROMPT = prompt
        patched = True
    except Exception as exc:
        logger.debug("Background review module unavailable for routing patch: %s", exc)

    try:
        import run_agent

        agent_cls = getattr(run_agent, "AIAgent", None)
        if agent_cls is not None:
            agent_cls._MEMORY_REVIEW_PROMPT = prompt
            patched = True
    except Exception as exc:
        logger.debug("AIAgent class unavailable for routing prompt patch: %s", exc)
    return patched


def _auto_extract_project_facts_only(provider: Any, messages: list[dict[str, Any]]) -> None:
    store = getattr(provider, "_store", None)
    if store is None:
        return
    extracted = 0
    for msg in messages:
        if msg.get("role") != "user":
            continue
        content = msg.get("content", "")
        if not isinstance(content, str) or len(content) < 10:
            continue
        for sentence in _split_sentences(content):
            if len(sentence) < 10:
                continue
            if not any(pattern.search(sentence) for pattern in _PROJECT_DECISION_PATTERNS):
                continue
            route = decide_memory_route(sentence, target="memory")
            if route.destination != DESTINATION_BUILTIN_MEMORY:
                continue
            try:
                store.add_fact(sentence[:400], category="project")
                extracted += 1
            except Exception:
                pass
    if extracted:
        logger.info("Auto-extracted %d routed project facts from conversation", extracted)


def _split_sentences(content: str) -> list[str]:
    return [
        item.strip()
        for item in re.split(r"(?<=[.!?。！？；;])\s+|[。！？；;]\s*", content)
        if item.strip()
    ]


def _route_to_life_memory_store(
    content: str,
    *,
    route: MemoryRouteDecision,
    store_handler: Callable[[dict[str, Any]], str] | None,
    source: str,
    source_ref: str,
) -> str:
    if store_handler is None:
        return _error_result("life_memory_store handler is unavailable.")
    payload = {
        "content": content,
        "explicit_user_request": _has_explicit_save_intent(content),
        "source": source,
        "source_ref": source_ref,
        "context": {
            "routed_from": source_ref,
            "classification": route.classification.value,
            "route_reason": route.reason,
        },
    }
    try:
        raw = store_handler(payload)
        return _annotate_result(raw, route=route)
    except Exception as exc:
        logger.exception("life memory routed store failed")
        return _error_result(f"life_memory_store routing failed: {exc}")


def _annotate_result(raw: str, *, route: MemoryRouteDecision) -> str:
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return raw
    if not isinstance(data, dict):
        return raw
    data["routed_by"] = ROUTER_NAME
    data["routed_to"] = DESTINATION_LIFE_MEMORY
    data["classification"] = route.classification.value
    data["route_reason"] = route.reason
    return json_dumps(data)


def _declined_tool_result(route: MemoryRouteDecision) -> str:
    return json_dumps(
        {
            "success": False,
            "ok": False,
            "outcome": "declined",
            "routed_by": ROUTER_NAME,
            "routed_to": DESTINATION_SKIP,
            "classification": route.classification.value,
            "classification_confidence": route.confidence,
            "reason": route.reason,
            "message": "Memory write declined by layered memory routing policy.",
            "trace_id": make_id("trace"),
        }
    )


def _error_result(message: str) -> str:
    return json_dumps(
        {
            "success": False,
            "ok": False,
            "outcome": "error",
            "routed_by": ROUTER_NAME,
            "message": message,
            "trace_id": make_id("trace"),
        }
    )


def _has_explicit_save_intent(content: str | None) -> bool:
    return bool(content and _EXPLICIT_SAVE_RE.search(content))


def _clear_model_tool_cache() -> None:
    try:
        import model_tools

        cache = getattr(model_tools, "_tool_defs_cache", None)
        if hasattr(cache, "clear"):
            cache.clear()
    except Exception:
        pass
