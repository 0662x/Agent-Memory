# Tasks: Review Sync And Change Requests

**Input**: Design documents from `/specs/004-review-sync/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/review-sync.md`, `quickstart.md`

**Tests**: This feature requires parser unit tests, contract tests, integration tests against temporary SQLite, export/sync round-trip coverage, and full-suite validation. Test tasks are listed before the implementation tasks they verify.

**Organization**: Tasks are grouped by user story so each increment can be implemented and tested independently.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel when dependencies for the phase are met and files do not overlap.
- **[Story]**: Maps to user stories in `spec.md`, for example `[US1]`.
- Each task includes exact repository-relative file paths.

## Phase 1: Setup

**Purpose**: Add review-sync fixtures and confirm Spec Kit resolves this feature.

- [x] T001 [P] Create `tests/fixtures/review_change_requests.md` with valid delete, replace, merge, confirm, reject, mark_outdated, malformed, ambiguous, and unsafe request examples.
- [x] T002 [P] Add an implementation-status note to `specs/004-review-sync/quickstart.md` documenting the explicit review-sync workflow and Markdown boundaries.
- [x] T003 Run `bash .specify/scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks` and verify it resolves `specs/004-review-sync`.
- [x] T004 Run `uv run python -m pytest` to record the pre-feature baseline.

**Checkpoint**: The feature has fixture inputs, baseline tests pass, and Spec Kit points at `004-review-sync`.

---

## Phase 2: Foundational

**Purpose**: Create shared review-sync types, parser primitives, safe source loading, and trace operation support required by all user stories.

**Critical**: No user story implementation should start until this phase is complete.

### Tests For Foundation

- [x] T005 [P] Add unit tests in `tests/unit/test_review_sync.py` for fenced `life-memory-change` block parsing, line numbers, request ids, duplicate ids, and unsupported actions.
- [x] T006 [P] Add unit tests in `tests/unit/test_review_sync.py` for safe source loading from default review dir, inline text, missing file, path traversal rejection, and `max_actions` bounds.
- [x] T007 [P] Add unit tests in `tests/unit/test_review_sync.py` for stable dataclass/result shapes: `ReviewChangeRequest`, `ReviewSyncActionResult`, and `ReviewSyncPlan`.

### Implementation For Foundation

- [x] T008 Create `plugins/life_memory/review_sync.py` with request/action dataclasses, outcome constants, parser errors, safe source loader, and result serialization helpers.
- [x] T009 Update `plugins/life_memory/models.py` only if trace operation enums or shared dataclasses are required for review sync.
- [x] T010 Implement fenced-block parser in `plugins/life_memory/review_sync.py` for `delete`, `replace`, `merge`, `confirm`, `reject`, and `mark_outdated` actions.
- [x] T011 Implement path/input bounds in `plugins/life_memory/review_sync.py`, including default `$HERMES_HOME/life_memory_review/change-requests.md` resolution.
- [x] T012 Run `uv run python -m pytest tests/unit/test_review_sync.py -k 'parse or source or shape'` and verify foundation tests pass.

**Checkpoint**: Review-sync input can be parsed and represented without mutating SQLite.

---

## Phase 3: User Story 1 - Preview Review Change Requests (Priority: P1)

**Goal**: Dry-run review requests and preview exact planned operations without changing durable state.

**Independent Test**: Seed temporary memories, parse valid change requests, run dry-run planning, and prove repository state is unchanged.

### Tests For User Story 1

- [x] T013 [P] [US1] Add unit tests in `tests/unit/test_review_sync.py` for dry-run planning of exact-id delete, replace, merge, confirm, reject, and mark_outdated requests.
- [x] T014 [P] [US1] Add unit tests in `tests/unit/test_review_sync.py` proving dry-run returns target ids, warnings, parse errors, and proposed operation descriptions.
- [x] T015 [US1] Add integration tests in `tests/integration/test_review_sync_flow.py` proving dry-run does not mutate memory status, links, feedback, promotion score, or recall behavior.

