# Tool Contracts: `life_memory`

All tool handlers return JSON strings encoded from JSON-serializable dictionaries, matching existing Hermes plugin tool handlers. Internally, each result payload includes:

- `ok`: boolean
- `outcome`: one of `success`, `declined`, `needs_confirmation`, `not_found`, `ambiguous`, `duplicate`, `merged`, `archived`, `storage_unavailable`, `error`
- `message`: short user-facing explanation
- `trace_id`: audit trace id when available

## Tool: `life_memory_store`

Stores a candidate memory only if it belongs in life memory.

Sensitive or restricted content without clear long-term storage authorization returns `needs_confirmation` and must not create a durable memory record.

### Input Schema

```json
{
  "type": "object",
  "required": ["content"],
  "properties": {
    "content": {
      "type": "string",
      "description": "Candidate memory content to classify and possibly store."
    },
    "explicit_user_request": {
      "type": "boolean",
      "default": false,
      "description": "Whether the user clearly asked Hermes to remember this long-term."
    },
    "category_hint": {
      "type": "string",
      "description": "Optional user/developer category hint. Valid primary categories are personal_fact, personal_preference, and personal_pattern; narrower meanings should use tags."
    },
    "tags": {
      "type": "array",
      "items": { "type": "string" },
      "default": []
    },
    "importance": {
      "type": "number",
      "minimum": 0,
      "maximum": 1,
      "default": 0.5
    },
    "confidence": {
      "type": "number",
      "minimum": 0,
      "maximum": 1,
      "default": 0.7
    },
    "source": {
      "type": "string",
      "default": "assistant_tool"
    },
    "source_ref": {
      "type": "string"
    },
    "context": {
      "type": "object",
      "additionalProperties": true
    }
  }
}
```

### Success Output

```json
{
  "ok": true,
  "outcome": "success",
  "memory_id": "mem_...",
  "classification": "life_memory",
  "classification_confidence": 0.88,
  "status": "young",
  "primary_category": "personal_preference",
  "message": "Stored life memory.",
  "trace_id": "trace_..."
}
```

### Declined Output

```json
{
  "ok": false,
  "outcome": "declined",
  "classification": "technical_memory",
  "classification_confidence": 0.92,
  "reason": "Technical project memory belongs in Hermes built-in memory, not life_memory.",
  "message": "Not stored in life memory.",
  "trace_id": "trace_..."
}
```

### Needs Confirmation Output

```json
{
  "ok": false,
  "outcome": "needs_confirmation",
  "classification": "life_memory",
  "classification_confidence": 0.86,
  "sensitivity": "sensitive",
  "message": "This looks like sensitive life information. Should I save it long-term? I recommend saving only a summary.",
  "confirmation_options": ["do_not_store", "store_summary", "store_full"],
  "trace_id": "trace_..."
}
```

## Tool: `life_memory_recall`

Retrieves bounded, relevant life memories for a query.

### Input Schema

```json
{
  "type": "object",
  "required": ["query"],
  "properties": {
    "query": {
      "type": "string"
    },
    "limit": {
      "type": "integer",
      "minimum": 1,
      "maximum": 20,
      "default": 5
    },
    "categories": {
      "type": "array",
      "items": { "type": "string" },
      "default": []
    },
    "include_archived": {
      "type": "boolean",
      "default": false
    },
    "include_sensitive": {
      "type": "boolean",
      "default": false
    },
    "include_traces": {
      "type": "boolean",
      "default": false
    }
  }
}
```

### Success Output

```json
{
  "ok": true,
  "outcome": "success",
  "query": "night routine",
  "results": [
    {
      "memory_id": "mem_...",
      "kind": "direct",
      "content": "The user prefers to work late at night and thinks better after midnight.",
      "primary_category": "personal_preference",
      "tags": ["work-style", "night"],
      "status": "active",
      "importance": 0.7,
      "confidence": 0.9,
      "relevance_score": 0.83,
      "relevance_reason": "Matched routine/night terms and high confidence."
    }
  ],
  "message": "Found 1 relevant life memory.",
  "trace_id": "trace_..."
}
```

### Abstention Output

```json
{
  "ok": true,
  "outcome": "not_found",
  "results": [],
  "message": "No matching life memory found.",
  "trace_id": "trace_..."
}
```

