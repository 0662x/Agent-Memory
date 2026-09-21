from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Iterable

from .classification import classify_candidate
from .models import (
    EvidenceType,
    LifecycleStatus,
    MemoryClassification,
    MemoryKind,
    PromotionPath,
    ReflectionPhase,
    ReviewStatus,
    TraceOperation,
)
from .recall import tokenize
from .repository import LifeMemoryRepository
from .safety import evaluate_store_safety, safe_content_for_storage
from .session_adapter import HermesSessionAdapter, SessionMessage, SessionTranscript, SessionUnavailableError
from .time_utils import clamp, content_hash, now_iso, now_utc


@dataclass(frozen=True, slots=True)
class ReflectionCandidate:
    action: str
    reason: str
    memory_ids: tuple[str, ...] = ()
    content: str | None = None
    apply_safe: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "action": self.action,
            "reason": self.reason,
            "memory_ids": list(self.memory_ids),
            "apply_safe": self.apply_safe,
        }
        if self.content is not None:
            result["content"] = self.content
        if self.metadata:
            result["metadata"] = self.metadata
        return result


MODE_ALIASES = {
    "dedupe": ReflectionPhase.LIGHT.value,
    "decay": ReflectionPhase.LIGHT.value,
    "archive": ReflectionPhase.LIGHT.value,
    "merge": ReflectionPhase.REM.value,
    "patterns": ReflectionPhase.REM.value,
}


def normalize_reflection_mode(mode: str | None) -> str:
    normalized = str(mode or "all").strip().lower()
    return MODE_ALIASES.get(normalized, normalized)


def run_reflection(
    repo: LifeMemoryRepository,
    *,
    mode: str,
    apply: bool = False,
    limit: int = 20,
    session_ref: str | None = None,
    transcript: Iterable[dict[str, Any] | str] | str | None = None,
    time_window: dict[str, Any] | None = None,
    hermes_home: str | None = None,
) -> dict[str, Any]:
    phase = normalize_reflection_mode(mode)
    if phase not in {item.value for item in ReflectionPhase}:
        trace_id = repo.append_trace(
            operation=TraceOperation.REFLECT,
            actor="plugin",
            reason="Unsupported reflection mode.",
            after={"outcome": "error", "mode": mode},
        )
        return {
            "ok": False,
            "outcome": "error",
            "mode": mode,
            "apply": apply,
            "message": "Unsupported reflection mode.",
            "trace_id": trace_id,
        }

    bounded_limit = max(1, min(int(limit or 20), 100))
    input_window = {
        "mode": phase,
        "apply": bool(apply),
        "limit": bounded_limit,
        "session_ref": session_ref,
        "time_window": time_window or {},
        "has_transcript": transcript is not None,
    }
    run_id = repo.start_reflection_run(phase=phase, input_window=input_window)

    try:
        if phase == ReflectionPhase.LIGHT.value:
            payload = _reflect_light(repo, apply=apply, limit=bounded_limit, run_id=run_id)
        elif phase == ReflectionPhase.SESSION.value:
            payload = _reflect_session(
                repo,
                apply=apply,
                run_id=run_id,
                session_ref=session_ref,
                transcript=transcript,
                hermes_home=hermes_home,
            )
        elif phase == ReflectionPhase.REM.value:
            payload = _reflect_rem(repo, apply=apply, limit=bounded_limit, run_id=run_id)
        elif phase == ReflectionPhase.DEEP.value:
            payload = _reflect_deep(repo, apply=apply, limit=bounded_limit, run_id=run_id)
        else:
            payload = _reflect_daily(repo, run_id=run_id, limit=bounded_limit)
    except SessionUnavailableError as exc:
        repo.complete_reflection_run(
            run_id,
            candidate_count=0,
            applied_count=0,
            status="failed",
            notes=exc.reason,
        )
        trace_id = repo.append_trace(
            operation=TraceOperation.SESSION_EXTRACT,
            actor="plugin",
            reason="Session transcript unavailable.",
            after={"outcome": "not_found", "mode": phase, "session_ref": session_ref, "reason": exc.reason},
        )
        return {
            "ok": False,
            "outcome": "not_found",
            "mode": phase,
            "apply": apply,
            "run_id": run_id,
            "candidate_count": 0,
            "applied_count": 0,
            "candidates": [],
            "reports": [],
            "message": exc.reason,
            "trace_id": trace_id,
        }

    candidates = list(payload.get("candidates") or [])
    applied_count = int(payload.get("applied_count") or 0)
    report_ids = list(payload.get("report_ids") or [])
    report_path = f"reflection_reports:{report_ids[-1]}" if report_ids else None
    repo.complete_reflection_run(
        run_id,
        candidate_count=len(candidates),
        applied_count=applied_count,
        status="completed",
        report_path=report_path,
        notes=payload.get("notes"),
    )
    trace_id = repo.append_trace(
        operation=_trace_operation_for_phase(phase),
        actor="plugin",
        reason=f"{phase} reflection completed.",
        after={
            "outcome": "success",
            "mode": phase,
            "apply": bool(apply),
            "run_id": run_id,
            "candidate_count": len(candidates),
            "applied_count": applied_count,
            "report_ids": report_ids,
        },
    )
    return {
        "ok": True,
        "outcome": "success",
        "mode": phase,
        "apply": bool(apply),
        "run_id": run_id,
        "candidate_count": len(candidates),
        "applied_count": applied_count,
        "candidates": [candidate.to_dict() for candidate in candidates],
        "reports": report_ids,
        "message": payload.get("message") or f"{phase} reflection completed.",
        "trace_id": trace_id,
        **payload.get("extra", {}),
    }