### Implementation For User Story 1

- [x] T016 [US1] Implement `plan_review_sync()` in `plugins/life_memory/review_sync.py` for dry-run matching and proposed operation generation.
- [x] T017 [US1] Add repository read helpers in `plugins/life_memory/repository.py` only if existing memory lookup/search helpers are insufficient.
- [x] T018 [US1] Implement dry-run trace payload construction in `plugins/life_memory/review_sync.py` without raw restricted content.
- [x] T019 [US1] Run `uv run python -m pytest tests/unit/test_review_sync.py tests/integration/test_review_sync_flow.py -k 'dry_run or planned or no_mutation'` and verify US1 tests pass.

**Checkpoint**: Users can preview review changes safely.

---

## Phase 4: User Story 2 - Apply Exact Safe Changes (Priority: P1)

**Goal**: Apply confirmed exact-id changes through existing lifecycle, feedback, forget, supersession, merge, and trace semantics.

**Independent Test**: Apply one action at a time against temporary SQLite and verify recall/repository state.

### Tests For User Story 2

- [x] T020 [P] [US2] Add integration tests in `tests/integration/test_review_sync_flow.py` for exact-id delete applying soft-delete/tombstone semantics.
- [x] T021 [P] [US2] Add integration tests in `tests/integration/test_review_sync_flow.py` for replace creating a new memory and superseding the old memory.
- [x] T022 [P] [US2] Add integration tests in `tests/integration/test_review_sync_flow.py` for merge linking duplicate/source memories to a merged target.
- [x] T023 [P] [US2] Add integration tests in `tests/integration/test_review_sync_flow.py` for confirm, reject, and mark_outdated actions mapping to feedback/review status changes.
- [x] T024 [P] [US2] Add tests proving destructive apply requires `apply=true`, `confirm_apply=true`, and per-action confirmation where required.

### Implementation For User Story 2

- [x] T025 [US2] Implement apply handling in `plugins/life_memory/review_sync.py`, delegating to existing repository methods for delete, replacement, feedback, supersede, duplicate, and merge semantics.
- [x] T026 [US2] Add repository transaction wrapper or reuse existing transaction helper to avoid silent partial changes.
- [x] T027 [US2] Implement per-action applied result serialization with affected ids, created ids, and trace ids.
- [x] T028 [US2] Run `uv run python -m pytest tests/integration/test_review_sync_flow.py -k 'apply or delete or replace or merge or confirm'` and verify US2 tests pass.

**Checkpoint**: Exact confirmed review changes can update SQLite safely.

---

## Phase 5: User Story 3 - Block Ambiguous Or Unsafe Sync (Priority: P1)

**Goal**: Prevent review sync from bypassing safety, sensitivity, lifecycle, deletion, or ambiguity rules.

**Independent Test**: Use unsafe/malformed/sensitive/ambiguous requests and prove no durable changes occur.

### Tests For User Story 3

- [ ] T029 [P] [US3] Add unit tests in `tests/unit/test_review_sync.py` for query-based ambiguous matches, zero matches, deleted ids, archived ids, superseded ids, and stale export ids.
- [ ] T030 [P] [US3] Add unit tests in `tests/unit/test_review_sync.py` for replacement text classification, sensitive confirmation, restricted rejection, and prompt-injection rejection.
- [x] T031 [P] [US3] Add integration tests in `tests/integration/test_review_sync_flow.py` proving ambiguous, unsafe, restricted, and malformed requests apply no changes.
- [x] T032 [P] [US3] Add tests proving sync results and traces do not expose deleted/restricted raw content.

### Implementation For User Story 3

- [x] T033 [US3] Implement validation gates in `plugins/life_memory/review_sync.py`, reusing `classification.py` and `safety.py` for replacement/merged content.
- [x] T034 [US3] Implement exact-id and query-based target resolution with `ambiguous`, `not_found`, `needs_confirmation`, and `declined` outcomes.
- [x] T035 [US3] Ensure restricted raw-content requests are rejected or redacted in all result and trace paths.
- [x] T036 [US3] Run `uv run python -m pytest tests/unit/test_review_sync.py tests/integration/test_review_sync_flow.py -k 'ambiguous or unsafe or restricted or sensitive or malformed'` and verify US3 tests pass.

