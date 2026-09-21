from __future__ import annotations

import math

import pytest

from plugins.life_memory.embeddings import (
    FakeEmbeddingProvider,
    ProviderMetadata,
    UnavailableEmbeddingProvider,
    cosine_similarity,
    normalize_vector,
    prepare_embedding_text,
    should_embed_memory,
    validate_vector,
)


def test_fake_embedding_provider_is_deterministic_and_semantic() -> None:
    provider = FakeEmbeddingProvider()

    first = provider.embed("I usually buy coconut water after weekend runs.")
    second = provider.embed("I usually buy coconut water after weekend runs.")
    query = provider.embed("What do I drink after exercise?")
    unrelated = provider.embed("I organize my desk on Sunday evenings.")

    assert first == second
    assert len(first) == provider.dimension
    assert cosine_similarity(first, query) > cosine_similarity(first, unrelated)


def test_provider_metadata_is_stable() -> None:
    provider = FakeEmbeddingProvider(model="fake-test-v1", dimension=16)
    metadata = provider.metadata

    assert isinstance(metadata, ProviderMetadata)
    assert metadata.name == provider.name
    assert metadata.model == "fake-test-v1"
    assert metadata.dimension == 16
    assert metadata.locality == "fake"


def test_validate_vector_rejects_invalid_dimensions_and_values() -> None:
    assert validate_vector([0.1, 0.2], dimension=2) == (0.1, 0.2)

    with pytest.raises(ValueError):
        validate_vector([0.1], dimension=2)
    with pytest.raises(ValueError):
        validate_vector([math.inf, 0.2], dimension=2)
    with pytest.raises(ValueError):
        validate_vector([0.0, 0.0], dimension=2)


def test_normalize_and_cosine_similarity() -> None:
    normalized = normalize_vector([3.0, 4.0])

    assert normalized == pytest.approx((0.6, 0.8))
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_prepare_embedding_text_is_bounded() -> None:
    text = prepare_embedding_text("  a\n\n" + "b" * 500, max_chars=20)

    assert text.startswith("a b")
    assert len(text) <= 20


def test_unavailable_provider_raises_predictably() -> None:
    provider = UnavailableEmbeddingProvider()

    with pytest.raises(RuntimeError):
        provider.embed("anything")


def test_external_provider_skips_restricted_and_sensitive_raw_content() -> None:
    provider = FakeEmbeddingProvider(locality="external")

    assert should_embed_memory({"sensitivity": "normal"}, provider)[0] is True
    assert should_embed_memory({"sensitivity": "restricted"}, provider)[0] is False
    assert should_embed_memory({"sensitivity": "sensitive"}, provider)[0] is False
    assert should_embed_memory({"status": "deleted", "sensitivity": "normal"}, provider)[0] is False
