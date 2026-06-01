# Feature Specification: Hermes Layered Life Memory Plugin

**Language Versions**: Chinese primary version `spec.md` / `spec.zh.md`; English version `spec.en.md`

**Feature Branch**: `001-life-memory-plugin`

**Created**: 2026-06-01

**Status**: Draft

**Input**: User description: "Build a layered memory system for Hermes that separates technical project memory, life memory, user profile memory, and abstract experience memory. Implement the `life_memory` part as a Hermes standalone plugin, not as a memory provider, and keep Hermes core unchanged."

## Overview

This feature introduces a layered long-term memory model for Hermes so different memory types remain clear, searchable, and controllable. Hermes' existing memory should continue to cover technical and project-related information. A new `life_memory` plugin should manage durable personal life context such as routines, habits, relationships, non-technical preferences, important life events, and repeated personal patterns.

The feature reduces memory pollution, avoids over-recording, and improves recall reliability by classifying candidate memories before storage.

## Problem Statement

Hermes already has multiple memory mechanisms, but the boundary between technical project memory, life memory, user profile preferences, temporary conversation details, and abstract experience can become unclear. When these domains are mixed, memory becomes harder to inspect, harder to correct, and more likely to recall irrelevant or outdated information.

The user needs a layered system that can decide whether a candidate memory belongs in life memory, technical memory, user profile memory, temporary working context, abstract experience, or nowhere.

## Goals

- Separate life memory from Hermes technical/project memory.
- Provide clear classification rules for deciding what should be saved and where.
- Store personal life memories with structured metadata such as `primary_category`, `tags`, importance, confidence, classification_confidence, source, timestamps, status, promotion_path, and trace.
- Recall relevant life memories without injecting unrelated or technical memories.
- Allow the user to correct, mark outdated, strengthen, merge, archive, or forget memories.
- Maintain memory quality through basic reflection, including deduplication, merging, `recent_state` TTL, archiving, and repeated-evidence pattern generation.
- Provide read-only Markdown review/export so the user can inspect confirmed memories, session extraction summaries, daily reports, review-needed items, and archived items.
- Avoid storing trivial, uncertain, temporary, or sensitive information by default; sensitive information requires explicit durable-storage authorization first.
- Validate a small, testable prototype around the modern agent-memory `write -> manage -> read` loop: selective write, structured metadata, scoped retrieval, update/forget, lightweight reflection, and audit trace.

## Non-Goals

- The MVP will not implement a standalone MCP server.
- The MVP will not require PostgreSQL, pgvector, multimodal memory, or knowledge graph memory.
- The MVP will not perform complex autonomous LLM-based reflection without user-visible controls.
- The MVP will not replace Hermes' existing memory system.
- The MVP will not modify Hermes core source code.
- The MVP will not install or develop the plugin inside Hermes bundled `hermes-agent/plugins` directory.
- The MVP will not treat `hermes-agent` as the PyCharm workspace folder for plugin installation; the workspace folder should be the parent Hermes home directory `.hermes`.
- The MVP will not introduce a separate memory-router plugin.
- The MVP will not implement a complete Agent Memory OS; project memory, skill promotion, cross-tool sharing, and shared multi-agent memory are future scope.
- The MVP will not treat daily reports / daily memory as a fact source or let them change `promotion_score`; first-version daily reports are report-only audit artifacts.
- The MVP will not train a learned memory policy or let the model autonomously decide all long-term memory governance actions; the prototype favors inspectable rules, explicit user actions, and lightweight reflection.

## Conceptual Memory Layers

- **L0: Conversation Context**: Short-term details that exist only in the current conversation, such as the latest question, a temporary clarification, or one-off discussion detail. These should not be stored permanently.
- **L1: Temporary Working Memory**: Active-task context that may expire quickly, such as "the user is currently designing the Hermes life-memory plugin." For the MVP, this should not be stored in life memory by default.
- **L2: Technical Project Memory**: Technical, academic, project, and engineering-related information, such as code structure, debugging history, SSH configuration, Hermes/OpenClaw setup, coursework progress, experiment results, and toolchain configuration. These must not be stored by the life-memory plugin.
- **L3: User Profile Memory**: Stable identity and global long-term preferences, such as the user's name, language preference, writing style preference, long-term academic or career goals, and stable response format requirements. The life-memory plugin may classify this content but should not store it as ordinary life memory.
- **L4: Life Event Memory**: Personal non-technical life context, routines, habits, relationships, important life events, lifestyle preferences, and daily patterns. This is the main responsibility of the life-memory plugin.
- **L5: Abstract Experience Memory**: Higher-level patterns inferred from repeated events or repeated user behavior. These must not be created from a single casual message and should be stored only when enough evidence exists.

