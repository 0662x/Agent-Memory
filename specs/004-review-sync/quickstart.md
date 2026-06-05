# Quickstart: Review Sync And Change Requests

This quickstart describes the intended validation workflow for `004-review-sync`. It is a draft until implementation tasks are complete.

## 1. Repository

```bash
cd /Users/oliver/Projects/hermes-life-memory
```

Expected branch:

```bash
git branch --show-current
# expected: 004-review-sync
```

## 2. Spec Prerequisites

```bash
bash .specify/scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks
```

Expected output should resolve:

```text
FEATURE_DIR=/Users/oliver/Projects/hermes-life-memory/specs/004-review-sync
AVAILABLE_DOCS includes research.md, data-model.md, contracts/, quickstart.md, tasks.md
```

Latest validation:

```text
2026-06-06 Australia/Sydney
FEATURE_DIR=/Users/oliver/Projects/hermes-life-memory/specs/004-review-sync
AVAILABLE_DOCS includes research.md, data-model.md, contracts/, quickstart.md, tasks.md
```

## 3. Export Review Markdown

After implementation, seed a temporary database and export review files:

```bash
uv run python - <<'PY'
from plugins.life_memory import life_memory_store, life_memory_export_review

life_memory_store({"content": "I usually buy coconut water after weekend runs."})
print(life_memory_export_review({"include_archive": True, "include_sensitive": "summary_only"}))
PY
```

Expected files:

```text
$HERMES_HOME/life_memory_review/change-requests.md
$HERMES_HOME/life_memory_review/memory-library/facts.md
$HERMES_HOME/life_memory_review/memory-library/preferences.md
```

## 4. Write A Change Request

Add a structured request to `change-requests.md`:

````markdown
```life-memory-change
id: req-001
action: replace
memory_id: mem_example
replacement: I now buy unsweetened soy milk after Saturday runs.
reason: User corrected older coconut-water memory.
confirm: true
```
````

## 5. Dry-Run Sync

```bash
uv run python - <<'PY'
from plugins.life_memory import life_memory_sync_review

print(life_memory_sync_review({"apply": False}))
PY
```

Expected behavior:

- Parses request blocks.
- Returns planned actions, warnings, errors, affected memory ids, and trace id.
- Does not change recall results, lifecycle status, feedback rows, links, or promotion scores.

## 6. Apply Sync

```bash
uv run python - <<'PY'
from plugins.life_memory import life_memory_sync_review

print(life_memory_sync_review({"apply": True, "confirm_apply": True}))
PY
```

Expected behavior:

- Applies only valid confirmed requests.
- Reuses existing forget/feedback/store/supersession semantics.
- Writes trace rows.
- Returns applied action results and created/replaced/deleted memory ids.

## 7. Re-Export Review

```bash
uv run python - <<'PY'
from plugins.life_memory import life_memory_export_review

print(life_memory_export_review({"include_archive": True, "include_sensitive": "summary_only"}))
PY
```

Expected behavior:

- Updated Markdown reflects the new SQLite state.
- Deleted raw content remains redacted.
- `change-requests.md` remains a template or keeps unapplied requests according to implementation policy.

## 8. Test Commands

Targeted tests after implementation:

```bash
uv run python -m pytest tests/unit/test_review_sync.py tests/integration/test_review_sync.py tests/integration/test_export_review.py tests/contract/test_tool_contracts.py
```

Full suite:

```bash
uv run python -m pytest
```

Baseline validation before implementation:

```text
2026-06-06 Australia/Sydney
uv run python -m pytest
137 passed in 0.74s
Python 3.11.15, pytest 9.0.3
```

## 9. Current Status

This stage is a draft specification. No `life_memory_sync_review` implementation exists yet. Markdown export remains read-only until this feature is implemented and validated.