def _reflect_light(repo: LifeMemoryRepository, *, apply: bool, limit: int, run_id: str) -> dict[str, Any]:
    memories = repo.list_reflection_memories(limit=limit)
    candidates: list[ReflectionCandidate] = []
    candidates.extend(_expired_recent_state_candidates(repo))
    candidates.extend(_tag_cleanup_candidates(memories))
    candidates.extend(_evidence_accounting_candidates(repo, memories))
    candidates.extend(_duplicate_candidates(memories))

    applied = 0
    archived_ids: list[str] = []
    linked_ids: list[str] = []
    if apply:
        for candidate in candidates:
            if candidate.action == "archive_recent_state":
                memory_id = candidate.memory_ids[0]
                repo.update_memory_status(
                    memory_id,
                    status=LifecycleStatus.ARCHIVED,
                    decay_reason="ttl_expired",
                    review_status=ReviewStatus.NEEDS_REVIEW,
                )
                repo.append_trace(
                    operation=TraceOperation.ARCHIVE,
                    actor="plugin",
                    reason=candidate.reason,
                    memory_id=memory_id,
                    after={"status": LifecycleStatus.ARCHIVED.value, "decay_reason": "ttl_expired"},
                )
                archived_ids.append(memory_id)
                applied += 1
            elif candidate.action == "tag_cleanup":
                repo.update_memory_tags(candidate.memory_ids[0], tuple(candidate.metadata.get("normalized_tags", [])))
                applied += 1
            elif candidate.action == "evidence_accounting":
                repo.refresh_memory_evidence_counts(candidate.memory_ids[0])
                applied += 1
            elif candidate.action == "duplicate_candidate" and len(candidate.memory_ids) == 2:
                link_id = repo.write_reflection_candidate_link(
                    from_memory_id=candidate.memory_ids[1],
                    to_memory_id=candidate.memory_ids[0],
                    relation="duplicate_candidate",
                    reason=candidate.reason,
                )
                linked_ids.append(link_id)
                applied += 1

    report_ids = _write_candidate_report(
        repo,
        report_type="light",
        title="Light Reflection",
        candidates=candidates,
        run_id=run_id,
    )
    return {
        "candidates": candidates,
        "applied_count": applied,
        "report_ids": report_ids,
        "message": "Light reflection completed.",
        "extra": {"archived_memory_ids": archived_ids, "candidate_link_ids": linked_ids},
    }


def _expired_recent_state_candidates(repo: LifeMemoryRepository) -> list[ReflectionCandidate]:
    return [
        ReflectionCandidate(
            action="archive_recent_state",
            memory_ids=(memory["memory_id"],),
            content=memory["content"],
            reason="recent_state memory passed valid_until and should be archived.",
            metadata={"valid_until": memory.get("valid_until")},
        )
        for memory in repo.list_expired_recent_state_memories()
    ]


def _tag_cleanup_candidates(memories: list[dict[str, Any]]) -> list[ReflectionCandidate]:
    candidates: list[ReflectionCandidate] = []
    for memory in memories:
        tags = list(memory.get("tags") or [])
        normalized = _normalize_tags(tags)
        if tags != normalized:
            candidates.append(
                ReflectionCandidate(
                    action="tag_cleanup",
                    memory_ids=(memory["memory_id"],),
                    reason="Tags can be normalized without changing memory meaning.",
                    metadata={"original_tags": tags, "normalized_tags": normalized},
                )
            )
    return candidates