## Research-Informed Prototype Scope

Recent agent-memory research emphasizes the `write -> manage -> read` loop rather than treating memory as plain RAG or vector storage. This prototype uses a conservative vertical slice: classify and filter before writing, preserve structured metadata and audit traces after writing, and filter reads by scope, status, sensitivity, and relevance.

The MVP validates only whether the `life_memory` layer improves personal-life continuity in Hermes. It does not attempt to implement a full Memory OS. It first tests six questions: what is worth writing, how old memories are updated, how incorrect recall is avoided, how users can delete or correct memories, how limited abstract experiences can emerge from repeated evidence, and how Markdown review lets the user inspect what the system actually remembers.

The prototype should absorb practical lessons from A-MEM- and Mem0-style systems: a memory item should not be just a text chunk, but should carry `primary_category`, tags, context, source, confidence, links, and trace. It should also borrow evaluation ideas from LongMemEval and LoCoMo by testing extraction, multi-session recall, temporal update, forget, and abstention.

For safety, the prototype is local-first and user-controlled by default. Retrieved memory content is data, not a new instruction layer. Sensitive information, potential prompt-injection text, and untrusted memories must not be automatically promoted or automatically injected.

## Lifecycle Status Model

The MVP uses the following lifecycle states instead of implementing a full generational Memory OS immediately:

- **`young`**: A newly stored life memory that has not yet been reused or confirmed by the user.
- **`active`**: A normally recallable memory that passed basic classification and boundary checks.
- **`reinforced`**: A memory confirmed by the user, repeatedly useful in recall, or proven stable across multiple contexts.
- **`pattern_candidate`**: Multiple pieces of evidence suggest a possible life pattern, but not enough evidence exists to create an `abstract_experience`.
- **`archived`**: A low-value, stale, rarely used, or reflection-demoted memory; excluded from normal recall by default.
- **`deleted`**: A memory the user asked to forget or delete; it must not be used by normal recall or reflection.

State transitions must be traceable. Automatic reflection may suggest state changes; low-risk `pattern_candidate -> abstract_experience` promotion may happen automatically when `apply=true` and thresholds are met. Sensitive content, conflicts, and high-risk merges should be handled conservatively and ask for user confirmation when needed.

`young` memories may participate in recall with low weight, but they are constrained: the default score multiplier is `0.50`, each recall may return at most 2 young memories, sensitive/restricted young memories are excluded, and young memories cannot be used as action-boundary facts. Stable, high-impact `major_life_fact` memories may fast-promote from `young` to `active` when strict conditions are met, but they cannot jump directly to `reinforced`, `personal_pattern`, or `abstract_experience`.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Classify Candidate Memory (Priority: P1)

As a Hermes user, I want Hermes to classify a memory candidate before saving it so that technical details, profile preferences, temporary context, and life memory do not pollute each other.

**Why this priority**: Classification is the gatekeeper for all storage, recall, feedback, forgetting, and reflection behavior.

**Independent Test**: Submit representative inputs for each memory layer and verify the expected classification.

**Acceptance Scenarios**:

1. **Given** the user says "My Hermes runs on Mac, and Windows is connected through SSH," **When** the candidate is classified, **Then** the result is `technical_memory` and it is not stored in life memory.
2. **Given** the user says "Remember that I prefer to work late at night and usually think better after midnight," **When** the candidate is classified, **Then** the result is `life_memory` and it is eligible for life-memory storage.
3. **Given** the user says "From now on, when you generate English content for me, include Chinese translation below," **When** the candidate is classified, **Then** the result is `user_profile` and it is not stored as ordinary life memory.
4. **Given** the user says "I'm a bit tired today" without asking Hermes to remember it, **When** the candidate is classified, **Then** the result is `no_save`.
5. **Given** repeated evidence shows a durable behavior pattern, **When** the pattern is classified for reflection, **Then** the result may be `abstract_experience` only if there is enough supporting evidence.

---

### User Story 2 - Store Life Memory (Priority: P1)

As a Hermes user, I want Hermes to store important personal life memories separately from technical project memory so that my long-term personal context remains useful and does not pollute technical memory.

**Why this priority**: Correct storage is the foundation for useful life-memory recall.

