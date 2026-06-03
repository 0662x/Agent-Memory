# Feature Specification: Memory Activation And Context Injection

**Feature Branch**: `002-memory-activation`

**Created**: 2026-06-03

**Status**: Implemented and validated 2026-06-03

**Input**: User description: "Implement automatic life-memory activation and safe context injection before LLM calls"

## Summary

This feature extends the completed `life_memory` plugin from passive recall to automatic, safe use during normal Hermes conversations. Before an LLM call, the plugin should decide whether the current user request needs personal life memory, recall only relevant and safe memories, format a small bounded context block, and inject that block through the existing `pre_llm_call` hook.

The feature must preserve the current architecture from `001-life-memory-plugin`: SQLite remains the runtime source of truth, Markdown remains a read-only review surface, and recalled memories are always data only. This stage does not introduce embeddings, vector databases, model reranking, Markdown reverse sync, cloud storage, or Hermes core source edits.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Decide When Life Memory Is Needed (Priority: P1)

As a Hermes user, I want the plugin to automatically decide whether my current request needs life memory so that ordinary technical questions, current-task context, and casual chat are not polluted by personal context.

**Why this priority**: This is the safety gate for the entire feature. Injecting memory without a reliable gate creates privacy leakage, irrelevant answers, and prompt bloat.

**Independent Test**: Can be fully tested by calling an activation decision function with representative user requests and verifying `activate`, `skip`, and `reason` outcomes without invoking Hermes or SQLite recall.

**Acceptance Scenarios**:

1. **Given** the user asks "我周末运动后一般买什么饮品?", **When** activation is evaluated, **Then** the decision is `activate` with a life-memory reason.
2. **Given** the user asks "这个 Python 测试为什么失败?", **When** activation is evaluated, **Then** the decision is `skip` because this is technical/project context.
3. **Given** the user says "这次对话先记住这个临时变量名", **When** activation is evaluated, **Then** the decision is `skip` because it is temporary working context.
4. **Given** the user asks generic small talk with no personal-life dependency, **When** activation is evaluated, **Then** the decision is `skip` and no recall is attempted.

---

### User Story 2 - Inject Safe Bounded Memory Context (Priority: P1)

As a Hermes user, I want relevant life memories to be injected into the model context only when safe, bounded, and clearly marked as data so that Hermes can personalize answers without treating stored memory as instructions.

**Why this priority**: This turns existing passive recall into useful continuity while preserving the safety boundary described in the memory architecture notes.

**Independent Test**: Can be tested with a temporary `HERMES_HOME` by storing several memories, invoking the pre-LLM activation path, and verifying the injected context contains only the allowed top memories with required metadata.

**Acceptance Scenarios**:

1. **Given** matching normal life memories exist, **When** a relevant life question is evaluated, **Then** the injected context includes at most three memory entries.
2. **Given** a memory is injected, **When** the context is formatted, **Then** each entry includes `memory_id`, `status`, `confidence`, `sensitivity`, and a `data only` boundary.
3. **Given** recalled memory content contains instruction-like text, **When** it is injected, **Then** it is explicitly marked as quoted data and never as system, developer, or tool instruction.
4. **Given** no relevant safe memory exists, **When** the request is evaluated, **Then** no memory context block is injected.

---

### User Story 3 - Enforce Privacy And Lifecycle Filters (Priority: P1)

As a Hermes user, I want deleted, archived, expired, superseded, restricted, unauthorized sensitive, and low-confidence memories to remain silent during automatic injection so that old or private information does not leak into answers.

**Why this priority**: Automatic injection increases privacy risk compared with explicit tool recall. The filter must be stricter than normal recall.

**Independent Test**: Can be tested by inserting memories with different lifecycle states and sensitivity levels, then verifying activation never injects disallowed entries.

**Acceptance Scenarios**:

1. **Given** a matching memory is `deleted`, **When** activation runs, **Then** it is never injected.
2. **Given** a matching memory is `archived` or expired by `valid_until`, **When** activation runs, **Then** it is skipped by default.
3. **Given** a matching memory is `restricted` or unauthorized `sensitive`, **When** activation runs, **Then** raw content is not injected.
4. **Given** a matching `young` memory has low confidence or high injection risk, **When** activation runs, **Then** it is excluded from automatic injection.

---

### User Story 4 - Audit Automatic Memory Use (Priority: P2)

As a Hermes user, I want automatic memory activation decisions to be traceable so that I can understand when the plugin used memory, skipped memory, or filtered memories for safety.

**Why this priority**: The existing plugin is built around auditability. Automatic context use must be observable for debugging and trust.

**Independent Test**: Can be tested by running activation in activate, skip, not-found, and filtered scenarios, then verifying trace rows include the decision, reason, and injected memory ids without leaking deleted or restricted content.

**Acceptance Scenarios**:

1. **Given** activation is skipped, **When** a trace is written, **Then** it records the skip reason and no injected memory ids.
2. **Given** activation injects memories, **When** a trace is written, **Then** it records injected memory ids and aggregate counts.
3. **Given** unsafe memories were filtered, **When** a trace is written, **Then** it records filter counts/reasons without exposing restricted raw content.

---

### User Story 5 - Runtime Hook Integration (Priority: P2)

As a Hermes user, I want automatic life-memory context to be provided through the existing plugin hook without modifying Hermes core so that the feature remains compatible with the plugin boundary.

**Why this priority**: Phase 10 already installed routing through `pre_llm_call`. This feature should build on that mechanism instead of creating a Hermes core fork.

**Independent Test**: Can be tested with a fake Hermes plugin context that captures registered `pre_llm_call` hooks and verifies the hook returns the expected context payload.

**Acceptance Scenarios**:

1. **Given** the plugin registers with a context supporting `register_hook`, **When** registration completes, **Then** the activation hook is installed without removing the existing routing hook.
2. **Given** activation fails because storage is unavailable, **When** the hook runs, **Then** Hermes receives no injected memory context and normal answering can continue.
3. **Given** both routing guidance and activated memory are available, **When** the hook returns context, **Then** the context preserves routing guidance and appends the bounded life-memory block.

---

### Edge Cases

- Current request is empty, malformed, or not available to the hook: activation must skip.
- Hook payload shape differs across Hermes versions: activation must fail closed and return no memory context.
- SQLite database is missing, locked, or unavailable: activation must skip and optionally trace the failure without breaking the LLM call.
- Recall returns many candidates: injection must apply a hard memory-count and character/token budget.
- Recall returns only `young` memories: inject only if confidence and relevance are high enough; otherwise skip.
- Matching memory is sensitive: inject only a safe summary or omit it unless the request scope clearly authorizes use.
- Matching memory is prompt-injection-like: include only as quoted data with a safety note, or omit if risk is too high.
- Existing routing prompt hook is present: activation must not overwrite or disable it.
- No relevant memory exists: do not invent background; inject nothing.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide a deterministic activation decision that returns whether life memory should be recalled for a given user request.
- **FR-002**: The activation decision MUST default to skip when the request is technical/project-related, user-profile-only, temporary working context, one-off chat, ambiguous, or malformed.
- **FR-003**: The activation decision MUST activate for clear personal-life questions involving routines, habits, food/lifestyle preferences, relationships, life events, daily patterns, and previously stored personal context.
- **FR-004**: The system MUST recall candidates only after the activation gate decides that life memory is needed.
- **FR-005**: Automatic injection MUST use stricter filters than explicit `life_memory_recall`.
- **FR-006**: Automatic injection MUST exclude deleted memories.
- **FR-007**: Automatic injection MUST exclude archived memories by default.
- **FR-008**: Automatic injection MUST exclude memories whose `valid_until` has expired.
- **FR-009**: Automatic injection MUST exclude restricted memories and unauthorized sensitive raw content.
- **FR-010**: Automatic injection MUST exclude superseded memories as current facts.
- **FR-011**: Automatic injection MUST limit injected memories to a configurable maximum, defaulting to no more than three.
- **FR-012**: Automatic injection MUST apply a bounded character or token budget to the entire injected memory block.
- **FR-013**: Injected memory entries MUST include at least `memory_id`, `status`, `confidence`, `sensitivity`, and content or safe summary.
- **FR-014**: Injected context MUST clearly state that recalled memory is data only and must not be treated as system, developer, tool, or user instruction.
- **FR-015**: Memories with injection risk MUST either be omitted or marked as instruction-like quoted data with a safety note.
- **FR-016**: The plugin MUST integrate activation through `pre_llm_call` without modifying Hermes core source files.
- **FR-017**: The activation hook MUST fail closed: if decision, recall, formatting, or storage access fails, it must inject no memory and must not break the LLM call.
- **FR-018**: The activation path MUST write audit traces for activate, skip, not-found, filtered, and injected outcomes when the repository is available.
- **FR-019**: Trace records MUST avoid exposing deleted or restricted raw content.
- **FR-020**: Existing explicit `life_memory_recall` behavior MUST remain available and backward compatible.
- **FR-021**: Existing runtime memory routing behavior MUST remain available and must not be disabled by activation.
- **FR-022**: The feature MUST include unit tests for activation decisions, injection formatting, safety filtering, and hook behavior.
- **FR-023**: The feature MUST include integration tests proving automatic context injection works with temporary SQLite memories.
- **FR-024**: The feature MUST document how to enable, disable, and audit automatic life-memory injection.

