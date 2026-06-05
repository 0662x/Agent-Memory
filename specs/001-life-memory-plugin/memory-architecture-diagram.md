# Life Memory Architecture Diagram

**Source**: [memory-architecture-notes.md](./memory-architecture-notes.md)
**Scope**: Original design plus implemented `001`, `002`, and `003` behavior.
**Runtime source of truth**: `$HERMES_HOME/life_memory.db`

## 1. Original Design In One Sentence

`life_memory` was designed as a Hermes standalone plugin that turns conversation signals into durable, auditable life memories through a SQLite state machine, while keeping technical memory, user profile, temporary context, and Markdown review separate.

The key idea is:

```text
Conversation is not memory.
Model output is not truth.
SQLite memory + evidence + lifecycle state is the runtime truth.
Markdown is only a human review/export surface.
```

## 2. Current Completed Flow (001-003)

This is the flow that is already implemented and validated enough to reason about today. It has two main runtime loops: saving life memory and using life memory before the model answers.

```mermaid
flowchart TD
    User[User message] --> Hermes[Hermes runtime]
    Hermes --> Hook[life_memory pre_llm_call hook]

    Hook --> WriteRoute{Memory write route?}
    WriteRoute -->|technical/project| BuiltinMemory[Hermes built-in memory]
    WriteRoute -->|user profile| BuiltinUser[Hermes built-in user profile]
    WriteRoute -->|temporary/no-save| NotStored[Do not store]
    WriteRoute -->|life-memory candidate| Store[life_memory_store]

    Store --> StoreGate[Classification + safety + sensitivity + duplicate gate]
    StoreGate -->|accepted| Memories[(life_memories)]
    StoreGate -->|declined / needs confirmation / duplicate| StoreTrace[store/classify trace]
    Memories --> EmbedIndex[(memory_embeddings derived index)]

    Hook --> Activation{Does this answer need life memory?}
    Activation -->|no| NormalAnswer[LLM answers normally]
    Activation -->|yes| Recall[life_memory_recall / hybrid recall]

    Memories --> Lexical[lexical candidates]
    EmbedIndex --> Semantic[semantic candidates]
    Lexical --> Recall
    Semantic --> Recall

    Recall --> Rerank[merge + explainable rerank]
    Rerank --> InjectionFilter[strict injection filter]
    InjectionFilter -->|safe top memories| ContextBlock[data-only memory context]
    InjectionFilter -->|nothing safe| NormalAnswer
    ContextBlock --> MemoryAnswer[LLM answers with bounded memory context]

    Recall --> RecallTrace[recall/activation trace]
    InjectionFilter --> RecallTrace

    Memories --> Manage[feedback / forget / reflect / export_review]
    Manage --> Memories
    Manage --> Review[Markdown review export]
```

Plain-language version:

| Runtime question | Current behavior |
| --- | --- |
| Should this be saved? | The router separates technical memory, user profile, temporary context, and life memory. Only life-memory candidates go to `life_memory_store`. |
| Is it safe to save? | `life_memory_store` classifies content, checks sensitivity/injection risk, rejects non-life memory, handles duplicates, and writes trace. |
| What is the truth source? | Accepted memories live in `life_memories`; semantic vectors live in `memory_embeddings` as a rebuildable derived index. |
| Should memory be used before answering? | `002` activation decides before the model answers. Technical/current-task/generic requests skip memory. |
| How is memory found? | `003` hybrid recall combines lexical candidates and semantic candidates, then reranks with lifecycle/metadata/time signals. |
| What reaches the model? | Only a small safe `data-only` context block. Deleted, archived, expired, restricted, unsafe, or low-confidence memories are filtered out. |
| How do you audit it? | Store, recall, activation, forget, feedback, and reflection actions write traces. Markdown export is read-only review output. |

The current happy path is:

```text
User says "remember my life habit"
  -> route to life_memory_store
  -> classify and safety-check
  -> write life_memories
  -> build derived memory_embeddings
  -> trace

Later user asks a related life question
  -> activation decides memory is needed before LLM answer
  -> hybrid recall finds lexical/semantic candidates
  -> strict injection filter keeps only safe relevant memory
  -> inject data-only block
  -> model answers with that memory
  -> trace
```

What is not fully done yet:

```text
Automatic session distillation after whole conversations.
Entity linking across people/places/habits.
Context lookup before memory writes to resolve conflicts like Mem0-style add pipeline.
Real embedding provider configuration beyond the deterministic fake/local provider.
Markdown reverse sync.
```

## 3. System Overview

```mermaid
flowchart TD
    User[User conversation] --> Hermes[Hermes runtime]

    Hermes --> PreHook[pre_llm_call hook]
    PreHook --> Routing[Runtime memory routing]
    PreHook --> Activation[002 activation gate]

    Routing -->|technical/project| HermesNative[Hermes native technical memory]
    Routing -->|stable profile| UserProfile[Hermes native user profile]
    Routing -->|life memory candidate| StoreTool[life_memory_store]
    Routing -->|temporary/no-save| NoSave[Do not persist]

    Activation -->|skip| LLM[LLM answer]
    Activation -->|activate| HybridRecall[003 hybrid recall]
    HybridRecall --> SafetyFilter[Strict injection filters]
    SafetyFilter -->|safe bounded data block| LLM
    SafetyFilter -->|none safe| LLM

    StoreTool --> Classifier[Classification + safety + sensitivity gates]
    Classifier -->|accepted| SQLite[(life_memory.db)]
    Classifier -->|declined / needs confirmation| Trace[Trace ledger]

    SQLite --> Lexical[Lexical recall index/search]
    SQLite --> Embeddings[Derived semantic embedding index]
    Lexical --> HybridRecall
    Embeddings --> HybridRecall

    SQLite --> Reflect[life_memory_reflect background]
    Reflect --> SQLite
    Reflect --> Reports[Reflection reports]

    SQLite --> Export[life_memory_export_review]
    Reports --> Export
    Export --> Markdown[Markdown review files]
```

## 4. Layer Boundaries

```mermaid
flowchart LR
    Input[Incoming information] --> Boundary{Memory boundary}

    Boundary -->|technical/project facts| L2[technical_memory\nHermes native]
    Boundary -->|language/style/global preference| L3[user_profile\nHermes native]
    Boundary -->|daily life facts, habits, relationships, lifestyle| L4[life_memory\nthis plugin]
    Boundary -->|current task only| Temp[temporary_working_memory\nnot durable]
    Boundary -->|multi-evidence inference| Abstract[abstract_experience\ninference only]
    Boundary -->|small talk, unsafe, unconfirmed sensitive| Drop[no_save / declined trace]
```

Practical meaning:

| Layer | Stored where | Example | Current project owns it? |
| --- | --- | --- | --- |
| Technical/project memory | Hermes native memory | repo setup, commands, bug context | No |
| User profile | Hermes native profile | answer language, global style | No |
| Life memory | `life_memory.db` | food habits, routines, life events | Yes |
| Temporary working memory | current conversation only | temporary variable, current task detail | No durable store |
| Abstract experience | derived from evidence | long-term pattern, marked inference | Partially in `001`; deeper work later |
| No-save | trace only or nothing | one-off chat, unsafe/sensitive unconfirmed | Yes, as gate/trace |

## 5. Write Path

```mermaid
sequenceDiagram
    participant U as User
    participant H as Hermes
    participant R as Routing hook
    participant S as life_memory_store
    participant C as Classifier/Safety
    participant DB as SQLite life_memory.db
    participant E as Embedding index
    participant T as Trace ledger

    U->>H: says something worth remembering
    H->>R: pre_llm_call routing check
    R->>R: classify boundary

    alt technical/profile/temporary/no-save
        R-->>H: route away from life_memory
        R->>T: optional routing trace
    else life memory candidate
        R->>S: call/store candidate
        S->>C: classify category, sensitivity, injection risk, duplicate/conflict
        alt accepted
            C->>DB: write life_memories + evidence as young/active
            DB->>E: 003 index derived semantic embedding
            S->>T: store trace
        else needs confirmation or declined
            C->>T: trace redacted decision
        end
    end
```

Important details:

| Step | What it does | Why it exists |
| --- | --- | --- |
| Boundary routing | Decides whether this belongs to life memory at all | Prevents technical/profile/temporary pollution |
| Classification | Chooses `personal_fact`, `personal_preference`, or `personal_pattern` | Keeps user-visible categories simple |
| Safety/sensitivity gate | Blocks unsafe, prompt-injection-like, or unconfirmed sensitive content | Prevents privacy and behavior leaks |
| SQLite write | Stores structured memory, lifecycle, evidence, traceable ids | Makes automation testable and auditable |
| Embedding indexing | Stores derived vector metadata after accepted writes | Improves paraphrase recall, but is not truth |