**Independent Test**: Ask Hermes to remember in-scope and out-of-scope facts, then verify that only eligible life memories are accepted.

**Acceptance Scenarios**:

1. **Given** the user explicitly asks Hermes to remember a life-related fact, **When** the fact fits L4 life memory, **Then** the plugin stores it with `primary_category`, tags, importance, confidence, classification_confidence, source, timestamps, status, promotion_path, and trace.
2. **Given** the memory is technical, project-related, academic implementation detail, tool configuration, or debugging history, **When** storage is requested, **Then** the plugin does not store it in life memory.
3. **Given** the content is trivial, temporary, uncertain, or useful only in the current conversation, **When** storage is requested without explicit durable intent, **Then** the plugin declines to store it.
4. **Given** the content is sensitive personal information, **When** the user has not explicitly requested durable storage, **Then** the plugin returns `needs_confirmation`, creates no durable memory, and asks whether to save it long-term and whether to save a summary or full content.
5. **Given** the content is a stable, high-impact personal-life fact and the user explicitly asks Hermes to remember it, **When** the `major_life_fact` fast-promotion conditions are met, **Then** the memory may move directly from `young` to `active` with `promotion_path=major_life_fact`.

---

### User Story 3 - Recall Relevant Life Memory (Priority: P1)

As a Hermes user, I want Hermes to recall relevant life memories when they help answer my current question so that Hermes can respond with continuity and personalization.

**Why this priority**: Recall is the primary user-facing value of stored life memory.

**Independent Test**: Store several life memories and ask targeted and broad recall questions.

**Acceptance Scenarios**:

1. **Given** the user asks a question related to a previous life memory, **When** recall is requested, **Then** the plugin returns relevant memories with identifiers or references.
2. **Given** unrelated life memories exist, **When** recall is requested, **Then** unrelated memories are not injected into the response.
3. **Given** technical memories exist elsewhere in Hermes, **When** life-memory recall is requested, **Then** technical project memory is excluded.
4. **Given** multiple memories match a query, **When** recall ranks results, **Then** high-importance, high-confidence, recently used, and semantically relevant memories are prioritized.
5. **Given** matching results include `young` memories, **When** recall returns results, **Then** young memories participate with low weight, at most 2 are returned, they are marked candidate/low_confidence, and sensitive/restricted young memories are excluded.

---

### User Story 4 - Correct And Forget Memory (Priority: P2)

As a Hermes user, I want to correct wrong or outdated memories and forget specific memories so that Hermes does not continue using inaccurate or unwanted personal context.

**Why this priority**: Long-term memory must remain user-controlled to be trustworthy.

**Independent Test**: Store a memory, apply feedback or deletion, and verify that future recall changes accordingly.

**Acceptance Scenarios**:

1. **Given** the user says a memory is wrong, **When** feedback is recorded, **Then** the memory is marked as corrected, stale, deleted, or replaced according to the user's instruction.
2. **Given** the user provides a replacement fact, **When** feedback is recorded, **Then** the plugin updates the existing memory rather than creating unnecessary duplicates.
3. **Given** the user asks to forget a specific memory, **When** the target is unambiguous, **Then** the memory is marked deleted or inactive and does not appear in normal recall.
4. **Given** a forget request could match multiple memories, **When** the target is ambiguous, **Then** the plugin asks for disambiguation instead of deleting multiple memories silently.

---

### User Story 5 - Reflect And Maintain Memory Quality (Priority: P3)

As a Hermes user, I want life memory to be periodically cleaned and organized so that the memory store remains useful over time.

**Why this priority**: Reflection improves quality after enough memories exist, but it depends on correct classification, storage, recall, and feedback first.

**Independent Test**: Create duplicate, stale, low-value, and repeated-pattern memories, then verify reflection output and memory status changes.

**Acceptance Scenarios**:

1. **Given** duplicate or highly similar memories exist, **When** reflection runs, **Then** the plugin identifies candidates for deduplication or merging.
2. **Given** compatible memories describe the same durable life fact, **When** reflection merges them, **Then** the resulting memory preserves useful source and trace information.
3. **Given** expired `recent_state` memories exist, **When** light reflection runs, **Then** the plugin archives them and records `decay_reason=ttl_expired`.
4. **Given** repeated evidence supports an abstract experience memory, **When** reflection creates an insight, **Then** the insight is labeled as an inference and references supporting memories.
5. **Given** there is only a single casual message, **When** reflection evaluates it, **Then** no abstract experience memory is created.
6. **Given** the user runs daily reflection, **When** a daily report is generated, **Then** the report is an audit artifact only and does not create durable memories or change `promotion_score`.