**Checkpoint**: Review sync is no less strict than existing memory tools.

---

## Phase 6: User Story 4 - Keep Review Export And Sync Compatible (Priority: P2)

**Goal**: Update export templates and ids so users can write valid change requests without SQLite inspection.

**Independent Test**: Export review files, use the generated template to write requests, then dry-run sync successfully.

### Tests For User Story 4

- [x] T037 [P] [US4] Update `tests/integration/test_export_review.py` to assert `change-requests.md` documents supported `life-memory-change` actions and dry-run/apply workflow.
- [x] T038 [P] [US4] Add integration test in `tests/integration/test_review_sync_flow.py` for export -> write template-based change request -> dry-run sync.
- [x] T039 [P] [US4] Add tests proving manual edits to `memory-library/*.md`, `memory-journal/*.md`, `archive.md`, and `review-needed.md` are ignored in MVP.

### Implementation For User Story 4

- [x] T040 [US4] Update `plugins/life_memory/export_review.py` to generate a structured `change-requests.md` template with examples for each supported action.
- [x] T041 [US4] Ensure exported actionable memory entries include stable `memory_id` values suitable for exact-id sync requests.
- [x] T042 [US4] Ensure sync reads only `change-requests.md` or explicit inline text in MVP.
- [x] T043 [US4] Run `uv run python -m pytest tests/integration/test_export_review.py tests/integration/test_review_sync_flow.py -k 'template or export or ignored'` and verify US4 tests pass.

**Checkpoint**: Exported Markdown and review sync form a safe round-trip workflow.

---

## Phase 7: User Story 5 - Audit Review Sync Runs (Priority: P2)

**Goal**: Trace every dry-run and apply run without leaking sensitive or deleted raw content.

**Independent Test**: Run sync in planned, applied, invalid, ambiguous, declined, and failed modes and verify trace rows.

### Tests For User Story 5

- [ ] T044 [P] [US5] Add unit tests in `tests/unit/test_review_sync.py` for trace payload construction, bounded source hashes, redactions, and action counts.
- [ ] T045 [P] [US5] Add integration tests in `tests/integration/test_review_sync_flow.py` for trace rows after dry-run, apply, invalid, ambiguous, declined, and failed outcomes.
- [ ] T046 [P] [US5] Add tests proving traces connect sync apply runs to underlying forget/feedback/store/link traces where available.

### Implementation For User Story 5

- [x] T047 [US5] Implement `append_review_sync_trace()` or equivalent helper in `plugins/life_memory/review_sync.py` using existing repository trace APIs.
- [x] T048 [US5] Add `review_sync` trace operation support in `plugins/life_memory/models.py` or repository code if required.
- [x] T049 [US5] Ensure trace payloads include request ids, outcomes, affected ids, warnings, counts, source hash, and redaction metadata, not raw restricted content.
- [x] T050 [US5] Run `uv run python -m pytest tests/unit/test_review_sync.py tests/integration/test_review_sync_flow.py -k 'trace or audit'` and verify US5 tests pass.

**Checkpoint**: Review sync is auditable.

---

## Phase 8: Tool Contract And Handler Integration

**Purpose**: Expose review sync as a plugin tool while preserving existing life-memory tool behaviors.

- [x] T051 [P] Add `life_memory_sync_review` schema tests to `tests/contract/test_tool_contracts.py`, covering default dry-run, inline text, apply confirmation, max_actions bounds, and result shape.
- [x] T052 [P] Add plugin registration smoke coverage in `tests/integration/test_plugin_handlers.py` for the seventh tool name if tool registration is expected in this stage.
- [x] T053 Update `plugins/life_memory/contracts.py` with `life_memory_sync_review` JSON schema and result envelope expectations.
- [x] T054 Update `plugins/life_memory/__init__.py` to register and implement the `life_memory_sync_review` handler, delegating to `review_sync.py`.
- [x] T055 Update `README.md` with review-sync behavior, dry-run/apply examples, safety boundaries, and audit guidance.
- [x] T056 Run `uv run python -m pytest tests/contract/test_tool_contracts.py tests/integration/test_plugin_handlers.py tests/integration/test_review_sync_flow.py` and verify integration tests pass.

