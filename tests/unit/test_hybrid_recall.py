from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from plugins.life_memory.embeddings import FakeEmbeddingProvider
from plugins.life_memory.hybrid_recall import (
    HybridCandidate,
    HybridRecallQuery,
    ScoreComponents,
    hybrid_rank_memories,
    merge_candidates,
)
from plugins.life_memory.repository import LifeMemoryRepository
from plugins.life_memory.time_utils import content_hash


def _memory(memory_id: str, content: str, **overrides: Any) -> dict[str, Any]:
    data = {
        "memory_id": memory_id,
        "kind": "direct",
        "content": content,
        "content_hash": content_hash(content),
        "primary_category": "personal_preference",
        "tags": ["routine"],
        "status": "active",
        "review_status": "pending",
        "sensitivity": "normal",
        "importance": 0.7,
        "confidence": 0.8,
        "feedback_score": 0,
        "evidence_count": 1,
        "unique_query_count": 0,
        "days_seen_count": 1,
        "promotion_score": 0,
        "injection_risk": 0,
        "valid_until": None,
        "updated_at": "2026-06-03T00:00:00+00:00",
        "last_confirmed_at": None,
    }
    data.update(overrides)
    return data


def _create_memory(repo: LifeMemoryRepository, memory_id: str, content: str, **overrides: Any) -> dict[str, Any]:
    now = "2026-06-03T00:00:00+00:00"
    tags = overrides.pop("tags", ["routine"])
    with repo.transaction() as conn:
        conn.execute(
            """
            INSERT INTO life_memories (
                memory_id, kind, classification, classification_reason,
                classification_confidence, content, content_hash, primary_category,
                tags_json, context_json, importance, confidence, feedback_score,
                source, source_ref, status, review_status, sensitivity,
                evidence_count, source_count, unique_query_count, days_seen_count,
                promotion_score, promotion_path, promotion_reason, decay_reason,
                last_confirmed_at, valid_from, valid_until, scope, authority,
                action_boundary, injection_risk, created_at, updated_at,
                last_accessed_at, access_count, deleted_at
            )
            VALUES (
                ?, 'direct', 'life_memory', 'test fixture', 0.9, ?, ?, ?,
                ?, '{}', ?, ?, ?, 'assistant_tool', NULL, ?, 'pending', ?,
                ?, 1, 0, 1, ?, NULL, NULL, NULL, ?, ?, ?, NULL,
                'assistant_tool', NULL, ?, ?, ?, NULL, 0, NULL
            )
            """,
            (
                memory_id,
                content,
                content_hash(content),
                overrides.get("primary_category", "personal_preference"),
                json.dumps(tags),
                overrides.get("importance", 0.7),
                overrides.get("confidence", 0.8),
                overrides.get("feedback_score", 0),
                overrides.get("status", "active"),
                overrides.get("sensitivity", "normal"),
                overrides.get("evidence_count", 1),
                overrides.get("promotion_score", 0),
                overrides.get("last_confirmed_at"),
                overrides.get("valid_from", now),
                overrides.get("valid_until"),
                overrides.get("injection_risk", 0),
                overrides.get("created_at", now),
                overrides.get("updated_at", now),
            ),
        )
    memory = repo.get_memory(memory_id)
    assert memory is not None
    return memory


def _index(repo: LifeMemoryRepository, memory: dict[str, Any], provider: FakeEmbeddingProvider) -> None:
    repo.upsert_memory_embedding(
        memory_id=memory["memory_id"],
        provider=provider.name,
        model=provider.model,
        dimension=provider.dimension,
        content_hash_value=memory["content_hash"],
        vector=provider.embed(memory["content"]),
    )


def test_hybrid_result_shapes_are_stable() -> None:
    query = HybridRecallQuery(query="What do I drink after exercise?", limit=3, candidate_limit=10)
    score = ScoreComponents(lexical=0.2, semantic=0.8, metadata=0.5, temporal=0.1)
    candidate = HybridCandidate(memory=_memory("mem_1", "content"), sources={"vector"}, score_components=score)

    rendered = candidate.to_result()

    assert query.limit == 3
    assert rendered["memory_id"] == "mem_1"
    assert rendered["score_components"]["semantic"] == 0.8
    assert rendered["recall_sources"] == ["vector"]


def test_fixture_schema_is_valid() -> None:
    data = json.loads(Path("tests/fixtures/hybrid_recall_cases.json").read_text())

    assert data["cases"]
    for case in data["cases"]:
        assert case["case_id"]
        assert case["query"]
        assert case["expected_memory_id"]
        assert case["memories"]


