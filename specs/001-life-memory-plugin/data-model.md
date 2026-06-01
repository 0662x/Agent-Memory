# Data Model: Hermes 分层生活记忆插件

## Overview

MVP 使用单个 SQLite database：`$HERMES_HOME/life_memory.db`。数据库由插件首次加载或首次工具调用时初始化。所有时间字段使用 timezone-aware ISO-8601 string。所有 JSON 字段以 TEXT 保存，由 repository 层统一 encode/decode。

## Enums

### Memory Classification

- `technical_memory`
- `life_memory`
- `user_profile`
- `temporary_working_memory`
- `abstract_experience`
- `no_save`

### Lifecycle Status

- `young`
- `active`
- `reinforced`
- `pattern_candidate`
- `archived`
- `deleted`

### Review Status

- `pending`: 新记忆或候选项尚未被人工或自动晋升确认。
- `approved`: 人工确认可以作为稳定记忆使用。
- `rejected`: 人工或规则明确拒绝。
- `needs_review`: 高风险、冲突、敏感或抽象候选，需要人工确认。
- `auto_promoted`: 未经人工审核，但通过 background/dreaming 阈值自动晋升。

### Memory Kind

- `direct`: 用户或 assistant 显式写入的生活记忆。
- `reflected`: reflection 从多条记忆中派生出的抽象经验。

### Sensitivity

- `normal`: 默认生活记忆。
- `sensitive`: 需要用户明确要求长期保存，召回时需要更明确查询。
- `restricted`: 保留元数据但默认不进入普通召回；用于未来更严格隐私策略。

### Feedback Type

- `useful`
- `wrong`
- `outdated`
- `important`
- `duplicate`
- `delete`
- `merge`

### Trace Operation

- `classify`
- `store`
- `recall`
- `feedback`
- `forget`
- `reflect`
- `merge`
- `archive`
- `reinforce`
- `conflict`
- `supersede`
- `dream_light`
- `dream_rem`
- `dream_deep`
- `session_extract`
- `reflection_report`
- `export_review`
- `model_classify`
- `model_extract`
- `model_rerank`
- `model_reflect`
- `model_summarize`

### Reflection Phase

- `session`: 从完成的会话或会话引用中抽取有效记忆候选。
- `light`: 低成本整理、去重、补标签、统计 evidence。
- `rem`: 发现模式、冲突、候选抽象经验和 session/daily 反思草稿。
- `deep`: 基于阈值晋升、归档或形成稳定抽象经验。
- `daily`: 生成每日 reflection report；MVP 只作为审计，不参与晋升信号。

### Evidence Type

- `explicit_user_statement`
- `assistant_tool_call`
- `repeated_observation`
- `recall_use`
- `user_feedback`
- `session_extract`
- `reflection_report`
- `reflection`

### Promotion Path

- `normal_evidence`: 普通证据累积晋升。
- `major_life_fact`: 重大、明确、长期有效的个人事实快速晋升到 `active`。
- `user_confirmed`: 用户明确确认或强化。
- `reflected_pattern`: reflection 从多条证据生成或晋升的模式。

## Tables

### `schema_version`

Tracks database migrations.

| Field | Type | Notes |
|-------|------|-------|
| `version` | INTEGER PRIMARY KEY | Current schema version |
| `applied_at` | TEXT NOT NULL | ISO timestamp |

### `life_memories`

Main memory table. SQLite `rowid` is kept for FTS integration; stable external references use `memory_id`.

