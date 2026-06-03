# Feature Specification: Hybrid Recall For Life Memory

**Feature Branch**: `003-hybrid-recall`

**Created**: 2026-06-03

**Status**: Draft

**Input**: User description: "Improve life-memory recall with lexical and vector candidate retrieval plus time-aware reranking"

## Summary

This feature upgrades `life_memory` recall from mostly lexical matching to hybrid recall. The plugin should still keep SQLite as the source of truth, but it may maintain a separate semantic index for memory content. When a user explicitly calls `life_memory_recall` or when `002-memory-activation` automatically needs memory context, the system should combine lexical candidates and semantic candidates, apply existing safety/lifecycle filters, and rerank results using relevance, confidence, importance, user feedback, lifecycle state, and temporal validity.

This feature is intended to improve recall when the user's question uses different wording from the stored memory. It must not make vector search the authority for truth, bypass privacy filters, or silently send sensitive life memories to an external embedding provider.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Recall Semantically Similar Memories (Priority: P1)

As a Hermes user, I want life-memory recall to find relevant memories even when I phrase my question differently from the stored text, so that Hermes can use my memory naturally instead of depending on exact keywords.

**Why this priority**: This is the main capability gap after `001` and `002`. Activation can decide when to use memory, but recall still needs to find the right memories under paraphrased or indirect questions.

**Independent Test**: Can be tested with a fake deterministic embedding provider by storing memories, querying with paraphrases, and verifying hybrid recall ranks the semantically matching memory above lexical-only distractors.

**Acceptance Scenarios**:

1. **Given** a stored memory says "I usually buy coconut water after weekend runs", **When** the user asks "What do I drink after exercise?", **Then** recall returns the coconut-water memory even if the exact words "weekend runs" are absent from the query.
2. **Given** Chinese stored memory says "我周六下午慢跑后通常买无糖豆浆", **When** the user asks "我运动完一般喝什么?", **Then** recall returns the soy-milk memory with a semantic-match reason.
3. **Given** lexical recall and vector recall return overlapping candidates, **When** hybrid recall merges them, **Then** each memory appears only once with combined score evidence.

---

### User Story 2 - Preserve Privacy And Lifecycle Boundaries (Priority: P1)

As a Hermes user, I want hybrid recall to preserve the current safety and lifecycle rules so that semantic search never resurfaces deleted, expired, restricted, or superseded memories as current facts.

**Why this priority**: Vector retrieval increases the chance of broad matches. It must not weaken the strict privacy and lifecycle filters already established in `001` and `002`.

**Independent Test**: Can be tested by seeding memories with deleted, archived, expired, restricted, sensitive, and superseded states, then proving hybrid recall and activation injection exclude or gate them exactly as the current recall path does.

**Acceptance Scenarios**:

1. **Given** a semantically matching memory is `deleted`, **When** hybrid recall runs, **Then** it is not returned.
2. **Given** a semantically matching memory is expired by `valid_until`, **When** hybrid recall runs, **Then** it is excluded unless an explicit historical/archival recall mode allows it.
3. **Given** a sensitive memory would require authorization, **When** automatic activation uses hybrid recall, **Then** raw sensitive content is not injected.
4. **Given** an old memory has a `superseded_by` link to a newer memory, **When** both are semantically relevant, **Then** the newer current memory ranks above or replaces the superseded memory in normal recall.

---

### User Story 3 - Rerank With Time-Aware Evidence (Priority: P1)

As a Hermes user, I want recall ranking to prefer current, reliable, and relevant memories over stale or weakly supported memories, so that Hermes does not answer from outdated facts just because they are semantically similar.

**Why this priority**: Vector similarity answers "is this about the same topic?" but not "is this still true?" Time-aware reranking is required for trustworthy long-term memory.

**Independent Test**: Can be tested with controlled memories that have different timestamps, lifecycle states, confidence values, feedback scores, and supersession links, then verifying the ranked output prefers current high-confidence facts.

**Acceptance Scenarios**:

