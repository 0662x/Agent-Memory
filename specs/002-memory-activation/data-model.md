# Data Model: Memory Activation And Context Injection

## Overview

This feature does not require new durable domain tables. It adds in-memory activation entities and uses the existing `$HERMES_HOME/life_memory.db` tables from `001-life-memory-plugin`:

- `life_memories` for candidate memory rows;
- `memory_links` for supersede/support relationships;
- `memory_traces` or the existing trace table for audit events;
- existing FTS/LIKE search helpers for retrieval.

If implementation adds new trace operation enum values, they are stored as text and do not require a SQLite migration.

## Entities

### ActivationDecision

Represents whether the current request should trigger automatic life-memory recall.

| Field | Type | Notes |
|-------|------|-------|
| `activate` | bool | True only when life memory is clearly relevant |
| `reason` | str | Human-readable explanation for activate/skip |
| `confidence` | float | 0.0 to 1.0 rule confidence |
| `request_type` | str | `life_memory`, `technical`, `temporary`, `profile`, `smalltalk`, `ambiguous`, `malformed` |
| `query` | str | Normalized query to pass to recall when activated |
| `matched_terms` | list[str] | Rule terms or signals that drove the decision |

Validation:

- `activate=false` when `query` is empty or hook payload is malformed.
- `confidence` is clamped to `0.0..1.0`.
- `technical`, `temporary`, `profile`, `smalltalk`, `ambiguous`, and `malformed` request types do not run recall.

### ActivationContext

Normalized view of the `pre_llm_call` hook payload.

| Field | Type | Notes |
|-------|------|-------|
| `current_user_text` | str | Best-effort current user request extracted from hook kwargs |
| `conversation_hint` | str | Optional short context if Hermes provides it |
| `hook_source` | str | Where text was found, e.g. `user_message`, `conversation_history`, `message`, `messages`, `prompt`, `unknown` |
| `raw_keys` | list[str] | Hook payload keys for debugging, not raw content |
| `allow_sensitive` | bool | Defaults false; reserved for future explicit scope support |

Validation:

- Missing text produces an activation skip.
- Raw full prompt/history should not be stored in traces.
- Official Hermes `pre_llm_call` payloads should resolve from `user_message`; `conversation_history` is only a fallback.

### InjectionPolicy

Runtime settings for automatic injection.

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `max_memories` | int | 3 | Hard cap for injected entries |
| `candidate_limit` | int | 12 | Candidate fetch/rank limit before strict filters |
| `max_block_chars` | int | 1600 | Hard budget for final context block |
| `max_content_chars` | int | 320 | Per-memory content budget |
| `min_relevance_score` | float | 0.20 | Minimum ranked relevance for injection |
| `min_confidence` | float | 0.60 | Minimum memory confidence for stable statuses |
| `min_young_confidence` | float | 0.80 | Minimum confidence for injecting young memories |
| `allow_archived` | bool | false | Archived memories are skipped by default |
| `allow_sensitive` | bool | false | Sensitive raw content is skipped by default |

Validation:

- `max_memories` is clamped to `1..5`.
- `max_block_chars` and `max_content_chars` must be positive.
- Defaults must satisfy the spec requirement that no more than three memories are injected.

### InjectedMemoryEntry

Sanitized memory item selected for pre-LLM context.

| Field | Type | Notes |
|-------|------|-------|
| `memory_id` | str | Stable memory id |
| `status` | str | Lifecycle status |
| `confidence` | float | Existing memory confidence |
| `sensitivity` | str | `normal`, `sensitive`, or `restricted` |
| `primary_category` | str | Existing primary category |
| `tags` | list[str] | Existing tags, bounded |
| `content` | str | Bounded content or safe summary |
| `relevance_score` | float | Score from existing ranking plus injection filters |
| `relevance_reason` | str | Short reason for inclusion |
| `safety_note` | str | Required when content is instruction-like or otherwise constrained |
| `data_only` | bool | Always true |

Validation:

- Deleted, expired, restricted, unauthorized sensitive, and superseded current facts cannot become entries.
- `content` is truncated to the per-memory budget.
- `data_only` must be true.
- Prompt-injection-like content must be omitted or carry a safety note.

### InjectedMemoryBlock

Final text block returned from the hook.

| Field | Type | Notes |
|-------|------|-------|
| `context` | str | Data-only memory context string |
| `memory_ids` | list[str] | Injected memory ids |
| `entry_count` | int | Number of injected entries |
| `omitted_count` | int | Count of candidates omitted by filters or budget |
| `filter_reasons` | dict[str, int] | Aggregate filter counts |
| `trace_id` | str | Optional activation trace id |

Validation:

- Empty entries produce no block.
- Context must include a data-only boundary.
- Context length must be within policy budget.

### ActivationTrace

Audit payload written to the existing trace ledger.

| Field | Type | Notes |
|-------|------|-------|
| `operation` | str | Proposed value: `activation` |
| `outcome` | str | `skipped`, `activated`, `not_found`, `filtered`, `injected`, `error` |
| `reason` | str | Decision or failure reason |
| `request_type` | str | From ActivationDecision |
| `injected_memory_ids` | list[str] | Only ids, no raw restricted content |
| `candidate_count` | int | Number of candidates considered |
| `filter_reasons` | dict[str, int] | Aggregate safety/lifecycle filter counts |
| `error_type` | str | Optional exception class or failure category |

Validation:

- Trace input text should be redacted or bounded.
- Trace must not contain deleted or restricted raw content.

## Existing Memory Row Rules For Injection

A memory may be automatically injected only if all applicable conditions pass:

- `status != deleted`;
- `status != archived` unless policy explicitly allows archived;
- `valid_until` is absent or in the future;
- memory is not superseded as a current fact;
- `sensitivity == normal` unless future explicit scope allows sensitive summary;
- `injection_risk` is below the omission threshold, or the content is marked as quoted data with a safety note;
- confidence and relevance exceed policy thresholds;
- final block budget has remaining capacity.
