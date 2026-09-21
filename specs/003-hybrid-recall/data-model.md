# Data Model: Hybrid Recall For Life Memory

## Existing Source Of Truth

### `life_memories`

Existing authoritative memory table. Hybrid recall must continue to read lifecycle, content, sensitivity, confidence, importance, feedback, validity, and access metadata from this table.

Relevant fields:

- `memory_id`
- `content`
- `content_hash`
- `primary_category`
- `tags_json`
- `importance`
- `confidence`
- `feedback_score`
- `evidence_count`
- `unique_query_count`
- `days_seen_count`
- `promotion_score`
- `status`
- `review_status`
- `sensitivity`
- `valid_from`
- `valid_until`
- `last_confirmed_at`
- `updated_at`
- `injection_risk`

### `memory_links`

Existing relationship table. Hybrid rerank uses links to identify current-vs-superseded facts.

Relevant relations:

- `superseded_by`
- `merged_into`
- `duplicate_of`

## New Derived Table

### `memory_embeddings`

Stores semantic index rows derived from `life_memories`. This table is not the source of truth.

Fields:

- `embedding_id TEXT PRIMARY KEY`
- `memory_id TEXT NOT NULL REFERENCES life_memories(memory_id) ON DELETE CASCADE`
- `provider TEXT NOT NULL`
- `model TEXT NOT NULL`
- `dimension INTEGER NOT NULL`
- `content_hash TEXT NOT NULL`
- `vector_json TEXT NOT NULL`
- `status TEXT NOT NULL`
- `error TEXT`
- `created_at TEXT NOT NULL`
- `updated_at TEXT NOT NULL`

Indexes:

- Unique index on `(memory_id, provider, model, dimension)`.
- Index on `memory_id`.
- Index on `(provider, model, dimension, status)`.

Validation rules:

- `dimension` must equal the active provider dimension.
- `content_hash` must match the current `life_memories.content_hash` for the memory.
- `vector_json` must decode to exactly `dimension` finite numeric values.
- Rows with `status != 'ready'` are not searchable.
- Stale rows are ignored until rebuilt.

Status values:

- `ready`: vector exists and metadata is compatible.
- `stale`: content hash or provider metadata no longer matches.
- `skipped`: memory was intentionally not embedded, for example restricted content with external provider.
- `failed`: provider failed or returned invalid data.

## New Runtime Entities

### `EmbeddingProvider`

Configuration and callable behavior for vector generation.

Fields:

- `name`
- `model`
- `dimension`
- `locality`: `local`, `fake`, or `external`
- `available`

Rules:

- Tests use fake deterministic providers.
- External providers must not receive restricted raw content.
- Provider changes invalidate existing vectors for active search unless metadata matches.

### `EmbeddingVector`

Normalized vector produced by a provider.

Fields:

- `values`
- `dimension`
- `norm`

Rules:

- Empty or all-zero vectors are invalid for search.
- Cosine similarity is the default similarity metric.

### `HybridRecallQuery`

Normalized recall request.

Fields:

- `query`
- `tokens`
- `query_vector`
- `limit`
- `candidate_limit`
- `include_archived`
- `include_sensitive`
- `historical_mode`
- `provider_metadata`

Rules:

- If `query_vector` is unavailable, recall remains lexical-only.
- `candidate_limit` is bounded to prevent unbounded pre-LLM work.

### `HybridCandidate`

Merged candidate before final rerank.

Fields:

- `memory_id`
- `memory`
- `sources`: lexical, vector, or both
- `lexical_score`
- `semantic_score`
- `metadata_score`
- `temporal_score`
- `final_score`
- `filter_reason`
- `relevance_reason`

Rules:

- Duplicate candidates merge by `memory_id`.
- Missing lexical or semantic score defaults to zero.
- Candidates must pass existing recall filters before final return.

### `HybridRecallResult`

Final recall result exposed to explicit recall and activation.

Fields:

- Existing recall fields: `memory_id`, `kind`, `content`, `primary_category`, `tags`, `status`, `sensitivity`, `importance`, `confidence`, `relevance_score`, `relevance_reason`.
- New explanation fields: `score_components`, `recall_sources`, `semantic_available`, `embedding_model`, `temporal_note`.

Rules:

- Result shape must remain backward compatible for existing callers.
- New fields are additive.
- Sensitive/restricted content handling follows existing explicit recall and activation policies.

### `IndexRebuildReport`

Audit summary from embedding indexing or rebuild.

Fields:

- `provider`
- `model`
- `dimension`
- `indexed_count`
- `fresh_count`
- `stale_count`
- `skipped_count`
- `failed_count`
- `errors`

Rules:

- Report must not include restricted raw content.
- Counts are sufficient for quick audit and tests.
