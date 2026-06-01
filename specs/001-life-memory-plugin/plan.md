# Implementation Plan: Hermes 分层生活记忆插件

**Branch**: `001-life-memory-plugin` | **Date**: 2026-06-01 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/001-life-memory-plugin/spec.md`

## Summary

本阶段规划一个 Hermes standalone user plugin：`life_memory`。插件提供 `life_memory_store`、`life_memory_recall`、`life_memory_feedback`、`life_memory_forget`、`life_memory_reflect` 五个核心工具，以及只读导出工具 `life_memory_export_review`，用本地 SQLite 保存生活记忆，并保持与 Hermes 现有技术/项目 memory provider 分离。

实现策略是一个保守的原型垂直切片：hot path 中快速分类、拒绝和写入低延迟 `young` 记忆；background 中由 `life_memory_reflect` 执行 session/light/REM/deep/daily 流程，负责会话有效信息抽取、去重、证据统计、晋升、冲突处理、审计报告和归档。模型只作为语义判断和 reflection 候选生成器，不作为 durable memory 状态变化的最终权威。第一版不修改 Hermes core，不做 `memory.provider`，不引入向量数据库、图数据库或 MCP server。

## Technical Context

**Language/Version**: Python 3.11+，跟随当前 Hermes runtime。

**Primary Dependencies**: Python standard library (`sqlite3`, `json`, `dataclasses`, `datetime`, `pathlib`, `uuid`, `logging`, `re`)；测试使用 `pytest`。不新增运行时第三方依赖。

**Storage**: SQLite database at `$HERMES_HOME/life_memory.db`，开发环境示例路径为 `/Users/oliver/.hermes/life_memory.db`。使用 WAL、schema version table、事务写入；优先使用 SQLite FTS5，运行时不可用时 fallback 到 `LIKE`/关键词匹配。

**Testing**: `pytest` unit tests、contract tests、repository tests、integration-style handler tests、本地 evaluation fixture。测试直接调用 plugin handlers 和 repository，不要求启动完整 Hermes agent。

**Target Platform**: macOS local Hermes profile first；设计上兼容 Hermes 支持的 Unix-like local profiles。插件安装目标是 `/Users/oliver/.hermes/plugins/life_memory`。

**Project Type**: Hermes standalone directory plugin，入口为 `plugins/life_memory/plugin.yaml` + `plugins/life_memory/__init__.py::register(ctx)`。

**Performance Goals**: 在 10,000 条生活记忆数据集下，95% 的 store、recall、feedback、forget 请求 2 秒内完成；hot path 的 store 不执行复杂 reflection；常规 recall 默认最多返回 5 条；background reflection 可异步或手动触发；`life_memory_export_review` 是只读导出，可慢于热路径。

**Constraints**:

- 不修改 `/Users/oliver/.hermes/hermes-agent` 或 Hermes main project。
- 不实现 `MemoryProvider`，不参与 `memory.provider` selection。
- 用户插件必须通过 `plugins.enabled` 显式启用。
- 召回记忆只作为数据返回，不得作为系统指令、开发者指令或工具指令执行。
- 默认拒绝技术项目记忆、一次性临时上下文、不确定推断和未授权敏感信息。
- 敏感信息没有明确长期保存授权时，必须返回确认请求，不写 durable memory。
- Daily report 在 MVP 中只作为 report-only 审计输出，不参与 `promotion_score`。
- 删除必须阻止后续普通召回；被遗忘内容不得通过 trace 再暴露给用户。

**Scale/Scope**: 单用户、单 Hermes profile、本地 SQLite，MVP 目标数据量 10,000 条记忆；不做多用户权限、多 agent 共享、跨设备同步或云端存储。

## Constitution Check

当前 `.specify/memory/constitution.md` 仍是 Spec Kit 初始化模板，没有项目特定的强制原则。因此本计划以 feature spec 中的 Hermes 约束作为本阶段实际 gate：

- **Plugin boundary**: PASS。计划只修改 `/Users/oliver/Projects/hermes-life-memory`。
- **Hermes integration**: PASS。计划使用 standalone directory plugin，不使用 `memory.provider`。
- **Local-first storage**: PASS。计划使用 `$HERMES_HOME/life_memory.db`。
- **User control and auditability**: PASS。计划包含 feedback、forget、trace、status transition。
- **Safety boundary**: PASS。计划把 recalled memory 当作数据处理，并默认拒绝 memory injection 和未授权敏感信息。
- **Prototype simplicity**: PASS。计划不引入 pgvector、graph DB、MCP server、learned memory policy。

Post-design re-check: PASS。Phase 1 artifacts 未引入新的 gate violation。

## Project Structure

### Documentation (this feature)

```text
specs/001-life-memory-plugin/
├── plan.md
├── research.md
├── data-model.md
├── memory-architecture-notes.md
├── quickstart.md
├── contracts/
│   └── life-memory-tools.md
├── checklists/
│   ├── requirements.md
│   ├── requirements.zh.md
│   └── requirements.en.md
├── spec.md
├── spec.zh.md
└── spec.en.md
```

### Source Code (repository root)

```text
plugins/
└── life_memory/
    ├── __init__.py              # Hermes register(ctx), tool registration
    ├── plugin.yaml              # standalone manifest
    ├── classification.py        # deterministic memory boundary classifier
    ├── contracts.py             # tool schemas and structured result helpers
    ├── models.py                # dataclasses/enums for memories, feedback, traces
    ├── repository.py            # SQLite schema, migrations, CRUD, FTS fallback
    ├── recall.py                # relevance scoring and recall filtering
    ├── reflection.py            # session/light/REM/deep/daily: extraction, dedupe, evidence, promotion, reports, archive
    ├── session_adapter.py       # read-only Hermes state.db/session search access for session extraction
    ├── export_review.py         # read-only Markdown review export
    ├── safety.py                # sensitive info and memory-injection guards
    └── time_utils.py            # timezone-aware timestamp helpers