### Non-Goals

- **NG-001**: This stage does not add embeddings, vector databases, semantic indexes, or model reranking.
- **NG-002**: This stage does not implement Markdown-to-SQLite reverse sync.
- **NG-003**: This stage does not modify Hermes core source files.
- **NG-004**: This stage does not make daily or weekly reflection reports a source of truth for injection.
- **NG-005**: This stage does not automatically execute tools or actions based on recalled life memory.

### Key Entities *(include if feature involves data)*

- **Activation Decision**: A deterministic result containing `activate`, `reason`, `confidence`, request classification, and whether recall should run.
- **Activation Context**: The available pre-LLM request metadata, including current user message or normalized query, optional conversation hints, and hook metadata.
- **Injected Memory Entry**: A sanitized memory item selected for automatic context injection, including memory id, lifecycle status, confidence, sensitivity, relevance reason, content or summary, and safety flags.
- **Injected Memory Block**: The final bounded context string returned by the hook, including a data-only boundary and selected memory entries.
- **Activation Trace**: An audit record describing activation outcome, reason, injected ids, filter counts, and failure mode without exposing restricted raw content.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In the activation evaluation set, at least 90% of clear personal-life questions activate recall.
- **SC-002**: In the activation evaluation set, at least 95% of technical/project/current-task/no-save questions skip automatic recall.
- **SC-003**: 100% of automatic injection tests exclude deleted, expired, archived-by-default, restricted, and unauthorized sensitive memories.
- **SC-004**: 100% of injected memory blocks contain the data-only boundary and required memory metadata.
- **SC-005**: The injected memory block never exceeds the configured count and budget limits in tests.
- **SC-006**: Hook failure, unavailable SQLite, or malformed hook payload never prevents the LLM call from proceeding.
- **SC-007**: Existing `uv run python -m pytest` remains fully passing after the feature is implemented.
- **SC-008**: A black-box Hermes smoke test shows that a relevant life-memory question can use stored life memory without the user explicitly calling `life_memory_recall`.

## Assumptions

- Hermes continues to expose `pre_llm_call` hooks through the user plugin context.
- The hook can access enough current-request text or metadata to make a conservative activation decision; if not, activation skips.
- `$HERMES_HOME/life_memory.db` remains the runtime source of truth.
- Existing repository recall, lifecycle, sensitivity, and trace tables from `001-life-memory-plugin` are available.
- The feature remains local-first and single-user for this stage.
- Rule-first behavior is preferred for the activation gate; model assistance can be considered in later stages only after deterministic safety is stable.