def _evidence_accounting_candidates(
    repo: LifeMemoryRepository,
    memories: list[dict[str, Any]],
) -> list[ReflectionCandidate]:
    candidates: list[ReflectionCandidate] = []
    for memory in memories:
        counts = _read_evidence_counts(repo, memory["memory_id"])
        if counts is None:
            continue
        changed = any(int(memory.get(key) or 0) != value for key, value in counts.items())
        if changed:
            candidates.append(
                ReflectionCandidate(
                    action="evidence_accounting",
                    memory_ids=(memory["memory_id"],),
                    reason="Stored evidence counters differ from evidence rows.",
                    metadata={"expected": counts},
                )
            )
    return candidates


def _duplicate_candidates(memories: list[dict[str, Any]]) -> list[ReflectionCandidate]:
    candidates: list[ReflectionCandidate] = []
    active = [item for item in memories if item.get("status") != LifecycleStatus.ARCHIVED.value]
    for left_index, left in enumerate(active):
        for right in active[left_index + 1 :]:
            if left.get("primary_category") != right.get("primary_category"):
                continue
            score = _similarity(left.get("content", ""), right.get("content", ""))
            if score < 0.72:
                continue
            candidates.append(
                ReflectionCandidate(
                    action="duplicate_candidate",
                    memory_ids=(left["memory_id"], right["memory_id"]),
                    reason="Memories have high lexical overlap and may be duplicates.",
                    metadata={"similarity": round(score, 3)},
                )
            )
    return candidates


def _reflect_session(
    repo: LifeMemoryRepository,
    *,
    apply: bool,
    run_id: str,
    session_ref: str | None,
    transcript: Iterable[dict[str, Any] | str] | str | None,
    hermes_home: str | None,
) -> dict[str, Any]:
    adapter = HermesSessionAdapter(hermes_home=hermes_home)
    session = adapter.load(session_ref=session_ref, transcript=transcript)
    candidates = _session_candidates(session)

    applied = 0
    stored_ids: list[str] = []
    declined_count = 0
    if apply:
        for candidate in candidates:
            if candidate.action != "session_extract_candidate" or not candidate.apply_safe:
                declined_count += 1
                continue
            stored = _store_session_candidate(repo, candidate, session=session)
            if stored is None:
                declined_count += 1
                continue
            stored_ids.append(stored)
            applied += 1

    report_id = repo.write_reflection_report(
        report_type="session",
        report_date=now_iso()[:10],
        session_ids=[session.session_ref] if session.session_ref else [],
        content=_render_session_report(session, candidates, stored_ids),
        source_memory_ids=stored_ids,
        source_evidence_ids=[],
        created_by_run_id=run_id,
        review_status=ReviewStatus.PENDING,
    )
    return {
        "candidates": candidates,
        "applied_count": applied,
        "report_ids": [report_id],
        "message": "Session reflection completed.",
        "extra": {
            "session_ref": session.session_ref,
            "session_source": session.source,
            "stored_memory_ids": stored_ids,
            "declined_candidate_count": declined_count,
        },
    }


def _session_candidates(session: SessionTranscript) -> list[ReflectionCandidate]:
    candidates: list[ReflectionCandidate] = []
    seen_hashes: set[str] = set()
    for message in session.messages:
        if message.role not in {"user", "human", "unknown"}:
            continue
        for sentence in _candidate_sentences(message):
            hash_value = content_hash(sentence)
            if hash_value in seen_hashes:
                continue
            seen_hashes.add(hash_value)
            explicit = _explicit_store_requested(sentence)
            decision = classify_candidate(sentence, explicit_user_request=explicit, source="session_extract")
            safety = evaluate_store_safety(sentence, explicit_user_request=explicit)
            if decision.classification is MemoryClassification.LIFE_MEMORY and safety.allow_store:
                candidates.append(
                    ReflectionCandidate(
                        action="session_extract_candidate",
                        content=sentence,
                        reason=decision.reason,
                        apply_safe=True,
                        metadata={
                            "classification": decision.classification.value,
                            "primary_category": decision.primary_category,
                            "tags": list(decision.tags),
                            "source_ref": message.source_ref,
                            "sensitivity": safety.sensitivity.value,
                        },
                    )
                )
            else:
                candidates.append(
                    ReflectionCandidate(
                        action="declined_session_candidate",
                        content=sentence,
                        reason=safety.reason if not safety.allow_store else decision.reason,
                        apply_safe=False,
                        metadata={
                            "classification": decision.classification.value,
                            "source_ref": message.source_ref,
                            "sensitivity": safety.sensitivity.value,
                        },
                    )
                )
    return candidates


