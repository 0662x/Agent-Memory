# Tasks: Hybrid Recall For Life Memory

**Input**: Design documents from `/specs/003-hybrid-recall/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/hybrid-recall.md`, `quickstart.md`

**Tests**: This feature explicitly requires unit, integration, fixture-driven evaluation, activation regression, performance smoke, and full-suite validation. Test tasks are listed before the implementation tasks they verify.

**Organization**: Tasks are grouped by user story so each increment can be implemented and tested independently.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel when dependencies for the phase are met and files do not overlap.
- **[Story]**: Maps to user stories in `spec.md`, for example `[US1]`.
- Each task includes exact repository-relative file paths.

## Phase 1: Setup

**Purpose**: Add hybrid recall fixtures and confirm Spec Kit resolves this feature.

- [x] T001 [P] Create `tests/fixtures/hybrid_recall_cases.json` with English paraphrase cases, Chinese paraphrase cases, lexical distractors, stale/current pairs, and expected top memory ids.
- [x] T002 [P] Add a short implementation-status note to `specs/003-hybrid-recall/quickstart.md` saying hybrid recall is planned until tasks are implemented.
- [x] T003 Run `bash .specify/scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks` and verify it resolves `specs/003-hybrid-recall`.
- [x] T004 Run `uv run python -m pytest` to record the pre-feature baseline.

**Checkpoint**: The feature has fixture inputs, baseline tests pass, and Spec Kit points at `003-hybrid-recall`.

---

## Phase 2: Foundational

**Purpose**: Create shared embedding/vector primitives, repository embedding schema helpers, and hybrid recall result types required by all user stories.

**Critical**: No user story implementation should start until this phase is complete.

### Tests For Foundation

- [x] T005 [P] Add `tests/unit/test_embeddings.py` covering deterministic fake embeddings, provider metadata, invalid dimensions, non-finite values, empty vectors, vector normalization, and cosine similarity.
- [x] T006 [P] Add `tests/unit/test_repository.py` coverage for `memory_embeddings` schema creation, upsert, fetch, stale detection, incompatible provider/model/dimension rejection, and skipped/failed statuses.
- [x] T007 [P] Add `tests/unit/test_hybrid_recall.py` coverage for stable dataclass/result shapes and score component serialization.
- [x] T008 [P] Add `tests/fixtures/hybrid_recall_cases.json` loader tests in `tests/unit/test_hybrid_recall.py` to validate fixture schema before implementation.

### Implementation For Foundation

- [x] T009 Create `plugins/life_memory/embeddings.py` with `EmbeddingProvider`, provider metadata, `FakeEmbeddingProvider`, vector validation, normalization, cosine similarity, and bounded text preparation.
- [x] T010 Create `plugins/life_memory/hybrid_recall.py` with shared dataclasses or typed dictionaries for `HybridRecallQuery`, `HybridCandidate`, score components, and `HybridRecallResult` conversion.
- [x] T011 Update `plugins/life_memory/repository.py` to create `memory_embeddings` with indexes described in `specs/003-hybrid-recall/data-model.md`.
- [x] T012 Update `plugins/life_memory/repository.py` with helpers for upserting, fetching, listing, marking stale, and summarizing memory embeddings.
- [x] T013 Ensure repository initialization migrates existing databases safely without dropping any `life_memories` data.
- [x] T014 Run `uv run python -m pytest tests/unit/test_embeddings.py tests/unit/test_repository.py tests/unit/test_hybrid_recall.py -k 'embedding or vector or shape or fixture'` and verify foundation tests pass.

**Checkpoint**: Embedding primitives and SQLite derived-index helpers exist, with no changes to public recall behavior yet.

---

## Phase 3: User Story 1 - Recall Semantically Similar Memories (Priority: P1)

**Goal**: Find relevant memories under paraphrased English and Chinese queries by combining lexical and vector candidates.

**Independent Test**: Fake deterministic embeddings can index temporary memories and prove paraphrased queries return expected memories above lexical distractors.

### Tests For User Story 1

- [x] T015 [P] [US1] Add unit tests in `tests/unit/test_hybrid_recall.py` for vector candidate retrieval from fresh embeddings.
- [x] T016 [P] [US1] Add unit tests in `tests/unit/test_hybrid_recall.py` for lexical/vector candidate merge by `memory_id` without duplicates.
- [x] T017 [P] [US1] Add fixture-driven paraphrase ranking tests in `tests/unit/test_hybrid_recall.py` using `tests/fixtures/hybrid_recall_cases.json`.
- [x] T018 [US1] Add integration tests in `tests/integration/test_hybrid_recall_flow.py` proving English paraphrased query returns the expected memory in top 3.
- [x] T019 [US1] Add integration tests in `tests/integration/test_hybrid_recall_flow.py` proving Chinese paraphrased query returns the expected memory in top 3.
- [x] T020 [US1] Add regression tests in `tests/unit/test_recall.py` proving lexical-only recall still works when semantic recall is disabled.

