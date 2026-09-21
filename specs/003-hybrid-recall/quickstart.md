# Quickstart: Hybrid Recall For Life Memory

This quickstart validates the implemented `003-hybrid-recall` feature. It assumes `001-life-memory-plugin` and `002-memory-activation` are already working.

## 1. Repository

```bash
cd /Users/oliver/Projects/hermes-life-memory
```

Expected branch:

```bash
git branch --show-current
# expected: 003-hybrid-recall
```

## 2. Spec Prerequisites

```bash
bash .specify/scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks
```

Latest validation:

```text
2026-06-03 Australia/Sydney
FEATURE_DIR=/Users/oliver/Projects/hermes-life-memory/specs/003-hybrid-recall
AVAILABLE_DOCS includes research.md, data-model.md, contracts/, quickstart.md, tasks.md
```

## 3. Unit Checks

Run embedding and hybrid recall unit tests:

```bash
uv run python -m pytest tests/unit/test_embeddings.py tests/unit/test_hybrid_recall.py
```

Latest validation:

```text
2026-06-03 Australia/Sydney
uv run python -m pytest tests/unit/test_embeddings.py tests/unit/test_hybrid_recall.py tests/integration/test_hybrid_recall_flow.py tests/integration/test_activation_hook.py tests/unit/test_recall.py
37 passed in 0.36s
```

Covered behavior:

- fake embedding provider is deterministic;
- invalid vector dimensions are rejected;
- stale embeddings are ignored;
- lexical and vector candidates merge by `memory_id`;
- score components are present and explainable;
- superseded and expired memories are down-ranked or filtered according to mode.

## 4. Integration Checks

Run hybrid recall integration tests:

```bash
uv run python -m pytest tests/integration/test_hybrid_recall_flow.py
```

Expected behavior:

- paraphrased English and Chinese queries return expected memories;
- hybrid top-3 recall improves over lexical-only fixture baseline;
- deleted, expired, restricted, unauthorized sensitive, and superseded-current memories do not appear in normal automatic injection;
- unavailable embeddings fall back to lexical recall;
- large memory set smoke remains bounded;
- existing 10,000-row handler smoke now exercises the default hybrid recall handler with lexical fallback, while `test_large_hybrid_recall_smoke_is_bounded` covers fresh semantic-index candidates.

## 5. Activation Regression

```bash
uv run python -m pytest tests/integration/test_activation_hook.py tests/unit/test_activation.py
```

Expected behavior:

- `pre_llm_call` activation still fails closed;
- injected memory block remains data-only;
- max memory count and character budget are preserved;
- paraphrased life-memory question can use hybrid recall when semantic index is available.

## 6. Full Suite

```bash
uv run python -m pytest
```

Latest validation:

```text
2026-06-06 Australia/Sydney
uv run python -m pytest
137 passed in 0.75s
Python 3.11.15, pytest 9.0.3
```

## 7. Manual Hermes Smoke Test

Mount and enable the plugin as before, then run:

```bash
hermes -z
```

Store a unique memory:

```text
请记住：我周六下午慢跑后通常买无糖豆浆，测试标记是 HYBRID_RECALL_MARKER。
```

Ask with a paraphrase:

```text
我运动完一般喝什么？请直接回答。
```

Expected behavior:

- Hermes can answer using the soy-milk memory without exact lexical overlap;
- no deleted, restricted, or expired content is injected;
- trace or recall output can show semantic/hybrid score components when inspected;
- no native technical memory receives the life-memory fact.

## 8. Index Audit

Expected implementation should provide a way to inspect or rebuild the semantic index. The report should show counts similar to:

```text
indexed_count: N
fresh_count: N
stale_count: 0
skipped_count: 0
failed_count: 0
```

The report must not include restricted raw content.

## 9. Current Implementation Note

This stage currently uses a deterministic local fake embedding provider and SQLite JSON vector storage. That proves the hybrid recall architecture, score merging, stale-index handling, and activation integration without adding mandatory external model or vector database dependencies. A real local or external embedding provider can be added later behind the provider interface.

Latest manual result:

```text
2026-06-03 Australia/Sydney
Hermes CLI: /Users/oliver/.local/bin/hermes
Hermes version: Hermes Agent v0.15.1 (2026.5.29)
Plugin mount: /Users/oliver/.hermes/plugins/life_memory -> /Users/oliver/Projects/hermes-life-memory/plugins/life_memory
Marker: HYBRID_RECALL_MARKER_20260603_210840
Stored memory_id: mem_0870dbcadc7347dab6a451fd7abd577f
Stored content: 周六下午慢跑后，通常会买无糖豆浆
Embedding provider/model/status: fake-semantic / fake-semantic-v1 / ready
Prompt: 我运动完一般喝什么？请直接回答。
Response: 你运动完一般都喝无糖豆浆（尤其是周六下午慢跑后会买）喵。
Activation trace_id: trace_3ab4e91d6ce64f3281179beb437bbe06
Activation outcome: injected
Injected memory ids: ["mem_0870dbcadc7347dab6a451fd7abd577f"]
Context chars: 522
Cleanup trace_id: trace_b5761ac660ac4ee09a1961dc232f9d92
Cleanup outcome: smoke memory soft-deleted after verification
```

Observation: the smoke memory was stored through Hermes, indexed in `memory_embeddings`, recalled through automatic `pre_llm_call` activation for a paraphrased Chinese query, then soft-deleted through `life_memory_forget`.
