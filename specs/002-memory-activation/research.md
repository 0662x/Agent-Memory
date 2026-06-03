# Research: Memory Activation And Context Injection

## Decision: Rule-first activation gate

**Rationale**: Automatic context injection has higher risk than explicit tool recall. The gate must be deterministic, explainable, and easy to test against false positives. A rule-first gate can classify clear personal-life questions, clear technical/project questions, current-task context, and no-save cases without invoking a model.

**Alternatives considered**:

- **Always recall life memory before every LLM call**: Rejected. It increases privacy leakage, prompt bloat, and irrelevant personalization.
- **LLM classifier for every request**: Rejected for this phase. It adds latency and nondeterminism to the hot path.
- **Only manual `life_memory_recall`**: Rejected as the next stage goal is automatic use of existing memory.

## Decision: Skip by default on ambiguity

**Rationale**: The memory architecture notes state that recall should be conservative: better to recall too little than inject unrelated personal context. Ambiguous requests, malformed hook payloads, missing current-user text, or unavailable storage should produce no injected memory.

**Alternatives considered**:

- **Broad activation with post-filtering only**: Rejected. Even safe but irrelevant memory context can steer answers incorrectly.
- **Ask user every time activation is ambiguous**: Rejected. It would interrupt normal conversation and is unnecessary for a background hook.

## Decision: Reuse existing recall and ranking first

**Rationale**: `001-life-memory-plugin` already implemented FTS/LIKE fallback, CJK tokenization, lifecycle filtering, ranking, young downweighting, and traceable explicit recall. This phase should wrap and narrow that behavior instead of introducing new retrieval infrastructure.

**Alternatives considered**:

- **Embedding retrieval now**: Deferred. The project report identifies hybrid recall as useful after activation and safe injection are stable.
- **Separate activation-specific index**: Rejected. It adds schema and consistency complexity without being required for the first automatic-injection slice.

## Decision: Automatic injection is stricter than explicit recall

**Rationale**: Explicit `life_memory_recall` is user/tool initiated and can expose structured results for inspection. Automatic injection happens silently before an LLM call, so it must exclude more aggressively: deleted, expired, archived by default, restricted, unauthorized sensitive, superseded, very low-confidence, high-injection-risk, and weakly relevant memories.

**Alternatives considered**:

- **Use the exact explicit recall results**: Rejected. The explicit recall contract permits scenarios that are too permissive for automatic prompt context.
- **Only inject reinforced memories**: Rejected for MVP because recent high-confidence active memories should still be useful. The filter can allow active/reinforced and selected high-confidence young candidates under strict caps.

## Decision: Data-only bounded context format

**Rationale**: The existing architecture treats memory as data, never as instructions. The injected block must make this boundary explicit, include memory ids for audit/correction, and stay small enough to avoid prompt pollution.

**Alternatives considered**:

- **Inject raw memory text only**: Rejected. Missing ids, status, confidence, and safety boundary makes correction and auditing harder.
- **Inject full recall JSON**: Rejected. Too verbose and exposes implementation details that are not needed by the model.
- **Summarize all matching memories into prose**: Rejected for this phase. Summarization can distort facts and would require model involvement or new summary logic.

## Decision: Compose with existing `pre_llm_call` routing hook

**Rationale**: Phase 10 already uses `pre_llm_call` to add layered memory routing guidance. Activation should use the same hook path and preserve routing guidance. The hook output should append a memory context block only when activation succeeds.

**Alternatives considered**:

- **Register a second unrelated hook with uncertain ordering**: Rejected unless Hermes requires it. A composed hook is easier to test and reason about.
- **Patch Hermes core prompt assembly**: Rejected. It violates the plugin boundary.

## Decision: Trace activation without leaking restricted content

**Rationale**: Automatic memory use must be auditable. Trace rows should record activation outcome, reason, injected ids, filter counts, and failure modes, but must not store deleted or restricted raw content.

**Alternatives considered**:

- **No trace for pre-LLM activation**: Rejected. It would make automatic behavior hard to debug and trust.
- **Trace full injected context**: Rejected. It can duplicate sensitive personal context and conflict with redaction semantics.

## Decision: No new runtime dependency or SQLite migration

**Rationale**: This feature is a behavior layer over existing memory storage. The required state can be represented by in-memory dataclasses and existing trace rows. Avoiding a migration reduces risk and keeps the slice focused.

**Alternatives considered**:

- **Add activation history table**: Deferred. The trace ledger is enough for the first implementation.
- **Add plugin config table**: Deferred. Environment variables or module constants are sufficient for default max count/budget in this phase.
