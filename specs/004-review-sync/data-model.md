# Data Model: Review Sync And Change Requests

## Existing Source Of Truth

### `life_memories`

Authoritative memory table. Review sync reads this table to resolve ids, current status, sensitivity, lifecycle, content hash, and valid/current state. Apply mode mutates this table only through existing repository semantics.

Relevant fields:

- `memory_id`
- `content`
- `content_hash`
- `primary_category`
- `tags_json`
- `status`
- `review_status`
- `sensitivity`
- `confidence`
- `importance`
- `feedback_score`
- `valid_from`
- `valid_until`
- `updated_at`
- `injection_risk`

### `memory_links`

Existing relationship table. Review sync uses it for replace, merge, duplicate, and supersession behavior.

Relevant relations:

- `superseded_by`
- `merged_into`
- `duplicate_of`
- `conflicts_with`

### `memory_feedback`

Existing feedback table. Review sync should write feedback-equivalent actions through existing helpers when marking useful, wrong, outdated, duplicate, merge, reject, or important.

### `memory_traces`

Existing append-only trace ledger. Sync preview and apply runs should write safe trace payloads containing request ids, outcomes, affected ids, counts, and redacted source metadata.

## New Runtime Entities

### `ReviewChangeRequest`

Structured action parsed from `change-requests.md`.

Fields:

- `request_id`
- `action`: `delete`, `replace`, `merge`, `confirm`, `reject`, `mark_outdated`
- `target_memory_ids`
- `target_query`
- `replacement_content`
- `merged_content`
- `reason`
- `confirmation`
- `source_path`
- `start_line`
- `end_line`
- `raw_hash`

Rules:

- `request_id` must be stable and unique within a sync run.
- Exact ids are preferred.
- `target_query` is allowed for dry-run matching but must not silently mutate multiple rows.
- Replacement/merged content must pass classification and safety gates.
- Raw request text should be hashed or bounded in traces.

### `ReviewSyncPlan`

Dry-run output before mutation.

Fields:

- `source_path`
- `source_hash`
- `apply`
- `actions`
- `valid_count`
- `invalid_count`
- `ambiguous_count`
- `needs_confirmation_count`
- `declined_count`
- `warnings`
- `errors`

Rules:

- Dry-run must produce a plan without mutating SQLite.
- Plans should show affected ids and proposed operations, not hidden direct SQL.
- Sensitive/restricted content must be redacted or summarized.

### `ReviewSyncActionResult`

Per-action result returned by dry-run or apply.

Fields:

- `request_id`
- `action`
- `outcome`: `planned`, `applied`, `invalid`, `ambiguous`, `needs_confirmation`, `declined`, `not_found`, `failed`
- `target_memory_ids`
- `created_memory_ids`
- `trace_ids`
- `warnings`
- `errors`
- `redactions`

Rules:

- `applied` requires actual repository changes and trace ids.
- `planned` means dry-run only.
- `ambiguous`, `invalid`, `declined`, and `failed` must not mutate data.

### `ReviewSyncRun`

Run-level audit record. This may be represented by trace payload only or by a dedicated table if implementation needs stable query support.

Fields:

- `run_id`
- `mode`: `dry_run` or `apply`
- `source_path`
- `source_hash`
- `started_at`
- `completed_at`
- `parsed_count`
- `applied_count`
- `rejected_count`
- `failed_count`
- `trace_id`

Rules:

- Run metadata must not contain raw restricted content.
- Apply mode should be transactional per action or per run with explicit failure reporting.

## Optional New Table

### `review_sync_runs`

Only add this table if traces are insufficient.

Potential fields:

- `run_id TEXT PRIMARY KEY`
- `mode TEXT NOT NULL`
- `source_path TEXT`
- `source_hash TEXT NOT NULL`
- `status TEXT NOT NULL`
- `parsed_count INTEGER NOT NULL DEFAULT 0`
- `applied_count INTEGER NOT NULL DEFAULT 0`
- `rejected_count INTEGER NOT NULL DEFAULT 0`
- `failed_count INTEGER NOT NULL DEFAULT 0`
- `trace_id TEXT`
- `created_at TEXT NOT NULL`
- `completed_at TEXT`

Indexes:

- Index on `created_at`.
- Index on `status`.

Validation rules:

- `source_hash` must be content hash of the bounded sync input.
- `mode` must be `dry_run` or `apply`.
- Raw request content should not be stored in this table.
