# Tasks: Hermes 分层生活记忆插件

**Input**: Design documents from `/Users/oliver/Projects/hermes-life-memory/specs/001-life-memory-plugin/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/life-memory-tools.md`, `quickstart.md`

**Tests**: Required by the feature specification. Test tasks are included before implementation tasks for each user story.

**Organization**: Tasks are grouped by user story so each increment can be implemented and tested with bounded scope.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel after its phase prerequisites are complete because it touches a different file or isolated test scope.
- **[Story]**: User story mapping from `spec.md`.
- Every task includes an exact file path.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Establish the plugin package, pytest configuration, and repeatable local test fixtures.

- [x] T001 Create Python project and pytest configuration in `pyproject.toml`
- [x] T002 [P] Create temporary `HERMES_HOME` and handler fixtures in `tests/conftest.py`
- [x] T003 [P] Seed local evaluation cases for classification, recall, temporal update, forget, abstention, sensitive rejection, and memory-injection rejection in `tests/fixtures/evaluation_cases.json`
- [x] T004 Populate Hermes standalone plugin metadata in `plugins/life_memory/plugin.yaml`
- [x] T005 Add plugin constants, lazy runtime path helpers, and handler placeholders in `plugins/life_memory/__init__.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Build shared types, contracts, safety helpers, SQLite schema, trace infrastructure, and plugin registration. No user story implementation should begin until this phase is complete.

- [x] T006 [P] Implement enums and dataclasses for classifications, lifecycle states, feedback, traces, reflection runs, and tool results in `plugins/life_memory/models.py`
- [x] T007 [P] Implement timezone-aware timestamp, id, content hash, JSON encode/decode, and clamp helpers in `plugins/life_memory/time_utils.py`
- [x] T008 [P] Implement six tool JSON schemas and common result builders in `plugins/life_memory/contracts.py`
- [x] T009 [P] Implement baseline sensitive-content and prompt-injection detection primitives in `plugins/life_memory/safety.py`
- [x] T010 Implement SQLite connection setup, WAL mode, `schema_version`, all MVP tables, and optional FTS5 creation/fallback in `plugins/life_memory/repository.py`
- [x] T011 Implement repository transaction helpers, row mapping, append-only trace writes, memory evidence writes, and memory link writes in `plugins/life_memory/repository.py`
- [x] T012 [P] Add common contract envelope tests for `ok`, `outcome`, `message`, and `trace_id` in `tests/contract/test_tool_contracts.py`
- [x] T013 [P] Add schema creation, migration idempotency, trace write, and FTS fallback tests in `tests/unit/test_repository.py`
- [x] T014 [P] Add plugin registration smoke tests for all six tool names in `tests/integration/test_plugin_handlers.py`
- [x] T015 Wire `ctx.register_tool()` registration for `life_memory_store`, `life_memory_recall`, `life_memory_feedback`, `life_memory_forget`, `life_memory_reflect`, and `life_memory_export_review` in `plugins/life_memory/__init__.py`

**Checkpoint**: Foundation ready. Plugin can be discovered in tests, database initializes in a temporary `HERMES_HOME`, and common result envelopes are testable.

---

## Phase 3: User Story 1 - Classify Candidate Memory (Priority: P1)

**Goal**: Classify candidate memory before storage so technical, profile, temporary, abstract, and no-save content do not pollute life memory.

**Independent Test**: Run classification unit and fixture tests that cover `technical_memory`, `life_memory`, `user_profile`, `temporary_working_memory`, `abstract_experience`, and `no_save`.

### Tests for User Story 1

- [x] T016 [P] [US1] Write boundary classification tests for technical memory, life memory, user profile, temporary context, no-save, and repeated-pattern candidates in `tests/unit/test_classification.py`
- [x] T017 [US1] Add classification fixture cases and expected reasons to `tests/fixtures/evaluation_cases.json`

### Implementation for User Story 1

- [x] T018 [US1] Implement deterministic boundary classification rules and confidence reasoning in `plugins/life_memory/classification.py`
- [x] T019 [US1] Implement `primary_category` and tag suggestion rules for `personal_fact`, `personal_preference`, and `personal_pattern` in `plugins/life_memory/classification.py`
- [x] T020 [US1] Connect classification preflight and declined classification traces to the store placeholder path in `plugins/life_memory/__init__.py`

**Checkpoint**: Candidate memory classification works independently and does not require durable storage to be validated.

---

## Phase 4: User Story 2 - Store Life Memory (Priority: P1)

**Goal**: Store eligible L4 life memories with metadata, traces, sensitivity gates, `major_life_fact` fast promotion, and `recent_state` TTL.

**Independent Test**: Ask the store handler to remember in-scope life facts, reject technical/no-save content, return `needs_confirmation` for sensitive content, and persist accepted memories in a temporary SQLite database.

### Tests for User Story 2

- [x] T021 [P] [US2] Write `life_memory_store` schema, success, declined, and `needs_confirmation` contract tests in `tests/contract/test_tool_contracts.py`
- [x] T022 [P] [US2] Write repository tests for memory insert, evidence insert, trace insert, source metadata, and status defaults in `tests/unit/test_repository.py`
- [x] T023 [P] [US2] Write safety tests for sensitive confirmation, restricted raw-content handling, and memory-injection rejection in `tests/unit/test_safety.py`
- [x] T024 [P] [US2] Write store integration tests for accepted life memory, rejected technical memory, sensitive confirmation, `major_life_fact`, and `recent_state` TTL in `tests/integration/test_plugin_handlers.py`

### Implementation for User Story 2

- [x] T025 [US2] Implement repository methods for creating memories, evidence, status metadata, promotion metadata, validity windows, and declined-store traces in `plugins/life_memory/repository.py`
- [x] T026 [US2] Implement durable `life_memory_store` flow with classification, safety gates, duplicate precheck, trace writes, and JSON output in `plugins/life_memory/__init__.py`
- [x] T027 [US2] Implement `needs_confirmation`, summary-first sensitive handling, and injection-risk rejection decisions in `plugins/life_memory/safety.py`
- [x] T028 [US2] Implement `major_life_fact` fast promotion and `recent_state` 14-day TTL assignment in `plugins/life_memory/__init__.py`

**Checkpoint**: Eligible life memories can be stored and inspected in SQLite; unsafe, technical, and unauthorized sensitive candidates are not durably stored.

---

## Phase 5: User Story 3 - Recall Relevant Life Memory (Priority: P1)

**Goal**: Retrieve bounded, relevant life memories while excluding deleted, expired, archived-by-default, unrelated, technical, and unauthorized sensitive memories.

**Independent Test**: Store multiple memories, recall by targeted and broad queries, verify ranking, bounded results, access updates, abstention, and low-weight `young` handling.

### Tests for User Story 3

- [x] T029 [P] [US3] Write `life_memory_recall` contract tests for success, `not_found`, limit bounds, sensitivity flags, and result shape in `tests/contract/test_tool_contracts.py`
- [x] T030 [P] [US3] Write recall scoring, filtering, `young` cap, archived exclusion, expired `recent_state` exclusion, and injection-as-data tests in `tests/unit/test_recall.py`
- [x] T031 [P] [US3] Write recall integration tests for targeted recall, broad abstention, access count updates, and no unrelated memories in `tests/integration/test_plugin_handlers.py`

### Implementation for User Story 3

- [x] T032 [US3] Implement repository search, FTS/LIKE fallback, sensitivity filters, status filters, and access-update methods in `plugins/life_memory/repository.py`
- [x] T033 [US3] Implement deterministic recall scoring, bounded ranking, `young` multiplier, and relevance reasons in `plugins/life_memory/recall.py`
- [x] T034 [US3] Implement memory-injection-as-data handling and sensitive/restricted recall filtering in `plugins/life_memory/recall.py`
- [x] T035 [US3] Implement `life_memory_recall` handler output with references, relevance reasons, and trace writes in `plugins/life_memory/__init__.py`

**Checkpoint**: Minimal MVP is usable: classify, store, and recall work together with bounded, explainable results.

---

## Phase 6: User Story 4 - Correct And Forget Memory (Priority: P2)

**Goal**: Let the user correct, supersede, mark outdated, reinforce, merge, or forget memories without silent overwrites or accidental multi-delete.

**Independent Test**: Save a memory, apply feedback or deletion, then verify future recall and repository state reflect the correction, tombstone, or ambiguity result.

### Tests for User Story 4

- [x] T036 [P] [US4] Write `life_memory_feedback` and `life_memory_forget` contract tests for useful, wrong, outdated, important, duplicate, delete, merge, `ambiguous`, and `not_found` outcomes in `tests/contract/test_tool_contracts.py`
- [x] T037 [P] [US4] Write repository tests for feedback rows, supersede links, mirrored links, tombstone redaction, and deleted-content exclusion in `tests/unit/test_repository.py`
- [x] T038 [P] [US4] Write integration tests for correction replacement, outdated demotion, forget by id, forget-by-query ambiguity, and deleted memory recall exclusion in `tests/integration/test_plugin_handlers.py`

### Implementation for User Story 4

- [x] T039 [US4] Implement repository feedback, feedback-score, supersede, conflict, duplicate, and merge helpers in `plugins/life_memory/repository.py`
- [x] T040 [US4] Implement repository tombstone/redaction deletion semantics that preserve id/hash/status while removing ordinary recallable content in `plugins/life_memory/repository.py`
- [x] T041 [US4] Implement `life_memory_feedback` handler with replacement, supersede, merge, duplicate, important, useful, wrong, outdated, and delete delegation in `plugins/life_memory/__init__.py`
- [x] T042 [US4] Implement `life_memory_forget` handler with id deletion, query candidate lookup, confirmation requirement, ambiguity handling, and trace writes in `plugins/life_memory/__init__.py`
- [x] T043 [US4] Apply feedback score, status, supersede, and deleted-memory effects to recall ranking and filtering in `plugins/life_memory/recall.py`

**Checkpoint**: Users can correct and forget memories, and normal recall no longer presents deleted or superseded facts as current truth.

---

## Phase 7: User Story 6 - Export Human Review Markdown (Priority: P2)

**Goal**: Export a read-only Markdown review view so users can inspect confirmed memories, uncertain memories, journal reports, archive entries, and change request templates.

**Independent Test**: Populate a temporary database, run `life_memory_export_review`, verify expected files and redaction behavior, and confirm no memory status or promotion score changes.

### Tests for User Story 6

- [x] T044 [P] [US6] Write `life_memory_export_review` contract tests for default target, archive flag, sensitive export mode, file list, and read-only outcome in `tests/contract/test_tool_contracts.py`
- [x] T045 [P] [US6] Write Markdown export integration tests for `README.md`, `memory-journal/`, `memory-library/facts.md`, `memory-library/preferences.md`, `memory-library/patterns.md`, `review-needed.md`, `change-requests.md`, optional `archive.md`, and sensitive redaction in `tests/integration/test_export_review.py`

### Implementation for User Story 6

- [x] T046 [US6] Implement read-only repository export queries for active, reinforced, pattern_candidate, needs_review, archived, session report, and daily report rows in `plugins/life_memory/repository.py`
- [x] T047 [US6] Implement Markdown rendering, user-facing labels, section ordering, sensitive omission/summary-only behavior, and `change-requests.md` template output in `plugins/life_memory/export_review.py`
- [x] T048 [US6] Implement `life_memory_export_review` handler with default `$HERMES_HOME/life_memory_review` target, file list output, and no reverse sync in `plugins/life_memory/__init__.py`
- [x] T049 [US6] Add export trace writing without status, promotion score, or content mutation in `plugins/life_memory/repository.py`

**Checkpoint**: Users can inspect a readable Markdown view of what the plugin remembers without editing SQLite through Markdown.

---

## Phase 8: User Story 5 - Reflect And Maintain Memory Quality (Priority: P3)

**Goal**: Run background memory maintenance for session extraction, light cleanup, duplicate candidates, `recent_state` expiry, pattern promotion, and report-only daily reflection.

**Independent Test**: Create duplicate, stale, expired, session, and repeated-pattern memories, then run dry-run and apply reflection modes and verify proposed or applied state changes.

### Tests for User Story 5

- [x] T050 [P] [US5] Write session adapter tests for read-only session lookup, unavailable session handling, and transcript fallback in `tests/unit/test_session_adapter.py`
- [x] T051 [P] [US5] Write reflection unit tests for dry-run, light dedupe candidates, `recent_state` archive, session extraction candidates, deep pattern promotion, and daily report-only behavior in `tests/unit/test_reflection.py`
- [x] T052 [P] [US5] Write `life_memory_reflect` integration tests for `session`, `light`, `rem`, `deep`, `daily`, `apply=false`, `apply=true`, and no-fabrication failure cases in `tests/integration/test_plugin_handlers.py`

### Implementation for User Story 5

- [x] T053 [US5] Implement read-only Hermes session/state adapter with session-ref resolution, transcript normalization, and unavailable-state errors in `plugins/life_memory/session_adapter.py`
- [x] T054 [US5] Implement repository helpers for reflection runs, reflection reports, candidate links, applied counts, and report paths in `plugins/life_memory/repository.py`
- [x] T055 [US5] Implement `light` reflection for duplicate candidates, evidence accounting, low-cost tag cleanup, and expired `recent_state` archive in `plugins/life_memory/reflection.py`
- [x] T056 [US5] Implement `session` reflection for effective-memory extraction from session refs or explicit transcripts while reusing classification and safety gates in `plugins/life_memory/reflection.py`
- [x] T057 [US5] Implement `rem` and `deep` reflection for conflict candidates, pattern candidates, low-risk `abstract_experience` promotion with supporting memory ids, and conservative apply gates in `plugins/life_memory/reflection.py`
- [x] T058 [US5] Implement `daily` reflection report-only output that creates reports but no durable facts and no `promotion_score` changes in `plugins/life_memory/reflection.py`
- [x] T059 [US5] Implement `life_memory_reflect` handler with mode dispatch, dry-run/apply behavior, trace writes, and JSON output in `plugins/life_memory/__init__.py`

**Checkpoint**: Reflection can organize the memory store without turning daily summaries or weak guesses into durable facts.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Validate the vertical slice, document local usage, and harden behavior across stories.

- [x] T060 Add 10,000-row store/recall performance smoke coverage and bounded result assertions in `tests/integration/test_plugin_handlers.py`
- [x] T061 [P] Update repository overview, mount instructions, enable instructions, test command, and review-export command in `README.md`
- [x] T062 Validate `quickstart.md` against the implemented behavior and record any remaining caveats in `specs/001-life-memory-plugin/quickstart.md`
- [x] T063 Run `python -m pytest` and document the validation result in `README.md`
- [x] T064 Verify no Hermes main project files are modified and document allowed paths in `README.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 Setup**: No dependencies.
- **Phase 2 Foundational**: Depends on Phase 1 and blocks all user stories.
- **Phase 3 US1**: Depends on Phase 2.
- **Phase 4 US2**: Depends on Phase 2 and uses US1 classification.
- **Phase 5 US3**: Depends on US2 persisted memories.
- **Phase 6 US4**: Depends on US2 storage and US3 recall behavior.
- **Phase 7 US6**: Depends on Phase 2 and repository data; easiest after US2 creates realistic memories.
- **Phase 8 US5**: Depends on US2/US3 and optionally US4 for conflict/supersede behavior.
- **Phase 9 Polish**: Depends on the desired implemented stories.