---

### User Story 6 - Export Human Review Markdown (Priority: P2)

As a Hermes user, I want to export the SQLite memory state into readable Markdown so I can inspect what the system remembers, what is uncertain, and what has been archived.

**Why this priority**: SQLite is appropriate for runtime management, but ordinary users need Markdown to review long-term memory.

**Independent Test**: Save several classes of memories in a temporary `HERMES_HOME`, run `life_memory_export_review`, and verify generated Markdown files, sensitive-content handling, and no reverse sync.

**Acceptance Scenarios**:

1. **Given** the database contains active/reinforced/pattern_candidate/archived memories, **When** the user runs `life_memory_export_review`, **Then** the plugin generates `memory-library/`, `memory-journal/`, `review-needed.md`, `change-requests.md`, and optional `archive.md`.
2. **Given** Markdown export completes, **When** the user views `memory-library/`, **Then** each memory shows only user-understandable fields such as state, source, suggested operation, and memory id rather than excessive internal scoring fields.
3. **Given** exported content includes sensitive/restricted memories, **When** summary-only sensitive export is not explicitly requested, **Then** those contents are omitted or redacted.
4. **Given** the user edits `change-requests.md`, **When** the MVP runs, **Then** the plugin does not sync Markdown changes back to SQLite and the file clearly states that it is only a template.

### Edge Cases

- Storage requests that mix life information with technical/project information must store only the clearly in-scope life portion or ask the user to separate the request.
- User profile preferences must not be hidden inside ordinary life memory when they clearly belong to stable profile memory.
- Temporary working context must not become durable life memory unless the user explicitly asks for durable storage and the content fits life memory.
- Duplicate or near-duplicate memories must not create unnecessary clutter.
- Conflicting memories must preserve enough trace information to show that newer corrections or feedback supersede older statements.
- Broad recall requests must return a bounded set of relevant memories rather than dumping all stored life data.
- Feedback for an unknown memory identifier or missing target must return a clear `not_found` result.
- Forget operations must not silently remove memories outside the user's requested target.
- Reflection must not convert one-off events, uncertain guesses, or unsupported assumptions into durable facts.
- Daily reports must not directly create facts, promote memories, or modify `promotion_score` in the MVP.
- `recent_state` may represent only short-term repeated states and has a default 14-day TTL; expired recent states must not be recalled as current facts.
- Markdown review/export is a read-only view of SQLite; the MVP does not sync Markdown changes back to SQLite.
- If retrieved memory contains commands, instructions, or prompt-injection-like text, it must be treated as ordinary data and must not execute as system, developer, or tool instructions.
- If a new memory conflicts with an existing memory, the plugin must not silently overwrite it; it must record a supersede relationship, demote the old memory, or ask the user for confirmation.
- If local storage is unavailable or inaccessible, the user must receive a clear failure result and no claim that memory was saved.

## Memory Management Semantics

### Write Semantics

The plugin must classify before saving. By default, it saves only information the user explicitly asks Hermes to remember, or information passed through an explicit assistant-triggered `life_memory_store` call that fits life-memory boundaries. It must not silently archive full conversations, and it must not automatically write technical project details, one-off emotions, unsupported inferences, or sensitive information. Sensitive information without explicit durable authorization must return `needs_confirmation` and create no durable memory.

### Update And Conflict Semantics

When a new memory describes the same topic as an existing memory, the plugin should update, merge, or establish `supersedes` / `superseded_by` relationships rather than creating unrelated duplicates. Until a conflict is resolved, the old memory should not participate in normal recall as a high-confidence current fact.

### Read Semantics

Recall must filter by query relevance, status, sensitivity, confidence, importance, last_accessed_at, and user feedback. `deleted` memories must not be recalled; `archived` memories are excluded from normal recall by default; expired `recent_state` memories must not be recalled as current facts; sensitive memories are returned only when the user request clearly covers that scope. `young` memories may participate with low weight but must be marked uncertain and capped in count.

### Audit Semantics

