# Quickstart: Hermes 分层生活记忆插件

This quickstart reflects the current standalone prototype implementation.

## 1. Repository

```bash
cd /Users/oliver/Projects/hermes-life-memory
```

Implemented source package:

```text
plugins/life_memory/
├── __init__.py
├── classification.py
├── contracts.py
├── export_review.py
├── models.py
├── plugin.yaml
├── recall.py
├── reflection.py
├── repository.py
├── safety.py
├── session_adapter.py
└── time_utils.py
```

## 2. Run Tests

Use the project-pinned Python through `uv`:

```bash
uv run python -m pytest
```

Latest validation:

```text
2026-06-02 Australia/Sydney
uv run python -m pytest
71 passed in 0.34s
Python 3.11.15, pytest 9.0.3
```

Covered test groups:

- contract tests for all six tool schemas;
- integration tests that call handlers directly with a temporary `HERMES_HOME`;
- realistic transcript integration tests for bilingual/noisy sessions, do-not-store boundaries, correction, cross-session recall, and pattern promotion;
- unit tests for classification, safety, repository, recall, session adapter, and reflection;
- read-only Markdown export tests;
- 10,000-row store/recall performance smoke coverage with bounded recall results.

## 3. Development Mount

Hermes must see the plugin directory itself, not the repo root:

```bash
mkdir -p /Users/oliver/.hermes/plugins
ln -sfn /Users/oliver/Projects/hermes-life-memory/plugins/life_memory /Users/oliver/.hermes/plugins/life_memory
```

The installed plugin path must contain:

```text
/Users/oliver/.hermes/plugins/life_memory/plugin.yaml
/Users/oliver/.hermes/plugins/life_memory/__init__.py
```

Do not mount these paths:

```text
/Users/oliver/Projects/hermes-life-memory
/Users/oliver/.hermes/hermes-agent/plugins/life_memory
/Users/oliver/Projects/hermes-workspace/hermes-agent/plugins/life_memory
```

## 4. Enable Plugin

Enable through Hermes config or command:

```bash
hermes plugins enable life_memory
```

Equivalent config shape:

```yaml
plugins:
  enabled:
    - life_memory
```

## 5. Discovery Debugging

Use plugin debug logs if Hermes does not load the plugin:

```bash
HERMES_PLUGINS_DEBUG=1 hermes plugins list
```

Expected behavior:

- plugin key is `life_memory`;
- source is `user`;
- kind is `standalone`;
- error is empty after enabled;
- registered tools include `life_memory_store`, `life_memory_recall`, `life_memory_feedback`, `life_memory_forget`, `life_memory_reflect`, and `life_memory_export_review`.

## 6. Manual Prototype Checks

### Store life memory

Ask Hermes to remember:

```text
Remember that I prefer to work late at night and usually think better after midnight.
```

Expected result:

- stored as `life_memory`;
- `primary_category` is `personal_preference`, with routine/night/work-style tags;
- status starts as `young`;
- trace is recorded.

### Mixed-language session extraction

Run `life_memory_reflect` with an explicit transcript fallback:

```text
mode=session
apply=true
transcript=[
  {"role":"user","content":"不要长期记这个，我今天有点焦虑。"},
  {"role":"user","content":"这个可以长期记一下：我通常晚上十点以后 focus 更好。Also, I prefer short implementation plans before code changes."}
]
```

Expected result:

- temporary do-not-store state is declined;
- durable bilingual work-style signals become young memories only when `apply=true`;
- source refs are preserved in the session report.

### Reject technical memory

Ask Hermes to remember:

```text
My Hermes runs on Mac, and Windows is connected through SSH.
```

Expected result:

- classified as `technical_memory`;
- not stored in `life_memory`.

### Recall

Ask:

```text
What do you remember about my late-night work routine?
```

Expected result:

- bounded recall result with memory id;
- no unrelated memories;
- access count and last accessed time updated.

### Feedback and correction

Say:

```text
That memory is outdated. I now prefer focused work in the morning.
```

Expected result:

- old memory is superseded or archived;
- replacement fact is stored or linked;
- future recall does not present old fact as current.

### Forget

Say:

```text
Forget that late-night work routine memory.
```

Expected result:

- if one match exists, status becomes `deleted`;
- if multiple matches exist, Hermes asks for disambiguation;
- deleted content does not appear in future normal recall.

### Sensitive confirmation

Ask Hermes to remember sensitive personal information without saying it should be saved long-term.

Expected result:

- outcome is `needs_confirmation`;
- no durable memory is created;
- Hermes asks whether to save long-term and whether to save a summary or full content.

If the user explicitly says not to save sensitive content, a direct `declined` outcome is also valid and must not create durable memory.

### Recent state TTL

Create a memory tagged as a short-term recent state, then simulate expiry beyond 14 days.

Expected result:

- expired `recent_state` is not recalled as a current fact;
- `life_memory_reflect(mode="light", apply=true)` archives it with `decay_reason=ttl_expired`.

### REM/deep reflection

Run `life_memory_reflect(mode="rem")` or `life_memory_reflect(mode="deep")` after several compatible memories exist.

Expected result:

- `rem` proposes conflicts and pattern candidates;
- `deep` only auto-promotes low-risk reflected abstract experience memories with supporting memory ids;
- weak or sensitive patterns require review instead of automatic durable facts.

### Daily report

Run daily reflection:

```text
life_memory_reflect(mode="daily", apply=true)
```

Expected result:

- a daily report row is generated for audit;
- no durable memories are created from the daily report;
- `promotion_score` is not changed by the daily report.

### Export review Markdown

Programmatic smoke command:

```bash
uv run python - <<'PY'
from plugins.life_memory import life_memory_export_review

print(life_memory_export_review({
    "include_archive": True,
    "include_sensitive": "summary_only",
}))
PY
```

Expected result:

- Markdown review files are generated under the chosen export directory;
- expected files include `memory-library/`, `memory-journal/`, `review-needed.md`, `change-requests.md`, and optional `archive.md`;
- export is read-only from SQLite and does not sync Markdown edits back into the database.

## 7. Database Location

Runtime database:

```text
/Users/oliver/.hermes/life_memory.db
```

Tests use a temporary `HERMES_HOME` and must not write to the real Hermes profile.

## 8. Remaining Caveats

- Reflection is conservative and rule-based; this prototype does not call an external model.
- Session adapter support is intentionally schema-tolerant but limited to common `messages`, `session_messages`, and `sessions` table shapes.
- Explicit `transcript` is the reliable fallback for standalone session reflection tests.
- Daily reflection is report-only by design and must not be used as a durable fact source.
- Markdown review export is one-way; correction or forget requests must still go through tool calls.
- Realistic tests now cover more conversational noise, but they are still hand-written fixtures rather than production telemetry.