### User Story Dependency Graph

```text
Foundation
  └── US1 Classify
        └── US2 Store
              ├── US3 Recall
              │     └── US4 Feedback/Forget
              │           └── US5 Reflect
              └── US6 Export Review
```

### MVP Scope

The practical MVP is **US1 + US2 + US3**:

1. Classify candidates correctly.
2. Store eligible life memories in SQLite.
3. Recall relevant memories with bounded, explainable results.

`US4` and `US6` should follow before real use because user control and human review are central to trust. `US5` can be implemented after the core loop is stable.

---

## Parallel Execution Examples

### Foundation

```text
T006 models.py
T007 time_utils.py
T008 contracts.py
T009 safety.py
T012 contract tests
T013 repository tests
T014 integration smoke tests
```

### User Story 1

```text
T016 tests/unit/test_classification.py
T017 tests/fixtures/evaluation_cases.json
```

### User Story 2

```text
T021 tests/contract/test_tool_contracts.py
T022 tests/unit/test_repository.py
T023 tests/unit/test_safety.py
T024 tests/integration/test_plugin_handlers.py
```

### User Story 3

```text
T029 tests/contract/test_tool_contracts.py
T030 tests/unit/test_recall.py
T031 tests/integration/test_plugin_handlers.py
```

### User Story 4

