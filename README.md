# Hermes Life Memory Plugin

Standalone Hermes plugin for local, layered life memory. It keeps personal life
memory separate from technical/project memory and stores data in a local SQLite
database under `HERMES_HOME`.

## Repository Overview

Main implementation paths:

- `plugins/life_memory/__init__.py`: Hermes tool registration and handler entrypoints.
- `plugins/life_memory/classification.py`: rule-first memory classification.
- `plugins/life_memory/safety.py`: sensitive content and prompt-injection gates.
- `plugins/life_memory/repository.py`: SQLite schema, persistence, traces, review export, and reflection helpers.
- `plugins/life_memory/recall.py`: bounded lexical recall and ranking.
- `plugins/life_memory/embeddings.py`: deterministic local embedding provider seam and vector utilities for hybrid recall.
- `plugins/life_memory/hybrid_recall.py`: lexical/vector candidate merge, explainable score components, and time-aware reranking.
- `plugins/life_memory/reflection.py`: `light`, `session`, `rem`, `deep`, and `daily` memory maintenance.
- `plugins/life_memory/routing.py`: runtime routing patches that split Hermes default memory writes across native and life-memory stores, and compose pre-LLM routing guidance with activation context.
- `plugins/life_memory/activation.py`: automatic life-memory activation gate, strict injection filters, data-only context formatting, and activation traces.
- `plugins/life_memory/session_adapter.py`: read-only Hermes session/state adapter with transcript fallback.
- `plugins/life_memory/export_review.py`: read-only Markdown review export.
- `plugins/life_memory/review_sync.py`: explicit dry-run-first parser/planner/apply path for structured `change-requests.md` review edits.
- `tests/`: contract, integration, unit, performance smoke, and realistic transcript coverage.
- `specs/001-life-memory-plugin/`: base life-memory plugin spec, task list, quickstart, and design notes.
- `specs/002-memory-activation/`: automatic activation and context-injection spec, plan, tasks, and validation notes.
- `specs/003-hybrid-recall/`: hybrid lexical/vector recall spec, plan, tasks, and validation notes.
- `specs/004-review-sync/`: explicit Markdown change request sync spec, plan, tasks, and validation notes.

Registered tools:

- `life_memory_store`
- `life_memory_recall`
- `life_memory_feedback`
- `life_memory_forget`
- `life_memory_reflect`
- `life_memory_export_review`
- `life_memory_sync_review`

Registered hooks:

- `pre_llm_call`: injects a short layered routing reminder and, when clearly relevant and safe, a bounded data-only life-memory context block.

## Runtime Data

Default runtime paths:

- Database: `$HERMES_HOME/life_memory.db`
- Review export: `$HERMES_HOME/life_memory_review`

If `HERMES_HOME` is not set, the plugin uses `~/.hermes`.

## Development Mount

Hermes should see the plugin directory itself, not the repository root:

```bash
mkdir -p /Users/oliver/.hermes/plugins
ln -sfn /Users/oliver/Projects/hermes-life-memory/plugins/life_memory /Users/oliver/.hermes/plugins/life_memory
```

The mounted path should contain:

```text
/Users/oliver/.hermes/plugins/life_memory/plugin.yaml
/Users/oliver/.hermes/plugins/life_memory/__init__.py
```

Do not mount the repository root or copy files into the Hermes main source tree.

## Enable In Hermes

Enable the plugin through Hermes:

```bash
hermes plugins enable life_memory
```

Equivalent config shape:

```yaml
plugins:
  enabled:
    - life_memory
```

Discovery debugging:

```bash
HERMES_PLUGINS_DEBUG=1 hermes plugins list
```

Expected plugin metadata:

- key: `life_memory`
- source: `user`
- kind: `standalone`
- tools: all seven `life_memory_*` tools above

## Test Command

Use the project-pinned Python through `uv`:

```bash
uv run python -m pytest
```

The project is pinned to Python `3.11.15` through `.python-version`. On this
machine, plain `python` may be unavailable, so `uv run python -m pytest` is the
reproducible form of `python -m pytest`.

Latest validation:

```text
2026-06-06 Australia/Sydney
uv run python -m pytest
161 passed in 0.95s
Python 3.11.15, pytest 9.0.3
```

Additional realism coverage:

- `tests/fixtures/realistic_transcripts.json`: noisy multi-turn transcript cases with bilingual input, temporary context, do-not-store language, family facts, implicit routines, sensitive boundaries, and memory-injection boundaries.
- `tests/integration/test_realistic_memory_flows.py`: handler-level checks for realistic session extraction, Chinese daily-life store/recall, cross-session correction, recall after correction, and multi-session pattern promotion.
- `tests/unit/test_recall.py`: CJK n-gram recall coverage so Chinese daily questions can retrieve Chinese life memories.

## Review Export

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

By default this writes read-only Markdown files to:

```text
$HERMES_HOME/life_memory_review
```

Important boundary: Markdown export is audit-first. Normal runtime does not read
Markdown edits back into SQLite. The only supported reverse path is the explicit
`life_memory_sync_review` tool reading structured blocks from `change-requests.md`.

## Review Sync

`life_memory_sync_review` lets users turn review notes into bounded SQLite changes:

- reads only `$HERMES_HOME/life_memory_review/change-requests.md` or explicit inline text;
- parses fenced `life-memory-change` blocks;
- defaults to dry-run with `apply=false`;
- requires `apply=true`, `confirm_apply=true`, and per-action `confirm: true` for destructive changes;
- supports `delete`, `replace`, `merge`, `confirm`, `reject`, and `mark_outdated`;
- prefers exact `memory_id` targets and returns `ambiguous` for broad query matches;
- reuses existing forget, feedback, supersession, merge, safety, and trace semantics;
- ignores manual edits to `memory-library`, `memory-journal`, `review-needed.md`, and `archive.md`.

Example block:

````markdown
```life-memory-change
id: req-001
action: replace
memory_id: mem_example
replacement: I now buy unsweetened soy milk after Saturday runs.
reason: Corrected older running-drink memory.
confirm: true
```
````


## Hybrid Recall

Life-memory recall can now use a derived semantic index in addition to lexical search:

- SQLite `life_memories` remains the source of truth; embeddings are only a derived index.
- `FakeEmbeddingProvider` provides deterministic local embeddings for tests and offline prototype behavior.
- Hybrid recall merges lexical and vector candidates by `memory_id` and returns additive `score_components` plus `recall_sources`.
- Reranking uses semantic score, lexical score, importance, confidence, feedback, evidence, lifecycle, expiry, and supersession state.
- If embeddings are missing, stale, incompatible, or unavailable, recall falls back to lexical behavior.
- Automatic activation can use hybrid recall when a fresh semantic index is available, while keeping the same data-only injection and safety filters.

## Automatic Memory Activation

Before LLM calls, the plugin can now run a conservative activation pipeline:

- decide whether the current request clearly needs life memory;
- skip technical/project, user-profile, temporary, malformed, and ambiguous requests;
- recall a bounded candidate set only after the activation gate passes;
- exclude deleted, archived, expired, restricted, unauthorized sensitive, superseded, low-confidence, low-relevance, and high-injection-risk memories;
- inject at most a small data-only context block with `memory_id`, `status`, `confidence`, and `sensitivity`;
- fail closed to routing guidance only when hook payloads or storage are unavailable.

The injected memory block is data only. It must not be treated as system, developer, tool, or user instructions.

## Runtime Memory Routing

The plugin keeps Hermes source code untouched. When loaded, it patches imported
Hermes runtime objects in-process and can be removed by disabling or unmounting
the plugin.

Routing policy:

- L4 life memories go to `life_memory_store` and `$HERMES_HOME/life_memory.db`.
- L2 technical/project/environment memories stay in the built-in Hermes memory path.
- L3 stable user-profile instructions use the built-in `USER.md`/native profile path.
- Temporary task state, no-save content, one-off emotions, and trivial facts are declined.

The router also updates built-in memory tool descriptions, diverts mistaken L4
calls from the native `memory` tool into `life_memory_store`, prevents external
provider mirroring for L4 writes, and narrows holographic auto-extraction to
project/technical decisions instead of lifestyle preferences.

Latest black-box route validation:

```text
2026-06-02 Australia/Sydney
hermes -z "<natural Chinese weekend-running drink preference>"
life_memory.db: 1 routed L4 row created
memory_store.db: 0 matching native facts
MEMORY.md / USER.md: 0 matching lines
life_memory_recall: natural "weekend exercise drink" query returned 1 result
cleanup: life_memory_forget redacted the test row
```

## Implementation Boundaries

Allowed modified paths for this prototype:

- `/Users/oliver/Projects/hermes-life-memory/plugins/life_memory/`
- `/Users/oliver/Projects/hermes-life-memory/tests/`
- `/Users/oliver/Projects/hermes-life-memory/specs/001-life-memory-plugin/`
- `/Users/oliver/Projects/hermes-life-memory/specs/002-memory-activation/`
- `/Users/oliver/Projects/hermes-life-memory/specs/003-hybrid-recall/`
- `/Users/oliver/Projects/hermes-life-memory/specs/004-review-sync/`
- `/Users/oliver/Projects/hermes-life-memory/README.md`
- project metadata in `/Users/oliver/Projects/hermes-life-memory/`

Hermes main project files were not modified as part of this implementation.
`/Users/oliver/Projects/hermes-workspace` is not a git repository in this
environment, and `/Users/oliver/Projects/hermes-workspace/hermes-agent` is not
present here.

## Current Caveats

- Reflection is conservative and rule-based; it does not depend on an external model.
- `daily` reflection is report-only. It creates `reflection_reports` rows but no durable facts and no promotion-score changes.
- `session` reflection prefers read-only Hermes state/session lookup, but explicit `transcript` input is the reliable fallback for this standalone prototype.
- Sensitive content is confirmation-first and summary-first by default. Explicit full storage can keep selected life details in SQLite with sensitive metadata, but normal recall/export remains conservative and Markdown export never writes raw sensitive/restricted content.
- Runtime routing depends on Hermes internal module names such as `tools.memory_tool`, `agent.memory_manager`, and the holographic provider. Rerun `tests/unit/test_routing.py` and a black-box `hermes -z` route check after Hermes upgrades.