Every store, recall, feedback, forget, reflect, merge, archive, reinforce, export_review, and conflict-resolution action must leave an explainable trace: operation type, timestamp, trigger reason, source, affected memories, status changes, and whether the user confirmed it.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The feature MUST provide user-accessible capabilities named `life_memory_store`, `life_memory_recall`, `life_memory_feedback`, `life_memory_forget`, `life_memory_reflect`, and read-only `life_memory_export_review`.
- **FR-002**: The feature MUST classify candidate memories as one of `technical_memory`, `life_memory`, `user_profile`, `temporary_working_memory`, `abstract_experience`, or `no_save` before storage.
- **FR-003**: `life_memory_store` MUST store L4 life memories with at least content, `primary_category`, tags, importance, confidence, classification_confidence, source, creation time, update time, last accessed time, access count, status, sensitivity, promotion_path, related memory ids, supersedes/superseded-by relationships, and trace information.
- **FR-004**: `life_memory_store` MUST avoid storing L2 technical project memory, including programming projects, code structure, runtime environment, dependency configuration, debugging history, experiment results, academic coursework, report progress, tool configuration, and Hermes/OpenClaw/Codex/SSH/TTS/QQ bot technical setup.
- **FR-005**: `life_memory_store` MUST avoid storing L0 conversation context, trivial one-off messages, temporary emotions, uncertain guesses, unsupported inferences, and current-conversation-only details by default.
- **FR-006**: `life_memory_store` MUST NOT store sensitive personal information unless the user explicitly authorizes durable storage; without authorization it MUST return `needs_confirmation` and create no durable memory.
- **FR-007**: The feature MUST identify L3 user profile candidates separately from ordinary life memory so stable identity, language preferences, writing format requirements, long-term goals, and stable response constraints are not mixed into life-memory records.
- **FR-008**: `life_memory_recall` MUST retrieve relevant life memories based on the current query or conversation context while excluding technical memory and unrelated life memories.
- **FR-009**: Recall results MUST distinguish direct stored memories from reflected abstract experience insights and provide enough reference information for correction or deletion.
- **FR-010**: `life_memory_feedback` MUST support feedback types including useful, wrong, outdated, important, duplicate, delete, and merge.
- **FR-011**: Feedback MUST influence future recall, reflection, deduplication, merging, archiving, and memory priority.
- **FR-012**: `life_memory_forget` MUST support soft deletion so deleted memories are not recalled in normal use while the deletion action remains internally traceable.
- **FR-013**: `life_memory_reflect` MUST support basic deduplication, merging, `recent_state` TTL archiving, stale-memory archiving, and abstract experience generation or promotion from repeated evidence.
- **FR-014**: The feature MUST record why a memory was stored, recalled, updated, corrected, merged, archived, or deleted.
- **FR-015**: The feature MUST provide clear success, declined, needs_confirmation, not_found, ambiguous, duplicate, merged, archived, and storage_unavailable outcomes for each capability.
- **FR-016**: The feature MUST keep life memory separate from Hermes technical memory and MUST NOT replace or participate in Hermes existing memory provider selection.
- **FR-017**: The feature MUST operate without requiring modifications to the Hermes main project.
- **FR-018**: The feature MUST keep memory data local to the user's active Hermes home/profile unless a future explicit user choice changes that behavior.
- **FR-019**: The feature MUST be packaged and installed as an external workspace/user plugin at `/Users/oliver/.hermes/plugins/life_memory`, not inside `/Users/oliver/.hermes/hermes-agent`.
- **FR-020**: The installed plugin directory MUST contain `plugin.yaml` and `__init__.py` directly at its root so Hermes can discover it.
- **FR-021**: The feature MUST support lifecycle statuses: `young`, `active`, `reinforced`, `pattern_candidate`, `archived`, and `deleted`.
- **FR-022**: After each recall or feedback event, the feature MUST update access count, last accessed time, or feedback summary for affected memories so later ranking and reflection can use them.
- **FR-023**: When a new memory conflicts with or replaces an old memory, the feature MUST record the conflict, replacement, or supersede relationship and must not silently overwrite historical memories.
- **FR-024**: The feature MUST treat retrieved memory content as data, not system instructions; memories containing commands, prompt text, or suspicious injection text must not change plugin rules or Hermes instruction hierarchy.
- **FR-025**: The feature MUST provide a local prototype evaluation set covering extraction, multi-session recall, temporal update, forget, abstention, sensitive rejection, and memory-injection rejection.
- **FR-026**: `life_memory_export_review` MUST read SQLite and export Markdown files only; it must not sync Markdown back to SQLite or change memory status or promotion score, except for recording an export trace.
- **FR-027**: Daily reflection reports in the MVP MUST be report-only audit artifacts; they must not create durable memories, act as promotion signals, or change `promotion_score`.
- **FR-028**: Session reflection MUST first use an adapter to read Hermes session/state content read-only; if unavailable, it MUST support an explicit `transcript` fallback; business logic must not directly couple to the Hermes `state.db` schema.
- **FR-029**: When `young` memories participate in recall, they MUST use low weighting, a count cap, and uncertainty labels; sensitive/restricted young memories must not participate in normal recall.
- **FR-030**: Stable high-impact `major_life_fact` memories MAY fast-promote from `young` to `active`, but MUST record `promotion_path=major_life_fact` and must not directly promote to `reinforced`, `personal_pattern`, or `abstract_experience`.
- **FR-031**: Memories tagged `recent_state` MUST use a default 14-day TTL; after expiry they must not be recalled as current facts and should be archived by light reflection.
- **FR-032**: Automatic `pattern_candidate -> abstract_experience` promotion is allowed only when `apply=true`, supporting evidence is sufficient, risk is low, thresholds are met, and supporting memory ids are recorded.