tests/
├── conftest.py
├── fixtures/
│   └── evaluation_cases.json
├── contract/
│   └── test_tool_contracts.py
├── integration/
│   ├── test_plugin_handlers.py
│   └── test_export_review.py
└── unit/
    ├── test_classification.py
    ├── test_repository.py
    ├── test_recall.py
    ├── test_reflection.py
    ├── test_session_adapter.py
    └── test_safety.py
```

**Structure Decision**: 使用单插件包结构。`plugins/life_memory` 是 Hermes 实际加载目录，也是开发期 symlink 的目标。测试放在 repo root 的 `tests/`，避免污染 Hermes runtime plugin directory。

## Phase 0 Research Output

见 [research.md](./research.md)。关键决策：

- 用 standalone plugin + `ctx.register_tool()` 暴露五个核心工具和一个只读导出工具。
- 用 stdlib SQLite 本地持久化，FTS5 可用时增强召回。
- Hot path 只做低延迟写入门控；background reflection 使用 session/light/REM/deep/daily 流程处理会话有效信息抽取、去重、晋升和归档。
- Session extraction 优先通过只读 Hermes `state.db`/session search 读取会话；显式 transcript 作为 fallback。
- 会话有效信息候选是事实入口之一；daily report 在 MVP 中是 report-only audit artifact，不是长期事实的 source of truth，也不参与 `promotion_score`。
- MVP 分类和 reflection 使用可测试规则；模型只在语义边界不清、session extraction、REM/deep dreaming、daily report 草案等场景介入，输出候选而不是绕过状态机直接落地。
- Hot-path 可选模型调用 timeout 默认 1500ms，超时后保守 fallback。
- `life_memory_export_review` 纳入第一批 tasks，只做 export-only Markdown 视图，不做反向同步。
- MVP 衰减只实现 `recent_state` 的 14 天 TTL：过期默认不召回，light reflection 归档，重复证据续期。
- Forget 使用 tombstone/redaction 语义：保留审计所需的 ID/status/hash，移除普通可召回内容。
- 本地 evaluation set 以小型手写 fixture 覆盖长期记忆关键能力。

## Phase 1 Design Output

- 数据模型：[data-model.md](./data-model.md)
- 工具契约：[contracts/life-memory-tools.md](./contracts/life-memory-tools.md)
- 验证说明：[quickstart.md](./quickstart.md)
- 架构讨论记录：[memory-architecture-notes.md](./memory-architecture-notes.md)

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| None | N/A | N/A |