## 6. Answer-Time Activation Path

This is what `002-memory-activation` added.

```mermaid
sequenceDiagram
    participant U as User
    participant H as Hermes
    participant A as Activation gate
    participant HR as Hybrid recall
    participant F as Injection filter
    participant L as LLM
    participant T as Trace ledger

    U->>H: asks a question
    H->>A: pre_llm_call payload
    A->>A: deterministic decision

    alt technical / current task / generic / ambiguous
        A->>T: trace skip reason
        A-->>H: inject nothing
        H->>L: answer normally
    else needs life memory
        A->>HR: recall relevant memories
        HR-->>A: ranked candidates
        A->>F: stricter-than-recall filter
        F->>F: exclude deleted, archived, expired, restricted, unsafe, low-confidence young
        alt safe memories found
            F-->>H: bounded data-only memory block
            A->>T: trace injected ids + filter counts
            H->>L: answer with memory context
        else no safe match
            A->>T: trace not_found/filtered
            H->>L: answer without memory context
        end
    end
```

Key rule:

```text
The plugin decides whether to search memory before the model answers.
The recalled memory is injected as data only.
It is never system/developer/tool instruction.
```

## 7. Hybrid Recall Path

This is what `003-hybrid-recall` added.

```mermaid
flowchart TD
    Query[User query] --> Normalize[Normalize query]

    Normalize --> LexicalRecall[Lexical candidate recall]
    Normalize --> QueryEmbedding[Fake/local semantic embedding]

    QueryEmbedding --> VectorSearch[Vector candidate search\nfrom memory_embeddings]
    LexicalRecall --> Merge[Merge by memory_id]
    VectorSearch --> Merge

    Merge --> ConceptGate[Concept-overlap guard]
    ConceptGate --> LifecycleFilter[Lifecycle/privacy/supersession filters]
    LifecycleFilter --> Rerank[Explainable rerank]
    Rerank --> Results[Top memories + score components]

    subgraph DB[SQLite]
        Memories[life_memories\nsource of truth]
        EmbIndex[memory_embeddings\nderived index]
    end

    Memories --> LexicalRecall
    EmbIndex --> VectorSearch
    Memories --> LifecycleFilter
```

Scoring is intentionally explainable:

```text
final-ish score = lexical signal + semantic signal + metadata signal + temporal signal
```

Current prototype semantic recall is not a real external embedding model. It uses a deterministic fake provider so tests and smoke tests are local, repeatable, and safe. The vector index solves paraphrase discovery, not truth or freshness. Freshness still comes from lifecycle, timestamps, supersession, validity windows, feedback, and filters.

## 8. Runtime Data Model

```mermaid
erDiagram
    life_memories ||--o{ memory_evidence : has
    life_memories ||--o{ memory_links : links
    life_memories ||--o{ memory_embeddings : indexed_by
    life_memories ||--o{ feedback_events : receives
    life_memories ||--o{ traces : referenced_by
    reflection_reports ||--o{ traces : audited_by

    life_memories {
      text memory_id PK
      text content
      text status
      text primary_category
      text sensitivity
      real confidence
      real importance
      text valid_until
      text superseded_by
    }

    memory_embeddings {
      text embedding_id PK
      text memory_id FK
      text provider
      text model
      int dimension
      text content_hash
      text vector_json
      text status
    }

    traces {
      text trace_id PK
      text operation
      text outcome
      text redacted_input
      text metadata_json
      text created_at
    }
```

Simplified meaning:

| Table/area | Role |
| --- | --- |
| `life_memories` | Main durable memory rows and lifecycle state |
| `memory_evidence` | Why a memory exists and what supports it |
| `memory_links` | Supersedes, duplicate, conflict, related links |
| `memory_embeddings` | Derived semantic index, rebuildable and not authoritative |
| `traces` | Audit log for store, recall, activation, feedback, forget, reflect |
| `reflection_reports` | Derived reports and review artifacts, not primary truth |

## 9. Lifecycle State Machine