def _candidate_sentences(message: SessionMessage) -> tuple[str, ...]:
    parts = re.split(r"(?<=[.!?])\s+|[。！？]\s*|\n+", message.content)
    candidates = []
    for raw in parts:
        sentence = raw.strip(" -\t")
        if not sentence:
            continue
        lower = sentence.lower()
        if (
            re.search(r"\b(remember|save|store) that\b", lower)
            or re.search(r"\bi (?:prefer|usually|often|tend|like|love|live|moved|work|sleep)\b", lower)
            or re.search(r"\bmy (?:sister|brother|mother|father|partner|wife|husband|family|birthday)\b", lower)
            or re.search(r"\bthe user (?:prefers|usually|often|tends|lives|moved)\b", lower)
            or re.search(r"(记一下|记住|长期记|保存)", sentence)
            or re.search(r"(我通常|我一般|我经常|我往往|我偏好|我喜欢|我更喜欢|我住在|我搬到)", sentence)
            or re.search(r"我.{0,24}(通常|一般|经常|往往|习惯).{0,36}(接|送|照顾|陪|买|喝|吃|去|泡|做|安排|避开)", sentence)
            or re.search(r"我.{0,24}(每周|周[一二三四五六日天]).{0,36}(会|要|通常|一般|经常|习惯)", sentence)
            or re.search(r"我的(姐姐|妹妹|哥哥|弟弟|妈妈|爸爸|伴侣|妻子|丈夫|家人|朋友|侄女|侄子|外甥|外甥女|女儿|儿子|孩子)", sentence)
            or re.search(r"(侄女|侄子|外甥|外甥女|女儿|儿子|孩子).{0,24}(接|送|照顾|陪|上课|放学)", sentence)
            or re.search(r"(我希望以后|我以后想|我未来想|职业目标|长期目标|职业规划|想成为|想做[^。！？\n]{0,20}岗位)", sentence)
            or re.search(r"(不要长期记|不要保存|别保存)", sentence)
        ):
            candidates.append(sentence)
    return tuple(candidates)


def _explicit_store_requested(content: str) -> bool:
    return bool(re.search(r"\b(remember|save|store)\b", content, re.I) or re.search(r"(记一下|记住|长期记)", content))


def _store_session_candidate(
    repo: LifeMemoryRepository,
    candidate: ReflectionCandidate,
    *,
    session: SessionTranscript,
) -> str | None:
    content = str(candidate.content or "").strip()
    if not content:
        return None
    decision = classify_candidate(
        content,
        explicit_user_request=_explicit_store_requested(content),
        source="session_extract",
        source_ref=str(candidate.metadata.get("source_ref") or ""),
    )
    safety = evaluate_store_safety(
        content,
        explicit_user_request=_explicit_store_requested(content),
    )
    if decision.classification is not MemoryClassification.LIFE_MEMORY or not safety.allow_store:
        repo.record_declined_store_trace(
            content=content,
            reason=safety.reason if not safety.allow_store else decision.reason,
            outcome=safety.outcome if not safety.allow_store else "declined",
            classification=decision.classification.value,
            sensitivity=safety.sensitivity.value,
        )
        return None
    stored_content = safe_content_for_storage(content, safety.sensitivity)
    existing = repo.find_memory_by_content_hash(content_hash(stored_content))
    if existing is not None:
        return str(existing["memory_id"])
    tags = tuple(decision.tags)
    valid_until = _valid_until_for_tags(tags)
    record = repo.create_memory(
        content=stored_content,
        classification=decision.classification.value,
        classification_reason=decision.reason,
        classification_confidence=decision.confidence,
        primary_category=decision.primary_category or "personal_fact",
        tags=tags,
        context={
            "source": "session_reflection",
            "session_ref": session.session_ref,
            "transcript_source": session.source,
            "source_ref": candidate.metadata.get("source_ref"),
        },
        importance=0.55,
        confidence=0.72,
        source="session_extract",
        source_ref=str(candidate.metadata.get("source_ref") or session.session_ref or "explicit_transcript"),
        sensitivity=safety.sensitivity.value,
        injection_risk=safety.injection_risk,
        status=LifecycleStatus.YOUNG.value,
        valid_until=valid_until,
        authority="session_extract",
        evidence_type=EvidenceType.SESSION_EXTRACT,
    )
    repo.append_trace(
        operation=TraceOperation.SESSION_EXTRACT,
        actor="plugin",
        reason="Stored session extraction candidate.",
        memory_id=record["memory_id"],
        input_text=content,
        after={"outcome": "success", "session_ref": session.session_ref},
    )
    return str(record["memory_id"])