### Implementation For User Story 1

- [x] T021 [US1] Implement query embedding and vector candidate lookup in `plugins/life_memory/hybrid_recall.py` using `LifeMemoryRepository` embedding helpers.
- [x] T022 [US1] Implement lexical/vector candidate merge in `plugins/life_memory/hybrid_recall.py` with recall sources and raw score components.
- [x] T023 [US1] Implement `hybrid_rank_memories()` in `plugins/life_memory/hybrid_recall.py` with bounded `limit` and `candidate_limit`.
- [x] T024 [US1] Update `plugins/life_memory/recall.py` to expose a hybrid recall adapter while preserving existing `rank_memories()` lexical behavior.
- [x] T025 [US1] Update `plugins/life_memory/__init__.py` `life_memory_recall` handler to accept optional `recall_mode`, `semantic`, and `candidate_limit` fields without breaking old payloads.
- [x] T026 [US1] Run `uv run python -m pytest tests/unit/test_hybrid_recall.py tests/integration/test_hybrid_recall_flow.py tests/unit/test_recall.py -k 'semantic or paraphrase or lexical or merge'` and verify US1 tests pass.

**Checkpoint**: Hybrid recall can find paraphrased memories and lexical fallback remains intact.

---

## Phase 4: User Story 2 - Preserve Privacy And Lifecycle Boundaries (Priority: P1)

**Goal**: Ensure vector retrieval never bypasses deletion, expiry, sensitivity, archive, or supersession boundaries.

**Independent Test**: Seed disallowed memories with fresh embeddings and prove they do not appear in normal hybrid recall or automatic injection.

### Tests For User Story 2

- [x] T027 [P] [US2] Add unit tests in `tests/unit/test_hybrid_recall.py` proving deleted, archived-by-default, expired, restricted, and unauthorized sensitive semantic candidates are filtered.
- [x] T028 [P] [US2] Add unit tests in `tests/unit/test_hybrid_recall.py` proving external providers skip restricted raw content during indexing.
- [x] T029 [P] [US2] Add integration tests in `tests/integration/test_hybrid_recall_flow.py` proving disallowed memories with fresh embeddings are excluded from normal recall.
- [x] T030 [P] [US2] Add activation regression tests in `tests/integration/test_activation_hook.py` proving hybrid recall does not inject restricted, sensitive, expired, or deleted semantic matches.
- [x] T031 [P] [US2] Add tests in `tests/unit/test_repository.py` proving embeddings for deleted or stale memories are not returned as searchable rows.

### Implementation For User Story 2

- [x] T032 [US2] Implement lifecycle and sensitivity filtering for vector candidates in `plugins/life_memory/hybrid_recall.py`, reusing existing recall semantics.
- [x] T033 [US2] Implement external-provider indexing guardrails in `plugins/life_memory/embeddings.py` or repository indexing helpers.
- [x] T034 [US2] Ensure `plugins/life_memory/repository.py` fresh embedding queries join current `life_memories` metadata and ignore deleted/stale/incompatible rows.
- [x] T035 [US2] Ensure automatic activation still applies `is_memory_injectable()` after hybrid candidate discovery.
- [x] T036 [US2] Run `uv run python -m pytest tests/unit/test_hybrid_recall.py tests/integration/test_hybrid_recall_flow.py tests/integration/test_activation_hook.py -k 'deleted or expired or restricted or sensitive or privacy or stale'` and verify US2 tests pass.

**Checkpoint**: Semantic search is no less private or lifecycle-aware than lexical recall and activation injection.

---

## Phase 5: User Story 3 - Rerank With Time-Aware Evidence (Priority: P1)

**Goal**: Prefer current, reliable memories over stale or weak memories when semantic similarity is broad.

**Independent Test**: Controlled old/new memory pairs and confidence/evidence variations prove the final ranking prefers current supported facts.

### Tests For User Story 3

