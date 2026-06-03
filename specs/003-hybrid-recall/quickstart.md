# Quickstart: Hybrid Recall For Life Memory

This quickstart will validate the `003-hybrid-recall` feature after implementation. It assumes `001-life-memory-plugin` and `002-memory-activation` are already working.

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

Expected after tasks are generated:

```text
FEATURE_DIR resolves to specs/003-hybrid-recall
AVAILABLE_DOCS includes research.md, data-model.md, contracts/, quickstart.md, tasks.md
```

## 3. Unit Checks

Run embedding and hybrid recall unit tests:

```bash
uv run python -m pytest tests/unit/test_embeddings.py tests/unit/test_hybrid_recall.py
```

Expected behavior:

- fake embedding provider is deterministic;
- invalid vector dimensions are rejected;
- stale embeddings are ignored;
- lexical and vector candidates merge by `memory_id`;
- score components are present and explainable;
- superseded and expired memories are down-ranked or filtered according to mode.

## 4. Integration Checks

Run hybrid recall integration tests:

```bash
uv run python -m pytest tests/integration/test_hybrid_recall.py
```

Expected behavior:

- paraphrased English and Chinese queries return expected memories;
- hybrid top-3 recall improves over lexical-only fixture baseline;
- deleted, expired, restricted, unauthorized sensitive, and superseded-current memories do not appear in normal automatic injection;
- unavailable embeddings fall back to lexical recall;
- large memory set smoke remains bounded.

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

Expected final validation:

```text
All tests pass.
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

Expected behavior after implementation:

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
