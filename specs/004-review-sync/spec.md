# Feature Specification: Review Sync And Change Requests

**Feature Branch**: `004-review-sync`

**Created**: 2026-06-06

**Status**: Draft

**Input**: User description: "Implement safe Markdown change request sync for life memory review"

## Summary

This feature adds an explicit, safe review-sync path for `life_memory` Markdown exports. Today `life_memory_export_review` writes human-readable Markdown files, including a `change-requests.md` template, but the plugin intentionally does not read Markdown back into SQLite. This stage should let the user express bounded review actions in that file and run a new sync tool that parses, validates, previews, and optionally applies those actions to SQLite.

The core design constraint is that Markdown remains an audit and review surface, not an unrestricted database editor. Sync must be opt-in, dry-run by default, traceable, and conservative around ambiguous, sensitive, restricted, deleted, or multi-match changes. Applied changes should reuse existing `life_memory_feedback`, `life_memory_forget`, supersession, merge, and trace semantics where possible.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Preview Review Change Requests (Priority: P1)

As a Hermes user, I want to write structured change requests in `change-requests.md` and preview what would happen before anything changes, so that I can safely review the memory library without risking accidental data loss.

**Why this priority**: Dry-run preview is the safety gate for the entire feature. Without it, reverse sync could silently corrupt or delete memories.

**Independent Test**: Can be tested with a temporary `HERMES_HOME`, an exported review directory, and a hand-written `change-requests.md` containing delete, replace, merge, confirm, and reject requests. Running sync in dry-run mode should return parsed actions, matched memory ids, warnings, and no database mutations.

**Acceptance Scenarios**:

1. **Given** a `change-requests.md` contains a valid delete request with an exact `memory_id`, **When** sync runs with `apply=false`, **Then** the result shows a planned delete and the memory remains recallable.
2. **Given** a valid replacement request references one existing `memory_id`, **When** dry-run sync parses it, **Then** the result shows the old memory id, replacement text, expected supersession behavior, and no SQLite state change.
3. **Given** a malformed change request exists, **When** dry-run sync runs, **Then** it reports a parse error with line number and applies nothing.

---

### User Story 2 - Apply Exact Safe Changes (Priority: P1)

As a Hermes user, I want explicitly confirmed change requests to update, delete, merge, or confirm memories using the same lifecycle and trace semantics as existing tools, so that review feedback becomes part of the durable memory state.

**Why this priority**: The feature is useful only if review feedback can be applied safely after preview.

**Independent Test**: Can be tested by seeding memories, writing exact-id change requests, running sync with `apply=true` and confirmation fields, then verifying recall, repository status, memory links, and trace rows.

**Acceptance Scenarios**:

1. **Given** a delete request references a single active memory id and includes confirmation, **When** sync applies it, **Then** the memory is soft-deleted with tombstone/redaction semantics and ordinary recall no longer returns it.
2. **Given** a replace request references a single active memory id, **When** sync applies it, **Then** the old memory is superseded and a replacement memory is created with evidence and trace.
3. **Given** a merge request references multiple existing memory ids and a target summary, **When** sync applies it, **Then** duplicate/source links are recorded and recall prefers the merged target.

---

### User Story 3 - Block Ambiguous Or Unsafe Sync (Priority: P1)

As a Hermes user, I want the sync process to refuse ambiguous, sensitive, restricted, or unsafe requests unless they are explicitly scoped and confirmed, so that Markdown editing does not bypass memory safety rules.

**Why this priority**: Reverse sync creates a new write path. It must be at least as strict as existing tool handlers.

**Independent Test**: Can be tested with query-based requests, sensitive memories, restricted content, deleted ids, duplicate matches, and injection-like replacement text. Sync should return `needs_confirmation`, `ambiguous`, `declined`, or `invalid` outcomes and apply nothing.

**Acceptance Scenarios**:

1. **Given** a request tries to delete by query and matches multiple memories, **When** sync runs, **Then** it returns `ambiguous` and does not delete any memory.
2. **Given** replacement text contains prompt-injection-like instructions, **When** sync validates it, **Then** the request is declined or marked unsafe and no durable memory is written.
3. **Given** a request references restricted content, **When** sync previews or applies it, **Then** raw restricted content is not emitted in the result, traces, or regenerated Markdown.

---

### User Story 4 - Keep Review Export And Sync Compatible (Priority: P2)

As a Hermes user, I want exported review files to include stable identifiers and a clear change-request template, so that writing a sync request is straightforward and does not require inspecting SQLite directly.

**Why this priority**: Sync usability depends on the export format giving users enough context to write safe, exact requests.

**Independent Test**: Can be tested by running `life_memory_export_review`, inspecting generated files, writing a request using the template, and proving sync can parse the template without ambiguity.

**Acceptance Scenarios**:

1. **Given** review export runs, **When** `change-requests.md` is generated, **Then** it documents the supported action syntax and warns that sync is explicit and dry-run by default.
2. **Given** memory-library files are exported, **When** a user reads them, **Then** each actionable memory entry includes a stable `memory_id` suitable for exact requests.
3. **Given** sync applies changes, **When** review export runs again, **Then** the regenerated Markdown reflects the updated memory state.

---

### User Story 5 - Audit Review Sync Runs (Priority: P2)

As a Hermes user, I want every sync preview and apply run to be traceable, so that I can understand which Markdown requests were parsed, rejected, or applied.

**Why this priority**: Review sync changes durable memory state and needs the same auditability as store, feedback, forget, reflect, and activation.

**Independent Test**: Can be tested by running dry-run and apply modes, then verifying trace rows include request ids, outcomes, affected memory ids, warnings, and redacted source metadata without leaking sensitive raw content.

**Acceptance Scenarios**:

1. **Given** sync runs in dry-run mode, **When** it finishes, **Then** a trace records parsed action counts and warnings without mutating memories.
2. **Given** sync applies a delete or replacement, **When** it finishes, **Then** trace rows connect the sync run to the underlying forget/feedback/store operations.
3. **Given** a request is rejected for safety, **When** trace is written, **Then** it records the reason without raw restricted content.

### Edge Cases

- `change-requests.md` is missing, empty, duplicated, or outside the expected review directory.
- The exported memory id no longer exists because the database changed after export.
- A request references a deleted, archived, superseded, or restricted memory.
- A query-based request matches zero memories or more than one memory.
- A request tries to edit memory content by modifying `facts.md` instead of `change-requests.md`.
- A request includes unsupported actions, invalid ids, duplicate request ids, invalid YAML/Markdown blocks, or oversized replacement text.
- Replacement text is sensitive, restricted, prompt-injection-like, or belongs to technical/user-profile memory rather than life memory.
- Sync apply partially fails after some actions; the system must use transactions or report exactly what was applied.
- Review export is regenerated while old change requests still exist.
- User wants historical review of sync results without exposing deleted raw content.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide an explicit review-sync capability, tentatively named `life_memory_sync_review`, that is not invoked by normal recall, activation, export, or reflection.
- **FR-002**: Review sync MUST read only a bounded `change-requests.md` file or explicitly supplied change-request text, not arbitrary Markdown review files.
- **FR-003**: Review sync MUST default to `apply=false` dry-run mode.
- **FR-004**: Dry-run mode MUST parse, validate, match, and preview actions without changing `life_memories`, `memory_links`, feedback rows, promotion scores, or lifecycle status.
- **FR-005**: Supported MVP actions MUST include `delete`, `replace`, `merge`, `confirm`, `reject`, and `mark_outdated`.
- **FR-006**: Exact `memory_id` requests MUST be preferred over query-based requests.
- **FR-007**: Query-based requests MUST return `ambiguous` when they match multiple memories and MUST apply nothing unless narrowed to exact ids.
- **FR-008**: Apply mode MUST require an explicit confirmation field or parameter for destructive actions such as delete, replace, merge, and reject.
- **FR-009**: Apply mode MUST reuse existing repository/tool semantics for soft delete, feedback, supersession, duplicate/merge links, evidence, and traces where possible.
- **FR-010**: Sync MUST reject or require confirmation for sensitive memories, and MUST reject restricted raw-content writes.
- **FR-011**: Sync MUST run existing classification and safety checks on replacement or confirmation text before durable storage.
- **FR-012**: Sync MUST not treat Markdown content as instructions to the agent; parsed requests are data only.
- **FR-013**: Sync MUST be transactional per run or per action with explicit applied/failed reporting; it MUST NOT leave silent partial changes.
- **FR-014**: Sync results MUST include parsed actions, outcomes, affected memory ids, warnings, errors, and trace ids.
- **FR-015**: Sync traces MUST avoid deleted, sensitive, or restricted raw content and store bounded source metadata.
- **FR-016**: `life_memory_export_review` MUST generate or update a `change-requests.md` template documenting supported action syntax and dry-run/apply workflow.
- **FR-017**: Sync MUST ignore manual edits to `memory-library/*.md`, `memory-journal/*.md`, `archive.md`, and `review-needed.md` in MVP.
- **FR-018**: Existing store, recall, feedback, forget, reflect, export, activation, routing, and hybrid recall tests MUST remain passing.
- **FR-019**: The feature MUST include unit tests for parser, validator, matcher, safety gates, and transaction planning.
- **FR-020**: The feature MUST include integration tests covering dry-run, apply, ambiguity, safety rejection, export compatibility, and trace behavior.