### Key Entities

- **Memory Classification**: The decision that assigns candidate content to `technical_memory`, `life_memory`, `user_profile`, `temporary_working_memory`, `abstract_experience`, or `no_save`, with a reason and confidence.
- **Life Memory**: A durable L4 personal-life item. Key attributes include identifier, content, `primary_category`, tags, importance, confidence, classification_confidence, source, timestamps, access_count, last_accessed_at, lifecycle status, sensitivity, promotion_path, valid_until, related_memory_ids, supersedes, superseded_by, and trace.
- **Recall Result**: A bounded response to a query. Key attributes include matching memory references, relevance reason, rank signals, and whether each item is a direct memory or reflected insight.
- **Feedback Entry**: A user-provided correction, rating, or classification change attached to a memory. It influences later recall, reflection, and display.
- **Forget Request**: A user action targeting one or more memories for soft deletion. It includes target reference, ambiguity status, and completion outcome.
- **Reflection Insight**: A synthesized L5 pattern derived from multiple eligible life memories. It includes supporting memory references and must be labeled as an inference.
- **Review Export**: A read-only Markdown review view generated from SQLite, including `memory-library/`, `memory-journal/`, `review-needed.md`, `change-requests.md`, and optional `archive.md`.
- **Reflection Report**: The output of a reflection run. MVP daily reports are audit-only and are not fact sources or promotion signals.
- **Memory Trace**: A record of why a memory was stored, recalled, corrected, deleted, merged, archived, or reflected.
- **Lifecycle State**: The current governance state of a memory, determining whether it participates in normal recall, needs review, or may be promoted or archived by reflection.
- **Evaluation Case**: A local prototype validation case containing input, expected classification, expected state transition, expected recall/abstention behavior, and expected safety boundary behavior.

## Memory Boundary Rules

### Store In Hermes Built-In Technical/Project Memory

The following must not be stored by the life-memory plugin: programming projects, code structure, runtime environment, dependency configuration, debugging history, experiment results, academic coursework, report progress, tool configuration, and Hermes/OpenClaw/Codex/SSH/TTS/QQ bot technical setup.

### Store In Life Memory Plugin

The following are eligible for the life-memory plugin: personal routines, habits, non-technical preferences, life events, relationship context, emotional patterns over time, lifestyle context, and repeated personal behavior patterns.

### Classify As User Profile

The following should be classified separately from ordinary life memory: stable identity, long-term response preferences, language preferences, writing format requirements, long-term goals, and stable constraints.

### Do Not Store By Default

The following should not be stored by default: trivial one-off messages, temporary emotions, uncertain guesses, information inferred without enough evidence, sensitive information unless explicitly requested, and details that are only useful in the current conversation.

## Example Scenarios

- **Technical Memory**: "My Hermes runs on Mac, and Windows is connected through SSH." Expected classification: `technical_memory`. Expected behavior: do not store in life memory.
- **Life Memory**: "Remember that I prefer to work late at night and usually think better after midnight." Expected classification: `life_memory`. Expected behavior: store as `primary_category=personal_preference` with routine/habit tags.
- **User Profile**: "From now on, when you generate English content for me, include Chinese translation below." Expected classification: `user_profile`. Expected behavior: do not store as ordinary life memory.
- **No Save**: "I'm a bit tired today." Expected classification: `no_save` unless the user explicitly asks to record it. Expected behavior: do not store permanently.
- **Abstract Experience**: Repeated evidence shows that the user rejects over-engineered solutions and prefers MVP-first implementation. Expected classification: `abstract_experience`. Expected behavior: store only after repeated evidence exists.
- **Sensitive Confirmation**: The user asks to remember sensitive life information without explicit durable-storage authorization. Expected behavior: return `needs_confirmation` and create no durable memory.
- **Recent State**: Multiple sessions show the user has recently been tired. Expected behavior: if stored, store only as a short-term `tag=recent_state` item with a default 14-day TTL; after expiry it must not be recalled as a current fact.

