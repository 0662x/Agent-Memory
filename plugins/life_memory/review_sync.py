"""Explicit Markdown change-request sync for life-memory review exports."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .classification import classify_candidate
from .models import FeedbackType, LifecycleStatus, MemoryClassification, ReviewStatus, Sensitivity, TraceOperation
from .recall import rank_memories
from .repository import LifeMemoryRepository
from .safety import evaluate_store_safety, safe_content_for_storage
from .time_utils import content_hash

CHANGE_BLOCK_LANGUAGE = "life-memory-change"
SUPPORTED_ACTIONS = {"delete", "replace", "merge", "confirm", "reject", "mark_outdated"}
DESTRUCTIVE_ACTIONS = {"delete", "replace", "merge", "reject", "mark_outdated"}
MAX_INLINE_CHARS = 100_000


@dataclass(slots=True)
class ReviewChangeRequest:
    request_id: str | None
    action: str | None
    target_memory_ids: tuple[str, ...] = ()
    target_query: str | None = None
    replacement_content: str | None = None
    merged_content: str | None = None
    reason: str | None = None
    confirm: bool = False
    source_path: str | None = None
    start_line: int = 0
    end_line: int = 0
    raw_hash: str | None = None
    errors: tuple[str, ...] = ()

    @property
    def is_valid(self) -> bool:
        return not self.errors and bool(self.request_id) and self.action in SUPPORTED_ACTIONS


@dataclass(slots=True)
class ReviewSyncActionResult:
    request_id: str | None
    action: str | None
    outcome: str
    target_memory_ids: list[str] = field(default_factory=list)
    created_memory_ids: list[str] = field(default_factory=list)
    trace_ids: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    line: int | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "request_id": self.request_id,
            "action": self.action,
            "outcome": self.outcome,
            "target_memory_ids": list(self.target_memory_ids),
            "created_memory_ids": list(self.created_memory_ids),
            "trace_ids": list(self.trace_ids),
            "warnings": list(self.warnings),
            "errors": list(self.errors),
        }
        if self.line is not None:
            result["line"] = self.line
        return result


@dataclass(slots=True)
class ReviewSyncPlan:
    apply: bool
    source_path: str | None
    source_hash: str
    actions: list[ReviewSyncActionResult]
    trace_id: str | None = None

    @property
    def summary(self) -> dict[str, int]:
        outcomes = {
            "parsed": len(self.actions),
            "planned": 0,
            "applied": 0,
            "invalid": 0,
            "ambiguous": 0,
            "needs_confirmation": 0,
            "declined": 0,
            "not_found": 0,
            "failed": 0,
        }
        for action in self.actions:
            if action.outcome in outcomes:
                outcomes[action.outcome] += 1
        return outcomes

    @property
    def outcome(self) -> str:
        summary = self.summary
        if summary["failed"]:
            return "failed"
        if summary["invalid"]:
            return "invalid"
        if summary["ambiguous"]:
            return "ambiguous"
        if summary["needs_confirmation"]:
            return "needs_confirmation"
        if summary["declined"]:
            return "declined"
        if summary["not_found"] and not summary["planned"] and not summary["applied"]:
            return "not_found"
        if self.apply and summary["applied"] > 0:
            return "applied"
        return "planned" if not self.apply else "applied"

    @property
    def ok(self) -> bool:
        return self.outcome in {"planned", "applied"}

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "outcome": self.outcome,
            "apply": self.apply,
            "source_path": self.source_path,
            "source_hash": self.source_hash,
            "summary": self.summary,
            "actions": [action.to_dict() for action in self.actions],
            "trace_id": self.trace_id,
        }


def load_change_request_text(
    *,
    review_dir: Path,
    source_file: str = "change-requests.md",
    change_requests_text: str | None = None,
) -> tuple[str, Path | None]:
    if change_requests_text is not None:
        text = str(change_requests_text)
        if len(text) > MAX_INLINE_CHARS:
            raise ValueError("change_requests_text is too large.")
        return text, None

    safe_source = Path(source_file)
    if safe_source.is_absolute() or ".." in safe_source.parts:
        raise ValueError("source_file must stay inside the review directory.")
    path = (review_dir / safe_source).resolve()
    root = review_dir.resolve()
    if root not in path.parents and path != root:
        raise ValueError("source_file must stay inside the review directory.")
    if not path.exists():
        raise FileNotFoundError(str(path))
    return path.read_text(encoding="utf-8"), path


def parse_review_change_requests(
    text: str,
    *,
    source_path: str | None = None,
    max_actions: int = 50,
) -> list[ReviewChangeRequest]:
    max_count = max(1, min(int(max_actions), 200))
    lines = text.splitlines()
    requests: list[ReviewChangeRequest] = []
    seen_ids: set[str] = set()
    index = 0
    while index < len(lines):
        if lines[index].strip() == f"```{CHANGE_BLOCK_LANGUAGE}":
            start = index + 1
            block_lines: list[str] = []
            index += 1
            while index < len(lines) and lines[index].strip() != "```":
                block_lines.append(lines[index])
                index += 1
            closed = index < len(lines)
            end = index + 1 if closed else len(lines)
            request = _parse_block(
                block_lines,
                source_path=source_path,
                start_line=start,
                end_line=end,
                closed=closed,
            )
            errors = list(request.errors)
            if request.request_id:
                if request.request_id in seen_ids:
                    errors.append(f"duplicate request id: {request.request_id}")
                seen_ids.add(request.request_id)
            if errors:
                request.errors = tuple(errors)
            requests.append(request)
            if len(requests) >= max_count:
                break
        index += 1
    return requests


def _parse_block(
    block_lines: list[str],
    *,
    source_path: str | None,
    start_line: int,
    end_line: int,
    closed: bool,
) -> ReviewChangeRequest:
    fields: dict[str, str] = {}
    errors: list[str] = []
    for offset, raw_line in enumerate(block_lines, start=start_line + 1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            errors.append(f"line {offset}: expected key: value")
            continue
        key, value = stripped.split(":", 1)
        fields[key.strip().lower()] = value.strip()
    if not closed:
        errors.append("missing closing fence")

    request_id = _clean(fields.get("id") or fields.get("request_id"))
    action = _clean(fields.get("action"))
    action = action.lower() if action else None
    if not request_id:
        errors.append("missing id")
    if not action:
        errors.append("missing action")
    elif action not in SUPPORTED_ACTIONS:
        errors.append(f"unsupported action: {action}")

    return ReviewChangeRequest(
        request_id=request_id,
        action=action,
        target_memory_ids=tuple(_parse_memory_ids(fields)),
        target_query=_clean(fields.get("query") or fields.get("target_query")),
        replacement_content=_clean(fields.get("replacement") or fields.get("replacement_content")),
        merged_content=_clean(fields.get("merged_content") or fields.get("merged") or fields.get("target_content")),
        reason=_clean(fields.get("reason") or fields.get("note")),
        confirm=_parse_bool(fields.get("confirm"), default=False),
        source_path=source_path,
        start_line=start_line,
        end_line=end_line,
        raw_hash=content_hash("\n".join(block_lines)),
        errors=tuple(errors),
    )


def _parse_memory_ids(fields: dict[str, str]) -> list[str]:
    values: list[str] = []
    if fields.get("memory_id"):
        values.append(fields["memory_id"].strip())
    raw_many = fields.get("memory_ids") or fields.get("target_memory_ids")
    if raw_many:
        text = raw_many.strip()
        if text.startswith("[") and text.endswith("]"):
            text = text[1:-1]
        for part in text.split(","):
            values.append(part.strip().strip('"').strip("'"))
    seen: set[str] = set()
    normalized: list[str] = []
    for value in values:
        if value and value not in seen:
            normalized.append(value)
            seen.add(value)
    return normalized


def _parse_bool(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"true", "yes", "y", "1", "confirmed"}


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def plan_review_sync(
    repo: LifeMemoryRepository,
    requests: list[ReviewChangeRequest],
    *,
    apply: bool = False,
    confirm_apply: bool = False,
    source_hash: str,
    source_path: str | None = None,
) -> ReviewSyncPlan:
    planned_pairs: list[tuple[ReviewChangeRequest | None, ReviewSyncActionResult]] = []
    for request in requests:
        if request.errors or not request.is_valid:
            planned_pairs.append((
                None,
                ReviewSyncActionResult(
                    request_id=request.request_id,
                    action=request.action,
                    outcome="invalid",
                    errors=list(request.errors or ("invalid request",)),
                    line=request.start_line or None,
                ),
            ))
            continue
        planned = _plan_one(repo, request, apply=apply, confirm_apply=confirm_apply)
        planned_pairs.append((request, planned))

    if apply and all(action.outcome == "planned" for _, action in planned_pairs):
        actions = [
            _apply_one(repo, request, action) if request is not None else action
            for request, action in planned_pairs
        ]
    else:
        actions = [action for _, action in planned_pairs]

    plan = ReviewSyncPlan(apply=apply, source_path=source_path, source_hash=source_hash, actions=actions)
    plan.trace_id = append_review_sync_trace(repo, plan)
    return plan


def _plan_one(
    repo: LifeMemoryRepository,
    request: ReviewChangeRequest,
    *,
    apply: bool,
    confirm_apply: bool,
) -> ReviewSyncActionResult:
    targets, target_error = _resolve_targets(repo, request)
    if target_error is not None:
        return target_error

    action = request.action or ""
    warnings: list[str] = []
    errors: list[str] = []
    target_ids = [str(memory["memory_id"]) for memory in targets]

    if action in DESTRUCTIVE_ACTIONS and not request.confirm:
        warnings.append("destructive action requires confirm: true before apply")
        if apply:
            return ReviewSyncActionResult(
                request_id=request.request_id,
                action=action,
                outcome="needs_confirmation",
                target_memory_ids=target_ids,
                warnings=warnings,
                line=request.start_line or None,
            )
    if action in DESTRUCTIVE_ACTIONS and apply and not confirm_apply:
        return ReviewSyncActionResult(
            request_id=request.request_id,
            action=action,
            outcome="needs_confirmation",
            target_memory_ids=target_ids,
            warnings=[*warnings, "apply mode requires confirm_apply: true"],
            line=request.start_line or None,
        )

    if action == "replace":
        if len(targets) != 1:
            errors.append("replace requires exactly one target memory")
        if not request.replacement_content:
            errors.append("replace requires replacement content")
        if not errors:
            validation = _validate_life_content(request.replacement_content or "", confirmed=request.confirm)
            if validation.outcome != "planned":
                return ReviewSyncActionResult(
                    request_id=request.request_id,
                    action=action,
                    outcome=validation.outcome,
                    target_memory_ids=target_ids,
                    warnings=warnings + validation.warnings,
                    errors=validation.errors,
                    line=request.start_line or None,
                )
            warnings.extend(validation.warnings)
    elif action == "merge":
        if len(targets) < 2:
            errors.append("merge requires at least two target memories")
        if not request.merged_content:
            errors.append("merge requires merged_content")
        if not errors:
            validation = _validate_life_content(request.merged_content or "", confirmed=request.confirm)
            if validation.outcome != "planned":
                return ReviewSyncActionResult(
                    request_id=request.request_id,
                    action=action,
                    outcome=validation.outcome,
                    target_memory_ids=target_ids,
                    warnings=warnings + validation.warnings,
                    errors=validation.errors,
                    line=request.start_line or None,
                )
            warnings.extend(validation.warnings)
    elif action in {"delete", "confirm", "reject", "mark_outdated"} and not targets:
        errors.append(f"{action} requires at least one target memory")

    if errors:
        return ReviewSyncActionResult(
            request_id=request.request_id,
            action=action,
            outcome="invalid",
            target_memory_ids=target_ids,
            warnings=warnings,
            errors=errors,
            line=request.start_line or None,
        )

    return ReviewSyncActionResult(
        request_id=request.request_id,
        action=action,
        outcome="planned",
        target_memory_ids=target_ids,
        warnings=warnings,
        line=request.start_line or None,
    )


@dataclass(slots=True)
class _ContentValidation:
    outcome: str = "planned"
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _validate_life_content(content: str, *, confirmed: bool) -> _ContentValidation:
    decision = classify_candidate(content, explicit_user_request=True)
    safety = evaluate_store_safety(content, explicit_user_request=True)
    if decision.classification is not MemoryClassification.LIFE_MEMORY:
        return _ContentValidation(outcome="declined", errors=["replacement content is not life memory"])
    if safety.sensitivity is Sensitivity.RESTRICTED:
        return _ContentValidation(outcome="declined", errors=["restricted raw content cannot be written through review sync"])
    if not safety.allow_store:
        return _ContentValidation(outcome=safety.outcome, errors=[safety.reason])
    warnings: list[str] = []
    if safety.sensitivity is Sensitivity.SENSITIVE and not confirmed:
        return _ContentValidation(
            outcome="needs_confirmation",
            warnings=["sensitive replacement content requires confirm: true"],
        )
    if safety.sensitivity is Sensitivity.SENSITIVE:
        warnings.append("sensitive replacement content will use existing sensitive storage rules")
    return _ContentValidation(warnings=warnings)


def _resolve_targets(
    repo: LifeMemoryRepository,
    request: ReviewChangeRequest,
) -> tuple[list[dict[str, Any]], ReviewSyncActionResult | None]:
    if request.target_memory_ids:
        targets: list[dict[str, Any]] = []
        missing: list[str] = []
        deleted: list[str] = []
        for memory_id in request.target_memory_ids:
            memory = repo.get_memory(memory_id)
            if memory is None:
                missing.append(memory_id)
            elif memory.get("status") == LifecycleStatus.DELETED.value:
                deleted.append(memory_id)
            else:
                targets.append(memory)
        if missing or deleted:
            return [], ReviewSyncActionResult(
                request_id=request.request_id,
                action=request.action,
                outcome="not_found",
                target_memory_ids=[*missing, *deleted],
                errors=["target memory not found or already deleted"],
                line=request.start_line or None,
            )
        return targets, None

    if request.target_query:
        candidates = repo.search_memories(
            query=request.target_query,
            limit=10,
            include_archived=True,
            include_sensitive=True,
        )
        ranked = rank_memories(request.target_query, candidates, limit=10, include_archived=True, include_sensitive=True)
        if not ranked:
            return [], ReviewSyncActionResult(
                request_id=request.request_id,
                action=request.action,
                outcome="not_found",
                errors=["query matched no memories"],
                line=request.start_line or None,
            )
        if len(ranked) > 1:
            return [], ReviewSyncActionResult(
                request_id=request.request_id,
                action=request.action,
                outcome="ambiguous",
                target_memory_ids=[str(item["memory_id"]) for item in ranked[:5]],
                errors=["query matched multiple memories; use exact memory_id"],
                line=request.start_line or None,
            )
        memory = repo.get_memory(str(ranked[0]["memory_id"]))
        return ([memory] if memory is not None else []), None

    return [], ReviewSyncActionResult(
        request_id=request.request_id,
        action=request.action,
        outcome="invalid",
        errors=["target memory_id, memory_ids, or query is required"],
        line=request.start_line or None,
    )


def _apply_one(
    repo: LifeMemoryRepository,
    request: ReviewChangeRequest,
    planned: ReviewSyncActionResult,
) -> ReviewSyncActionResult:
    action = request.action or ""
    target_ids = list(planned.target_memory_ids)
    trace_ids: list[str] = []
    created_ids: list[str] = []
    try:
        if action == "delete":
            for memory_id in target_ids:
                trace_id = repo.delete_memory(memory_id, reason=request.reason or "Review sync delete request.")
                if trace_id:
                    trace_ids.append(trace_id)
        elif action == "replace":
            replacement_id, trace_id = _create_review_memory(
                repo,
                request.replacement_content or "",
                source_ref=f"review_sync:{request.request_id}",
            )
            created_ids.append(replacement_id)
            trace_ids.append(trace_id)
            repo.record_feedback(
                memory_id=target_ids[0],
                feedback_type=FeedbackType.WRONG,
                note=request.reason,
                replacement_content=request.replacement_content,
                target_memory_id=replacement_id,
            )
            repo.adjust_feedback_score(target_ids[0], -0.4)
            repo.supersede_memory(target_ids[0], replacement_id, reason=request.reason or "Review sync replacement.")
        elif action == "merge":
            replacement_id, trace_id = _create_review_memory(
                repo,
                request.merged_content or "",
                source_ref=f"review_sync:{request.request_id}",
            )
            created_ids.append(replacement_id)
            trace_ids.append(trace_id)
            for memory_id in target_ids:
                repo.record_feedback(
                    memory_id=memory_id,
                    feedback_type=FeedbackType.MERGE,
                    note=request.reason,
                    target_memory_id=replacement_id,
                )
                repo.merge_memory(memory_id, replacement_id, reason=request.reason or "Review sync merge.")
        elif action == "confirm":
            for memory_id in target_ids:
                memory = repo.get_memory(memory_id)
                if memory is None:
                    continue
                repo.record_feedback(memory_id=memory_id, feedback_type=FeedbackType.USEFUL, note=request.reason)
                repo.adjust_feedback_score(memory_id, 0.15)
                repo.update_memory_status(
                    memory_id,
                    status=str(memory["status"]),
                    review_status=ReviewStatus.APPROVED,
                )
        elif action == "reject":
            for memory_id in target_ids:
                repo.record_feedback(memory_id=memory_id, feedback_type=FeedbackType.WRONG, note=request.reason)
                repo.adjust_feedback_score(memory_id, -0.3)
                repo.update_memory_status(
                    memory_id,
                    status=LifecycleStatus.ARCHIVED,
                    decay_reason="review_rejected",
                    review_status=ReviewStatus.REJECTED,
                )
        elif action == "mark_outdated":
            for memory_id in target_ids:
                repo.record_feedback(memory_id=memory_id, feedback_type=FeedbackType.OUTDATED, note=request.reason)
                repo.adjust_feedback_score(memory_id, -0.3)
                repo.update_memory_status(memory_id, status=LifecycleStatus.ARCHIVED, decay_reason="outdated")
        else:
            raise ValueError(f"Unsupported action: {action}")

        sync_trace = repo.append_trace(
            operation=TraceOperation.REVIEW_SYNC,
            actor="plugin",
            reason=f"Applied review sync action {action}.",
            after={
                "request_id": request.request_id,
                "action": action,
                "target_memory_ids": target_ids,
                "created_memory_ids": created_ids,
                "underlying_trace_ids": trace_ids,
            },
        )
        trace_ids.append(sync_trace)
        planned.outcome = "applied"
        planned.created_memory_ids = created_ids
        planned.trace_ids = trace_ids
        return planned
    except Exception as exc:  # pragma: no cover - defensive safety path
        return ReviewSyncActionResult(
            request_id=request.request_id,
            action=action,
            outcome="failed",
            target_memory_ids=target_ids,
            created_memory_ids=created_ids,
            trace_ids=trace_ids,
            warnings=planned.warnings,
            errors=[str(exc)],
            line=request.start_line or None,
        )


def _create_review_memory(repo: LifeMemoryRepository, content: str, *, source_ref: str) -> tuple[str, str]:
    decision = classify_candidate(content, explicit_user_request=True)
    safety = evaluate_store_safety(content, explicit_user_request=True)
    if decision.classification is not MemoryClassification.LIFE_MEMORY or not safety.allow_store:
        raise ValueError("Review sync content failed classification or safety gates.")
    if safety.sensitivity is Sensitivity.RESTRICTED:
        raise ValueError("Restricted raw content cannot be written through review sync.")
    stored_content = safe_content_for_storage(content, safety.sensitivity)
    existing = repo.find_memory_by_content_hash(content_hash(stored_content))
    if existing is not None:
        trace_id = repo.append_trace(
            operation=TraceOperation.REVIEW_SYNC,
            actor="plugin",
            reason="Review sync replacement matched existing memory.",
            memory_id=existing["memory_id"],
            after={"outcome": "duplicate", "memory_id": existing["memory_id"]},
        )
        return str(existing["memory_id"]), trace_id
    record = repo.create_memory(
        content=stored_content,
        classification=decision.classification.value,
        classification_reason=decision.reason,
        classification_confidence=decision.confidence,
        primary_category=decision.primary_category or "personal_fact",
        tags=decision.tags,
        context={"source": "review_sync"},
        importance=0.7,
        confidence=0.85,
        source="review_sync",
        source_ref=source_ref,
        sensitivity=safety.sensitivity.value,
        injection_risk=safety.injection_risk,
        status=LifecycleStatus.ACTIVE.value,
        review_status=ReviewStatus.APPROVED.value,
        valid_until=None,
    )
    return record["memory_id"], record["trace_id"]


def append_review_sync_trace(repo: LifeMemoryRepository, plan: ReviewSyncPlan) -> str:
    actions_payload = []
    for action in plan.actions:
        actions_payload.append(
            {
                "request_id": action.request_id,
                "action": action.action,
                "outcome": action.outcome,
                "target_memory_ids": action.target_memory_ids,
                "created_memory_ids": action.created_memory_ids,
                "warning_count": len(action.warnings),
                "error_count": len(action.errors),
            }
        )
    return repo.append_trace(
        operation=TraceOperation.REVIEW_SYNC,
        actor="plugin",
        reason="Review sync run completed.",
        after={
            "outcome": plan.outcome,
            "apply": plan.apply,
            "source_path": plan.source_path,
            "source_hash": plan.source_hash,
            "summary": plan.summary,
            "actions": actions_payload,
        },
    )


def run_review_sync(
    repo: LifeMemoryRepository,
    *,
    review_dir: Path,
    source_file: str = "change-requests.md",
    change_requests_text: str | None = None,
    apply: bool = False,
    confirm_apply: bool = False,
    max_actions: int = 50,
) -> ReviewSyncPlan:
    text, source_path = load_change_request_text(
        review_dir=review_dir,
        source_file=source_file,
        change_requests_text=change_requests_text,
    )
    source_hash = content_hash(text)
    requests = parse_review_change_requests(
        text,
        source_path=str(source_path) if source_path else None,
        max_actions=max_actions,
    )
    if not requests:
        plan = ReviewSyncPlan(
            apply=apply,
            source_path=str(source_path) if source_path else None,
            source_hash=source_hash,
            actions=[
                ReviewSyncActionResult(
                    request_id=None,
                    action=None,
                    outcome="not_found",
                    errors=["no life-memory-change request blocks found"],
                )
            ],
        )
        plan.trace_id = append_review_sync_trace(repo, plan)
        return plan
    return plan_review_sync(
        repo,
        requests,
        apply=apply,
        confirm_apply=confirm_apply,
        source_hash=source_hash,
        source_path=str(source_path) if source_path else None,
    )


def result_message(plan: ReviewSyncPlan) -> str:
    if plan.outcome == "planned":
        return "Review sync dry-run completed. No memory changes were applied."
    if plan.outcome == "applied":
        return "Review sync applied confirmed changes."
    if plan.outcome == "ambiguous":
        return "Review sync found ambiguous request targets. Use exact memory_id values."
    if plan.outcome == "needs_confirmation":
        return "Review sync requires explicit confirmation before applying destructive changes."
    if plan.outcome == "not_found":
        return "No review change requests or target memories were found."
    if plan.outcome == "declined":
        return "Review sync declined one or more unsafe change requests."
    return "Review sync could not complete because one or more requests were invalid."
