# Tasks: Memory Activation And Context Injection

**Input**: Design documents from `/specs/002-memory-activation/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/activation-hook.md`, `quickstart.md`

**Tests**: This feature explicitly requires unit, integration, fixture-driven activation evaluation, and full-suite validation. Test tasks are listed before the implementation tasks they verify.

**Organization**: Tasks are grouped by user story so each increment can be implemented and tested independently.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel when dependencies for the phase are met and files do not overlap.
- **[Story]**: Maps to user stories in `spec.md`, for example `[US1]`.
- Each task includes exact repository-relative file paths.

## Phase 1: Setup

**Purpose**: Add the activation evaluation fixture and confirm the feature branch resolves through Spec Kit.

- [x] T001 [P] Create `tests/fixtures/activation_cases.json` with positive life-memory activation cases, negative technical/project cases, temporary/no-save cases, malformed cases, and expected reason fragments.
- [x] T002 [P] Add a feature note to `specs/002-memory-activation/quickstart.md` documenting that activation is disabled until implementation is complete and tests are added.
- [x] T003 Run `bash .specify/scripts/bash/setup-tasks.sh --json` and verify it resolves `specs/002-memory-activation` before implementation begins.

**Checkpoint**: The feature has fixture inputs and Spec Kit points at `002-memory-activation`.

---

## Phase 2: Foundational

**Purpose**: Create shared activation types, policy defaults, hook payload normalization, and trace operation support required by all user stories.

**Critical**: No user story implementation should start until this phase is complete.

### Tests For Foundation

- [x] T004 [P] Add unit tests in `tests/unit/test_activation.py` for `InjectionPolicy` default clamping and malformed `ActivationContext` normalization.
- [x] T005 [P] Add unit tests in `tests/unit/test_activation.py` for stable activation result shapes: `ActivationDecision`, `InjectedMemoryEntry`, and `InjectedMemoryBlock`.

### Implementation For Foundation

- [x] T006 Create `plugins/life_memory/activation.py` with `ActivationDecision`, `ActivationContext`, `InjectionPolicy`, `InjectedMemoryEntry`, `InjectedMemoryBlock`, filter reason constants, and fail-closed result helpers.
- [x] T007 Update `plugins/life_memory/models.py` to add trace operation names for activation/context injection if the existing trace enum is used by repository trace writing.
- [x] T008 Implement hook payload normalization in `plugins/life_memory/activation.py`, extracting current user text from common hook payload shapes such as `message`, `messages`, `prompt`, `input`, and keyword arguments.
- [x] T009 Run `uv run python -m pytest tests/unit/test_activation.py` and confirm foundation tests pass or fail only on later story-specific assertions.

**Checkpoint**: Activation types and hook payload normalization exist and can be imported without touching routing behavior.

---

## Phase 3: User Story 1 - Decide When Life Memory Is Needed (Priority: P1)

**Goal**: Deterministically decide whether the current request should trigger life-memory recall.

**Independent Test**: `decide_activation()` can be tested with fixture cases without SQLite, Hermes, or hook integration.

### Tests For User Story 1

- [x] T010 [P] [US1] Add fixture-driven activation gate tests in `tests/unit/test_activation.py` using `tests/fixtures/activation_cases.json`.
- [x] T011 [P] [US1] Add explicit unit tests in `tests/unit/test_activation.py` for Chinese personal-life questions, English personal-life questions, technical/project questions, profile-only instructions, temporary working context, generic small talk, and malformed empty input.
- [x] T012 [P] [US1] Add regression tests in `tests/unit/test_activation.py` proving activation does not call repository recall when the decision is skip.

### Implementation For User Story 1

- [x] T013 [US1] Implement `decide_activation()` in `plugins/life_memory/activation.py` with rule-first personal-life, technical/project, profile-only, temporary/no-save, smalltalk, ambiguous, and malformed classifications.
- [x] T014 [US1] Add Chinese and English activation keywords/patterns in `plugins/life_memory/activation.py` for routines, habits, food/lifestyle preferences, relationships, life events, daily patterns, and remembered personal context.
- [x] T015 [US1] Reuse or align with `plugins/life_memory/classification.py` where appropriate so activation skips technical/user-profile/temporary/no-save boundaries consistently with store routing.
- [x] T016 [US1] Implement normalized query output and matched-term reasons in `plugins/life_memory/activation.py`.
- [x] T017 [US1] Run `uv run python -m pytest tests/unit/test_activation.py -k activation` and verify US1 tests pass.