1. **Given** an older memory says "I buy coconut water after runs" and a newer memory says "I now buy soy milk after runs", **When** the user asks what they drink after running, **Then** the newer memory ranks first and the older memory is marked as superseded or lower-confidence historical context.
2. **Given** two semantically similar memories differ in `confidence`, `feedback_score`, and `evidence_count`, **When** hybrid rerank runs, **Then** the better-supported memory ranks higher.
3. **Given** a memory is tagged as a short-lived recent state, **When** its `valid_until` has passed, **Then** it does not outrank stable current memories.

---

### User Story 4 - Keep Embeddings Local-Controlled And Auditable (Priority: P2)

As a Hermes user, I want embedding generation and semantic recall to be configurable and auditable so that I can understand which model/index was used and avoid accidental external disclosure of personal memories.

**Why this priority**: Embeddings are derived from personal memory content. The plugin must make provider choice explicit and keep enough metadata to rebuild or audit the semantic index.

**Independent Test**: Can be tested with a fake local embedding provider, an unavailable provider, and changed provider metadata, verifying the system records provider/version metadata and fails closed to lexical recall when embedding is unavailable.

**Acceptance Scenarios**:

1. **Given** no embedding provider is configured, **When** recall runs, **Then** lexical recall continues to work and the result explains semantic recall was unavailable.
2. **Given** a fake embedding provider is configured, **When** a memory is stored or indexed, **Then** the embedding metadata records provider name, model id, vector dimension, and content hash.
3. **Given** an embedding model id or dimension changes, **When** recall runs, **Then** stale embeddings are ignored or scheduled for rebuild rather than mixed with incompatible vectors.
4. **Given** a restricted memory exists, **When** embeddings are generated, **Then** the system does not send its raw content to an external provider.

---

### User Story 5 - Integrate With Automatic Activation (Priority: P2)

As a Hermes user, I want the automatic memory activation feature to benefit from improved recall without changing its safety gate or injection limits.

**Why this priority**: `002-memory-activation` is now the normal path for pre-answer memory use. Hybrid recall must improve that path while preserving fail-closed behavior.

**Independent Test**: Can be tested by storing paraphrased memories, running `build_activation_context()`, and verifying the injected memory context uses hybrid recall but still respects max-count, budget, and safety filters.

**Acceptance Scenarios**:

1. **Given** activation decides a life-memory question should recall memory, **When** the query is a paraphrase, **Then** activation can inject a semantically matching safe memory.
2. **Given** hybrid recall fails because embeddings are unavailable, **When** activation runs, **Then** it falls back to lexical recall or injects nothing; it never breaks the LLM call.
3. **Given** many semantic candidates match broadly, **When** activation formats injected context, **Then** it still injects only the configured top safe memories.

---

### Edge Cases

- Embedding provider is unavailable, slow, misconfigured, or returns invalid dimensions.
- Existing memories have no embeddings yet because they were created before this feature.
- Embedding metadata is stale because the model id, provider, dimension, or content hash changed.
- Vector similarity returns semantically broad but non-answering memories.
- Lexical recall and vector recall disagree strongly on the best candidate.
- Query is too short, ambiguous, or mostly generic terms such as "what about that?".
- Memory content is sensitive, restricted, deleted, expired, archived, or superseded.
- The database contains thousands of memories and only some have embeddings.
- The user asks for historical memory rather than current facts.
- Automatic activation must stay bounded even when vector recall returns many candidates.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide a hybrid recall path that can combine lexical candidates and semantic/vector candidates for life-memory recall.
- **FR-002**: The system MUST keep SQLite `life_memory.db` as the source of truth; embeddings MUST be treated as a derived index only.
- **FR-003**: The system MUST preserve existing explicit `life_memory_recall` behavior and remain backward compatible when embeddings are unavailable.
- **FR-004**: The system MUST expose deterministic test seams for embedding generation so tests can use a fake provider without network or external model calls.
- **FR-005**: The system MUST store enough embedding metadata to validate provider, model id, vector dimension, content hash, and freshness.
- **FR-006**: The system MUST ignore or rebuild stale embeddings when memory content hash, provider, model id, or vector dimension no longer matches the active configuration.
- **FR-007**: The system MUST never use vector similarity alone to bypass lifecycle, sensitivity, deletion, expiry, or supersession filters.
- **FR-008**: The system MUST merge lexical and vector candidate sets without duplicate memory entries.
- **FR-009**: The system MUST produce explainable score components for returned memories, including lexical contribution, semantic contribution when available, and metadata/time contribution.
- **FR-010**: The system MUST rerank candidates using relevance, confidence, importance, feedback score, evidence count, lifecycle status, temporal validity, and supersession state.
- **FR-011**: The system MUST prefer current non-superseded memories over older superseded memories in normal recall.
- **FR-012**: The system MUST support a lexical-only fallback when embeddings are disabled or unavailable.
- **FR-013**: The system MUST make embedding provider behavior configurable so a local/fake provider can be used without sending memory content externally.
- **FR-014**: The system MUST avoid sending restricted raw content to an external embedding provider.
- **FR-015**: The system MUST keep automatic activation fail-closed and bounded when hybrid recall is used by `build_activation_context()`.
- **FR-016**: The system MUST include unit tests for embedding metadata validation, vector similarity, candidate merging, stale embedding behavior, and reranking.
- **FR-017**: The system MUST include integration tests proving paraphrased recall improves over lexical-only behavior without weakening privacy filters.
- **FR-018**: The system MUST include performance smoke coverage showing hybrid recall remains bounded with a large memory set.
- **FR-019**: The system MUST document how to enable, disable, rebuild, and audit the semantic index.
- **FR-020**: The system MUST preserve existing full-suite validation with `uv run python -m pytest`.