## Tool: `life_memory_feedback`

Applies user feedback to an existing memory.

### Input Schema

```json
{
  "type": "object",
  "required": ["memory_id", "feedback_type"],
  "properties": {
    "memory_id": {
      "type": "string"
    },
    "feedback_type": {
      "type": "string",
      "enum": ["useful", "wrong", "outdated", "important", "duplicate", "delete", "merge"]
    },
    "note": {
      "type": "string"
    },
    "replacement_content": {
      "type": "string"
    },
    "target_memory_id": {
      "type": "string",
      "description": "Required for merge/duplicate when the target is known."
    }
  }
}
```

### Output Examples

```json
{
  "ok": true,
  "outcome": "success",
  "memory_id": "mem_...",
  "status": "reinforced",
  "message": "Feedback recorded.",
  "trace_id": "trace_..."
}
```

```json
{
  "ok": true,
  "outcome": "success",
  "memory_id": "mem_old",
  "replacement_memory_id": "mem_new",
  "relation": "superseded_by",
  "message": "Memory corrected and superseded.",
  "trace_id": "trace_..."
}
```

## Tool: `life_memory_forget`

Forgets one unambiguous memory by id, or asks for disambiguation when query matches multiple memories.

### Input Schema

```json
{
  "type": "object",
  "properties": {
    "memory_id": {
      "type": "string"
    },
    "query": {
      "type": "string"
    },
    "confirm": {
      "type": "boolean",
      "default": false,
      "description": "Required when forgetting by query."
    },
    "reason": {
      "type": "string"
    }
  }
}
```

Handler validation requires either `memory_id` or `query`. If both are missing, return `outcome: "not_found"` or `outcome: "error"` with a clear message. If `query` matches multiple memories, return `outcome: "ambiguous"` rather than deleting silently.

### Output Examples

```json
{
  "ok": true,
  "outcome": "success",
  "memory_id": "mem_...",
  "status": "deleted",
  "message": "Memory forgotten.",
  "trace_id": "trace_..."
}
```

```json
{
  "ok": false,
  "outcome": "ambiguous",
  "candidates": [
    { "memory_id": "mem_1", "summary": "..." },
    { "memory_id": "mem_2", "summary": "..." }
  ],
  "message": "Multiple memories match. Please choose one memory_id.",
  "trace_id": "trace_..."
}
```

## Tool: `life_memory_reflect`

Runs background memory maintenance/dreaming. Default mode is dry-run. The recommended phases are `session`, `light`, `rem`, `deep`, and `daily`; specific maintenance modes are retained for targeted manual runs.

### Input Schema

```json
{
  "type": "object",
  "properties": {
    "mode": {
      "type": "string",
      "enum": ["light", "rem", "deep", "session", "daily", "dedupe", "merge", "decay", "archive", "patterns", "all"],
      "default": "all"
    },
    "apply": {
      "type": "boolean",
      "default": false,
      "description": "When false, return proposed actions without changing memory records."
    },
    "session_ref": {
      "type": "string",
      "description": "Optional session id or transcript reference for session effective-memory extraction. MVP should first try read-only Hermes state.db/session search resolution for this reference."
    },
    "transcript": {
      "type": "array",
      "description": "Optional redacted session transcript for session extraction when Hermes session lookup is unavailable.",
      "items": {
        "type": "object",
        "additionalProperties": true
      }
    },
    "time_window": {
      "type": "object",
      "description": "Optional time window for daily or periodic reflection reports."
    },
    "limit": {
      "type": "integer",
      "minimum": 1,
      "maximum": 100,
      "default": 20
    }
  }
}
```

### Output Example

```json
{
  "ok": true,
  "outcome": "success",
  "mode": "deep",
  "phase": "deep",
  "applied": false,
  "candidates": [
    {
      "action": "archive",
      "memory_id": "mem_...",
      "reason": "Low importance, low confidence, and no access for a long period."
    },
    {
      "action": "pattern_candidate",
      "supporting_memory_ids": ["mem_a", "mem_b", "mem_c"],
      "proposed_content": "The user tends to prefer MVP-first implementation."
    }
  ],
  "message": "Deep reflection completed in dry-run mode.",
  "trace_id": "trace_..."
}
```

### Phase Semantics