def test_merge_candidates_deduplicates_and_preserves_sources() -> None:
    memory = _memory("mem_1", "I usually buy coconut water after weekend runs.")
    lexical = HybridCandidate(memory=memory, sources={"lexical"}, score_components=ScoreComponents(lexical=0.4))
    vector = HybridCandidate(memory=memory, sources={"vector"}, score_components=ScoreComponents(semantic=0.8))

    merged = merge_candidates([lexical], [vector])

    assert len(merged) == 1
    assert merged[0].sources == {"lexical", "vector"}
    assert merged[0].score_components.lexical == 0.4
    assert merged[0].score_components.semantic == 0.8


def test_hybrid_rank_uses_vector_candidates_for_paraphrases(hermes_home: Path) -> None:
    provider = FakeEmbeddingProvider()
    repo = LifeMemoryRepository(hermes_home=hermes_home)
    repo.initialize()
    target = _create_memory(repo, "mem_coconut", "I usually buy coconut water after weekend runs.", tags=["routine", "drink", "exercise"])
    distractor = _create_memory(repo, "mem_desk", "I usually organize my desk on Sunday evenings.", tags=["routine"])
    _index(repo, target, provider)
    _index(repo, distractor, provider)

    results = hybrid_rank_memories(
        "What do I drink after exercise?",
        repo=repo,
        embedding_provider=provider,
        limit=3,
    )

    assert results[0]["memory_id"] == "mem_coconut"
    assert "vector" in results[0]["recall_sources"]
    assert results[0]["score_components"]["semantic"] > 0


def test_fixture_driven_paraphrase_cases(hermes_home: Path) -> None:
    provider = FakeEmbeddingProvider()
    data = json.loads(Path("tests/fixtures/hybrid_recall_cases.json").read_text())

    for case in data["cases"]:
        repo = LifeMemoryRepository(hermes_home=hermes_home / case["case_id"])
        repo.initialize()
        memories = {}
        for item in case["memories"]:
            memory = _create_memory(
                repo,
                item["memory_id"],
                item["content"],
                tags=item.get("tags", []),
                primary_category=item.get("primary_category", "personal_preference"),
                confidence=item.get("confidence", 0.8),
                importance=item.get("importance", 0.7),
            )
            memories[item["memory_id"]] = memory
            _index(repo, memory, provider)
        for item in case["memories"]:
            if item.get("superseded_by"):
                repo.write_memory_link(
                    from_memory_id=item["memory_id"],
                    to_memory_id=item["superseded_by"],
                    relation="superseded_by",
                    reason="fixture replacement",
                )

        results = hybrid_rank_memories(case["query"], repo=repo, embedding_provider=provider, limit=3)
        assert [item["memory_id"] for item in results[:3]][0] == case["expected_memory_id"], case["case_id"]


def test_hybrid_filters_disallowed_semantic_candidates(hermes_home: Path) -> None:
    provider = FakeEmbeddingProvider()
    repo = LifeMemoryRepository(hermes_home=hermes_home)
    repo.initialize()
    allowed = _create_memory(repo, "allowed", "I buy soy milk after runs.", tags=["drink", "exercise"])
    deleted = _create_memory(repo, "deleted", "I buy coconut water after runs.", tags=["drink", "exercise"], status="deleted")
    expired = _create_memory(repo, "expired", "I buy mineral water after runs.", tags=["drink", "exercise"], valid_until="2000-01-01T00:00:00+00:00")
    restricted = _create_memory(repo, "restricted", "My private address is near the running path.", tags=["exercise"], sensitivity="restricted")
    for memory in (allowed, deleted, expired, restricted):
        _index(repo, memory, provider)

    results = hybrid_rank_memories("What do I drink after exercise?", repo=repo, embedding_provider=provider, limit=10)

    assert [item["memory_id"] for item in results] == ["allowed"]


def test_score_components_prefer_current_supported_memory(hermes_home: Path) -> None:
    provider = FakeEmbeddingProvider()
    repo = LifeMemoryRepository(hermes_home=hermes_home)
    repo.initialize()
    old = _create_memory(repo, "old", "I used to buy coconut water after runs.", tags=["drink", "exercise"], confidence=0.7, importance=0.5)
    new = _create_memory(repo, "new", "I now buy soy milk after runs.", tags=["drink", "exercise"], confidence=0.95, importance=0.9, evidence_count=3, feedback_score=0.4)
    _index(repo, old, provider)
    _index(repo, new, provider)
    repo.write_memory_link(from_memory_id="old", to_memory_id="new", relation="superseded_by", reason="updated routine")

    results = hybrid_rank_memories("What do I usually drink after running?", repo=repo, embedding_provider=provider, limit=5)

    assert results[0]["memory_id"] == "new"
    assert results[0]["score_components"]["metadata"] > 0
    assert results[0]["temporal_note"] == "current_non_superseded"