def _reflect_rem(repo: LifeMemoryRepository, *, apply: bool, limit: int, run_id: str) -> dict[str, Any]:
    memories = repo.list_reflection_memories(limit=limit)
    candidates = _conflict_candidates(memories) + _pattern_group_candidates(memories)
    applied = 0
    link_ids: list[str] = []
    pattern_ids: list[str] = []
    if apply:
        for candidate in candidates:
            if candidate.action == "conflict_candidate" and len(candidate.memory_ids) == 2:
                link_ids.append(
                    repo.write_reflection_candidate_link(
                        from_memory_id=candidate.memory_ids[0],
                        to_memory_id=candidate.memory_ids[1],
                        relation="conflict_candidate",
                        reason=candidate.reason,
                    )
                )
                for memory_id in candidate.memory_ids:
                    repo.update_memory_status(memory_id, status=LifecycleStatus.YOUNG, review_status=ReviewStatus.NEEDS_REVIEW)
                applied += 1
            elif candidate.action == "pattern_candidate":
                for memory_id in candidate.memory_ids:
                    memory = repo.get_memory(memory_id)
                    if memory is None or memory["status"] in {LifecycleStatus.DELETED.value, LifecycleStatus.ARCHIVED.value}:
                        continue
                    repo.update_memory_status(
                        memory_id,
                        status=LifecycleStatus.PATTERN_CANDIDATE,
                        review_status=ReviewStatus.NEEDS_REVIEW,
                    )
                    pattern_ids.append(memory_id)
                    applied += 1
                anchor = candidate.memory_ids[0] if candidate.memory_ids else None
                if anchor:
                    for memory_id in candidate.memory_ids[1:]:
                        link_ids.append(
                            repo.write_reflection_candidate_link(
                                from_memory_id=memory_id,
                                to_memory_id=anchor,
                                relation="supports_pattern_candidate",
                                reason=candidate.reason,
                            )
                        )
    report_ids = _write_candidate_report(
        repo,
        report_type="rem",
        title="REM Reflection",
        candidates=candidates,
        run_id=run_id,
    )
    return {
        "candidates": candidates,
        "applied_count": applied,
        "report_ids": report_ids,
        "message": "REM reflection completed.",
        "extra": {"candidate_link_ids": link_ids, "pattern_candidate_memory_ids": pattern_ids},
    }


def _conflict_candidates(memories: list[dict[str, Any]]) -> list[ReflectionCandidate]:
    candidates: list[ReflectionCandidate] = []
    active = [item for item in memories if item.get("status") != LifecycleStatus.ARCHIVED.value]
    for left_index, left in enumerate(active):
        for right in active[left_index + 1 :]:
            if left.get("primary_category") != right.get("primary_category"):
                continue
            left_text = str(left.get("content") or "").lower()
            right_text = str(right.get("content") or "").lower()
            if "prefer" not in left_text or "prefer" not in right_text:
                continue
            if _has_temporal_preference_conflict(left_text, right_text):
                candidates.append(
                    ReflectionCandidate(
                        action="conflict_candidate",
                        memory_ids=(left["memory_id"], right["memory_id"]),
                        reason="Preference memories may conflict and need review.",
                        apply_safe=False,
                    )
                )
    return candidates


def _pattern_group_candidates(memories: list[dict[str, Any]]) -> list[ReflectionCandidate]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for memory in memories:
        if memory.get("status") in {LifecycleStatus.DELETED.value, LifecycleStatus.ARCHIVED.value}:
            continue
        signature = _pattern_signature(memory)
        if signature:
            groups.setdefault(signature, []).append(memory)
    candidates: list[ReflectionCandidate] = []
    for signature, group in sorted(groups.items()):
        unique_ids = tuple(memory["memory_id"] for memory in group)
        if len(unique_ids) < 3:
            continue
        candidates.append(
            ReflectionCandidate(
                action="pattern_candidate",
                memory_ids=unique_ids,
                reason=f"Multiple memories support a recurring {signature} pattern.",
                metadata={"signature": signature, "supporting_count": len(unique_ids)},
            )
        )
    return candidates


def _reflect_deep(
    repo: LifeMemoryRepository,
    *,
    apply: bool,
    limit: int,
    run_id: str,
) -> dict[str, Any]:
    memories = repo.list_reflection_memories(limit=limit)
    candidates = _deep_promotion_candidates(memories)
    applied = 0
    reflected_ids: list[str] = []
    link_ids: list[str] = []
    if apply:
        for candidate in candidates:
            if not candidate.apply_safe:
                continue
            reflected_id = _apply_reflected_pattern(repo, candidate, run_id=run_id)
            if reflected_id is None:
                continue
            reflected_ids.append(reflected_id)
            for memory_id in candidate.memory_ids:
                link_ids.append(
                    repo.write_reflection_candidate_link(
                        from_memory_id=reflected_id,
                        to_memory_id=memory_id,
                        relation="supported_by",
                        reason="Reflected pattern cites supporting memory.",
                    )
                )
            applied += 1
    report_ids = _write_candidate_report(
        repo,
        report_type="deep",
        title="Deep Reflection",
        candidates=candidates,
        run_id=run_id,
    )
    return {
        "candidates": candidates,
        "applied_count": applied,
        "report_ids": report_ids,
        "message": "Deep reflection completed.",
        "extra": {"reflected_memory_ids": reflected_ids, "candidate_link_ids": link_ids},
    }