**Checkpoint**: The plugin can decide when to activate life memory without performing recall.

---

## Phase 4: User Story 2 - Inject Safe Bounded Memory Context (Priority: P1)

**Goal**: Recall relevant memories after activation and format a small data-only context block with required metadata.

**Independent Test**: Temporary memory rows can be created and passed through the activation pipeline to produce a bounded context block.

### Tests For User Story 2

- [x] T018 [P] [US2] Add unit tests in `tests/unit/test_activation.py` for `format_injected_memory_block()` including the data-only boundary, `memory_id`, `status`, `confidence`, `sensitivity`, relevance reason, content truncation, and max block budget.
- [x] T019 [P] [US2] Add unit tests in `tests/unit/test_activation.py` for max memory count enforcement with more than three otherwise eligible candidates.
- [x] T020 [P] [US2] Add unit tests in `tests/unit/test_activation.py` for instruction-like memory content being omitted or marked with a `safety_note` as quoted data.
- [x] T021 [US2] Add integration test in `tests/integration/test_activation_hook.py` that stores normal life memories in temporary `HERMES_HOME`, runs the activation pipeline directly, and verifies a relevant question returns an injected block.
- [x] T022 [US2] Add integration test in `tests/integration/test_activation_hook.py` that a relevant question with no matching safe memories returns no context block.

### Implementation For User Story 2

- [x] T023 [US2] Implement `select_injectable_memories()` in `plugins/life_memory/activation.py`, reusing `LifeMemoryRepository.search_memories()` and `rank_memories()` from existing recall code.
- [x] T024 [US2] Implement `format_injected_memory_entry()` and `format_injected_memory_block()` in `plugins/life_memory/activation.py` using the contract in `specs/002-memory-activation/contracts/activation-hook.md`.
- [x] T025 [US2] Implement per-memory and full-block budget enforcement in `plugins/life_memory/activation.py` with stable `budget_exceeded` filter counts.
- [x] T026 [US2] Implement `build_activation_context()` in `plugins/life_memory/activation.py` to run normalize -> decide -> recall -> select -> format and return injected/skipped/not_found/fail-closed result dictionaries.
- [x] T027 [US2] Ensure `build_activation_context()` catches repository/formatting exceptions and returns an empty context instead of raising into the LLM-call path.
- [x] T028 [US2] Run `uv run python -m pytest tests/unit/test_activation.py tests/integration/test_activation_hook.py -k 'format or injected or bounded or not_found'` and verify US2 tests pass.

**Checkpoint**: Relevant safe memories can be converted into a bounded data-only context block without hook integration.

---

## Phase 5: User Story 3 - Enforce Privacy And Lifecycle Filters (Priority: P1)

**Goal**: Automatic injection excludes memories that should not silently enter prompt context.

**Independent Test**: Seed memories with lifecycle/sensitivity/link variations and prove disallowed rows never appear in injected context.

### Tests For User Story 3

- [x] T029 [P] [US3] Add unit tests in `tests/unit/test_activation.py` for filter reason codes: `deleted`, `archived`, `expired`, `restricted`, `sensitive_unauthorized`, `superseded`, `low_confidence`, `low_relevance`, `high_injection_risk`, `budget_exceeded`, and `malformed_memory`.
- [x] T030 [P] [US3] Add integration test in `tests/integration/test_activation_hook.py` proving deleted, archived, and expired memories are not injected even when query terms match.
- [x] T031 [P] [US3] Add integration test in `tests/integration/test_activation_hook.py` proving restricted and unauthorized sensitive memories do not inject raw content.
- [x] T032 [P] [US3] Add integration test in `tests/integration/test_activation_hook.py` proving superseded memories are not injected as current facts.
- [x] T033 [P] [US3] Add unit test in `tests/unit/test_activation.py` proving low-confidence young memories are excluded while high-confidence relevant young memories remain capped.

