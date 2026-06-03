# Implementation Plan: Memory Activation And Context Injection

**Branch**: `002-memory-activation` | **Date**: 2026-06-03 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/002-memory-activation/spec.md`

## Summary

This phase adds automatic life-memory activation and safe context injection to the existing Hermes `life_memory` user plugin. The completed `001-life-memory-plugin` stage already provides durable life-memory storage, explicit recall, feedback, forgetting, reflection, Markdown review export, and runtime write-routing. This stage uses those existing capabilities before each LLM call: decide whether life memory is needed, recall relevant safe candidates, format a small data-only memory block, and inject it through the existing `pre_llm_call` hook.

The implementation remains rule-first and local-first. It does not add embeddings, vector storage, model reranking, Markdown reverse sync, cloud services, or Hermes core source edits. Automatic injection is deliberately stricter than explicit `life_memory_recall`: if the request is ambiguous, the hook payload is missing, SQLite is unavailable, or all candidates are unsafe, it injects nothing and lets Hermes continue normally.

## Technical Context

**Language/Version**: Python 3.11+, following the current Hermes runtime.

**Primary Dependencies**: Python standard library only for runtime (`dataclasses`, `re`, `logging`, `json`, `typing`, `pathlib` as needed). Existing plugin modules are reused: `classification.py`, `repository.py`, `recall.py`, `safety.py`, `routing.py`, and `time_utils.py`. Tests use existing `pytest` setup.

**Storage**: Existing `$HERMES_HOME/life_memory.db`. No new SQLite tables are required. The existing `traces` table should record activation decisions. A Python enum value such as `activation` or `context_injection` may be added for trace operation names without a schema migration.

**Testing**: `pytest` unit tests, integration-style handler/hook tests, fixture-driven activation evaluation, and one optional manual Hermes smoke test. Tests should run through `uv run python -m pytest`.

**Target Platform**: macOS local Hermes profile first, compatible with the current standalone user plugin layout.

**Project Type**: Hermes standalone directory plugin extension under `plugins/life_memory`.

**Performance Goals**:

- `pre_llm_call` activation path should add minimal latency and must avoid model calls.
- Activation gate should be deterministic string/rule matching and complete in milliseconds.
- Automatic recall should fetch a bounded candidate set and inject at most 3 memory entries by default.
- Injection block should stay within a configurable character budget, defaulting to a conservative small context block.
- Hook failure must be fail-closed and must not block the LLM call.

**Constraints**:

- Do not modify Hermes core source files.
- Do not introduce new runtime third-party dependencies.
- Do not add embeddings, vector databases, semantic indexes, or model reranking in this phase.
- Do not sync Markdown edits back into SQLite.
- Do not execute tools or actions from recalled memory.
- Recalled memory is data only, never an instruction.
- Deleted, expired, restricted, unauthorized sensitive, and superseded memories must not be injected.
- Existing explicit `life_memory_recall` behavior must remain backward compatible.
- Existing runtime write-routing must remain installed and must not be disabled by activation.

**Scale/Scope**: Single-user local profile, existing 10,000-row performance smoke target from `001`. This feature only adds pre-LLM decision/recall/filter/format/inject behavior.

## Constitution Check

Current `.specify/memory/constitution.md` is still the Spec Kit template, so this plan uses the existing project constraints as the effective gates:

- **Plugin boundary**: PASS. Work stays in `/Users/oliver/Projects/hermes-life-memory` and the standalone user plugin.
- **No Hermes core edits**: PASS. Integration uses `pre_llm_call` hook and runtime plugin code only.
- **Local-first storage**: PASS. Uses existing `$HERMES_HOME/life_memory.db`.
- **Safety boundary**: PASS. Injected memory is data only, bounded, and filtered more strictly than explicit recall.
- **Auditability**: PASS. Activation outcomes are traced when repository access is available.
- **Prototype simplicity**: PASS. No embeddings, vector DB, model rerank, or Markdown sync in this phase.

Post-design re-check: PASS. Phase 1 design artifacts preserve the same constraints and add no new external dependencies.

## Project Structure

### Documentation (this feature)

```text
specs/002-memory-activation/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
└── contracts/
    └── activation-hook.md
```

### Source Code (repository root)

```text
plugins/
└── life_memory/
    ├── activation.py            # New: activation gate, safe recall wrapper, injection formatter
    ├── routing.py               # Update: compose routing guidance with activation context in pre_llm_call
    ├── __init__.py              # Update only if registration wiring needs to expose activation hook config
    ├── models.py                # Update: activation dataclasses/enums and trace operation names if needed
    ├── repository.py            # Reuse: search, filters, traces; small helper only if needed
    ├── recall.py                # Reuse ranking; add auto-injection scoring helper only if needed
    └── safety.py                # Reuse injection-risk checks and sensitivity handling

tests/
├── fixtures/
│   └── activation_cases.json
├── unit/
│   └── test_activation.py
└── integration/
    └── test_activation_hook.py
```

**Structure Decision**: Add a focused `activation.py` module instead of expanding `routing.py` into a mixed policy engine. `routing.py` should continue handling write-routing and hook installation; activation owns read-time decisions, filters, formatting, and hook payload normalization. This keeps write-routing and read-time activation testable independently.

## Phase 0 Research Output

See [research.md](./research.md). Key decisions:

- Use a rule-first activation gate and skip by default on ambiguity.
- Reuse existing lexical/FTS recall first; no embedding or rerank in this phase.
- Apply stricter injection filters than explicit recall.
- Format a small data-only context block with metadata and budget limits.
- Compose with the existing `pre_llm_call` routing hook rather than replacing it.
- Trace activation decisions without leaking restricted or deleted content.

## Phase 1 Design Output

- Data model: [data-model.md](./data-model.md)
- Hook and formatter contracts: [contracts/activation-hook.md](./contracts/activation-hook.md)
- Validation guide: [quickstart.md](./quickstart.md)

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| None | N/A | N/A |
