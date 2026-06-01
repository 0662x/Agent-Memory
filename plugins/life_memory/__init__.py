"""Hermes standalone plugin entrypoint for layered life memory."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any, Callable

from .classification import classify_candidate
from .contracts import TOOL_SCHEMAS, result_json
from .export_review import export_review_markdown
from .models import FeedbackType, LifecycleStatus, MemoryClassification, TraceOperation
from .reflection import normalize_reflection_mode, run_reflection
from .repository import LifeMemoryRepository
from .recall import rank_memories
from .safety import evaluate_store_safety, safe_content_for_storage
from .time_utils import clamp, content_hash, make_id, now_utc

PLUGIN_NAME = "life_memory"
TOOLSET_NAME = "life_memory"
DATABASE_FILENAME = "life_memory.db"
REVIEW_DIRNAME = "life_memory_review"


@dataclass(frozen=True, slots=True)
class RuntimePaths:
    hermes_home: Path
    database: Path
    review_dir: Path


def get_hermes_home() -> Path:
    raw = os.environ.get("HERMES_HOME")
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".hermes"


def get_runtime_paths(hermes_home: str | os.PathLike[str] | None = None) -> RuntimePaths:
    home = Path(hermes_home).expanduser() if hermes_home is not None else get_hermes_home()
    return RuntimePaths(
        hermes_home=home,
        database=home / DATABASE_FILENAME,
        review_dir=home / REVIEW_DIRNAME,
    )


def _placeholder(tool_name: str) -> str:
    return result_json(
        ok=False,
        outcome="error",
        message=f"{tool_name} is registered but its durable workflow is not implemented yet.",
        trace_id=make_id("trace"),
        tool=tool_name,
    )


def _args(args: dict[str, Any] | None, kwargs: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    if args:
        merged.update(args)
    merged.update(kwargs)
    return merged


def life_memory_store(args: dict[str, Any] | None = None, **kwargs: Any) -> str:
    payload = _args(args, kwargs)
    content = str(payload.get("content") or "").strip()
    if not content:
        return result_json(
            ok=False,
            outcome="error",
            message="content is required.",
            trace_id=make_id("trace"),
            tool="life_memory_store",
        )

    repo = LifeMemoryRepository()
    repo.initialize()
    decision = classify_candidate(
        content,
        explicit_user_request=bool(payload.get("explicit_user_request", False)),
        evidence_count=int(payload.get("evidence_count", 1) or 1),
        category_hint=payload.get("category_hint"),
        tags=payload.get("tags") or (),
        source=payload.get("source"),
        source_ref=payload.get("source_ref"),
        context=payload.get("context") or {},
    )
    safety = evaluate_store_safety(
        content,
        explicit_user_request=bool(payload.get("explicit_user_request", False)),
    )

    if safety.outcome == "declined":
        trace_id = repo.record_declined_store_trace(
            content=content,
            reason=safety.reason,
            outcome="declined",
            classification=decision.classification.value,
            sensitivity=safety.sensitivity.value,
        )
        return result_json(
            ok=False,
            outcome="declined",
            classification=decision.classification.value,
            classification_confidence=decision.confidence,
            sensitivity=safety.sensitivity.value,
            injection_risk=safety.injection_risk,
            reason=safety.reason,
            message="Not stored in life memory.",
            trace_id=trace_id,
        )

    if decision.classification is not MemoryClassification.LIFE_MEMORY:
        trace_id = repo.append_trace(
            operation=TraceOperation.CLASSIFY,
            actor="plugin",
            reason=decision.reason,
            input_text=content,
            after={
                "outcome": "declined",
                "classification": decision.classification.value,
                "classification_confidence": decision.confidence,
            },
        )
        return result_json(
            ok=False,
            outcome="declined",
            classification=decision.classification.value,
            classification_confidence=decision.confidence,
            reason=decision.reason,
            message="Not stored in life memory.",
            trace_id=trace_id,
        )

    if safety.outcome == "needs_confirmation":
        trace_id = repo.record_declined_store_trace(
            content=content,
            reason=safety.reason,
            outcome="needs_confirmation",
            classification=decision.classification.value,
            sensitivity=safety.sensitivity.value,
        )
        return result_json(
            ok=False,
            outcome="needs_confirmation",
            classification=decision.classification.value,
            classification_confidence=decision.confidence,
            sensitivity=safety.sensitivity.value,
            message=(
                "This looks like sensitive life information. Should I save it long-term? "
                "I recommend saving only a summary."
            ),
            confirmation_options=list(safety.confirmation_options),
            trace_id=trace_id,
        )

    explicit_user_request = bool(payload.get("explicit_user_request", False))
    source = str(payload.get("source") or ("user_explicit" if explicit_user_request else "assistant_tool"))
    source_ref = payload.get("source_ref")
    context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    stored_content = safe_content_for_storage(content, safety.sensitivity)
    tags = tuple(decision.tags)
    importance = clamp(payload.get("importance", 0.5))
    confidence = clamp(payload.get("confidence", 0.7))
    status, promotion_path, promotion_reason = _promotion_metadata(
        content=content,
        tags=tags,
        explicit_user_request=explicit_user_request,
        importance=importance,
        confidence=confidence,
    )
    valid_until = _valid_until_for_tags(tags)
    existing = repo.find_memory_by_content_hash(content_hash(stored_content))
    if existing is not None:
        trace_id = repo.append_trace(
            operation=TraceOperation.STORE,
            actor="plugin",
            reason="Duplicate life memory declined before insert.",
            memory_id=existing["memory_id"],
            input_text=content,
            after={"outcome": "duplicate", "existing_memory_id": existing["memory_id"]},
        )
        return result_json(
            ok=False,
            outcome="duplicate",
            memory_id=existing["memory_id"],
            classification=decision.classification.value,
            classification_confidence=decision.confidence,
            message="Duplicate life memory already exists.",
            trace_id=trace_id,
        )

    record = repo.create_memory(
        content=stored_content,
        classification=decision.classification.value,
        classification_reason=decision.reason,
        classification_confidence=decision.confidence,
        primary_category=decision.primary_category or "personal_fact",
        tags=tags,
        context=context,
        importance=importance,
        confidence=confidence,
        source=source,
        source_ref=str(source_ref) if source_ref else None,
        sensitivity=safety.sensitivity.value,
        injection_risk=safety.injection_risk,
        status=status,
        promotion_path=promotion_path,
        promotion_reason=promotion_reason,
        valid_until=valid_until,
    )
    return result_json(
        ok=True,
        outcome="success",
        memory_id=record["memory_id"],
        classification=decision.classification.value,
        classification_confidence=decision.confidence,
        status=status,
        primary_category=decision.primary_category,
        tags=list(decision.tags),
        sensitivity=safety.sensitivity.value,
        promotion_path=promotion_path,
        valid_until=valid_until,
        message="Stored life memory.",
        trace_id=record["trace_id"],
    )


def _promotion_metadata(
    *,
    content: str,
    tags: tuple[str, ...],
    explicit_user_request: bool,
    importance: float,
    confidence: float,
) -> tuple[str, str | None, str | None]:
    major_terms = ("moved to", "married", "had a child", "started a new job", "graduated", "live in")
    major = "major_life_fact" in tags or any(term in content.lower() for term in major_terms)
    if explicit_user_request and major and importance >= 0.8 and confidence >= 0.8:
        return "active", "major_life_fact", "Explicit stable major life fact."
    return "young", None, None


def _valid_until_for_tags(tags: tuple[str, ...]) -> str | None:
    if "recent_state" not in tags:
        return None
    return (now_utc() + timedelta(days=14)).isoformat(timespec="seconds")


def life_memory_recall(args: dict[str, Any] | None = None, **kwargs: Any) -> str:
    payload = _args(args, kwargs)
    query = str(payload.get("query") or "").strip()
    if not query:
        return result_json(
            ok=False,
            outcome="error",
            message="query is required.",
            trace_id=make_id("trace"),
            tool="life_memory_recall",
        )
    limit = max(1, min(int(payload.get("limit", 5) or 5), 20))
    categories = tuple(str(item) for item in (payload.get("categories") or ()) if str(item).strip())
    include_archived = bool(payload.get("include_archived", False))
    include_sensitive = bool(payload.get("include_sensitive", False))

    repo = LifeMemoryRepository()
    repo.initialize()
    candidates = repo.search_memories(
        query=query,
        limit=max(limit * 4, 20),
        categories=categories,
        include_archived=include_archived,
        include_sensitive=include_sensitive,
    )
    results = rank_memories(
        query,
        candidates,
        limit=limit,
        include_archived=include_archived,
        include_sensitive=include_sensitive,
    )
    memory_ids = [item["memory_id"] for item in results]
    repo.update_access(memory_ids)
    trace_id = repo.append_trace(
        operation=TraceOperation.RECALL,
        actor="plugin",
        reason=f"Recall query returned {len(results)} result(s).",
        input_text=query,
        after={"outcome": "success" if results else "not_found", "memory_ids": memory_ids},
    )

    if not results:
        return result_json(
            ok=True,
            outcome="not_found",
            query=query,
            results=[],
            message="No matching life memory found.",
            trace_id=trace_id,
        )
    return result_json(
        ok=True,
        outcome="success",
        query=query,
        results=results,
        message=f"Found {len(results)} relevant life memory.",
        trace_id=trace_id,
    )


def life_memory_feedback(args: dict[str, Any] | None = None, **kwargs: Any) -> str:
    payload = _args(args, kwargs)
    memory_id = str(payload.get("memory_id") or "").strip()
    feedback_type = str(payload.get("feedback_type") or "").strip()
    if not memory_id or not feedback_type:
        return result_json(
            ok=False,
            outcome="error",
            message="memory_id and feedback_type are required.",
            trace_id=make_id("trace"),
            tool="life_memory_feedback",
        )

    repo = LifeMemoryRepository()
    repo.initialize()
    memory = repo.get_memory(memory_id)
    if memory is None or memory["status"] == LifecycleStatus.DELETED.value:
        trace_id = repo.append_trace(
            operation=TraceOperation.FEEDBACK,
            actor="plugin",
            reason="Feedback target not found.",
            memory_id=memory_id,
            after={"outcome": "not_found", "feedback_type": feedback_type},
        )
        return result_json(
            ok=False,
            outcome="not_found",
            memory_id=memory_id,
            message="Memory not found.",
            trace_id=trace_id,
        )

    note = payload.get("note")
    note_text = str(note) if note is not None else None
    replacement = payload.get("replacement_content")
    replacement_text = str(replacement).strip() if replacement is not None else None
    target = payload.get("target_memory_id")
    target_id = str(target).strip() if target is not None else None

    if feedback_type == FeedbackType.DELETE.value:
        return _forget_by_id(repo, memory_id, reason=note_text or "Delete feedback requested.")

    if feedback_type in {FeedbackType.DUPLICATE.value, FeedbackType.MERGE.value}:
        if not target_id:
            trace_id = repo.append_trace(
                operation=TraceOperation.FEEDBACK,
                actor="plugin",
                reason="Duplicate or merge feedback requires target_memory_id.",
                memory_id=memory_id,
                after={"outcome": "ambiguous", "feedback_type": feedback_type},
            )
            return result_json(
                ok=False,
                outcome="ambiguous",
                memory_id=memory_id,
                message="Please provide target_memory_id for duplicate or merge feedback.",
                trace_id=trace_id,
            )
        if repo.get_memory(target_id) is None:
            trace_id = repo.append_trace(
                operation=TraceOperation.FEEDBACK,
                actor="plugin",
                reason="Feedback target_memory_id not found.",
                memory_id=memory_id,
                after={"outcome": "not_found", "target_memory_id": target_id},
            )
            return result_json(
                ok=False,
                outcome="not_found",
                memory_id=target_id,
                message="Target memory not found.",
                trace_id=trace_id,
            )
        repo.record_feedback(
            memory_id=memory_id,
            feedback_type=feedback_type,
            note=note_text,
            target_memory_id=target_id,
        )
        if feedback_type == FeedbackType.DUPLICATE.value:
            repo.link_duplicate(memory_id, target_id, reason=note_text or "User marked duplicate.")
            repo.adjust_feedback_score(memory_id, -0.2)
            trace_id = repo.append_trace(
                operation=TraceOperation.FEEDBACK,
                actor="plugin",
                reason="Memory marked as duplicate.",
                memory_id=memory_id,
                after={"outcome": "duplicate", "target_memory_id": target_id},
            )
            return result_json(
                ok=True,
                outcome="duplicate",
                memory_id=memory_id,
                target_memory_id=target_id,
                message="Duplicate feedback recorded.",
                trace_id=trace_id,
            )
        repo.merge_memory(memory_id, target_id, reason=note_text or "User requested merge.")
        trace_id = repo.append_trace(
            operation=TraceOperation.MERGE,
            actor="plugin",
            reason="Memory merged into target.",
            memory_id=memory_id,
            after={"outcome": "merged", "target_memory_id": target_id},
        )
        return result_json(
            ok=True,
            outcome="merged",
            memory_id=memory_id,
            target_memory_id=target_id,
            message="Memory marked as merged.",
            trace_id=trace_id,
        )

    if feedback_type in {FeedbackType.USEFUL.value, FeedbackType.IMPORTANT.value}:
        delta = 0.2 if feedback_type == FeedbackType.USEFUL.value else 0.35
        repo.record_feedback(memory_id=memory_id, feedback_type=feedback_type, note=note_text)
        repo.adjust_feedback_score(memory_id, delta)
        repo.update_memory_status(memory_id, status=LifecycleStatus.REINFORCED)
        trace_id = repo.append_trace(
            operation=TraceOperation.REINFORCE,
            actor="plugin",
            reason=f"{feedback_type} feedback reinforced memory.",
            memory_id=memory_id,
            after={"outcome": "success", "status": LifecycleStatus.REINFORCED.value},
        )
        return result_json(
            ok=True,
            outcome="success",
            memory_id=memory_id,
            status=LifecycleStatus.REINFORCED.value,
            message="Feedback recorded.",
            trace_id=trace_id,
        )

    if feedback_type in {FeedbackType.WRONG.value, FeedbackType.OUTDATED.value}:
        if replacement_text:
            replacement_result = _create_replacement_memory(
                repo,
                replacement_text,
                source_ref=f"feedback:{memory_id}",
            )
            if replacement_result["outcome"] != "success":
                return result_json(
                    ok=False,
                    outcome=replacement_result["outcome"],
                    memory_id=memory_id,
                    message=replacement_result["message"],
                    trace_id=replacement_result["trace_id"],
                )
            replacement_id = replacement_result["memory_id"]
            repo.record_feedback(
                memory_id=memory_id,
                feedback_type=feedback_type,
                note=note_text,
                replacement_content=replacement_text,
                target_memory_id=replacement_id,
            )
            repo.adjust_feedback_score(memory_id, -0.4)
            repo.supersede_memory(
                memory_id,
                replacement_id,
                reason=note_text or f"User marked memory {feedback_type} and supplied replacement.",
            )
            trace_id = repo.append_trace(
                operation=TraceOperation.SUPERSEDE,
                actor="plugin",
                reason="Memory corrected and superseded.",
                memory_id=memory_id,
                after={
                    "outcome": "success",
                    "replacement_memory_id": replacement_id,
                    "relation": "superseded_by",
                },
            )
            return result_json(
                ok=True,
                outcome="success",
                memory_id=memory_id,
                replacement_memory_id=replacement_id,
                relation="superseded_by",
                message="Memory corrected and superseded.",
                trace_id=trace_id,
            )

        repo.record_feedback(memory_id=memory_id, feedback_type=feedback_type, note=note_text)
        repo.adjust_feedback_score(memory_id, -0.3)
        repo.update_memory_status(
            memory_id,
            status=LifecycleStatus.ARCHIVED,
            decay_reason=feedback_type,
        )
        trace_id = repo.append_trace(
            operation=TraceOperation.ARCHIVE,
            actor="plugin",
            reason=f"Memory marked {feedback_type}.",
            memory_id=memory_id,
            after={"outcome": "archived", "status": LifecycleStatus.ARCHIVED.value},
        )
        return result_json(
            ok=True,
            outcome="archived",
            memory_id=memory_id,
            status=LifecycleStatus.ARCHIVED.value,
            message="Memory archived based on feedback.",
            trace_id=trace_id,
        )

    trace_id = repo.append_trace(
        operation=TraceOperation.FEEDBACK,
        actor="plugin",
        reason="Unsupported feedback_type.",
        memory_id=memory_id,
        after={"outcome": "error", "feedback_type": feedback_type},
    )
    return result_json(
        ok=False,
        outcome="error",
        memory_id=memory_id,
        message="Unsupported feedback_type.",
        trace_id=trace_id,
    )


def life_memory_forget(args: dict[str, Any] | None = None, **kwargs: Any) -> str:
    payload = _args(args, kwargs)
    memory_id = str(payload.get("memory_id") or "").strip()
    query = str(payload.get("query") or "").strip()
    reason = str(payload.get("reason") or "User requested forget.")
    confirm = bool(payload.get("confirm", False))

    if not memory_id and not query:
        return result_json(
            ok=False,
            outcome="error",
            message="memory_id or query is required.",
            trace_id=make_id("trace"),
            tool="life_memory_forget",
        )

    repo = LifeMemoryRepository()
    repo.initialize()
    if memory_id:
        return _forget_by_id(repo, memory_id, reason=reason)

    candidates = repo.search_memories(
        query=query,
        limit=10,
        include_archived=False,
        include_sensitive=True,
    )
    ranked = rank_memories(query, candidates, limit=10, include_sensitive=True)
    if not ranked:
        trace_id = repo.append_trace(
            operation=TraceOperation.FORGET,
            actor="plugin",
            reason="Forget query found no memory.",
            input_text=query,
            after={"outcome": "not_found"},
        )
        return result_json(
            ok=False,
            outcome="not_found",
            query=query,
            message="No matching memory found.",
            trace_id=trace_id,
        )

    if len(ranked) > 1 or not confirm:
        candidates_payload = [
            {"memory_id": item["memory_id"], "summary": item["content"][:120]}
            for item in ranked[:5]
        ]
        trace_id = repo.append_trace(
            operation=TraceOperation.FORGET,
            actor="plugin",
            reason="Forget query requires disambiguation or confirmation.",
            input_text=query,
            after={
                "outcome": "ambiguous",
                "candidate_ids": [item["memory_id"] for item in ranked[:5]],
            },
        )
        return result_json(
            ok=False,
            outcome="ambiguous",
            query=query,
            candidates=candidates_payload,
            message="Multiple or unconfirmed memories match. Please choose one memory_id.",
            trace_id=trace_id,
        )

    return _forget_by_id(repo, ranked[0]["memory_id"], reason=reason)


def _create_replacement_memory(
    repo: LifeMemoryRepository,
    content: str,
    *,
    source_ref: str,
) -> dict[str, Any]:
    decision = classify_candidate(content, explicit_user_request=True)
    safety = evaluate_store_safety(content, explicit_user_request=True)
    if decision.classification is not MemoryClassification.LIFE_MEMORY:
        trace_id = repo.record_declined_store_trace(
            content=content,
            reason=decision.reason,
            outcome="declined",
            classification=decision.classification.value,
            sensitivity=safety.sensitivity.value,
        )
        return {"outcome": "declined", "message": "Replacement is not a life memory.", "trace_id": trace_id}
    if not safety.allow_store:
        trace_id = repo.record_declined_store_trace(
            content=content,
            reason=safety.reason,
            outcome=safety.outcome,
            classification=decision.classification.value,
            sensitivity=safety.sensitivity.value,
        )
        return {"outcome": safety.outcome, "message": safety.reason, "trace_id": trace_id}

    stored_content = safe_content_for_storage(content, safety.sensitivity)
    existing = repo.find_memory_by_content_hash(content_hash(stored_content))
    if existing is not None:
        return {
            "outcome": "success",
            "memory_id": existing["memory_id"],
            "message": "Replacement matched existing memory.",
            "trace_id": make_id("trace"),
        }

    tags = tuple(decision.tags)
    status, promotion_path, promotion_reason = _promotion_metadata(
        content=content,
        tags=tags,
        explicit_user_request=True,
        importance=0.7,
        confidence=0.8,
    )
    record = repo.create_memory(
        content=stored_content,
        classification=decision.classification.value,
        classification_reason=decision.reason,
        classification_confidence=decision.confidence,
        primary_category=decision.primary_category or "personal_fact",
        tags=tags,
        context={"source": "feedback_replacement"},
        importance=0.7,
        confidence=0.8,
        source="feedback",
        source_ref=source_ref,
        sensitivity=safety.sensitivity.value,
        injection_risk=safety.injection_risk,
        status=status,
        promotion_path=promotion_path,
        promotion_reason=promotion_reason,
        valid_until=_valid_until_for_tags(tags),
    )
    return {
        "outcome": "success",
        "memory_id": record["memory_id"],
        "message": "Replacement memory stored.",
        "trace_id": record["trace_id"],
    }


def _forget_by_id(repo: LifeMemoryRepository, memory_id: str, *, reason: str) -> str:
    trace_id = repo.delete_memory(memory_id, reason=reason)
    if trace_id is None:
        trace_id = repo.append_trace(
            operation=TraceOperation.FORGET,
            actor="plugin",
            reason="Forget target not found.",
            memory_id=memory_id,
            after={"outcome": "not_found"},
        )
        return result_json(
            ok=False,
            outcome="not_found",
            memory_id=memory_id,
            message="Memory not found.",
            trace_id=trace_id,
        )
    return result_json(
        ok=True,
        outcome="success",
        memory_id=memory_id,
        status=LifecycleStatus.DELETED.value,
        message="Memory forgotten.",
        trace_id=trace_id,
    )


def life_memory_reflect(args: dict[str, Any] | None = None, **kwargs: Any) -> str:
    payload = _args(args, kwargs)
    requested_mode = str(payload.get("mode") or "all")
    mode = normalize_reflection_mode(requested_mode)
    apply_changes = bool(payload.get("apply", False))
    try:
        limit = max(1, min(int(payload.get("limit", 20) or 20), 100))
    except (TypeError, ValueError):
        limit = 20
    session_ref = str(payload.get("session_ref") or "").strip() or None
    transcript = payload.get("transcript")
    time_window = payload.get("time_window") if isinstance(payload.get("time_window"), dict) else {}

    repo = LifeMemoryRepository()
    repo.initialize()

    if mode == "all":
        modes = ["light", "rem", "deep", "daily"]
        if session_ref or transcript:
            modes.insert(0, "session")
        results = [
            run_reflection(
                repo,
                mode=item,
                apply=apply_changes,
                limit=limit,
                session_ref=session_ref,
                transcript=transcript if item == "session" else None,
                time_window=time_window,
                hermes_home=str(get_hermes_home()),
            )
            for item in modes
        ]
        candidate_count = sum(int(item.get("candidate_count") or 0) for item in results)
        applied_count = sum(int(item.get("applied_count") or 0) for item in results)
        trace_id = repo.append_trace(
            operation=TraceOperation.REFLECT,
            actor="plugin",
            reason="All reflection modes completed.",
            after={
                "outcome": "success",
                "apply": apply_changes,
                "modes": modes,
                "run_ids": [item.get("run_id") for item in results],
                "candidate_count": candidate_count,
                "applied_count": applied_count,
            },
        )
        return result_json(
            ok=all(bool(item.get("ok")) for item in results),
            outcome="success",
            mode="all",
            apply=apply_changes,
            results=results,
            candidate_count=candidate_count,
            applied_count=applied_count,
            message="All reflection modes completed.",
            trace_id=trace_id,
        )

    result = run_reflection(
        repo,
        mode=mode,
        apply=apply_changes,
        limit=limit,
        session_ref=session_ref,
        transcript=transcript,
        time_window=time_window,
        hermes_home=str(get_hermes_home()),
    )
    return result_json(**result)


def life_memory_export_review(args: dict[str, Any] | None = None, **kwargs: Any) -> str:
    payload = _args(args, kwargs)
    paths = get_runtime_paths()
    target_raw = payload.get("target_dir")
    target_dir = Path(str(target_raw)).expanduser() if target_raw else paths.review_dir
    include_archive = bool(payload.get("include_archive", True))
    include_sensitive = str(payload.get("include_sensitive") or "summary_only")
    if include_sensitive not in {"none", "summary_only"}:
        return result_json(
            ok=False,
            outcome="error",
            message="include_sensitive must be 'none' or 'summary_only'.",
            trace_id=make_id("trace"),
            tool="life_memory_export_review",
        )

    repo = LifeMemoryRepository()
    repo.initialize()
    data = repo.export_review_data(
        include_archive=include_archive,
        include_sensitive=include_sensitive,
    )
    files = export_review_markdown(
        target_dir=target_dir,
        data=data,
        include_archive=include_archive,
        include_sensitive=include_sensitive,
    )
    trace_id = repo.write_export_trace(target_dir=str(target_dir), files=files)
    return result_json(
        ok=True,
        outcome="success",
        target_dir=str(target_dir),
        files=files,
        read_only=True,
        message="Exported read-only life memory review files.",
        trace_id=trace_id,
    )


_HANDLERS: dict[str, Callable[..., str]] = {
    "life_memory_store": life_memory_store,
    "life_memory_recall": life_memory_recall,
    "life_memory_feedback": life_memory_feedback,
    "life_memory_forget": life_memory_forget,
    "life_memory_reflect": life_memory_reflect,
    "life_memory_export_review": life_memory_export_review,
}


def register(ctx: Any) -> None:
    """Register life-memory tools with Hermes."""
    for name, handler in _HANDLERS.items():
        schema = TOOL_SCHEMAS[name]
        ctx.register_tool(
            name=name,
            toolset=TOOLSET_NAME,
            schema=schema,
            handler=handler,
            description=schema.get("description", ""),
        )