### Implementation For User Story 3

- [x] T034 [US3] Implement `is_memory_injectable()` in `plugins/life_memory/activation.py` with strict lifecycle, sensitivity, confidence, relevance, expiry, and injection-risk filtering.
- [x] T035 [US3] Add superseded-current-fact detection in `plugins/life_memory/activation.py` by consulting existing `memory_links` data or a small helper in `plugins/life_memory/repository.py` if no suitable helper exists.
- [x] T036 [US3] Ensure automatic injection defaults to `include_archived=false` and `allow_sensitive=false` even if explicit recall can support broader options.
- [x] T037 [US3] Ensure `young` memory injection uses stricter confidence/relevance thresholds and max count behavior than normal recall.
- [x] T038 [US3] Run `uv run python -m pytest tests/unit/test_activation.py tests/integration/test_activation_hook.py -k 'filter or sensitive or restricted or superseded or young'` and verify US3 tests pass.

**Checkpoint**: Automatic injection is stricter than explicit recall and privacy/lifecycle filters are covered.

---

## Phase 6: User Story 4 - Audit Automatic Memory Use (Priority: P2)

**Goal**: Activation decisions and filter outcomes are traceable without leaking restricted or deleted raw content.

**Independent Test**: Activation can run in skipped, injected, not_found, filtered, and error cases and produce safe trace records when repository access is available.

### Tests For User Story 4

- [x] T039 [P] [US4] Add unit tests in `tests/unit/test_activation.py` for trace payload construction that records outcome, reason, request type, candidate count, injected ids, and aggregate filter counts.
- [x] T040 [P] [US4] Add integration tests in `tests/integration/test_activation_hook.py` for trace rows after skipped, injected, not_found, and filtered activation outcomes.
- [x] T041 [P] [US4] Add integration test in `tests/integration/test_activation_hook.py` proving traces do not contain deleted or restricted raw content.

### Implementation For User Story 4

- [x] T042 [US4] Implement `append_activation_trace()` or equivalent helper in `plugins/life_memory/activation.py`, using the existing repository trace API when available.
- [x] T043 [US4] Wire trace writing into `build_activation_context()` for skipped, activated, not_found, filtered, injected, and fail-closed outcomes.
- [x] T044 [US4] Update `plugins/life_memory/models.py` and any trace operation handling to support an activation operation name if needed.
- [x] T045 [US4] Ensure trace input is bounded/redacted and stores memory ids/filter counts rather than full injected context.
- [x] T046 [US4] Run `uv run python -m pytest tests/unit/test_activation.py tests/integration/test_activation_hook.py -k 'trace or audit'` and verify US4 tests pass.

**Checkpoint**: Automatic memory use is auditable and traces are privacy-preserving.

---

## Phase 7: User Story 5 - Runtime Hook Integration (Priority: P2)

**Goal**: Compose automatic activation with the existing `pre_llm_call` routing hook without modifying Hermes core or disabling routing guidance.

**Independent Test**: Fake Hermes plugin context captures hook registration and validates the returned context payload.

### Tests For User Story 5

- [x] T047 [P] [US5] Add integration test in `tests/integration/test_activation_hook.py` with a fake `register_hook` context proving the plugin installs a `pre_llm_call` hook that preserves routing guidance.
- [x] T048 [P] [US5] Add integration test in `tests/integration/test_activation_hook.py` proving routing guidance plus activated memory context are returned for a relevant life-memory request.
- [x] T049 [P] [US5] Add integration test in `tests/integration/test_activation_hook.py` proving storage unavailable, malformed payload, or activation failure returns routing guidance only and does not raise.
- [x] T050 [P] [US5] Add regression tests in `tests/unit/test_routing.py` to ensure Phase 10 write-routing still routes L2/L3/L4 correctly after hook composition.

### Implementation For User Story 5