```text
T036 tests/contract/test_tool_contracts.py
T037 tests/unit/test_repository.py
T038 tests/integration/test_plugin_handlers.py
```

### User Story 6

```text
T044 tests/contract/test_tool_contracts.py
T045 tests/integration/test_export_review.py
```

### User Story 5

```text
T050 tests/unit/test_session_adapter.py
T051 tests/unit/test_reflection.py
T052 tests/integration/test_plugin_handlers.py
```

---

## Implementation Strategy

### MVP First

1. Complete Phase 1 and Phase 2.
2. Complete US1, US2, and US3.
3. Run tests for classification, store, recall, repository, safety, contract, and integration paths.
4. Stop and validate the end-to-end prototype before adding correction, export, and reflection.

### Incremental Delivery

1. Foundation ready.
2. US1 classify.
3. US2 store.
4. US3 recall.
5. US4 feedback/forget.
6. US6 export review.
7. US5 reflection.
8. Polish and full quickstart validation.

### Notes

- Tests should be written before implementation tasks in the same story.
- `[P]` tasks should not touch the same file in the same phase unless the earlier task is complete.
- Do not modify `/Users/oliver/.hermes/hermes-agent` or `/Users/oliver/Projects/hermes-workspace/hermes-agent`.
- Runtime data must stay under `$HERMES_HOME`, with tests using temporary `HERMES_HOME`.
- Markdown export is read-only in MVP; do not implement Markdown-to-SQLite reverse sync.
