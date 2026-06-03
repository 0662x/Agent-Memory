"""Hybrid lexical/vector recall and time-aware reranking."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .embeddings import (
    EmbeddingProvider,
    cosine_similarity,
    get_default_embedding_provider,
    semantic_concepts,
    should_embed_memory,
    validate_vector,
)
from .recall import rank_memories
from .time_utils import clamp


@dataclass(frozen=True, slots=True)
class HybridRecallQuery:
    query: str
    limit: int = 5
    candidate_limit: int = 30
    include_archived: bool = False
    include_sensitive: bool = False
    historical_mode: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "limit", max(1, min(int(self.limit or 1), 20)))
        object.__setattr__(self, "candidate_limit", max(self.limit, min(max(int(self.candidate_limit or 1), 1), 200)))


@dataclass(slots=True)
class ScoreComponents:
    lexical: float = 0.0
    semantic: float = 0.0
    metadata: float = 0.0
    temporal: float = 0.0
    final: float = 0.0

    def combine(self) -> float:
        self.lexical = clamp(self.lexical)
        self.semantic = clamp(self.semantic)
        self.metadata = clamp(self.metadata)
        self.temporal = clamp(self.temporal, -1.0, 1.0)
        self.final = round(
            self.lexical * 0.35
            + self.semantic * 0.45
            + self.metadata * 0.15
            + self.temporal * 0.05,
            4,
        )
        return self.final

    def merge(self, other: "ScoreComponents") -> None:
        self.lexical = max(self.lexical, other.lexical)
        self.semantic = max(self.semantic, other.semantic)
        self.metadata = max(self.metadata, other.metadata)
        self.temporal = max(self.temporal, other.temporal)
        self.final = max(self.final, other.final)

    def to_dict(self) -> dict[str, float]:
        return {
            "lexical": round(self.lexical, 4),
            "semantic": round(self.semantic, 4),
            "metadata": round(self.metadata, 4),
            "temporal": round(self.temporal, 4),
            "final": round(self.final, 4),
        }


@dataclass(slots=True)
class HybridCandidate:
    memory: dict[str, Any]
    sources: set[str] = field(default_factory=set)
    score_components: ScoreComponents = field(default_factory=ScoreComponents)
    relevance_reason_parts: list[str] = field(default_factory=list)
    temporal_note: str = "current_non_superseded"
    semantic_available: bool = False
    embedding_model: str | None = None

    @property
    def memory_id(self) -> str:
        return str(self.memory.get("memory_id") or "")

    def to_result(self) -> dict[str, Any]:
        self.score_components.combine()
        content = str(self.memory.get("content") or "")
        reason = " ".join(part for part in self.relevance_reason_parts if part).strip()
        if not reason:
            reason = "Hybrid recall matched memory candidate."
        result = {
            "memory_id": self.memory_id,
            "kind": self.memory.get("kind", "direct"),
            "content": content,
            "primary_category": self.memory.get("primary_category"),
            "tags": list(self.memory.get("tags") or []),
            "status": self.memory.get("status"),
            "sensitivity": self.memory.get("sensitivity", "normal"),
            "importance": self.memory.get("importance", 0),
            "confidence": self.memory.get("confidence", 0),
            "relevance_score": self.score_components.final,
            "relevance_reason": reason,
            "score_components": self.score_components.to_dict(),
            "recall_sources": sorted(self.sources),
            "semantic_available": self.semantic_available,
            "embedding_model": self.embedding_model,
            "temporal_note": self.temporal_note,
        }
        if self.memory.get("safety_note"):
            result["safety_note"] = self.memory["safety_note"]
        return result


def merge_candidates(
    lexical_candidates: Sequence[HybridCandidate],
    vector_candidates: Sequence[HybridCandidate],
) -> list[HybridCandidate]:
    merged: dict[str, HybridCandidate] = {}
    for candidate in [*lexical_candidates, *vector_candidates]:
        memory_id = candidate.memory_id
        if not memory_id:
            continue
        existing = merged.get(memory_id)
        if existing is None:
            merged[memory_id] = candidate
            continue
        existing.sources.update(candidate.sources)
        existing.score_components.merge(candidate.score_components)
        existing.relevance_reason_parts.extend(candidate.relevance_reason_parts)
        existing.semantic_available = existing.semantic_available or candidate.semantic_available
        existing.embedding_model = existing.embedding_model or candidate.embedding_model
    return list(merged.values())


def hybrid_rank_memories(
    query: str,
    memories: Iterable[dict[str, Any]] | None = None,
    *,
    repo: Any | None = None,
    embedding_provider: EmbeddingProvider | None = None,
    limit: int = 5,
    candidate_limit: int = 30,
    categories: tuple[str, ...] | list[str] = (),
    include_archived: bool = False,
    include_sensitive: bool = False,
    historical_mode: bool = False,
) -> list[dict[str, Any]]:
    recall_query = HybridRecallQuery(
        query=query,
        limit=limit,
        candidate_limit=candidate_limit,
        include_archived=include_archived,
        include_sensitive=include_sensitive,
        historical_mode=historical_mode,
    )
    provider = embedding_provider or get_default_embedding_provider()

    lexical_pool = list(memories) if memories is not None else _repo_search(
        repo,
        query=query,
        candidate_limit=recall_query.candidate_limit,
        categories=categories,
        include_archived=include_archived,
        include_sensitive=include_sensitive,
    )
    lexical_candidates = _lexical_candidates(query, lexical_pool, recall_query)
    vector_candidates, semantic_available, embedding_model = _vector_candidates(
        query,
        repo=repo,
        provider=provider,
        recall_query=recall_query,
        categories=categories,
        include_archived=include_archived,
        include_sensitive=include_sensitive,
    )

    candidates = merge_candidates(lexical_candidates, vector_candidates)
    ranked: list[HybridCandidate] = []
    for candidate in candidates:
        if _is_superseded(repo, candidate.memory_id):
            if not historical_mode:
                continue
            candidate.temporal_note = "superseded_historical"
        _apply_metadata_and_temporal_scores(candidate, repo=repo, historical_mode=historical_mode)
        candidate.semantic_available = semantic_available or candidate.semantic_available
        candidate.embedding_model = embedding_model
        candidate.score_components.combine()
        ranked.append(candidate)

    ranked.sort(key=lambda item: item.score_components.final, reverse=True)
    return [candidate.to_result() for candidate in ranked[: recall_query.limit]]


def index_memory_embedding(
    repo: Any,
    memory: Mapping[str, Any],
    provider: EmbeddingProvider | None = None,
    *,
    allow_sensitive_external: bool = False,
) -> dict[str, Any]:
    provider = provider or get_default_embedding_provider()
    allowed, reason = should_embed_memory(dict(memory), provider, allow_sensitive_external=allow_sensitive_external)
    if not allowed:
        return repo.upsert_memory_embedding(
            memory_id=str(memory.get("memory_id")),
            provider=provider.name,
            model=provider.model,
            dimension=provider.dimension,
            content_hash_value=str(memory.get("content_hash") or ""),
            vector=[1.0] + [0.0 for _ in range(max(provider.dimension - 1, 0))],
            status="skipped",
            error=reason,
        )
    try:
        vector = provider.embed(str(memory.get("content") or ""))
    except Exception as exc:
        return repo.upsert_memory_embedding(
            memory_id=str(memory.get("memory_id")),
            provider=provider.name,
            model=provider.model,
            dimension=provider.dimension,
            content_hash_value=str(memory.get("content_hash") or ""),
            vector=[1.0] + [0.0 for _ in range(max(provider.dimension - 1, 0))],
            status="failed",
            error=type(exc).__name__,
        )
    return repo.upsert_memory_embedding(
        memory_id=str(memory.get("memory_id")),
        provider=provider.name,
        model=provider.model,
        dimension=provider.dimension,
        content_hash_value=str(memory.get("content_hash") or ""),
        vector=vector,
        status="ready",
    )


def _repo_search(
    repo: Any | None,
    *,
    query: str,
    candidate_limit: int,
    categories: tuple[str, ...] | list[str],
    include_archived: bool,
    include_sensitive: bool,
) -> list[dict[str, Any]]:
    if repo is None or not hasattr(repo, "search_memories"):
        return []
    try:
        return repo.search_memories(
            query=query,
            limit=candidate_limit,
            categories=categories,
            include_archived=include_archived,
            include_sensitive=include_sensitive,
        )
    except Exception:
        return []


def _lexical_candidates(query: str, memories: list[dict[str, Any]], recall_query: HybridRecallQuery) -> list[HybridCandidate]:
    ranked = rank_memories(
        query,
        memories,
        limit=recall_query.candidate_limit,
        include_archived=recall_query.include_archived,
        include_sensitive=recall_query.include_sensitive,
    )
    candidates: list[HybridCandidate] = []
    for item in ranked:
        lexical = clamp(float(item.get("relevance_score") or 0), 0, 1)
        candidate = HybridCandidate(
            memory=item,
            sources={"lexical"},
            score_components=ScoreComponents(lexical=lexical),
            relevance_reason_parts=[str(item.get("relevance_reason") or "Lexical recall matched query terms.")],
        )
        if item.get("safety_note"):
            candidate.memory["safety_note"] = item["safety_note"]
        candidates.append(candidate)
    return candidates


def _vector_candidates(
    query: str,
    *,
    repo: Any | None,
    provider: EmbeddingProvider,
    recall_query: HybridRecallQuery,
    categories: tuple[str, ...] | list[str],
    include_archived: bool,
    include_sensitive: bool,
) -> tuple[list[HybridCandidate], bool, str | None]:
    if repo is None or not hasattr(repo, "list_searchable_embeddings"):
        return [], False, None
    try:
        query_vector = validate_vector(provider.embed(query), dimension=provider.dimension)
    except Exception:
        return [], False, None
    query_concepts = semantic_concepts(query)

    try:
        rows = repo.list_searchable_embeddings(
            provider=provider.name,
            model=provider.model,
            dimension=provider.dimension,
            include_archived=include_archived,
            include_sensitive=include_sensitive,
            categories=categories,
            limit=max(recall_query.candidate_limit * 5, recall_query.candidate_limit),
        )
    except Exception:
        return [], False, None

    candidates: list[HybridCandidate] = []
    for row in rows:
        overlap = query_concepts & semantic_concepts(_memory_semantic_text(row))
        meaningful_overlap = overlap - {"routine"}
        if not meaningful_overlap:
            continue
        vector = row.get("vector") or []
        similarity = cosine_similarity(query_vector, vector)
        if similarity < 0.12:
            continue
        candidate = HybridCandidate(
            memory=row,
            sources={"vector"},
            score_components=ScoreComponents(semantic=similarity),
            relevance_reason_parts=[f"Semantic similarity {similarity:.2f} from {provider.model}."],
            semantic_available=True,
            embedding_model=provider.model,
        )
        candidates.append(candidate)
    candidates.sort(key=lambda item: item.score_components.semantic, reverse=True)
    return candidates[: recall_query.candidate_limit], True, provider.model


def _memory_semantic_text(memory: Mapping[str, Any]) -> str:
    return " ".join(
        [
            str(memory.get("content") or ""),
            str(memory.get("primary_category") or ""),
            " ".join(str(tag) for tag in memory.get("tags") or []),
        ]
    )


def _apply_metadata_and_temporal_scores(candidate: HybridCandidate, *, repo: Any | None, historical_mode: bool) -> None:
    memory = candidate.memory
    metadata = 0.0
    metadata += clamp(memory.get("importance", 0)) * 0.25
    metadata += clamp(memory.get("confidence", 0)) * 0.30
    metadata += clamp(memory.get("feedback_score", 0)) * 0.15
    metadata += min(float(memory.get("evidence_count") or 0), 5.0) / 5.0 * 0.15
    metadata += min(float(memory.get("days_seen_count") or 0), 5.0) / 5.0 * 0.05
    metadata += clamp(memory.get("promotion_score", 0)) * 0.10
    candidate.score_components.metadata = clamp(metadata)

    temporal = 0.0
    status = str(memory.get("status") or "")
    if status in {"active", "reinforced", "pattern_candidate"}:
        temporal += 0.25
    elif status == "young":
        temporal -= 0.15
    elif status == "archived":
        temporal -= 0.35
    if memory.get("valid_until") and _is_expired(str(memory["valid_until"])):
        temporal -= 0.8
        candidate.temporal_note = "expired"
    elif candidate.temporal_note != "superseded_historical":
        candidate.temporal_note = "current_non_superseded"
    if candidate.temporal_note == "superseded_historical":
        temporal -= 0.55 if not historical_mode else 0.2
    candidate.score_components.temporal = clamp(temporal, -1.0, 1.0)

    parts = []
    if candidate.score_components.semantic > 0:
        parts.append("Semantic recall matched paraphrased life-memory context.")
    if candidate.score_components.lexical > 0:
        parts.append("Lexical recall also matched query terms.")
    if candidate.temporal_note == "current_non_superseded":
        parts.append("Memory is current and not superseded.")
    elif candidate.temporal_note:
        parts.append(f"Temporal note: {candidate.temporal_note}.")
    candidate.relevance_reason_parts.extend(parts)


def _is_superseded(repo: Any | None, memory_id: str) -> bool:
    if repo is None or not memory_id or not hasattr(repo, "fetch_one"):
        return False
    try:
        row = repo.fetch_one(
            """
            SELECT 1 AS found FROM memory_links
            WHERE from_memory_id = ?
              AND relation IN ('superseded_by', 'merged_into', 'duplicate_of')
            LIMIT 1
            """,
            (memory_id,),
        )
        return row is not None
    except Exception:
        return False


def _is_expired(value: str) -> bool:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed <= datetime.now(timezone.utc)