## Project Constraints For Planning

- The deliverable is a Hermes standalone plugin named `life_memory`.
- The plugin must use Hermes directory-plugin entrypoints: `plugin.yaml` and `__init__.py` with `register(ctx)`.
- The plugin must not be implemented as a `memory.provider`.
- The plugin source repository is `/Users/oliver/Projects/hermes-life-memory`.
- The source plugin package directory is `/Users/oliver/Projects/hermes-life-memory/plugins/life_memory`, not the repository root.
- The Hermes runtime home/workspace folder is `/Users/oliver/.hermes`.
- In the PyCharm workspace, the Hermes folder should be exposed as `/Users/oliver/Projects/hermes-workspace/.hermes` pointing to `/Users/oliver/.hermes`.
- The PyCharm workspace must not use `/Users/oliver/Projects/hermes-workspace/hermes-agent` as the Hermes plugin workspace, because that path points inside `/Users/oliver/.hermes/hermes-agent`.
- Runtime plugin installation must target `/Users/oliver/.hermes/plugins/life_memory`.
- If using a symlink during development, `/Users/oliver/.hermes/plugins/life_memory` must point to `/Users/oliver/Projects/hermes-life-memory/plugins/life_memory`.
- Runtime plugin installation must not point `/Users/oliver/.hermes/plugins/life_memory` at the repository root `/Users/oliver/Projects/hermes-life-memory`, because Hermes expects `plugin.yaml` and `__init__.py` directly inside the installed plugin directory.
- When accessed through the PyCharm workspace, the same target is `/Users/oliver/Projects/hermes-workspace/.hermes/plugins/life_memory`.
- Runtime plugin installation must not target `/Users/oliver/.hermes/hermes-agent/plugins/life_memory`.
- Runtime plugin installation must not target `/Users/oliver/Projects/hermes-workspace/hermes-agent/plugins/life_memory`.
- The plugin must be enabled through Hermes plugin configuration, for example by adding `life_memory` to `plugins.enabled` in `/Users/oliver/.hermes/config.yaml` or by using the Hermes plugin enable command.
- Persistent storage must be local to `HERMES_HOME`, with the planned backing store at `$HERMES_HOME/life_memory.db`, such as `/Users/oliver/.hermes/life_memory.db`.
- Hermes source files under `/Users/oliver/.hermes/hermes-agent` are reference-only for this feature and must not be modified.

## Planning Decisions

- Temporary working memory remains conversation-only for the MVP unless the user explicitly requests durable storage and the content fits life-memory boundaries.
- Abstract experience memory starts with explicit reflection, repeated-evidence rules, and low-risk automatic promotion when `apply=true`; fully autonomous high-risk reflection is future scope.
- Life-memory retrieval is exposed through recall behavior for the MVP; always-on pre-response injection can be evaluated later.
- Memory inspection is handled through recall results with identifiers, feedback and forget actions, and read-only `life_memory_export_review` Markdown export for the MVP.
- Technical-memory routing is rule-based classification for the MVP; a separate memory-router plugin is future scope.
- The MVP does not require a vector database or graph database; structured SQLite, full-text/keyword search, and lightweight relevance ranking are enough for the first prototype.
- `pattern_candidate` enters the life-memory MVP instead of the technical `skill_candidate`; real skill promotion remains future work for Hermes technical memory or another plugin.
- Prototype evaluation uses a small hand-written test set rather than directly replicating LongMemEval or LoCoMo, while still covering the long-term memory ability categories they emphasize.
- Effective-information extraction from sessions is preferred over "daily memory" as a fact source; daily reports are audit-only in the MVP.
- Session extraction uses an adapter to read Hermes session/state data, with explicit `transcript` fallback.
- SQLite is the runtime source of truth; Markdown is a read-only human review view and the MVP does not implement reverse sync.

## Research References

