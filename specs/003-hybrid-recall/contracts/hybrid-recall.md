# Contract: Hybrid Recall For Life Memory

## Public Behavior

Hybrid recall is an internal upgrade to life-memory recall. Existing callers must still be able to call `life_memory_recall` with the same payload shape. New fields may be returned, but existing fields must remain stable.

## `life_memory_recall` Input

Existing fields remain valid:

```json
{
  "query": "What do I drink after exercise?",
  "limit": 5,
  "categories": [],
  "include_archived": false,
  "include_sensitive": false
}
```

Optional fields for this feature:

```json
{
  "recall_mode": "hybrid",
  "candidate_limit": 30,
  "semantic": true,
  "historical_mode": false
}
```

Field rules:

- `recall_mode`: `lexical`, `hybrid`, or `auto`; default should preserve backward-compatible behavior while allowing configured hybrid use.
- `candidate_limit`: bounded internal candidate pool size.
- `semantic`: if false, skip vector candidate retrieval.
- `historical_mode`: if true, may include historical/superseded context only when explicitly requested and safe.

## `life_memory_recall` Output

Existing envelope remains valid:

```json
{
  "ok": true,
  "outcome": "success",
  "query": "What do I drink after exercise?",
  "memories": [
    {
      "memory_id": "mem_example",
      "content": "I usually buy coconut water after weekend runs.",
      "status": "active",
      "sensitivity": "normal",
      "confidence": 0.9,
      "relevance_score": 1.42,
      "relevance_reason": "Matched semantically similar exercise drink context."
    }
  ]
}
```

Additive fields for hybrid recall:

```json
{
  "recall_mode": "hybrid",
  "semantic_available": true,
  "embedding_model": "fake-hash-v1",
  "score_components": {
    "lexical": 0.35,
    "semantic": 0.82,
    "metadata": 0.41,
    "temporal": 0.2,
    "final": 1.28
  },
  "recall_sources": ["lexical", "vector"],
  "temporal_note": "current_non_superseded"
}
```

Backward compatibility rules:

- Existing tests expecting `memory_id`, `content`, `status`, `sensitivity`, `confidence`, `relevance_score`, and `relevance_reason` must continue to pass.
- Additive fields must not be required by old callers.
- If embeddings are unavailable, output should include lexical results and may include `semantic_available: false`.

## Internal Hybrid Recall API

Proposed module-level callable:

```python
def hybrid_rank_memories(
    query: str,
    memories: Iterable[dict[str, Any]] | None = None,
    *,
    repo: Any | None = None,
    embedding_provider: Any | None = None,
    limit: int = 5,
    candidate_limit: int = 30,
    include_archived: bool = False,
    include_sensitive: bool = False,
    historical_mode: bool = False,
) -> list[dict[str, Any]]:
    ...
```

Rules:

- If `repo` and `embedding_provider` are unavailable, use lexical ranking on `memories`.
- If embedding generation fails, return lexical results rather than raising for normal recall paths.
- If called by automatic activation, activation remains responsible for strict injection filtering.

## Embedding Provider Interface

```python
class EmbeddingProvider(Protocol):
    name: str
    model: str
    dimension: int
    locality: str

    def embed(self, text: str) -> list[float]:
        ...
```

Rules:

- `embed()` must return exactly `dimension` finite floats.
- Fake provider must be deterministic.
- External provider implementations must declare `locality = "external"`.

## Repository Embedding Helpers

Proposed operations:

```python
repo.upsert_memory_embedding(...)
repo.get_fresh_memory_embedding(...)
repo.list_embedding_candidates(...)
repo.mark_stale_embeddings(...)
repo.rebuild_missing_embeddings(...)
```

Rules:

- Helpers must validate provider/model/dimension/content hash.
- Search must ignore stale, failed, skipped, incompatible, or invalid vectors.
- Rebuild report must contain counts, not raw restricted content.

## Activation Integration Contract

`build_activation_context()` should continue to return the same envelope as `002`. If hybrid recall is available, selected memories may carry additive `score_components` and `recall_sources`, but the injected block must remain bounded and data-only.

Failure contract:

- Embedding provider unavailable: no exception escapes the hook.
- Vector search invalid: lexical fallback or no context.
- Broad semantic candidates: existing activation filters and max-memory limits apply.

## Privacy Contract

- Restricted raw content must not be sent to external providers.
- Sensitive raw content requires explicit configuration before external embedding.
- Deleted memories must not be embedded for active recall.
- Existing embeddings for deleted memories must not be searchable.
- Traces and rebuild reports must not include restricted raw content.
