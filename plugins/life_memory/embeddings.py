"""Embedding provider seams and vector utilities for life-memory recall.

The default provider is deterministic and local. It is intentionally simple: it
exists to make hybrid recall testable without network calls or model assets.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from .time_utils import clamp

_WORD_RE = re.compile(r"[a-z0-9_]+|[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+", re.I)
_CONCEPT_GROUPS = (
    ("exercise", ("exercise", "run", "running", "runs", "workout", "gym", "sport", "运动", "锻炼", "跑步", "慢跑", "健身")),
    ("drink", ("drink", "drinks", "water", "coconut", "soy", "milk", "coffee", "tea", "饮", "饮品", "喝", "水", "椰子水", "豆浆", "咖啡", "茶")),
    ("weekend", ("weekend", "saturday", "sunday", "周末", "周六", "周日", "星期六", "星期日")),
    ("routine", ("usually", "often", "typically", "routine", "habit", "一般", "通常", "经常", "习惯")),
    ("food", ("food", "eat", "dinner", "meal", "晚饭", "晚餐", "饭后", "吃")),
    ("home", ("home", "address", "live", "house", "住", "地址", "家")),
    ("relationship", ("family", "friend", "partner", "mother", "father", "sister", "brother", "朋友", "家人", "妈妈", "爸爸", "姐姐", "妹妹", "哥哥", "弟弟", "伴侣")),
    ("technical", ("work", "project", "code", "python", "pytest", "工作", "项目", "代码", "测试")),
)


@dataclass(frozen=True, slots=True)
class ProviderMetadata:
    name: str
    model: str
    dimension: int
    locality: str
    available: bool = True


@runtime_checkable
class EmbeddingProvider(Protocol):
    name: str
    model: str
    dimension: int
    locality: str

    @property
    def metadata(self) -> ProviderMetadata: ...

    def embed(self, text: str) -> list[float]: ...


class FakeEmbeddingProvider:
    """Small deterministic semantic provider used for tests and local fallback."""

    name = "fake-semantic"

    def __init__(self, *, model: str = "fake-semantic-v1", dimension: int = 16, locality: str = "fake") -> None:
        self.model = model
        self.dimension = max(8, int(dimension))
        self.locality = locality

    @property
    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            name=self.name,
            model=self.model,
            dimension=self.dimension,
            locality=self.locality,
            available=True,
        )

    def embed(self, text: str) -> list[float]:
        prepared = prepare_embedding_text(text, max_chars=1200).lower()
        vector = [0.0 for _ in range(self.dimension)]

        for index, (_, terms) in enumerate(_CONCEPT_GROUPS):
            if index >= self.dimension:
                break
            hits = sum(1 for term in terms if term in prepared)
            if hits:
                vector[index] += min(1.0, 0.55 + hits * 0.15)

        # Add deterministic lexical texture so unrelated texts with the same broad
        # concepts do not collapse into identical vectors.
        for token in _tokens(prepared):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=4).digest()
            bucket = int.from_bytes(digest[:2], "big") % self.dimension
            weight = 0.05 + (digest[2] / 255.0) * 0.05
            vector[bucket] += weight

        return list(normalize_vector(vector))


class UnavailableEmbeddingProvider:
    name = "unavailable"
    model = "unavailable"
    dimension = 16
    locality = "local"

    @property
    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(self.name, self.model, self.dimension, self.locality, available=False)

    def embed(self, text: str) -> list[float]:
        raise RuntimeError("Embedding provider is unavailable.")


def get_default_embedding_provider() -> EmbeddingProvider:
    return FakeEmbeddingProvider()


def validate_vector(values: list[float] | tuple[float, ...], *, dimension: int) -> tuple[float, ...]:
    vector = tuple(float(value) for value in values)
    if len(vector) != int(dimension):
        raise ValueError(f"Expected vector dimension {dimension}, got {len(vector)}.")
    if not vector or not all(math.isfinite(value) for value in vector):
        raise ValueError("Embedding vector must contain finite values.")
    if math.sqrt(sum(value * value for value in vector)) <= 0:
        raise ValueError("Embedding vector must not be all zeros.")
    return vector


def normalize_vector(values: list[float] | tuple[float, ...]) -> tuple[float, ...]:
    vector = tuple(float(value) for value in values)
    norm = math.sqrt(sum(value * value for value in vector))
    if norm <= 0 or not math.isfinite(norm):
        raise ValueError("Cannot normalize an empty or invalid vector.")
    return tuple(value / norm for value in vector)


def cosine_similarity(left: list[float] | tuple[float, ...], right: list[float] | tuple[float, ...]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    try:
        a = normalize_vector(left)
        b = normalize_vector(right)
    except ValueError:
        return 0.0
    return clamp(sum(x * y for x, y in zip(a, b)), -1.0, 1.0)


def prepare_embedding_text(text: str, *, max_chars: int = 1200) -> str:
    prepared = " ".join(str(text or "").split())
    if len(prepared) <= max_chars:
        return prepared
    return prepared[: max(1, max_chars)].rstrip()


def should_embed_memory(
    memory: dict[str, object],
    provider: EmbeddingProvider,
    *,
    allow_sensitive_external: bool = False,
) -> tuple[bool, str | None]:
    status = str(memory.get("status") or "")
    if status == "deleted":
        return False, "deleted"
    sensitivity = str(memory.get("sensitivity") or "normal")
    if provider.locality == "external" and sensitivity == "restricted":
        return False, "restricted_external"
    if provider.locality == "external" and sensitivity == "sensitive" and not allow_sensitive_external:
        return False, "sensitive_external"
    return True, None


def semantic_concepts(text: str) -> set[str]:
    prepared = prepare_embedding_text(text, max_chars=1200).lower()
    concepts: set[str] = set()
    for name, terms in _CONCEPT_GROUPS:
        if any(term in prepared for term in terms):
            concepts.add(name)
    return concepts


def _tokens(text: str) -> tuple[str, ...]:
    tokens: list[str] = []
    for raw in _WORD_RE.findall(text):
        if re.fullmatch(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+", raw):
            if len(raw) <= 8:
                tokens.append(raw)
            tokens.extend(raw[index : index + 2] for index in range(max(0, len(raw) - 1)))
        elif len(raw) > 2:
            tokens.append(raw.lower())
    return tuple(dict.fromkeys(tokens))
