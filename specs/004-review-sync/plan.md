# Implementation Plan: Review Sync And Change Requests

**Branch**: `004-review-sync` | **Date**: 2026-06-06 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/004-review-sync/spec.md`

## Summary

This phase adds an explicit, dry-run-first Markdown review sync capability for the completed `life_memory` plugin. The feature will parse a constrained `change-requests.md` file, validate requests against current SQLite state and safety gates, preview planned actions, and optionally apply confirmed changes using existing store/feedback/forget/link/trace semantics.

Markdown remains a review surface, not the source of truth. SQLite remains authoritative. Sync is never automatic, does not watch files, and does not read arbitrary edited export files. The initial tool surface is expected to be `life_memory_sync_review`, added as a seventh plugin tool only after parser, validator, dry-run, safety, and trace behavior are tested.

## Technical Context

**Language/Version**: Python 3.11+, matching the existing Hermes plugin runtime.

**Primary Dependencies**: Python standard library only. Use `dataclasses`, `hashlib`, `json`, `pathlib`, `re`, and existing plugin modules. Tests use the existing `pytest` setup.

**Storage**: Existing `$HERMES_HOME/life_memory.db` remains the source of truth. MVP can store sync audit data in the existing trace ledger; a small `review_sync_runs` table may be added if trace payloads are not enough for run-level status.

**Testing**: Add parser unit tests, repository/transaction tests if a new table is introduced, contract tests for the new tool schema, integration tests against temporary `HERMES_HOME`, and export/sync round-trip tests.

**Target Platform**: macOS local Hermes profile first; standalone user plugin layout.

**Project Type**: Python package/plugin under `plugins/life_memory`, with tests under `tests/` and feature docs under `specs/004-review-sync/`.

**Performance Goals**:

- Parse typical `change-requests.md` files under 100 requests in under 1 second.
- Keep dry-run and apply bounded by explicit `max_actions`.
- Avoid scanning exported journal/library files in MVP.
- Preserve existing 10,000-row recall/store performance tests.

**Constraints**:

- Do not modify Hermes core source files.
- Do not make Markdown the source of truth.
- Do not auto-apply Markdown edits.
- Do not parse arbitrary natural language from all review files.
- Do not bypass existing safety, sensitivity, deletion, lifecycle, supersession, or injection-risk rules.
- Do not expose deleted/restricted raw content in sync result payloads or traces.
- Preserve existing public tool behavior and all current tests.

**Scale/Scope**: Single-user local profile; bounded explicit sync runs; no cross-device or multi-user conflict resolution.

## Constitution Check

Current `.specify/memory/constitution.md` is still the Spec Kit placeholder, so this plan follows established project gates:

- **Plugin boundary**: PASS. Work stays in `/Users/oliver/Projects/hermes-life-memory` and the standalone plugin.
- **No Hermes core edits**: PASS. Sync is a plugin tool and repository extension only.
- **Local-first storage**: PASS. SQLite remains authoritative; Markdown is input only for explicit sync requests.
- **Safety boundary**: PASS. Sync uses existing classification, safety, sensitivity, lifecycle, and forget semantics.
- **Auditability**: PASS. Dry-run/apply outcomes must write safe traces and return trace ids.
- **Prototype simplicity**: PASS. MVP uses constrained structured Markdown syntax and stdlib parsing.

Post-design re-check: pending implementation.

## Project Structure

### Documentation

```text
specs/004-review-sync/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── review-sync.md
└── tasks.md
```

### Source Code

```text
plugins/life_memory/
├── review_sync.py      # New: parser, validator, planner, dry-run/apply orchestration
├── export_review.py    # Update: richer change-requests template and stable actionable ids
├── repository.py       # Update only if run-level sync helpers/table are needed
├── contracts.py        # Update: life_memory_sync_review JSON schema
├── models.py           # Update only if new enums/dataclasses help trace/result shape
└── __init__.py         # Update: register life_memory_sync_review handler

tests/
├── fixtures/
│   └── review_change_requests.md
├── unit/
│   └── test_review_sync.py
├── integration/
│   ├── test_review_sync.py
│   └── test_export_review.py
└── contract/
    └── test_tool_contracts.py
```

**Structure Decision**: Keep parser/planner/apply logic in a focused `review_sync.py` module. Existing `export_review.py` should only generate templates and stable ids. Existing handlers should delegate to `review_sync.py` rather than embedding parsing logic in `__init__.py`.

## Phase 0 Research Output

See [research.md](./research.md). Key decisions:

- Use structured fenced Markdown blocks, not arbitrary free-form edit parsing.
- Make dry-run the default and require explicit apply confirmation for destructive actions.
- Prefer exact `memory_id` targeting; query-based targeting is preview-only unless unambiguous and explicitly confirmed.
- Reuse existing feedback/forget/store/link semantics instead of inventing a parallel mutation engine.
- Use trace-first auditing; add a table only if traces are insufficient for run-level reporting.

## Phase 1 Design Output

- Data model: [data-model.md](./data-model.md)
- Contract: [contracts/review-sync.md](./contracts/review-sync.md)
- Validation guide: [quickstart.md](./quickstart.md)

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| None | N/A | N/A |