- [x] T051 [US5] Update `plugins/life_memory/routing.py` to compose `ROUTING_CONTEXT` with `build_activation_context()` inside the `pre_llm_call` hook.
- [x] T052 [US5] Update `plugins/life_memory/routing.py` so activation failures are logged/debug-traced but never raise from the hook.
- [x] T053 [US5] Update `plugins/life_memory/__init__.py` only if necessary to pass activation dependencies/configuration into `install_memory_routing()` without changing existing tool registration behavior.
- [x] T054 [US5] Ensure activation hook behavior remains no-op when Hermes lacks `register_hook` or provides an unknown hook payload shape.
- [x] T055 [US5] Run `uv run python -m pytest tests/integration/test_activation_hook.py tests/unit/test_routing.py` and verify hook integration and routing regression tests pass.

**Checkpoint**: Hermes pre-LLM context can include automatic life-memory context while preserving routing behavior and fail-closed safety.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, validation, performance guardrails, and final smoke checks.

- [x] T056 [P] Update `README.md` with automatic activation behavior, default safety filters, enable/disable notes, and audit guidance.
- [x] T057 [P] Update `specs/002-memory-activation/quickstart.md` with final implemented commands, expected test results, and manual Hermes smoke-test observations.
- [x] T058 [P] Updated and reviewed `specs/002-memory-activation/contracts/activation-hook.md` for official Hermes `pre_llm_call` payload compatibility.
- [x] T059 Add performance smoke coverage in `tests/integration/test_activation_hook.py` proving activation remains bounded with a large memory set and injects no more than the configured maximum.
- [x] T060 Run `uv run python -m pytest` and record the result in `README.md` and `specs/002-memory-activation/quickstart.md`.
- [x] T061 Run manual Hermes smoke test from `specs/002-memory-activation/quickstart.md`, if Hermes runtime is available, and record outcome or blocker in `specs/002-memory-activation/quickstart.md`.
- [x] T062 Review `git status --short` and ensure 001-stage routing/report files and 002 activation files are intentionally tracked or separated before commit.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 Setup**: No dependencies.
- **Phase 2 Foundational**: Depends on Phase 1 and blocks all user stories.
- **Phase 3 US1**: Depends on Phase 2.
- **Phase 4 US2**: Depends on US1 activation decision and Phase 2 policy/types.
- **Phase 5 US3**: Depends on US2 candidate selection/formatting.
- **Phase 6 US4**: Depends on US1/US2 outcomes and US3 filter reason codes.
- **Phase 7 US5**: Depends on US1/US2/US3 core activation behavior and should preserve Phase 10 routing.
- **Phase 8 Polish**: Depends on implemented user stories selected for this feature.

### User Story Dependency Graph

```text
Foundation
  └── US1 Activation gate
        └── US2 Safe bounded context
              └── US3 Strict privacy/lifecycle filters
                    ├── US4 Audit traces
                    └── US5 pre_llm_call hook integration
```

### MVP Scope

The independently useful MVP for this feature is **US1 + US2 + US3**:

1. Decide whether life memory is needed.
2. Build a bounded data-only memory block for relevant requests.
3. Exclude unsafe or stale memories from automatic injection.

`US4` and `US5` should follow immediately because production use requires auditability and runtime hook integration.

---

## Parallel Opportunities

- T001 and T002 can run in parallel.
- T004 and T005 can run in parallel.
- T010, T011, and T012 can run in parallel after Phase 2.
- T018, T019, T020, T021, and T022 can run in parallel if test files are coordinated.
- T029 through T033 can run in parallel once US2 implementation exists.
- T039 through T041 can run in parallel once activation outcomes exist.
- T047 through T050 can run in parallel once hook composition API is defined.
- Documentation tasks T056 through T058 can run in parallel after implementation stabilizes.

---

## Implementation Strategy

### MVP First

1. Complete Phase 1 and Phase 2.
2. Implement and validate US1 activation gate.
3. Implement and validate US2 bounded data-only context.
4. Implement and validate US3 strict privacy/lifecycle filtering.
5. Stop and run `uv run python -m pytest tests/unit/test_activation.py tests/integration/test_activation_hook.py`.

### Full Feature

1. Add US4 trace/audit support.
2. Add US5 hook integration while preserving Phase 10 routing tests.
3. Run full `uv run python -m pytest`.
4. Run manual Hermes smoke test when runtime is available.
