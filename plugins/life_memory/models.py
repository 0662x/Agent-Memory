from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MemoryClassification(str, Enum):
    TECHNICAL_MEMORY = "technical_memory"
    LIFE_MEMORY = "life_memory"
    USER_PROFILE = "user_profile"
    TEMPORARY_WORKING_MEMORY = "temporary_working_memory"
    ABSTRACT_EXPERIENCE = "abstract_experience"
    NO_SAVE = "no_save"


class LifecycleStatus(str, Enum):
    YOUNG = "young"
    ACTIVE = "active"
    REINFORCED = "reinforced"
    PATTERN_CANDIDATE = "pattern_candidate"
    ARCHIVED = "archived"
    DELETED = "deleted"


class ReviewStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_REVIEW = "needs_review"
    AUTO_PROMOTED = "auto_promoted"


class MemoryKind(str, Enum):
    DIRECT = "direct"
    REFLECTED = "reflected"


class Sensitivity(str, Enum):
    NORMAL = "normal"
    SENSITIVE = "sensitive"
    RESTRICTED = "restricted"


class FeedbackType(str, Enum):
    USEFUL = "useful"
    WRONG = "wrong"
    OUTDATED = "outdated"
    IMPORTANT = "important"
    DUPLICATE = "duplicate"
    DELETE = "delete"
    MERGE = "merge"


class TraceOperation(str, Enum):
    CLASSIFY = "classify"
    STORE = "store"
    RECALL = "recall"
    FEEDBACK = "feedback"
    FORGET = "forget"
    REFLECT = "reflect"
    MERGE = "merge"
    ARCHIVE = "archive"
    REINFORCE = "reinforce"
    CONFLICT = "conflict"
    SUPERSEDE = "supersede"
    DREAM_LIGHT = "dream_light"
    DREAM_REM = "dream_rem"
    DREAM_DEEP = "dream_deep"
    SESSION_EXTRACT = "session_extract"
    REFLECTION_REPORT = "reflection_report"
    EXPORT_REVIEW = "export_review"
    MODEL_CLASSIFY = "model_classify"
    MODEL_EXTRACT = "model_extract"
    MODEL_RERANK = "model_rerank"
    MODEL_REFLECT = "model_reflect"
    MODEL_SUMMARIZE = "model_summarize"
    ACTIVATION = "activation"
    CONTEXT_INJECTION = "context_injection"


class ReflectionPhase(str, Enum):
    SESSION = "session"
    LIGHT = "light"
    REM = "rem"
    DEEP = "deep"
    DAILY = "daily"


class EvidenceType(str, Enum):
    EXPLICIT_USER_STATEMENT = "explicit_user_statement"
    ASSISTANT_TOOL_CALL = "assistant_tool_call"
    REPEATED_OBSERVATION = "repeated_observation"
    RECALL_USE = "recall_use"
    USER_FEEDBACK = "user_feedback"
    SESSION_EXTRACT = "session_extract"
    REFLECTION_REPORT = "reflection_report"
    REFLECTION = "reflection"


class PromotionPath(str, Enum):
    NORMAL_EVIDENCE = "normal_evidence"
    MAJOR_LIFE_FACT = "major_life_fact"
    USER_CONFIRMED = "user_confirmed"
    REFLECTED_PATTERN = "reflected_pattern"


class ToolOutcome(str, Enum):
    SUCCESS = "success"
    DECLINED = "declined"
    NEEDS_CONFIRMATION = "needs_confirmation"
    NOT_FOUND = "not_found"
    AMBIGUOUS = "ambiguous"
    DUPLICATE = "duplicate"
    MERGED = "merged"
    ARCHIVED = "archived"
    STORAGE_UNAVAILABLE = "storage_unavailable"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class ClassificationDecision:
    classification: MemoryClassification
    confidence: float
    reason: str
    primary_category: str | None = None
    tags: tuple[str, ...] = ()
    should_store: bool = False


@dataclass(frozen=True, slots=True)
class ToolResult:
    ok: bool
    outcome: ToolOutcome
    message: str
    trace_id: str | None = None
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result = {
            "ok": self.ok,
            "outcome": self.outcome.value,
            "message": self.message,
            "trace_id": self.trace_id,
        }
        result.update(self.data)
        return result


@dataclass(frozen=True, slots=True)
class TraceRecord:
    trace_id: str
    operation: TraceOperation
    actor: str
    reason: str
    memory_id: str | None = None
    input_hash: str | None = None
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    created_at: str | None = None


@dataclass(frozen=True, slots=True)
class ReflectionRunRecord:
    run_id: str
    phase: ReflectionPhase
    started_at: str
    status: str
    completed_at: str | None = None
    input_window: dict[str, Any] = field(default_factory=dict)
    candidate_count: int = 0
    applied_count: int = 0
    report_path: str | None = None
    notes: str | None = None
