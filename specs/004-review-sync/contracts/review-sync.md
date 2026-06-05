# Contract: Review Sync And Change Requests

## Public Tool: `life_memory_sync_review`

This tool is explicit and user-invoked. Normal store, recall, activation, reflection, and export do not call it automatically.

## Input

Default dry-run from exported review directory:

```json
{
  "apply": false,
  "review_dir": "$HERMES_HOME/life_memory_review",
  "source_file": "change-requests.md",
  "max_actions": 50
}
```

Inline dry-run input for tests or API use:

```json
{
  "apply": false,
  "change_requests_text": "```life-memory-change\naction: delete\nmemory_id: mem_example\nconfirm: false\n```",
  "max_actions": 10
}
```

Apply mode:

```json
{
  "apply": true,
  "review_dir": "$HERMES_HOME/life_memory_review",
  "source_file": "change-requests.md",
  "confirm_apply": true,
  "max_actions": 50
}
```

Field rules:

- `apply`: defaults to `false`.
- `review_dir`: defaults to `$HERMES_HOME/life_memory_review`.
- `source_file`: defaults to `change-requests.md`; MVP should reject paths outside `review_dir` unless explicit inline text is provided.
- `change_requests_text`: optional inline source; useful for tests and explicit API calls.
- `confirm_apply`: required for destructive apply mode.
- `max_actions`: bounded maximum parsed requests.
- `include_sensitive`: optional and defaults to `false`; does not override restricted content rules.

## Supported Markdown Syntax

MVP parses fenced blocks only:

````markdown
```life-memory-change
id: req-001
action: replace
memory_id: mem_abc123
replacement: I now buy unsweetened soy milk after Saturday runs.
reason: User corrected older coconut-water habit.
confirm: true
```
````

Supported actions:

- `delete`
- `replace`
- `merge`
- `confirm`
- `reject`
- `mark_outdated`

Examples:

````markdown
```life-memory-change
id: req-delete-001
action: delete
memory_id: mem_old
reason: This memory is wrong.
confirm: true
```

```life-memory-change
id: req-merge-001
action: merge
memory_ids: [mem_a, mem_b]
merged_content: User usually buys unsweetened soy milk after Saturday runs.
reason: Duplicate running-drink memories.
confirm: true
```
````

## Output

Dry-run output:

```json
{
  "ok": true,
  "outcome": "planned",
  "apply": false,
  "source_hash": "sha256:...",
  "summary": {
    "parsed": 2,
    "planned": 1,
    "invalid": 0,
    "ambiguous": 1,
    "needs_confirmation": 0,
    "declined": 0
  },
  "actions": [
    {
      "request_id": "req-delete-001",
      "action": "delete",
      "outcome": "planned",
      "target_memory_ids": ["mem_old"],
      "warnings": []
    }
  ],
  "trace_id": "trace_example"
}
```

Apply output:

```json
{
  "ok": true,
  "outcome": "applied",
  "apply": true,
  "summary": {
    "parsed": 1,
    "applied": 1,
    "failed": 0
  },
  "actions": [
    {
      "request_id": "req-delete-001",
      "action": "delete",
      "outcome": "applied",
      "target_memory_ids": ["mem_old"],
      "trace_ids": ["trace_forget", "trace_sync"]
    }
  ],
  "trace_id": "trace_sync_run"
}
```

Failure output:

```json
{
  "ok": false,
  "outcome": "invalid",
  "apply": false,
  "message": "change-requests.md contains malformed request blocks",
  "actions": [
    {
      "request_id": null,
      "action": null,
      "outcome": "invalid",
      "line": 12,
      "errors": ["missing action"]
    }
  ],
  "trace_id": "trace_sync_invalid"
}
```

## Safety Contract

- Dry-run never mutates durable memory state.
- Apply never runs unless `apply=true` and required confirmations are present.
- Restricted raw content is never returned or traced.
- Replacement and merged content pass classification, sensitivity, and prompt-injection checks before storage.
- Query-based targets that match multiple memories return `ambiguous` and apply nothing.
- Deleted memory content is not resurfaced through sync output.
- Manual edits to exported library/journal/archive files are ignored in MVP.

## Repository/Handler Contract

Proposed callable boundaries:

```python
def parse_review_change_requests(text: str, *, source_path: str | None = None) -> list[ReviewChangeRequest]:
    ...


def plan_review_sync(repo, requests, *, apply: bool = False, max_actions: int = 50) -> ReviewSyncPlan:
    ...


def apply_review_sync_plan(repo, plan, *, confirm_apply: bool = False) -> ReviewSyncPlan:
    ...
```

Handler rules:

- `life_memory_sync_review` reads input, parses requests, builds a plan, optionally applies it, writes trace, and returns the result envelope.
- The handler must catch parsing/repository errors and return structured failure results.
- Apply should run inside repository transactions when possible.