### Non-Goals

- **NG-001**: This stage does not make a vector database the source of truth for memory.
- **NG-002**: This stage does not require a cloud embedding service.
- **NG-003**: This stage does not modify Hermes core source files.
- **NG-004**: This stage does not change the `002-memory-activation` decision gate semantics.
- **NG-005**: This stage does not implement Markdown-to-SQLite reverse sync.
- **NG-006**: This stage does not add autonomous tool execution based on recalled memories.
- **NG-007**: This stage does not rely on opaque model reranking for safety-critical filtering.

### Key Entities *(include if feature involves data)*

- **Embedding Provider**: A configurable component that converts text into numeric vectors. It includes provider name, model id, dimension, locality policy, and availability status.
- **Memory Embedding**: A derived semantic index row for a `life_memories` record, including `memory_id`, vector, provider, model id, dimension, content hash, and timestamps.
- **Hybrid Recall Query**: A normalized query with lexical tokens, optional query embedding, recall mode, and safety/temporal options.
- **Hybrid Candidate**: A candidate memory produced by lexical recall, vector recall, or both, with merged score components and explanation metadata.
- **Rerank Result**: The final ordered memory result after lifecycle, sensitivity, temporal, and metadata scoring have been applied.
- **Index Rebuild Report**: An audit summary describing how many memories have fresh, stale, missing, skipped, or failed embeddings.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In a fixture set of paraphrased life-memory queries, hybrid recall returns the expected memory in the top 3 for at least 85% of cases.
- **SC-002**: In the same fixture set, hybrid recall improves top-3 recall over lexical-only recall by at least 20 percentage points or documents why the baseline is already saturated.
- **SC-003**: 100% of privacy/lifecycle tests exclude deleted, expired, restricted, unauthorized sensitive, and superseded-current memories from normal automatic injection.
- **SC-004**: 100% of returned hybrid recall results include explainable score components.
- **SC-005**: When embeddings are unavailable, explicit recall and automatic activation continue without raising and fall back to lexical behavior.
- **SC-006**: Stale or incompatible embeddings are never mixed into active vector search in tests.
- **SC-007**: Hybrid recall remains bounded in performance smoke tests with at least 10,000 memories or the existing project performance scale.
- **SC-008**: Existing `uv run python -m pytest` remains fully passing after implementation.

## Assumptions

- The project remains a local-first single-user Hermes plugin.
- Existing `life_memory.db` schema, recall filters, lifecycle states, `memory_links`, and activation hook are available from `001` and `002`.
- Tests should not require network access or paid model APIs; fake deterministic embeddings must be sufficient for correctness tests.
- If a real embedding provider is later used, provider configuration must make external disclosure explicit.
- Semantic recall improves candidate discovery, while lifecycle and temporal logic decide whether a memory is current enough to trust.