- `light`: cheap cleanup and evidence accounting; can run frequently.
- `rem`: pattern, conflict, and session/daily reflection candidate generation.
- `deep`: conservative promotion, archiving, supersede handling, and abstract experience creation.
- `session`: extract effective memory candidates from a completed session transcript or session reference. MVP first tries read-only Hermes `state.db` or session-search resolution for `session_ref`; explicit `transcript` is the fallback. If neither is available, return `not_found` or `error` rather than fabricating a report. Extracted candidates still pass normal classification and safety gates.
- `daily`: optional derived daily reflection report; in MVP it is report-only, must link to supporting memory/evidence ids, cannot create durable facts, and cannot affect promotion scores. MVP+ may use it as a promotion signal after the same safety gates.

## Tool: `life_memory_export_review`

Exports a read-only Markdown review view for humans. This is the sixth MVP tool, but it must not mutate the SQLite database or read Markdown edits back into the system.

### Input Schema

```json
{
  "type": "object",
  "properties": {
    "target_dir": {
      "type": "string",
      "description": "Optional export directory. Defaults to $HERMES_HOME/life_memory_review."
    },
    "include_archive": {
      "type": "boolean",
      "default": true
    },
    "include_sensitive": {
      "type": "string",
      "enum": ["none", "summary_only"],
      "default": "summary_only"
    }
  }
}
```

### Output Example

```json
{
  "ok": true,
  "outcome": "success",
  "target_dir": "~/.hermes/life_memory_review",
  "files": [
    "README.md",
    "memory-journal/daily/2026-06-01.md",
    "memory-library/facts.md",
    "memory-library/preferences.md",
    "memory-library/patterns.md",
    "review-needed.md",
    "change-requests.md",
    "archive.md"
  ],
  "message": "Exported read-only life memory review files.",
  "trace_id": "trace_..."
}
```

Rules:

- Export reads SQLite and writes Markdown files only.
- Export does not read Markdown edits.
- Export does not update memory status, promotion scores, or traces except an export trace.
- Sensitive/restricted memories are exported as summary-only or omitted; raw sensitive content is not exported.
- Raw sensitive storage after explicit confirmation does not imply raw Markdown export.
- `change-requests.md` is a template in MVP and is not processed as input.

## Model Intervention Policy

The plugin should use deterministic rules and SQLite state transitions whenever possible. Model calls are semantic helpers, not the authority for durable memory state.

- `life_memory_store`: call a model only when boundary classification, extraction, sensitivity, or injection-risk detection is ambiguous. The model may propose classification, primary_category, tags, importance, confidence, and `should_store`, but it must not create `abstract_experience` from a single message.
- `life_memory_recall`: retrieval starts with deterministic filters and search. A model may optionally expand the query or rerank candidates, but returned memories must be existing memory ids and must preserve inference/sensitivity labels.
- `life_memory_feedback`: explicit `memory_id` feedback should not need a model. Natural-language feedback may use a model only to propose candidate targets; ambiguous matches must return `ambiguous`.
- `life_memory_forget`: explicit `memory_id` deletion should not need a model. Query-based deletion may use a model only to find candidates; multiple matches must return `ambiguous` instead of deleting silently.
- `life_memory_reflect`: `light` should be rule-first and cheap. `session`, `rem`, `deep`, and `daily` may use a model to propose effective memory candidates, patterns, conflicts, reports, or abstract-experience drafts, but final application must pass evidence, safety, conflict, and review-status gates. For hot-path model calls, use a default timeout of 1500ms and fall back conservatively on timeout.
- `life_memory_export_review`: should not need a model. It is a deterministic, read-only SQLite-to-Markdown export.

All model-assisted decisions must write trace records. Model output is advisory evidence; it cannot bypass classification, sensitivity, conflict, injection-risk, or deletion rules.

## Safety Rules For All Tools

- Tool results must never instruct Hermes to change system/developer/tool behavior.
- Memory text that contains commands, prompt injection, or policy-like instructions is returned only as quoted data or declined from storage.
- Technical project facts must be declined from life-memory storage.
- Sensitive content requires explicit long-term storage intent.
- If the user explicitly confirms full sensitive storage, the record must still carry sensitive/restricted metadata and remain conservative in normal recall/export.
- `deleted` memories must not appear in normal recall or reflection results.