- A-MEM: Dynamic memory organization, linking, and evolution; informs tags, context, related memory links, and memory evolution. https://arxiv.org/abs/2502.12110
- Mem0: Production long-term memory emphasizes selective extraction, consolidation, retrieval, and low latency/token cost. https://arxiv.org/abs/2504.19413
- LongMemEval: Long-term memory evaluation covers extraction, multi-session reasoning, temporal reasoning, knowledge updates, and abstention. https://arxiv.org/abs/2410.10813
- LoCoMo: Long-dialogue memory exposes temporal, causal, and multi-session understanding challenges. https://arxiv.org/abs/2402.17753
- AgeMem: Treats long-term/short-term memory management as agent actions such as store, retrieve, update, summarize, and discard. https://arxiv.org/abs/2601.01885
- Memory for Autonomous LLM Agents survey: Formalizes agent memory as a `write -> manage -> read` loop and emphasizes contradiction handling, latency budgets, and privacy governance. https://arxiv.org/abs/2603.07670
- Privacy and safety papers: Memory can be extracted, injected, or contaminated over time, so the prototype must be conservative, auditable, and deletable by default. https://arxiv.org/abs/2502.13172 / https://arxiv.org/abs/2503.03704 / https://arxiv.org/abs/2605.17830

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of representative classification test cases are assigned to the expected category among `technical_memory`, `life_memory`, `user_profile`, `temporary_working_memory`, `abstract_experience`, and `no_save`.
- **SC-002**: At least 95% of explicit, in-scope life-memory store requests in an acceptance test set are saved and recallable in a later session.
- **SC-003**: 100% of excluded technical/project/profile/temporary/no-save test items are declined, classified outside life memory, or separated from storage rather than saved as life memory.
- **SC-004**: At least 90% of targeted recall queries return the expected relevant life memory within the first five returned results.
- **SC-005**: 100% of exact-target forget requests prevent the forgotten memory from appearing in later normal recall and reflection results.
- **SC-006**: At least 90% of feedback updates measurably change later recall, priority, status, or reflection behavior for the affected memory.
- **SC-007**: 100% of reflection insights in acceptance tests cite or reference supporting memories and label the output as an inference.
- **SC-008**: In a test set containing duplicate and stale memories, reflection identifies at least 90% of duplicate candidates and at least 90% of stale low-value candidates.
- **SC-009**: For a memory set of 10,000 stored items, at least 95% of common store, recall, feedback, forget, and reflect requests complete within 2 seconds.
- **SC-010**: In the temporal update test set, 100% of old memories explicitly superseded by new facts do not appear as current facts in normal recall results.
- **SC-011**: In the abstention test set, at least 95% of questions with no relevant memory return "no matching memory" or an equivalent result rather than inventing life context.
- **SC-012**: In the sensitive rejection and memory-injection rejection test sets, 100% of unauthorized sensitive content and suspicious injection content is not automatically stored, promoted, or executed as instructions.
- **SC-013**: 100% of store, feedback, forget, reflect, merge, archive, and conflict-resolution operations have a viewable trace explaining source, reason, and status changes.
- **SC-014**: `life_memory_export_review` generates the expected Markdown files in acceptance tests and 100% does not change memory status, promotion score, or SQLite content except for export trace.
- **SC-015**: 100% of daily report acceptance cases create no durable memory and do not change `promotion_score`.
- **SC-016**: 100% of sensitive store cases without explicit durable authorization return `needs_confirmation` and create no durable memory.
- **SC-017**: 100% of expired `recent_state` test items do not participate in normal recall as current facts and are archived after light reflection.

## Assumptions

- The initial feature is for a single active Hermes user/profile at a time; shared multi-user permissions are outside the first scope.
- Life memories are captured only through explicit user intent or explicit tool use triggered by the assistant; the feature does not silently archive every conversation.
- Sensitive information can be stored only when the user clearly asks for durable storage; without authorization the plugin must ask for confirmation, and recall, export, and reflection should be more conservative than for ordinary life memories.
- Forgetting means the memory is no longer used for future normal recall or reflection; any internal operational trace must not expose the forgotten content to the user.
- Reflections are optional derived context and never override direct user corrections.
- Daily reports are audit views, not fact sources; fact entry should come from explicit store calls, session-extraction candidates, or repeated evidence validated by reflection.
- Markdown review/export is a human inspection entrypoint, not a database editing channel; user Markdown edits do not automatically change SQLite in the MVP.
- Prototype validation prioritizes explainability, testability, and user control over the automation level of complex research systems.
- Research findings guide prototype scope and evaluation design; actual implementation must follow Hermes plugin constraints, local storage constraints, and user privacy boundaries.