| Field | Type | Notes |
|-------|------|-------|
| `memory_id` | TEXT UNIQUE NOT NULL | UUID-style stable identifier |
| `kind` | TEXT NOT NULL | `direct` or `reflected` |
| `classification` | TEXT NOT NULL | Expected `life_memory` or `abstract_experience` for stored rows |
| `classification_reason` | TEXT NOT NULL | Human-readable reason |
| `classification_confidence` | REAL NOT NULL | Confidence in boundary/category classification, 0.0 to 1.0 |
| `content` | TEXT NOT NULL | Redacted marker after forget |
| `content_hash` | TEXT NOT NULL | Hash for duplicate detection and deleted tombstones |
| `primary_category` | TEXT NOT NULL | `personal_fact`, `personal_preference`, or `personal_pattern` |
| `tags_json` | TEXT NOT NULL | JSON array of strings |
| `context_json` | TEXT NOT NULL | Optional source context, redacted on forget when needed |
| `importance` | REAL NOT NULL | 0.0 to 1.0 |
| `confidence` | REAL NOT NULL | 0.0 to 1.0 |
| `feedback_score` | REAL NOT NULL | Accumulated signal used by ranking/reflection |
| `source` | TEXT NOT NULL | `user_explicit`, `assistant_tool`, `session_extract`, `feedback`, `reflection`, `import` |
| `source_ref` | TEXT | Session/message/tool reference if available |
| `status` | TEXT NOT NULL | Lifecycle status |
| `review_status` | TEXT NOT NULL | Review status; defaults to `pending` |
| `sensitivity` | TEXT NOT NULL | Sensitivity enum |
| `evidence_count` | INTEGER NOT NULL | Count of supporting evidence records |
| `source_count` | INTEGER NOT NULL | Count of distinct sources/source refs |
| `unique_query_count` | INTEGER NOT NULL | Distinct recall query contexts that surfaced it |
| `days_seen_count` | INTEGER NOT NULL | Number of distinct days with supporting evidence |
| `promotion_score` | REAL NOT NULL | Background/dreaming promotion score, 0.0 to 1.0 |
| `promotion_path` | TEXT | Promotion path enum when the memory is promoted |
| `promotion_reason` | TEXT | Why the memory was promoted or considered promotable |
| `decay_reason` | TEXT | Why the memory was decayed or archived |
| `last_confirmed_at` | TEXT | Last explicit confirmation or strong automatic confirmation |
| `valid_from` | TEXT | Optional start of validity window |
| `valid_until` | TEXT | Optional expiry/end of validity window |
| `scope` | TEXT | Optional usage scope such as `general`, `home`, `workday`, `relationship:<id>` |
| `authority` | TEXT | Source authority/trust label, e.g. `user_direct`, `assistant_inferred`, `session_extract`, `reflection_report` |
| `action_boundary` | TEXT | When this memory may affect future behavior, or what it must not trigger |
| `injection_risk` | REAL NOT NULL | 0.0 to 1.0 risk score for instruction-like or poisoning-like content |
| `created_at` | TEXT NOT NULL | ISO timestamp |
| `updated_at` | TEXT NOT NULL | ISO timestamp |
| `last_accessed_at` | TEXT | Updated by recall |
| `access_count` | INTEGER NOT NULL | Starts at 0 |
| `deleted_at` | TEXT | Set for tombstone deletion |

Validation:

- `content` must be non-empty unless the record is `deleted`, in which case it must be a redacted marker.
- Each stored memory has exactly one `primary_category`; subtypes such as habit, routine, relationship, event, lifestyle, food, family, work_style, or emotion_pattern should be represented with `tags_json`.
- `classification_confidence`, `importance`, `confidence`, and `feedback_score` are clamped to `0.0..1.0` where applicable.
- `deleted` rows are excluded from normal recall and reflection.
- `archived` rows are excluded from normal recall unless explicitly requested.
- `reflected` rows must have supporting links in `memory_links`.
- `needs_review` rows may be recalled only as low-trust candidate data unless explicitly requested.
- `auto_promoted` rows must have enough evidence and a trace explaining promotion.
- `major_life_fact` promotion may move a memory from `young` to `active`, but must not directly create `reinforced` or `abstract_experience` records.
- `recent_state` memories use the MVP TTL rule: `valid_until = created_or_refreshed_at + 14 days`, expired rows are excluded from normal recall and archived by light reflection.
- `session_extract` authority may create `young` memory candidates only after classification and safety gates.
- `reflection_report` authority cannot by itself promote a memory; it must link to supporting evidence.

### `memory_evidence`

Stores evidence supporting or weakening a memory. Event-level evidence and session-level effective extraction are the preferred sources of truth; reflection reports are derived evidence.