def _deep_promotion_candidates(memories: list[dict[str, Any]]) -> list[ReflectionCandidate]:
    candidates: list[ReflectionCandidate] = []
    for memory in memories:
        if memory.get("status") != LifecycleStatus.PATTERN_CANDIDATE.value:
            continue
        eligible, reasons = _is_low_risk_pattern(memory)
        support_ids = _supporting_memory_ids(memory, memories)
        content = _reflected_pattern_content([memory for memory in memories if memory["memory_id"] in support_ids])
        candidates.append(
            ReflectionCandidate(
                action="promote_abstract_experience",
                memory_ids=support_ids,
                content=content,
                reason="; ".join(reasons) if reasons else "Pattern satisfies conservative promotion thresholds.",
                apply_safe=eligible,
                metadata={
                    "classification": MemoryClassification.ABSTRACT_EXPERIENCE.value,
                    "supporting_memory_ids": list(support_ids),
                },
            )
        )
    existing_keys = {tuple(candidate.memory_ids) for candidate in candidates}
    for group_candidate in _pattern_group_candidates(memories):
        ids = tuple(group_candidate.memory_ids)
        if ids in existing_keys:
            continue
        group = [memory for memory in memories if memory["memory_id"] in ids]
        eligible = all(
            memory.get("sensitivity") == "normal"
            and clamp(memory.get("injection_risk", 0)) < 0.1
            and clamp(memory.get("confidence", 0)) >= 0.7
            for memory in group
        )
        candidates.append(
            ReflectionCandidate(
                action="promote_abstract_experience",
                memory_ids=ids,
                content=_reflected_pattern_content(group),
                reason=(
                    "Repeated compatible memories can be promoted as a low-risk reflected pattern."
                    if eligible
                    else "Pattern group needs review before promotion."
                ),
                apply_safe=eligible,
                metadata={
                    "classification": MemoryClassification.ABSTRACT_EXPERIENCE.value,
                    "supporting_memory_ids": list(ids),
                },
            )
        )
    return candidates


