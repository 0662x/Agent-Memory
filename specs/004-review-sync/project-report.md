# Review Sync 阶段项目报告

**项目阶段**：004 Review Sync And Change Requests
**当前状态**：完成
**报告日期**：2026-06-06 Australia/Sydney
**最近自动化验证**：`uv run python -m pytest`，161 项测试全部通过

## 1. 阶段目标

`004-review-sync` 的目标是把 Markdown review 从纯只读导出，升级为显式、受限、可审计的 change request 入口。

这个阶段没有把 Markdown 变成数据库，也没有实现通用双向同步。SQLite 仍然是 source of truth。唯一允许的反向路径是用户显式调用 `life_memory_sync_review`，读取 `change-requests.md` 中结构化的 `life-memory-change` block。

## 2. 已完成能力

### 2.1 结构化 Change Request Parser

新增 `plugins/life_memory/review_sync.py`，支持解析 fenced Markdown block：

````markdown
```life-memory-change
id: req-001
action: replace
memory_id: mem_example
replacement: I now buy unsweetened soy milk after Saturday runs.
reason: Corrected older memory.
confirm: true
```
````

支持动作：

- `delete`
- `replace`
- `merge`
- `confirm`
- `reject`
- `mark_outdated`

Parser 记录 request id、action、target ids/query、source line、raw hash、errors，并检测 duplicate id、unsupported action、missing action 和 malformed line。

### 2.2 Dry-Run First Planning

`life_memory_sync_review` 默认 `apply=false`。Dry-run 会：

- 解析请求；
- 解析 exact `memory_id` 或 query target；
- 返回 planned/invalid/ambiguous/declined/not_found/needs_confirmation；
- 写 review-sync trace；
- 不修改 `life_memories`、`memory_links`、feedback、review status 或 promotion state。

### 2.3 Confirmed Apply

当且仅当满足这些条件时才 apply：

- tool payload `apply=true`；
- tool payload `confirm_apply=true`；
- destructive action block 内 `confirm: true`；
- batch 中所有 actions 都先 plan 成功。

Apply 复用现有 repository 语义：

- `delete` 使用 soft-delete/tombstone；
- `replace` 创建 replacement memory，并用 `superseded_by` link 归档旧 memory；
- `merge` 创建 merged target，并把 source memories 标记 `merged_into`；
- `confirm` 更新 review status 并记录 useful feedback；
- `reject` 归档并标记 rejected；
- `mark_outdated` 归档并记录 outdated feedback。

### 2.4 Safety And Ambiguity Gates

Review sync 不允许通过 Markdown 绕过现有安全边界：

- query 命中多条时返回 `ambiguous`，不 apply；
- deleted/missing id 返回 `not_found`；
- replacement/merged content 会重新跑 classification 和 safety；
- prompt-injection-like content 会被 declined；
- restricted raw content 会被 declined；
- results 和 traces 不包含 restricted raw content；
- manual edits to `memory-library`, `memory-journal`, `review-needed.md`, or `archive.md` are ignored in MVP。

### 2.5 Export Template Integration

`life_memory_export_review` 现在生成更明确的 `change-requests.md`：

- 说明 SQLite 仍是 source of truth；
- 说明 sync 显式且 dry-run by default；
- 说明只读取 `change-requests.md`；
- 提供 delete/replace/merge examples；
- 提醒其他 Markdown 文件的手工编辑在 MVP 中被忽略。

### 2.6 Tool Registration

新增第七个插件工具：

```text
life_memory_sync_review
```

工具 schema 支持：

- `apply`
- `confirm_apply`
- `review_dir`
- `source_file`
- `change_requests_text`
- `max_actions`

## 3. 测试和验证

最新全量测试：

```text
2026-06-06 Australia/Sydney
uv run python -m pytest
161 passed in 0.95s
Python 3.11.15, pytest 9.0.3
```

Targeted validation：

```text
uv run python -m pytest tests/unit/test_review_sync.py tests/integration/test_review_sync_flow.py tests/contract/test_tool_contracts.py tests/integration/test_export_review.py tests/integration/test_plugin_handlers.py
55 passed in 0.45s
```

覆盖范围：

- parser line numbers、duplicate ids、unsupported actions；
- source loading、inline text、path traversal rejection；
- dry-run no mutation；
- exact-id delete/replace/merge/confirm apply；
- destructive confirmation requirements；
- ambiguous query rejection；
- malformed request rejection；
- unsafe replacement rejection；
- restricted raw-content rejection and trace redaction；
- export template compatibility；
- ignored manual edits outside `change-requests.md`；
- plugin registration and contract envelope；
- 100 request parser bounded smoke；
- full-suite regression against activation, hybrid recall, routing, reflection, export, forget, and feedback。

## 4. Local Smoke

A temporary `HERMES_HOME` smoke test validated this flow:

```text
store old coconut-water memory
export review files
write exact-id replace request into change-requests.md
dry-run sync -> planned
apply sync -> applied
re-export review files
recall "Saturday runs soy milk" -> success
remove temporary HERMES_HOME
```

No real Hermes profile or external model was used.

## 5. Remaining Boundaries

The stage intentionally does not implement:

- arbitrary Markdown diff parsing;
- continuous filesystem watching;
- natural-language LLM parsing of review edits;
- cross-device or multi-user conflict resolution;
- real UI for conflict resolution;
- raw sensitive/restricted Markdown round-trip.

The sync path is still explicit, structured, and conservative by design.
