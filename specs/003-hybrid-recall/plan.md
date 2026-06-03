# Implementation Plan: Hybrid Recall For Life Memory

**Branch**: `003-hybrid-recall` | **Date**: 2026-06-03 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/003-hybrid-recall/spec.md`

## Summary

This phase upgrades `life_memory` recall from lexical-only ranking to hybrid recall. The implementation will keep the existing SQLite memory rows as the source of truth, add a derived semantic index for embeddings, merge lexical and vector candidates, and rerank with explainable score components that include relevance, confidence, importance, feedback, lifecycle state, temporal validity, and supersession links.

The feature must improve paraphrased recall without weakening `001` storage/privacy boundaries or `002` automatic activation safety. Embeddings are an optional index: if embedding generation or search is unavailable, explicit recall and automatic activation must fall back to lexical behavior.

## Technical Context

**Language/Version**: Python 3.11+, matching the current Hermes plugin runtime.

**Primary Dependencies**: Python standard library only for the first implementation path. Runtime code should use `dataclasses`, `math`, `sqlite3`, `json`, and existing plugin modules. No mandatory third-party embedding/vector dependency in this phase. Tests use the existing `pytest` setup.

**Storage**: Existing `$HERMES_HOME/life_memory.db` remains the source of truth. Add a derived SQLite table for memory embeddings and metadata. Vectors may be serialized as JSON text for prototype simplicity unless implementation evidence shows a compact binary encoding is needed.

**Testing**: `uv run python -m pytest`; add unit tests for embeddings, hybrid recall, rerank, repository embedding helpers, and activation integration; add integration tests with temporary `HERMES_HOME` and fake deterministic embeddings.

**Target Platform**: macOS local Hermes profile first, compatible with standalone user plugin layout.

**Project Type**: Python package/plugin under `plugins/life_memory`, with tests under `tests/` and feature docs under `specs/003-hybrid-recall/`.

**Performance Goals**:

- Preserve existing lexical recall fallback latency and behavior.
- Keep hybrid candidate fetching bounded by configurable limits.
- Support the existing project smoke scale of 10,000 memories.
- Avoid model calls in default tests and default offline behavior.
- Ensure automatic activation remains bounded by `002` injection count and context budget.

**Constraints**:

- Do not modify Hermes core source files.
- Do not make embeddings or a vector index the source of truth.
- Do not require network access or cloud APIs for tests.
- Do not send restricted raw content to an external embedding provider.
- Do not bypass existing lifecycle, sensitivity, expiry, deletion, or supersession filters.
- Do not use opaque model reranking for safety-critical filtering.
- Preserve backward compatibility for `life_memory_recall` and `build_activation_context()`.

**Scale/Scope**: Single-user local profile, existing 10,000-row performance smoke target, bounded top-k hybrid candidate search.

## Constitution Check

Current `.specify/memory/constitution.md` is still the Spec Kit placeholder, so this plan uses the established project gates from `001` and `002`:

- **Plugin boundary**: PASS. Work remains inside `/Users/oliver/Projects/hermes-life-memory` and the standalone user plugin.
- **No Hermes core edits**: PASS. Recall and activation integration happen in plugin modules only.
- **Local-first storage**: PASS. SQLite remains the source of truth; embeddings are derived metadata.
- **Safety boundary**: PASS. Existing privacy/lifecycle filters remain mandatory after vector candidate discovery.
- **Auditability**: PASS. Hybrid results expose score components; index rebuild status is documented and testable.
- **Prototype simplicity**: PASS. Fake deterministic embeddings and JSON-serialized vectors avoid mandatory external dependencies.

Post-design re-check: PASS. Phase 1 design artifacts preserve the same constraints and add no required third-party runtime dependency.

## Project Structure

### Documentation (this feature)

```text
specs/003-hybrid-recall/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── hybrid-recall.md
└── tasks.md
```

### Source Code (repository root)

```text
plugins/life_memory/
├── embeddings.py       # New: provider protocol, fake/local deterministic provider, vector utilities
├── hybrid_recall.py    # New: candidate merge, score components, time-aware rerank
├── recall.py           # Update: expose hybrid path while preserving lexical fallback
├── repository.py       # Update: embedding table, freshness helpers, vector candidate queries
├── activation.py       # Update only if needed to call hybrid recall through existing selection path
├── models.py           # Update only if trace/enums/config dataclasses are needed
└── __init__.py         # Update only if tool docs or handler wiring needs to expose hybrid options

tests/
├── fixtures/
│   └── hybrid_recall_cases.json
├── unit/
│   ├── test_embeddings.py
│   ├── test_hybrid_recall.py
│   ├── test_recall.py
│   └── test_repository.py
└── integration/
    ├── test_hybrid_recall.py
    └── test_activation_hook.py
```

**Structure Decision**: Add focused `embeddings.py` and `hybrid_recall.py` modules instead of expanding `recall.py` into a mixed indexing/ranking engine. `recall.py` should remain the public recall adapter and lexical fallback. `repository.py` owns SQLite persistence for derived embeddings. `activation.py` should consume the upgraded recall behavior through a narrow API so the `002` gate and injection filters remain intact.

## Phase 0 Research Output

See [research.md](./research.md). Key decisions:

- Use fake deterministic embeddings for tests and default offline correctness.
- Store embeddings as a derived SQLite index with provider/model/dimension/content-hash metadata.
- Merge lexical and vector candidates before rerank; never trust vector results as current facts.
- Apply lifecycle/privacy filters before final results and before automatic injection.
- Use explainable weighted rerank before considering any future model rerank.

## Phase 1 Design Output

- Data model: [data-model.md](./data-model.md)
- Contract: [contracts/hybrid-recall.md](./contracts/hybrid-recall.md)
- Validation guide: [quickstart.md](./quickstart.md)

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| None | N/A | N/A |