- [x] T037 [P] [US3] Add unit tests in `tests/unit/test_hybrid_recall.py` for score component weighting: lexical, semantic, metadata, temporal, and final score.
- [x] T038 [P] [US3] Add unit tests in `tests/unit/test_hybrid_recall.py` proving newer non-superseded current memories outrank older superseded memories.
- [x] T039 [P] [US3] Add unit tests in `tests/unit/test_hybrid_recall.py` proving confidence, feedback, evidence count, and importance affect ranking predictably.
- [x] T040 [P] [US3] Add integration tests in `tests/integration/test_hybrid_recall_flow.py` for coconut-water-to-soy-milk replacement behavior.
- [x] T041 [P] [US3] Add tests proving expired `recent_state` memories do not outrank stable current memories.

### Implementation For User Story 3

- [x] T042 [US3] Implement score component calculation in `plugins/life_memory/hybrid_recall.py` with explainable numeric fields.
- [x] T043 [US3] Implement supersession-aware ranking using `memory_links` in `plugins/life_memory/hybrid_recall.py` or a repository helper.
- [x] T044 [US3] Implement temporal scoring from `valid_until`, `last_confirmed_at`, `updated_at`, lifecycle status, and historical mode.
- [x] T045 [US3] Add final relevance reason formatting that mentions semantic, lexical, and temporal evidence without exposing hidden/private data.
- [x] T046 [US3] Run `uv run python -m pytest tests/unit/test_hybrid_recall.py tests/integration/test_hybrid_recall_flow.py -k 'rerank or temporal or superseded or current or score'` and verify US3 tests pass.

**Checkpoint**: Hybrid recall ranks by semantic relevance and current trust, not vector similarity alone.

---

## Phase 6: User Story 4 - Keep Embeddings Local-Controlled And Auditable (Priority: P2)

**Goal**: Make embedding generation configurable, rebuildable, and auditable without leaking restricted content.

**Independent Test**: Fake provider, unavailable provider, changed metadata, and rebuild reports can be tested without network access.

### Tests For User Story 4

- [x] T047 [P] [US4] Add unit tests in `tests/unit/test_embeddings.py` for unavailable provider fallback and provider locality metadata.
- [x] T048 [P] [US4] Add unit tests in `tests/unit/test_repository.py` for rebuild reports containing fresh, stale, skipped, and failed counts.
- [x] T049 [P] [US4] Add integration tests in `tests/integration/test_hybrid_recall_flow.py` proving provider/model/dimension changes ignore old embeddings until rebuilt.
- [x] T050 [P] [US4] Add tests proving rebuild reports and traces do not contain restricted raw content.
- [x] T051 [P] [US4] Add optional contract coverage in `tests/contract/test_tool_contracts.py` if `life_memory_recall` schema exposes `recall_mode`, `semantic`, or `candidate_limit`.

### Implementation For User Story 4

- [x] T052 [US4] Implement provider configuration helpers in `plugins/life_memory/embeddings.py` with lexical fallback when unavailable.
- [x] T053 [US4] Implement embedding rebuild/index report helpers in `plugins/life_memory/repository.py` or `plugins/life_memory/hybrid_recall.py`.
- [x] T054 [US4] Update `plugins/life_memory/contracts.py` if recall schema exposes hybrid options.
- [x] T055 [US4] Add trace or audit metadata for hybrid recall/index operations only if existing trace API can support it without schema changes.
- [x] T056 [US4] Run `uv run python -m pytest tests/unit/test_embeddings.py tests/unit/test_repository.py tests/integration/test_hybrid_recall_flow.py tests/contract/test_tool_contracts.py -k 'provider or rebuild or schema or audit or stale'` and verify US4 tests pass.

**Checkpoint**: Semantic index behavior is configurable, stale-safe, and auditable.

---

## Phase 7: User Story 5 - Integrate With Automatic Activation (Priority: P2)

**Goal**: Let `002-memory-activation` benefit from hybrid recall while preserving its gate, strict filters, fail-closed behavior, and injection budgets.

**Independent Test**: Activation can inject a safe paraphrased memory via hybrid recall and still fail closed when embeddings are unavailable.

### Tests For User Story 5

- [x] T057 [P] [US5] Add integration test in `tests/integration/test_activation_hook.py` proving paraphrased life-memory question injects expected memory when semantic index is available.
- [x] T058 [P] [US5] Add integration test in `tests/integration/test_activation_hook.py` proving embedding provider failure falls back to lexical or no context without raising.
- [x] T059 [P] [US5] Add regression tests in `tests/unit/test_activation.py` proving injected entries remain bounded and data-only with hybrid score fields present.
- [x] T060 [P] [US5] Add performance smoke in `tests/integration/test_hybrid_recall_flow.py` or `tests/integration/test_activation_hook.py` for large memory set hybrid activation.

