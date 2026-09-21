# Research: Hybrid Recall For Life Memory

## Decision 1: Treat embeddings as a derived index, not memory truth

**Decision**: Keep `life_memories` as the authoritative memory table. Add a separate embedding index keyed by `memory_id` and content hash.

**Rationale**: Vectors are lossy semantic indexes. They can help find related memories, but they cannot represent lifecycle state, source evidence, sensitivity, validity windows, feedback, or supersession relationships. The existing repository already has the fields required for trust decisions.

**Alternatives Considered**:

- Make a vector database the memory store: rejected because it would duplicate or weaken the structured state model built in `001`.
- Store only vectors and summaries: rejected because review, deletion, audit, and exact recall need source memory rows.

## Decision 2: Use a provider interface with fake deterministic embeddings for tests

**Decision**: Define an embedding provider interface and ship a fake deterministic provider for tests and offline smoke. Real providers can be added later behind the same interface.

**Rationale**: Correctness tests must not depend on network, paid APIs, or non-deterministic model behavior. A provider seam lets tests verify candidate merge, stale metadata, fallback, and rerank behavior without external services.

**Alternatives Considered**:

- Directly call a cloud embedding API: rejected because tests would be slow, costly, and privacy-sensitive.
- Add a mandatory local model dependency: rejected for this prototype because runtime dependencies are currently empty and the user may not have local model assets.

## Decision 3: Store embedding freshness metadata

**Decision**: Each embedding row must store provider name, model id, dimension, content hash, and timestamps. Hybrid recall must ignore incompatible or stale rows.

**Rationale**: Vector dimensions and embedding spaces are not interchangeable. A memory edited after embedding generation must not be searched using an old vector. Content hash already exists in `life_memories`, making freshness checks straightforward.

**Alternatives Considered**:

- Store only `memory_id` and vector: rejected because stale or incompatible embeddings would be indistinguishable from current ones.
- Rebuild all embeddings every run: rejected because it is wasteful and unnecessary for unchanged memories.

## Decision 4: Merge lexical and vector candidates before reranking

**Decision**: Run bounded lexical recall and bounded vector recall, merge by `memory_id`, then compute a final score from explainable components.

**Rationale**: Lexical recall is strong for exact names, rare terms, tags, and Chinese n-grams. Vector recall is strong for paraphrase. Combining both reduces failure modes.

**Alternatives Considered**:

- Replace lexical recall with vector recall: rejected because exact keyword behavior and existing tests must remain stable.
- Use vector recall only after lexical failure: rejected because lexical and vector signals together produce better ranking and explanations.

## Decision 5: Time-aware rerank is separate from vector similarity

**Decision**: Use vector similarity only as a semantic relevance component. Currentness and trust must come from lifecycle status, `valid_until`, `last_confirmed_at`, `updated_at`, feedback, confidence, evidence, and `memory_links` supersession relationships.

**Rationale**: Vector search can find old and new memories about the same topic but cannot know which is current. The memory system already encodes temporal and lifecycle signals.

**Alternatives Considered**:

- Assume newer vectors are better: rejected because an older stable fact may remain true, and a newer low-confidence memory may be noise.
- Let an LLM choose current facts: rejected for this phase because safety-critical filtering should remain deterministic and testable.

## Decision 6: Preserve activation fail-closed behavior

**Decision**: `002-memory-activation` may use hybrid recall, but if embeddings fail or return no usable candidates, activation must fall back to lexical behavior or inject nothing.

**Rationale**: Pre-LLM hooks must not block model calls. Automatic memory injection carries privacy risk, so the safe default is no memory context.

**Alternatives Considered**:

- Raise embedding errors to callers: rejected because hook failures would break normal conversations.
- Inject broad semantic matches when uncertain: rejected because this increases irrelevant or private context leakage.

## Decision 7: Keep first implementation dependency-free

**Decision**: The initial production path should be implementable with only standard-library vector math and SQLite. If a real embedding provider is later introduced, it should remain optional.

**Rationale**: The existing project has no runtime dependencies. The next feature should not force packaging, installation, or privacy complexity before the indexing and reranking architecture is proven.

**Alternatives Considered**:

- Add FAISS, sqlite-vss, or a vector DB immediately: rejected because it increases setup cost and makes local user-plugin deployment harder.
- Add a model reranker immediately: rejected because deterministic score components are easier to audit and test first.