| Field | Type | Notes |
|-------|------|-------|
| `evidence_id` | TEXT PRIMARY KEY | Stable evidence id |
| `memory_id` | TEXT NOT NULL | Target memory |
| `evidence_type` | TEXT NOT NULL | Evidence type enum |
| `content` | TEXT | Short evidence snippet; may be redacted for sensitive/deleted content |
| `content_hash` | TEXT NOT NULL | Hash for dedupe and redaction-safe trace |
| `source_ref` | TEXT | Session/message/tool/reflection report reference |
| `event_date` | TEXT | Date bucket for days_seen_count |
| `weight` | REAL NOT NULL | Evidence strength, 0.0 to 1.0 |
| `confidence` | REAL NOT NULL | Evidence confidence, 0.0 to 1.0 |
| `created_at` | TEXT NOT NULL | ISO timestamp |

Validation:

- Evidence must not bypass classification or safety gates.
- Evidence for deleted memories must not expose forgotten content.
- Session extract evidence must reference the source session/message where possible.
- Reflection report evidence must reference lower-level memory/evidence ids when available.

### `memory_links`

Represents relationships between memories.

| Field | Type | Notes |
|-------|------|-------|
| `link_id` | TEXT PRIMARY KEY | Stable link id |
| `from_memory_id` | TEXT NOT NULL | Source memory |
| `to_memory_id` | TEXT NOT NULL | Target memory |
| `relation` | TEXT NOT NULL | `related_to`, `duplicate_of`, `merged_into`, `supersedes`, `superseded_by`, `supports`, `conflicts_with` |
| `reason` | TEXT NOT NULL | Why link exists |
| `created_at` | TEXT NOT NULL | ISO timestamp |

Validation:

- A memory cannot link to itself.
- `supports` links are required for `reflected` abstract experience rows.
- `supersedes` and `superseded_by` must be mirrored by repository helpers.

### `memory_feedback`

Records user feedback and tool-level correction signals.

| Field | Type | Notes |
|-------|------|-------|
| `feedback_id` | TEXT PRIMARY KEY | Stable id |
| `memory_id` | TEXT NOT NULL | Target memory |
| `feedback_type` | TEXT NOT NULL | Feedback enum |
| `note` | TEXT | User note or reason |
| `replacement_content` | TEXT | Optional correction |
| `target_memory_id` | TEXT | For duplicate/merge feedback |
| `created_at` | TEXT NOT NULL | ISO timestamp |

Validation:

- `wrong` or `outdated` with replacement content should create update/supersede behavior.
- `delete` should delegate to forget semantics.
- `merge` requires `target_memory_id` or returns `ambiguous`.

### `memory_traces`

Append-only audit trail.

| Field | Type | Notes |
|-------|------|-------|
| `trace_id` | TEXT PRIMARY KEY | Stable id |
| `memory_id` | TEXT | Nullable for declined classification or broad recall |
| `operation` | TEXT NOT NULL | Trace operation enum |
| `actor` | TEXT NOT NULL | `user`, `assistant`, `plugin`, `reflection` |
| `reason` | TEXT NOT NULL | Human-readable explanation |
| `input_hash` | TEXT | Hash of sensitive input if content should not be retained |
| `before_json` | TEXT | Redacted snapshot if needed |
| `after_json` | TEXT | Redacted snapshot if needed |
| `created_at` | TEXT NOT NULL | ISO timestamp |

Validation:

- Forget traces must not expose forgotten content to user-facing output.
- Declined store attempts still get a trace with reason and classification, but sensitive raw content may be hashed only.
- Model traces must treat model output as advisory: store task, confidence, redacted input/output, and the validation result that accepted, rejected, or downgraded the proposal.
- Model output must not bypass classification, sensitivity, conflict, injection-risk, or deletion rules.

### `reflection_runs`

Records background dreaming/reflection runs.