### Non-Goals

- **NG-001**: This stage does not make Markdown the source of truth.
- **NG-002**: This stage does not continuously watch the filesystem or auto-apply Markdown changes.
- **NG-003**: This stage does not parse arbitrary natural-language edits from all exported Markdown files.
- **NG-004**: This stage does not implement a full conflict-resolution UI.
- **NG-005**: This stage does not modify Hermes core source files.
- **NG-006**: This stage does not sync across devices or users.
- **NG-007**: This stage does not let recalled memories execute tools or actions.

### Key Entities *(include if feature involves data)*

- **Review Change Request**: A structured user-authored request from `change-requests.md`, with request id, action, target ids or query, proposed content, reason, confirmation, and source line numbers.
- **Review Sync Plan**: A dry-run result containing parsed actions, validation state, matched memory ids, warnings, errors, and proposed repository operations.
- **Review Sync Run**: A persisted or traceable sync execution record with mode, source hash, parsed counts, applied counts, rejected counts, trace ids, and timestamp.
- **Review Sync Action Result**: Per-action outcome such as `planned`, `applied`, `invalid`, `ambiguous`, `needs_confirmation`, `declined`, or `failed`.
- **Change Request Template**: The exported Markdown instructions and examples that constrain user edits to supported actions.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of dry-run tests leave durable memory rows, links, feedback, promotion scores, and lifecycle status unchanged.
- **SC-002**: 100% of destructive apply tests require explicit confirmation before mutation.
- **SC-003**: 100% of ambiguous query-based requests apply no changes and return actionable disambiguation information.
- **SC-004**: 100% of restricted raw-content cases avoid exposing raw content in results, traces, and regenerated Markdown.
- **SC-005**: Exact-id delete, replace, merge, confirm, reject, and mark-outdated flows pass integration tests against temporary SQLite.
- **SC-006**: Review export followed by dry-run sync using the generated template succeeds without manual SQLite inspection.
- **SC-007**: Existing `uv run python -m pytest` remains fully passing after implementation.
- **SC-008**: A manual local smoke test can export review Markdown, add one safe exact-id change request, preview it, apply it, export again, and observe the updated review output.

## Assumptions

- The system remains local-first, single-user, and SQLite-backed.
- `$HERMES_HOME/life_memory_review/change-requests.md` is the default review-sync input.
- Users can copy exact `memory_id` values from exported review files.
- Existing repository semantics for feedback, forget, supersession, merge links, safety, and trace remain available.
- Dry-run is the default because Markdown is user-editable and may contain mistakes.
- Model assistance is not required for MVP parsing; structured requests are safer than free-form natural language edits.