### Implementation For User Story 5

- [x] T061 [US5] Update `plugins/life_memory/activation.py` to call hybrid recall through a narrow adapter when available, preserving `rank_memories()` fallback.
- [x] T062 [US5] Ensure `select_injectable_memories()` handles additive hybrid fields without changing injected block contract.
- [x] T063 [US5] Ensure hook failure handling still catches hybrid recall exceptions and returns routing guidance only.
- [x] T064 [US5] Run `uv run python -m pytest tests/integration/test_activation_hook.py tests/unit/test_activation.py -k 'hybrid or paraphrase or fallback or bounded'` and verify US5 tests pass.

**Checkpoint**: Automatic memory activation uses improved recall but remains as safe and bounded as `002`.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, validation, performance guardrails, and final smoke checks.

- [x] T065 [P] Update `README.md` with hybrid recall behavior, lexical fallback, semantic index safety, provider configuration, and audit guidance.
- [x] T066 [P] Update `specs/003-hybrid-recall/quickstart.md` with final implemented commands, expected test results, and manual Hermes smoke-test observations or blocker.
- [x] T067 [P] Review `specs/003-hybrid-recall/contracts/hybrid-recall.md` against final `life_memory_recall` schema and adjust only additive fields.
- [x] T068 Add performance smoke coverage proving hybrid recall remains bounded with at least 10,000 memories or the existing project performance scale.
- [x] T069 Run `uv run python -m pytest` and record the result in `README.md` and `specs/003-hybrid-recall/quickstart.md`.
- [ ] T070 Run manual Hermes smoke test from `specs/003-hybrid-recall/quickstart.md`, if Hermes runtime is available, and record outcome or blocker.
- [x] T071 Review `git status --short` and ensure only intended `003-hybrid-recall` files and code changes are staged.
- [ ] T072 Optional: add `specs/003-hybrid-recall/project-report.md` after implementation if a stage report is needed for review.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 Setup**: No dependencies.
- **Phase 2 Foundational**: Depends on Phase 1 and blocks all user stories.
- **Phase 3 US1**: Depends on Phase 2.
- **Phase 4 US2**: Depends on Phase 2 and should be validated before broad hybrid recall is used by activation.
- **Phase 5 US3**: Depends on US1 candidate merge and US2 lifecycle/privacy filtering.
- **Phase 6 US4**: Depends on embedding repository helpers from Phase 2 and can proceed after US1 basics.
- **Phase 7 US5**: Depends on US1, US2, and US3 core recall behavior.
- **Phase 8 Polish**: Depends on implemented user stories selected for this feature.

### User Story Dependency Graph

```text
Foundation
  └── US1 Semantic candidate recall
        ├── US2 Privacy/lifecycle boundaries
        └── US3 Time-aware rerank
              └── US5 Activation integration
        └── US4 Provider/index auditability
```

### MVP Scope

The independently useful MVP for this feature is **US1 + US2 + US3**:

1. Recall semantically similar memories.
2. Preserve privacy and lifecycle boundaries.
3. Rerank with currentness and reliability signals.

`US4` and `US5` should follow before considering the feature complete because operational use requires auditability and automatic activation integration.

---

## Parallel Opportunities

- T001 and T002 can run in parallel.
- T005, T006, T007, and T008 can run in parallel after Phase 1.
- T015 through T020 can run in parallel if test files are coordinated.
- T027 through T031 can run in parallel once foundation helpers exist.
- T037 through T041 can run in parallel after US1 candidate shape is stable.
- T047 through T051 can run in parallel after repository embedding helpers exist.
- T057 through T060 can run in parallel after hybrid recall API is stable.
- Documentation tasks T065 through T067 can run in parallel after implementation stabilizes.

---

## Implementation Strategy

### MVP First

1. Complete Phase 1 and Phase 2.
2. Implement and validate US1 semantic candidate recall.
3. Implement and validate US2 privacy/lifecycle boundaries.
4. Implement and validate US3 time-aware rerank.
5. Stop and run `uv run python -m pytest tests/unit/test_embeddings.py tests/unit/test_hybrid_recall.py tests/integration/test_hybrid_recall_flow.py`.

### Full Feature

1. Add US4 provider/index auditability.
2. Add US5 activation integration.
3. Run full `uv run python -m pytest`.
4. Run manual Hermes smoke test when runtime is available.
5. Update docs and commit with a clear `003-hybrid-recall` boundary.
