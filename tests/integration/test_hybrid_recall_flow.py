from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from plugins.life_memory.embeddings import FakeEmbeddingProvider, UnavailableEmbeddingProvider
from plugins.life_memory.hybrid_recall import hybrid_rank_memories, index_memory_embedding
from plugins.life_memory.repository import LifeMemoryRepository
from plugins.life_memory.time_utils import content_hash, json_dumps, now_iso


def _insert_memory(repo: LifeMemoryRepository, memory_id: str, content: str, **overrides: Any) -> dict[str, Any]:
    now = now_iso()
    tags = overrides.get("tags", ["routine"])
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
                ?, ?, ?, ?, ?, 'assistant_tool', NULL, ?, 'pending', ?,
                ?, 1, 0, 1, ?, NULL, NULL, NULL, NULL, ?, ?, NULL,
                'assistant_tool', NULL, ?, ?, ?, NULL, 0, NULL
            )
            """,
            (
                memory_id,
                content,
                content_hash(content),
                overrides.get("primary_category", "personal_preference"),
                json_dumps(tags),
                json_dumps({}),
                overrides.get("importance", 0.7),
                overrides.get("confidence", 0.8),
                overrides.get("feedback_score", 0),
                overrides.get("status", "active"),
                overrides.get("sensitivity", "normal"),
                overrides.get("evidence_count", 1),
                overrides.get("promotion_score", 0),
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


def test_english_paraphrased_hybrid_recall_returns_expected_memory(hermes_home: Path) -> None:
    provider = FakeEmbeddingProvider()
    repo = LifeMemoryRepository(hermes_home=hermes_home)
    repo.initialize()
    target = _insert_memory(repo, "target", "I usually buy coconut water after weekend runs.", tags=["routine", "drink", "exercise"])
    distractor = _insert_memory(repo, "distractor", "I usually plan my week on Sunday evenings.", tags=["routine"])
    index_memory_embedding(repo, target, provider)
    index_memory_embedding(repo, distractor, provider)

    results = hybrid_rank_memories("What do I drink after exercise?", repo=repo, embedding_provider=provider, limit=3)

    assert results[0]["memory_id"] == "target"
    assert results[0]["semantic_available"] is True


def test_chinese_paraphrased_hybrid_recall_returns_expected_memory(hermes_home: Path) -> None:
    provider = FakeEmbeddingProvider()
    repo = LifeMemoryRepository(hermes_home=hermes_home)
    repo.initialize()
    target = _insert_memory(repo, "soy", "我周六下午慢跑后通常买无糖豆浆。", tags=["routine", "drink", "exercise"])
    tea = _insert_memory(repo, "tea", "我晚饭后喜欢喝茉莉茶。", tags=["routine", "drink"])
    index_memory_embedding(repo, target, provider)
    index_memory_embedding(repo, tea, provider)

    results = hybrid_rank_memories("我运动完一般喝什么？", repo=repo, embedding_provider=provider, limit=3)

    assert results[0]["memory_id"] == "soy"


def test_provider_unavailable_falls_back_to_lexical_recall(hermes_home: Path) -> None:
    repo = LifeMemoryRepository(hermes_home=hermes_home)
    repo.initialize()
    _insert_memory(repo, "lexical", "晚饭后喜欢喝茉莉茶。", tags=["routine", "drink"])

    results = hybrid_rank_memories("晚饭后喝什么", repo=repo, embedding_provider=UnavailableEmbeddingProvider(), limit=3)

    assert results[0]["memory_id"] == "lexical"
    assert results[0]["semantic_available"] is False


def test_changed_provider_metadata_ignores_old_embeddings_until_rebuilt(hermes_home: Path) -> None:
    old_provider = FakeEmbeddingProvider(model="fake-old", dimension=16)
    new_provider = FakeEmbeddingProvider(model="fake-new", dimension=16)
    repo = LifeMemoryRepository(hermes_home=hermes_home)
    repo.initialize()
    memory = _insert_memory(repo, "target", "I usually buy coconut water after weekend runs.", tags=["routine", "drink", "exercise"])
    index_memory_embedding(repo, memory, old_provider)

    rows = repo.list_searchable_embeddings(provider=new_provider.name, model=new_provider.model, dimension=new_provider.dimension)

    assert rows == []
    results = hybrid_rank_memories("What do I drink after exercise?", repo=repo, embedding_provider=new_provider, limit=3)
    assert "vector" not in (results[0].get("recall_sources") if results else [])


def test_large_hybrid_recall_smoke_is_bounded(hermes_home: Path) -> None:
    provider = FakeEmbeddingProvider()
    repo = LifeMemoryRepository(hermes_home=hermes_home)
    repo.initialize()
    for index in range(350):
        memory = _insert_memory(repo, f"noise_{index}", f"I keep blue notebook marker {index} on a shelf.", tags=["fact"])
        index_memory_embedding(repo, memory, provider)
    target = _insert_memory(repo, "target", "I usually buy coconut water after weekend runs.", tags=["routine", "drink", "exercise"], confidence=0.95, importance=0.9)
    index_memory_embedding(repo, target, provider)

    results = hybrid_rank_memories("What do I drink after exercise?", repo=repo, embedding_provider=provider, limit=3, candidate_limit=40)

    assert len(results) <= 3
    assert results[0]["memory_id"] == "target"