**Checkpoint**: Review sync is available as an explicit plugin tool.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, validation, manual smoke, and final boundary checks.

- [x] T057 [P] Update `specs/004-review-sync/quickstart.md` with final implemented commands, expected test results, and manual smoke-test observations or blocker.
- [x] T058 [P] Review `specs/004-review-sync/contracts/review-sync.md` against final schema and handler behavior.
- [x] T059 Add performance smoke coverage proving parsing and dry-run remain bounded with at least 100 change requests and existing 10,000-row memory scale if practical.
- [x] T060 Run `uv run python -m pytest` and record the result in `README.md` and `specs/004-review-sync/quickstart.md`.
- [x] T061 Run a manual local smoke test: export review, add exact-id replacement, dry-run sync, apply sync, re-export review, and clean up test memory.
- [x] T062 Review `git status --short` and ensure only intended `004-review-sync` files and implementation changes are staged.
- [x] T063 Optional: add `specs/004-review-sync/project-report.md` after implementation if a stage report is needed for review.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 Setup**: No dependencies.
- **Phase 2 Foundational**: Depends on Phase 1 and blocks all user stories.
- **Phase 3 US1**: Depends on Phase 2.
- **Phase 4 US2**: Depends on US1 dry-run planning and existing repository mutation helpers.
- **Phase 5 US3**: Depends on US1/US2 validation paths and existing classification/safety gates.
- **Phase 6 US4**: Depends on parser syntax from Phase 2 and can proceed once template shape is stable.
- **Phase 7 US5**: Depends on US1/US2/US3 outcomes.
- **Phase 8 Tool Integration**: Depends on core parser/planner/apply behavior.
- **Phase 9 Polish**: Depends on implemented selected stories.

### User Story Dependency Graph

```text
Foundation
  └── US1 Dry-run preview
        ├── US2 Exact safe apply
        │     └── US5 Audit sync runs
        ├── US3 Ambiguity/safety blocks
        └── US4 Export/template compatibility
              └── Tool contract and handler integration
```

### MVP Scope

The independently useful MVP is **US1 + US3 + dry-run tool integration**:

1. Parse structured `change-requests.md`.
2. Preview planned changes with exact ids and warnings.
3. Refuse ambiguous or unsafe requests.
4. Expose dry-run through `life_memory_sync_review` without applying changes.

Full stage completion should add **US2 + US4 + US5** so confirmed changes can be applied, exported templates are usable, and all sync behavior is auditable.

---

## Parallel Opportunities

- T001 and T002 can run in parallel.
- T005, T006, and T007 can run in parallel after setup.
- T013 and T014 can run in parallel once parser shapes are stable.
- T020 through T024 can run in parallel if integration test fixtures are coordinated.
- T029 through T032 can run in parallel after validation hooks exist.
- T037 through T039 can run in parallel with US2 after template syntax is stable.
- T044 through T046 can run in parallel once outcome shapes are stable.
- Documentation tasks T055, T057, and T058 can run in parallel after implementation stabilizes.

---

## Implementation Strategy

### MVP First

1. Complete setup and foundational parser types.
2. Implement dry-run parse and plan.
3. Add ambiguity and safety validation.
4. Expose `life_memory_sync_review` in dry-run mode.
5. Run targeted parser, contract, and integration tests.

### Full Feature

1. Implement confirmed apply for exact-id delete/replace/merge/confirm/reject/mark_outdated.
2. Update export template for safe request authoring.
3. Add trace/audit integration.
4. Run full `uv run python -m pytest`.
5. Run manual export -> edit -> dry-run -> apply -> re-export smoke test.
