# Research: Review Sync And Change Requests

## Decision 1: Structured Markdown Blocks Instead Of Free-Form Edits

**Decision**: MVP review sync should parse only structured request blocks in `change-requests.md`, for example fenced `life-memory-change` blocks with simple key/value fields.

**Rationale**: Free-form Markdown edits are hard to validate safely. A constrained format makes dry-run behavior deterministic, line-numbered, testable, and explainable.

**Rejected Alternatives**:

- Parse arbitrary edits in `facts.md` or `preferences.md`: too easy to misinterpret and too hard to audit.
- Use natural-language LLM parsing: useful later, but unsafe as the first write path from Markdown.
- Treat Markdown as the database: conflicts with the established SQLite source-of-truth design.

## Decision 2: Dry-Run First, Apply Only With Explicit Confirmation

**Decision**: `life_memory_sync_review` defaults to `apply=false`. Destructive actions require both `apply=true` and explicit per-action confirmation or an equivalent tool parameter.

**Rationale**: Review files are human-editable and may contain stale ids, copy/paste errors, or malformed content. Preview is the safest way to avoid accidental deletion or replacement.

**Rejected Alternatives**:

- Auto-apply all valid requests: too risky for personal memory.
- Require confirmation only at tool level: insufficient for mixed safe/destructive batches.

## Decision 3: Exact IDs Are The Primary Targeting Mechanism

**Decision**: Sync should prefer exact `memory_id` references exported by review files. Query-based targeting is allowed for preview, but ambiguous matches apply nothing.

**Rationale**: Memory content can be similar, superseded, sensitive, or archived. Exact ids reduce false positives and make audit traces precise.

**Rejected Alternatives**:

- Query-only requests: convenient, but ambiguous in real memory libraries.
- Hidden row numbers in Markdown: unstable after export regeneration.

## Decision 4: Reuse Existing Mutation Semantics

**Decision**: Apply mode should delegate to existing repository/tool semantics for delete, replace, feedback, supersession, merge, and trace behavior.

**Rationale**: `life_memory_feedback` and `life_memory_forget` already encode important lifecycle and tombstone rules. A parallel sync mutation path would drift and create safety bugs.

**Rejected Alternatives**:

- Direct SQL updates from sync: faster, but bypasses safety and trace conventions.
- Treat sync actions as reflection changes: reflection is background maintenance, while review sync is explicit user control.

## Decision 5: Trace Ledger Is The First Audit Store

**Decision**: Use existing traces for sync run and action outcomes first. Add `review_sync_runs` only if implementation needs stable run-level queries beyond trace payloads.

**Rationale**: Existing tools already rely on trace ids and bounded JSON payloads. Avoid schema growth unless tests show it is necessary.

**Rejected Alternatives**:

- No persistence for dry-run: weak auditability.
- Dedicated tables for every action type immediately: more schema than the MVP needs.

## Decision 6: Export Template Must Teach The Safe Workflow

**Decision**: `life_memory_export_review` should generate a `change-requests.md` template with examples, exact-id guidance, dry-run/apply steps, and warnings that other Markdown files are read-only.

**Rationale**: The safer the template, the less likely users are to write unsupported edits.

**Rejected Alternatives**:

- Keep the current placeholder template: not enough for a sync-capable workflow.
- Put sync instructions only in README: users will work inside the review directory.