| Field | Type | Notes |
|-------|------|-------|
| `run_id` | TEXT PRIMARY KEY | Stable run id |
| `phase` | TEXT NOT NULL | `session`, `light`, `rem`, `deep`, or `daily` |
| `started_at` | TEXT NOT NULL | ISO timestamp |
| `completed_at` | TEXT | ISO timestamp |
| `input_window_json` | TEXT NOT NULL | Time/status/category filters used for this run |
| `candidate_count` | INTEGER NOT NULL | Number of candidates considered |
| `applied_count` | INTEGER NOT NULL | Number of changes applied |
| `report_path` | TEXT | Optional Markdown report path |
| `status` | TEXT NOT NULL | `success`, `partial`, `failed`, `dry_run` |
| `notes` | TEXT | Human-readable run notes |

### `reflection_reports`

Optional derived session/daily reflection records. These are not the primary source of truth; they summarize session extraction results and event-level evidence. In MVP, daily reports are report-only and do not influence promotion scores; MVP+ may allow them to influence promotion scores only when linked to supporting evidence.

| Field | Type | Notes |
|-------|------|-------|
| `report_id` | TEXT PRIMARY KEY | Stable report id |
| `report_type` | TEXT NOT NULL | `session`, `daily`, `weekly`, or `manual_review` |
| `report_date` | TEXT | Local date for daily/weekly reports |
| `session_ids_json` | TEXT NOT NULL | Source sessions reviewed; empty array for non-session reports |
| `content` | TEXT NOT NULL | Structured report text or redacted marker |
| `source_memory_ids_json` | TEXT NOT NULL | Supporting memory ids |
| `source_evidence_ids_json` | TEXT NOT NULL | Supporting evidence ids |
| `created_by_run_id` | TEXT | Reflection run that produced it |
| `review_status` | TEXT NOT NULL | Usually `pending`, `approved`, or `auto_promoted` |
| `created_at` | TEXT NOT NULL | ISO timestamp |
| `updated_at` | TEXT NOT NULL | ISO timestamp |

Validation:

- A reflection report must not create durable facts without linked supporting evidence.
- A session report may propose `young` memories or evidence, but those proposals still pass classification and safety gates.
- In MVP, daily/weekly reports must not raise promotion score.
- In MVP+, a daily/weekly report may raise promotion score, but cannot bypass sensitivity, conflict, or injection-risk checks.

### `life_memories_fts`

Optional FTS5 virtual table for `content`, `primary_category`, and tags. Created only if FTS5 is available. Repository methods must detect availability and fallback gracefully.

### `evaluation_cases`

This may be a test fixture rather than a runtime table for MVP. If stored in SQLite later, it uses:

| Field | Type | Notes |
|-------|------|-------|
| `case_id` | TEXT PRIMARY KEY | Stable id |
| `case_type` | TEXT NOT NULL | `classification`, `recall`, `temporal_update`, `forget`, `abstention`, `safety` |
| `input_json` | TEXT NOT NULL | Test input |
| `expected_json` | TEXT NOT NULL | Expected output subset |

## State Transitions

```text
young -> active              after enough low-risk evidence or useful recall
young -> deleted             after explicit forget
active -> reinforced         after useful/important feedback or repeated useful recall
active -> archived           after stale/low-value reflection
active -> deleted            after forget/delete feedback
active -> pattern_candidate  when repeated evidence suggests a possible pattern
pattern_candidate -> reflected abstract_experience after deep reflection and sufficient supporting links
pattern_candidate -> archived if evidence remains weak or stale
reinforced -> archived       if later marked outdated/stale
reinforced -> deleted        after forget/delete feedback
any non-deleted -> deleted   after explicit forget with unambiguous target
```

## Recall Ranking Signals

Ranking uses a simple explainable score:

- text relevance from FTS/keyword match;
- `importance`;
- `confidence`;
- `feedback_score`;
- `evidence_count`;
- `unique_query_count`;
- `days_seen_count`;
- `promotion_score`;
- recency from `last_accessed_at`/`updated_at`;
- penalty for `young` and `archived`;
- penalty for `needs_review` and high `injection_risk`;
- exclusion for `deleted`;
- stricter inclusion for `sensitive`/`restricted`.

The exact scoring weights belong in implementation tasks and tests; the contract only requires deterministic, bounded ordering.