```mermaid
stateDiagram-v2
    [*] --> young: accepted candidate
    young --> active: explicit remember / enough confidence / supporting evidence
    young --> archived: low value / expired recent_state / rejected
    active --> reinforced: feedback or repeated useful evidence
    active --> pattern_candidate: repeated cross-session pattern
    reinforced --> pattern_candidate: enough evidence for pattern
    pattern_candidate --> abstract_experience: high-confidence low-risk inference
    active --> archived: stale / superseded / low value
    reinforced --> archived: stale / superseded
    archived --> active: user re-confirms
    young --> deleted: user forgets
    active --> deleted: user forgets
    reinforced --> deleted: user forgets
    pattern_candidate --> deleted: user forgets
    archived --> deleted: user forgets
    deleted --> [*]
```

Lifecycle rules:

| State | Meaning | Recall behavior |
| --- | --- | --- |
| `young` | New or weakly supported memory | Can recall, lower weight; auto-injection stricter |
| `active` | Stable current life memory | Normal recall/injection if safe and relevant |
| `reinforced` | Repeated or positively confirmed memory | Higher confidence |
| `pattern_candidate` | Possible long-term pattern | Needs stronger evidence before abstract inference |
| `archived` | Old, low value, expired, or superseded | Excluded by default |
| `deleted` | User asked to forget | Never normal recall; tombstone only |

## 10. Hot Path vs Background

```mermaid
flowchart LR
    subgraph Hot[Hot path: during conversation]
        A[Activation decision]
        B[Safe bounded recall]
        C[Fast store gate]
        D[Trace]
    end

    subgraph Background[Background: reflect/dreaming]
        E[Session extraction]
        F[Light cleanup]
        G[REM pattern/conflict discovery]
        H[Deep promotion/archive]
        I[Daily report]
    end

    Hot --> DB[(SQLite)]
    Background --> DB
    DB --> Export[Markdown review export]
```

Design reason:

| Path | Should do | Should not do |
| --- | --- | --- |
| Hot path | deterministic gate, quick write, bounded recall, trace | heavy model reflection, complex merge, risky promotion |
| Background | session extraction, dedupe, evidence counting, promotion, archive, reports | bypass safety gates or create facts from summaries alone |

## 11. Markdown Boundary

```mermaid
flowchart TD
    DB[(SQLite source of truth)] --> ExportTool[life_memory_export_review]
    ExportTool --> ReviewDir[$HERMES_HOME/life_memory_review]
    ReviewDir --> Journal[memory-journal]
    ReviewDir --> Library[memory-library]
    ReviewDir --> ReviewNeeded[review-needed.md]
    ReviewDir --> Archive[archive.md]
    ReviewDir --> ChangeRequests[change-requests.md template]

    ChangeRequests -. future only .-> Sync[future sync/validation]
    Sync -. not MVP .-> DB
```

Current rule:

```text
Markdown export is readable audit output.
Markdown edits are not read back in MVP/001/002/003.
SQLite remains the runtime source of truth.
```

## 12. Spec Stages

| Stage | Plain meaning | What it implemented / should implement |
| --- | --- | --- |
| `001-life-memory-plugin` | Build the memory database and tools | store, recall, feedback, forget, reflect, export review, routing, lifecycle, traces |
| `002-memory-activation` | Let the plugin decide before answering whether memory is needed | activation gate, strict filtering, data-only context injection through `pre_llm_call` |
| `003-hybrid-recall` | Make recall understand paraphrases | lexical + semantic candidates, embedding index, explainable rerank, activation integration |
| Proposed `004` | Make memory creation smarter after sessions | session distillation, entity linking, context lookup before write, conflict/supersession review |

## 13. What To Remember About The Original Design

The architecture has four non-negotiable boundaries:

1. SQLite is the automation state machine and source of truth.
2. Embeddings, reports, and Markdown are derived views, not facts.
3. The model can suggest/extract/summarize, but cannot bypass safety, lifecycle, conflict, or deletion rules.
4. Automatic memory use happens before the model answers, through a bounded data-only context block.

If you are unsure where a future feature belongs, use this rule:

```text
Does it change what is true? Put it behind SQLite state/evidence/lifecycle gates.
Does it help find or display truth? Make it a derived index or export.
Does it infer higher-level meaning? Require supporting evidence ids and mark it as inference.
```