def _is_low_risk_pattern(memory: dict[str, Any]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    if int(memory.get("evidence_count") or 0) < 4:
        failures.append("evidence_count below 4")
    if int(memory.get("days_seen_count") or 0) < 3:
        failures.append("days_seen_count below 3")
    if int(memory.get("source_count") or 0) < 2:
        failures.append("source_count below 2")
    if clamp(memory.get("promotion_score", 0)) < 0.85:
        failures.append("promotion_score below 0.85")
    if clamp(memory.get("confidence", 0)) < 0.8:
        failures.append("confidence below 0.8")
    if memory.get("sensitivity") != "normal":
        failures.append("sensitive memories require review")
    if clamp(memory.get("injection_risk", 0)) >= 0.1:
        failures.append("instruction-like content requires review")
    return not failures, failures


def _supporting_memory_ids(memory: dict[str, Any], memories: list[dict[str, Any]]) -> tuple[str, ...]:
    support = memory.get("context", {}).get("supporting_memory_ids") if isinstance(memory.get("context"), dict) else None
    ids = [str(item) for item in support or [] if str(item)]
    if memory["memory_id"] not in ids:
        ids.insert(0, memory["memory_id"])
    if len(ids) >= 2:
        return tuple(ids[:8])
    similar = []
    for other in memories:
        if other["memory_id"] == memory["memory_id"]:
            continue
        if _similarity(memory.get("content", ""), other.get("content", "")) >= 0.35:
            similar.append(other["memory_id"])
    return tuple((ids + similar)[:8])


def _apply_reflected_pattern(
    repo: LifeMemoryRepository,
    candidate: ReflectionCandidate,
    *,
    run_id: str,
) -> str | None:
    content = str(candidate.content or "").strip()
    if not content:
        return None
    existing = repo.find_memory_by_content_hash(content_hash(content))
    if existing is not None:
        return str(existing["memory_id"])
    record = repo.create_memory(
        content=content,
        classification=MemoryClassification.ABSTRACT_EXPERIENCE.value,
        classification_reason="Conservative deep reflection promoted repeated supporting memories.",
        classification_confidence=0.86,
        primary_category="personal_pattern",
        tags=("abstract_experience", "inference", "reflected_pattern"),
        context={
            "inference": True,
            "supporting_memory_ids": list(candidate.memory_ids),
            "reflection_run_id": run_id,
        },
        importance=0.65,
        confidence=0.86,
        source="reflection",
        source_ref=f"reflection:{run_id}",
        sensitivity="normal",
        injection_risk=0,
        status=LifecycleStatus.ACTIVE.value,
        review_status=ReviewStatus.AUTO_PROMOTED.value,
        promotion_path=PromotionPath.REFLECTED_PATTERN.value,
        promotion_reason="Repeated low-risk evidence supports abstract experience.",
        authority="reflection",
        action_boundary="Use as an inference for personalization; do not override explicit user corrections.",
        evidence_type=EvidenceType.REFLECTION,
        kind=MemoryKind.REFLECTED,
    )
    repo.append_trace(
        operation=TraceOperation.DREAM_DEEP,
        actor="plugin",
        reason="Created reflected abstract experience from supporting memories.",
        memory_id=record["memory_id"],
        after={"supporting_memory_ids": list(candidate.memory_ids), "classification": "abstract_experience"},
    )
    return str(record["memory_id"])


def _reflect_daily(repo: LifeMemoryRepository, *, run_id: str, limit: int) -> dict[str, Any]:
    memories = repo.list_recent_memory_activity(limit=limit)
    report_id = repo.write_reflection_report(
        report_type="daily",
        report_date=now_iso()[:10],
        session_ids=[],
        content=_render_daily_report(memories),
        source_memory_ids=[memory["memory_id"] for memory in memories],
        source_evidence_ids=[],
        created_by_run_id=run_id,
        review_status=ReviewStatus.PENDING,
    )
    candidates = [
        ReflectionCandidate(
            action="daily_report_item",
            memory_ids=(memory["memory_id"],),
            content=memory.get("content"),
            reason="Included in report-only daily reflection.",
            apply_safe=False,
        )
        for memory in memories
    ]
    return {
        "candidates": candidates,
        "applied_count": 0,
        "report_ids": [report_id],
        "message": "Daily reflection report created without durable memory changes.",
        "extra": {"report_only": True},
    }


def _write_candidate_report(
    repo: LifeMemoryRepository,
    *,
    report_type: str,
    title: str,
    candidates: list[ReflectionCandidate],
    run_id: str | None,
) -> list[str]:
    content = _render_candidate_report(title, candidates)
    report_id = repo.write_reflection_report(
        report_type=report_type,
        report_date=now_iso()[:10],
        session_ids=[],
        content=content,
        source_memory_ids=_candidate_memory_ids(candidates),
        source_evidence_ids=[],
        created_by_run_id=run_id,
        review_status=ReviewStatus.PENDING,
    )
    return [report_id]


def _render_candidate_report(title: str, candidates: list[ReflectionCandidate]) -> str:
    lines = [f"# {title}", ""]
    if not candidates:
        lines.extend(["No candidates.", ""])
        return "\n".join(lines)
    for candidate in candidates:
        lines.extend(
            [
                f"## {candidate.action}",
                "",
                f"- Reason: {candidate.reason}",
                f"- Apply safe: {str(candidate.apply_safe).lower()}",
            ]
        )
        if candidate.memory_ids:
            lines.append(f"- Memory ids: {', '.join(candidate.memory_ids)}")
        if candidate.content:
            lines.extend(["", candidate.content])
        lines.append("")
    return "\n".join(lines)


def _render_session_report(
    session: SessionTranscript,
    candidates: list[ReflectionCandidate],
    stored_ids: list[str],
) -> str:
    accepted = [candidate for candidate in candidates if candidate.action == "session_extract_candidate"]
    declined = [candidate for candidate in candidates if candidate.action != "session_extract_candidate"]
    lines = [
        "# Session Reflection Report",
        "",
        f"- Session ref: {session.session_ref or 'explicit_transcript'}",
        f"- Source: {session.source}",
        f"- Candidate count: {len(candidates)}",
        f"- Stored young: {len(stored_ids)}",
        "",
        "## effective_candidates",
        "",
    ]
    if accepted:
        for candidate in accepted:
            lines.append(f"- {candidate.content}")
    else:
        lines.append("- None")
    lines.extend(["", "## stored_young", ""])
    lines.extend([f"- {memory_id}" for memory_id in stored_ids] or ["- None"])
    lines.extend(["", "## do_not_store", ""])
    if declined:
        for candidate in declined:
            lines.append(f"- {candidate.content} ({candidate.reason})")
    else:
        lines.append("- None")
    lines.extend(["", "## source_refs", ""])
    lines.extend([f"- {source_ref}" for source_ref in session.source_refs] or ["- None"])
    lines.append("")
    return "\n".join(lines)


def _render_daily_report(memories: list[dict[str, Any]]) -> str:
    candidates = [memory for memory in memories if memory.get("status") == LifecycleStatus.YOUNG.value]
    promotions = [memory for memory in memories if memory.get("status") == LifecycleStatus.PATTERN_CANDIDATE.value]
    archive = [
        memory
        for memory in memories
        if "recent_state" in set(memory.get("tags") or []) and memory.get("valid_until") and memory.get("valid_until") <= now_iso()
    ]
    do_not_promote = [memory for memory in memories if "recent_state" in set(memory.get("tags") or [])]
    sections = [
        ("candidate_memories", candidates),
        ("evidence_added", []),
        ("conflicts", []),
        ("promotion_candidates", promotions),
        ("archive_candidates", archive),
        ("do_not_promote", do_not_promote),
    ]
    lines = ["# Daily Reflection Report", ""]
    for title, rows in sections:
        lines.extend([f"## {title}", ""])
        if rows:
            for row in rows:
                lines.append(f"- {row['memory_id']}: {row.get('content', '')}")
        else:
            lines.append("- None")
        lines.append("")
    return "\n".join(lines)


def _candidate_memory_ids(candidates: list[ReflectionCandidate]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for candidate in candidates:
        for memory_id in candidate.memory_ids:
            if memory_id not in seen:
                seen.add(memory_id)
                result.append(memory_id)
    return result


def _read_evidence_counts(repo: LifeMemoryRepository, memory_id: str) -> dict[str, int] | None:
    row = repo.connect().execute(
        """
        SELECT
            COUNT(*) AS evidence_count,
            COUNT(DISTINCT COALESCE(source_ref, evidence_id)) AS source_count,
            COUNT(DISTINCT COALESCE(event_date, substr(created_at, 1, 10))) AS days_seen_count
        FROM memory_evidence
        WHERE memory_id = ?
        """,
        (memory_id,),
    ).fetchone()
    if row is None:
        return None
    return {
        "evidence_count": int(row["evidence_count"] or 0),
        "source_count": max(1, int(row["source_count"] or 0)),
        "days_seen_count": max(1, int(row["days_seen_count"] or 0)),
    }


def _normalize_tags(tags: Iterable[Any]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        value = str(tag).strip().lower().replace("-", "_").replace(" ", "_")
        if value and value not in seen:
            normalized.append(value)
            seen.add(value)
    return normalized


def _similarity(left: str, right: str) -> float:
    left_terms = set(tokenize(left))
    right_terms = set(tokenize(right))
    if not left_terms or not right_terms:
        return 0.0
    return len(left_terms & right_terms) / len(left_terms | right_terms)


def _has_temporal_preference_conflict(left: str, right: str) -> bool:
    pairs = (("night", "morning"), ("late", "morning"), ("coffee", "tea"))
    for first, second in pairs:
        if (first in left and second in right) or (second in left and first in right):
            return _similarity(left, right) >= 0.25
    return False


def _pattern_signature(memory: dict[str, Any]) -> str | None:
    tags = set(memory.get("tags") or [])
    content = str(memory.get("content") or "").lower()
    if "work_style" in tags or "work" in content or "focused" in content:
        return "work_style"
    if "routine" in tags or "usually" in content or "often" in content or "tend" in content:
        return "routine"
    if "preference" in tags or "prefer" in content or "like" in content:
        return "preference"
    if "family" in tags:
        return "family"
    return None


def _reflected_pattern_content(memories: list[dict[str, Any]]) -> str:
    if not memories:
        return "The user has a repeated life pattern supported by multiple memories."
    signature = _pattern_signature(memories[0]) or "life"
    snippets = []
    for memory in memories[:3]:
        text = re.sub(r"^remember that\s+", "", str(memory.get("content") or ""), flags=re.I).strip()
        snippets.append(text.rstrip("."))
    return f"The user has a recurring {signature} pattern: " + "; ".join(snippets) + "."


def _valid_until_for_tags(tags: tuple[str, ...]) -> str | None:
    if "recent_state" not in tags:
        return None
    return (now_utc() + timedelta(days=14)).isoformat(timespec="seconds")


def _trace_operation_for_phase(phase: str) -> TraceOperation:
    return {
        ReflectionPhase.LIGHT.value: TraceOperation.DREAM_LIGHT,
        ReflectionPhase.REM.value: TraceOperation.DREAM_REM,
        ReflectionPhase.DEEP.value: TraceOperation.DREAM_DEEP,
        ReflectionPhase.SESSION.value: TraceOperation.SESSION_EXTRACT,
        ReflectionPhase.DAILY.value: TraceOperation.REFLECTION_REPORT,
    }.get(phase, TraceOperation.REFLECT)
