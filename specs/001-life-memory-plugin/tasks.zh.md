# Tasks: Hermes 分层生活记忆插件

**Language Versions**: 中文主版本 `tasks.md` / `tasks.zh.md`; English version `tasks.en.md`

**Input**: 设计文档来自 `/Users/oliver/Projects/hermes-life-memory/specs/001-life-memory-plugin/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/life-memory-tools.md`, `quickstart.md`

**Tests**: specification 明确要求本地原型评估集和多类测试，因此每个用户故事都包含先写测试、再写实现的任务。

**Organization**: 任务按用户故事分组，方便每个增量独立实现、独立验证。

## 格式说明：`[ID] [P?] [Story] Description`

- **[P]**: 可以并行做，前提是所在阶段的前置任务已完成，且不会改同一个文件。
- **[Story]**: 对应 `spec.md` 中的用户故事，例如 `[US1]`。
- 每条任务都必须包含明确文件路径。

## Phase 1: Setup（共享基础准备）

**Purpose**: 建立插件包、pytest 配置和可重复运行的本地测试夹具。

- [x] T001 在 `pyproject.toml` 中创建 Python 项目和 pytest 配置
- [x] T002 [P] 在 `tests/conftest.py` 中创建临时 `HERMES_HOME` 和 handler 测试夹具
- [x] T003 [P] 在 `tests/fixtures/evaluation_cases.json` 中写入 classification、recall、temporal update、forget、abstention、sensitive rejection、memory-injection rejection 的本地评估用例
- [x] T004 在 `plugins/life_memory/plugin.yaml` 中填写 Hermes standalone plugin 元数据
- [x] T005 在 `plugins/life_memory/__init__.py` 中加入插件常量、延迟加载 runtime path helper 和 handler 占位函数

---

## Phase 2: Foundational（阻塞性基础设施）

**Purpose**: 建立共享类型、工具契约、安全 helper、SQLite schema、trace 基础设施和插件注册。这个阶段完成前，不应开始任何用户故事实现。

- [x] T006 [P] 在 `plugins/life_memory/models.py` 中实现 classification、lifecycle status、feedback、trace、reflection run、tool result 的 enum 和 dataclass
- [x] T007 [P] 在 `plugins/life_memory/time_utils.py` 中实现 timezone-aware timestamp、id、content hash、JSON encode/decode 和 clamp helper
- [x] T008 [P] 在 `plugins/life_memory/contracts.py` 中实现六个工具的 JSON schema 和通用 result builder
- [x] T009 [P] 在 `plugins/life_memory/safety.py` 中实现基础敏感内容检测和 prompt-injection 检测 primitive
- [x] T010 在 `plugins/life_memory/repository.py` 中实现 SQLite 连接、WAL、`schema_version`、全部 MVP tables 和可选 FTS5 创建/fallback
- [x] T011 在 `plugins/life_memory/repository.py` 中实现 repository transaction helper、row mapping、append-only trace 写入、memory evidence 写入和 memory link 写入
- [x] T012 [P] 在 `tests/contract/test_tool_contracts.py` 中加入通用 contract envelope 测试，覆盖 `ok`、`outcome`、`message`、`trace_id`
- [x] T013 [P] 在 `tests/unit/test_repository.py` 中加入 schema 创建、migration 幂等、trace 写入和 FTS fallback 测试
- [x] T014 [P] 在 `tests/integration/test_plugin_handlers.py` 中加入六个工具名的插件注册 smoke test
- [x] T015 在 `plugins/life_memory/__init__.py` 中用 `ctx.register_tool()` 注册 `life_memory_store`、`life_memory_recall`、`life_memory_feedback`、`life_memory_forget`、`life_memory_reflect`、`life_memory_export_review`

**Checkpoint**: 基础设施可用。测试中插件可以被发现，临时 `HERMES_HOME` 可以初始化数据库，通用 result envelope 可验证。

---

## Phase 3: User Story 1 - Classify Candidate Memory（优先级：P1）

**Goal**: 在保存前分类候选记忆，避免技术记忆、用户画像、临时上下文、抽象经验和 no-save 内容污染 life memory。

**Independent Test**: 运行 classification unit test 和 fixture test，覆盖 `technical_memory`、`life_memory`、`user_profile`、`temporary_working_memory`、`abstract_experience`、`no_save`。

### Tests for User Story 1

- [x] T016 [P] [US1] 在 `tests/unit/test_classification.py` 中编写边界分类测试，覆盖 technical memory、life memory、user profile、temporary context、no-save、repeated-pattern candidate
- [x] T017 [US1] 在 `tests/fixtures/evaluation_cases.json` 中补充 classification fixture cases 和 expected reasons

### Implementation for User Story 1

- [x] T018 [US1] 在 `plugins/life_memory/classification.py` 中实现确定性边界分类规则和 confidence reason
- [x] T019 [US1] 在 `plugins/life_memory/classification.py` 中实现 `personal_fact`、`personal_preference`、`personal_pattern` 的 `primary_category` 和 tags 建议规则
- [x] T020 [US1] 在 `plugins/life_memory/__init__.py` 中把 classification preflight 和 declined classification trace 接到 store 占位流程

**Checkpoint**: 候选记忆分类可以独立验证，不依赖 durable storage。

---

## Phase 4: User Story 2 - Store Life Memory（优先级：P1）

**Goal**: 保存符合条件的 L4 life memory，并记录 metadata、trace、sensitivity gate、`major_life_fact` 快速晋升和 `recent_state` TTL。

**Independent Test**: 调用 store handler 记住范围内生活事实、拒绝技术/no-save 内容、对敏感内容返回 `needs_confirmation`，并确认 accepted memory 持久化到临时 SQLite。

### Tests for User Story 2

- [x] T021 [P] [US2] 在 `tests/contract/test_tool_contracts.py` 中编写 `life_memory_store` schema、success、declined、`needs_confirmation` contract tests
- [x] T022 [P] [US2] 在 `tests/unit/test_repository.py` 中编写 memory insert、evidence insert、trace insert、source metadata、status default 的 repository tests
- [x] T023 [P] [US2] 在 `tests/unit/test_safety.py` 中编写 sensitive confirmation、restricted raw-content handling、memory-injection rejection 测试
- [x] T024 [P] [US2] 在 `tests/integration/test_plugin_handlers.py` 中编写 accepted life memory、rejected technical memory、sensitive confirmation、`major_life_fact`、`recent_state` TTL 的 store integration tests

### Implementation for User Story 2

- [x] T025 [US2] 在 `plugins/life_memory/repository.py` 中实现创建 memory、evidence、status metadata、promotion metadata、validity window 和 declined-store trace 的 repository methods
- [x] T026 [US2] 在 `plugins/life_memory/__init__.py` 中实现 durable `life_memory_store` 流程，包括 classification、safety gates、duplicate precheck、trace writes 和 JSON output
- [x] T027 [US2] 在 `plugins/life_memory/safety.py` 中实现 `needs_confirmation`、confirmation-first sensitive storage handling 和 injection-risk rejection decisions
- [x] T028 [US2] 在 `plugins/life_memory/__init__.py` 中实现 `major_life_fact` 快速晋升和 `recent_state` 14 天 TTL assignment

**Checkpoint**: 符合条件的生活记忆可以保存并在 SQLite 中检查；不安全、技术类、未授权敏感候选不会被 durable store。

---

## Phase 5: User Story 3 - Recall Relevant Life Memory（优先级：P1）

**Goal**: 召回有界、相关的 life memory，同时排除 deleted、expired、默认 archived、无关、技术类和未授权敏感记忆。

**Independent Test**: 保存多条记忆后，用定向和宽泛 query 召回，验证排序、有界结果、access 更新、abstention 和低权重 `young` 处理。

### Tests for User Story 3

- [x] T029 [P] [US3] 在 `tests/contract/test_tool_contracts.py` 中编写 `life_memory_recall` contract tests，覆盖 success、`not_found`、limit bounds、sensitivity flags 和 result shape
- [x] T030 [P] [US3] 在 `tests/unit/test_recall.py` 中编写 recall scoring、filtering、`young` cap、archived exclusion、expired `recent_state` exclusion、injection-as-data tests
- [x] T031 [P] [US3] 在 `tests/integration/test_plugin_handlers.py` 中编写 targeted recall、broad abstention、access count updates、no unrelated memories 的 recall integration tests

### Implementation for User Story 3

- [x] T032 [US3] 在 `plugins/life_memory/repository.py` 中实现 repository search、FTS/LIKE fallback、sensitivity filters、status filters 和 access-update methods
- [x] T033 [US3] 在 `plugins/life_memory/recall.py` 中实现确定性 recall scoring、有界排序、`young` multiplier 和 relevance reasons
- [x] T034 [US3] 在 `plugins/life_memory/recall.py` 中实现 memory-injection-as-data handling 和 sensitive/restricted recall filtering
- [x] T035 [US3] 在 `plugins/life_memory/__init__.py` 中实现 `life_memory_recall` handler output，包括 references、relevance reasons 和 trace writes

**Checkpoint**: 最小 MVP 可用：classification、store、recall 能串起来，并返回有界、可解释的结果。

---

## Phase 6: User Story 4 - Correct And Forget Memory（优先级：P2）

**Goal**: 允许用户纠正、替代、标记过期、强化、合并或遗忘记忆，同时避免静默覆盖和误删多条记忆。

**Independent Test**: 保存一条记忆，应用 feedback 或 deletion，再验证未来 recall 和 repository 状态反映 correction、tombstone 或 ambiguity result。

### Tests for User Story 4

- [x] T036 [P] [US4] 在 `tests/contract/test_tool_contracts.py` 中编写 `life_memory_feedback` 和 `life_memory_forget` contract tests，覆盖 useful、wrong、outdated、important、duplicate、delete、merge、`ambiguous`、`not_found` outcomes
- [x] T037 [P] [US4] 在 `tests/unit/test_repository.py` 中编写 feedback rows、supersede links、mirrored links、tombstone redaction、deleted-content exclusion 的 repository tests
- [x] T038 [P] [US4] 在 `tests/integration/test_plugin_handlers.py` 中编写 correction replacement、outdated demotion、forget by id、forget-by-query ambiguity、deleted memory recall exclusion integration tests

### Implementation for User Story 4

- [x] T039 [US4] 在 `plugins/life_memory/repository.py` 中实现 feedback、feedback-score、supersede、conflict、duplicate、merge helpers
- [x] T040 [US4] 在 `plugins/life_memory/repository.py` 中实现 tombstone/redaction deletion semantics：保留 id/hash/status，同时移除普通可召回内容
- [x] T041 [US4] 在 `plugins/life_memory/__init__.py` 中实现 `life_memory_feedback` handler，覆盖 replacement、supersede、merge、duplicate、important、useful、wrong、outdated 和 delete delegation
- [x] T042 [US4] 在 `plugins/life_memory/__init__.py` 中实现 `life_memory_forget` handler，覆盖 id deletion、query candidate lookup、confirmation requirement、ambiguity handling 和 trace writes
- [x] T043 [US4] 在 `plugins/life_memory/recall.py` 中把 feedback score、status、supersede、deleted-memory effects 应用到 recall ranking 和 filtering

**Checkpoint**: 用户可以纠正和遗忘记忆，正常召回不会继续把 deleted 或 superseded facts 当作当前事实。

---

## Phase 7: User Story 6 - Export Human Review Markdown（优先级：P2）

**Goal**: 导出只读 Markdown review view，让用户能检查已确认记忆、不确定记忆、journal reports、archive entries 和 change request template。

**Independent Test**: 填充临时数据库，运行 `life_memory_export_review`，验证预期文件和脱敏行为，并确认 memory status 和 promotion score 不发生变化。

### Tests for User Story 6

- [x] T044 [P] [US6] 在 `tests/contract/test_tool_contracts.py` 中编写 `life_memory_export_review` contract tests，覆盖 default target、archive flag、sensitive export mode、file list 和 read-only outcome
- [x] T045 [P] [US6] 在 `tests/integration/test_export_review.py` 中编写 Markdown export integration tests，覆盖 `README.md`、`memory-journal/`、`memory-library/facts.md`、`memory-library/preferences.md`、`memory-library/patterns.md`、`review-needed.md`、`change-requests.md`、optional `archive.md` 和 sensitive redaction

### Implementation for User Story 6

- [x] T046 [US6] 在 `plugins/life_memory/repository.py` 中实现 read-only export queries，覆盖 active、reinforced、pattern_candidate、needs_review、archived、session report、daily report rows
- [x] T047 [US6] 在 `plugins/life_memory/export_review.py` 中实现 Markdown rendering、用户可理解标签、section ordering、sensitive omission/summary-only behavior 和 `change-requests.md` template output
- [x] T048 [US6] 在 `plugins/life_memory/__init__.py` 中实现 `life_memory_export_review` handler，使用默认 `$HERMES_HOME/life_memory_review` target，返回 file list，并且不做 reverse sync
- [x] T049 [US6] 在 `plugins/life_memory/repository.py` 中加入 export trace writing，确保不修改 status、promotion score 或 content

**Checkpoint**: 用户可以通过可读 Markdown 检查插件记住了什么，但不会通过 Markdown 直接编辑 SQLite。

---

## Phase 8: User Story 5 - Reflect And Maintain Memory Quality（优先级：P3）

**Goal**: 运行 background memory maintenance，处理 session extraction、light cleanup、duplicate candidates、`recent_state` expiry、pattern promotion 和 report-only daily reflection。

**Independent Test**: 创建 duplicate、stale、expired、session、repeated-pattern memories，然后运行 dry-run 和 apply reflection modes，验证 proposed/applied 状态变化。

### Tests for User Story 5

- [x] T050 [P] [US5] 在 `tests/unit/test_session_adapter.py` 中编写 session adapter tests，覆盖 read-only session lookup、unavailable session handling、transcript fallback
- [x] T051 [P] [US5] 在 `tests/unit/test_reflection.py` 中编写 reflection unit tests，覆盖 dry-run、light dedupe candidates、`recent_state` archive、session extraction candidates、deep pattern promotion、daily report-only behavior
- [x] T052 [P] [US5] 在 `tests/integration/test_plugin_handlers.py` 中编写 `life_memory_reflect` integration tests，覆盖 `session`、`light`、`rem`、`deep`、`daily`、`apply=false`、`apply=true` 和 no-fabrication failure cases

### Implementation for User Story 5

- [x] T053 [US5] 在 `plugins/life_memory/session_adapter.py` 中实现 read-only Hermes session/state adapter，覆盖 session-ref resolution、transcript normalization 和 unavailable-state errors
- [x] T054 [US5] 在 `plugins/life_memory/repository.py` 中实现 reflection runs、reflection reports、candidate links、applied counts 和 report paths 的 repository helpers
- [x] T055 [US5] 在 `plugins/life_memory/reflection.py` 中实现 `light` reflection，覆盖 duplicate candidates、evidence accounting、低成本 tag cleanup 和 expired `recent_state` archive
- [x] T056 [US5] 在 `plugins/life_memory/reflection.py` 中实现 `session` reflection，从 session refs 或 explicit transcripts 抽取 effective-memory，同时复用 classification 和 safety gates
- [x] T057 [US5] 在 `plugins/life_memory/reflection.py` 中实现 `rem` 和 `deep` reflection，覆盖 conflict candidates、pattern candidates、带 supporting memory ids 的低风险 `abstract_experience` promotion 和 conservative apply gates
- [x] T058 [US5] 在 `plugins/life_memory/reflection.py` 中实现 `daily` reflection report-only output，确保它只创建 reports，不创建 durable facts，也不改变 `promotion_score`
- [x] T059 [US5] 在 `plugins/life_memory/__init__.py` 中实现 `life_memory_reflect` handler，覆盖 mode dispatch、dry-run/apply behavior、trace writes 和 JSON output

**Checkpoint**: Reflection 可以整理记忆库，但不会把 daily summaries 或弱猜测变成 durable facts。

---

## Phase 9: Polish & Cross-Cutting Concerns（收尾与横切验证）

**Purpose**: 验证垂直切片、补本文档、加固跨故事行为。

- [x] T060 在 `tests/integration/test_plugin_handlers.py` 中加入 10,000-row store/recall performance smoke coverage 和 bounded result assertions
- [x] T061 [P] 在 `README.md` 中更新 repository overview、mount instructions、enable instructions、test command 和 review-export command
- [x] T062 根据实际实现验证 `quickstart.md`，并在 `specs/001-life-memory-plugin/quickstart.md` 中记录剩余 caveats
- [x] T063 运行 `python -m pytest`，并在 `README.md` 中记录 validation result
- [x] T064 确认没有修改 Hermes main project files，并在 `README.md` 中记录允许修改的路径范围

---

## Phase 10: Runtime Memory Routing（运行时记忆路由）

**Purpose**: 不修改 Hermes core，通过用户插件把默认记忆写入按 L2/L3/L4 分层路由。

- [x] T065 在 `plugins/life_memory/routing.py` 中实现 memory route decision，复用 classification 将 L4 生活记忆路由到 `life_memory_store`，将 L2 技术/项目记忆路由到原生 `memory`，将 L3 用户画像路由到原生 `USER.md`
- [x] T066 在 `plugins/life_memory/routing.py` 和 `plugins/life_memory/__init__.py` 中安装软提示：patch 原生 `memory`/holographic schema 描述，并注册 `pre_llm_call` 分层路由提醒
- [x] T067 在 `plugins/life_memory/routing.py` 中包装 Hermes `tools.memory_tool.memory_tool()`，使误用原生 `memory` 保存 L4 时自动转交 `life_memory_store`
- [x] T068 在 `plugins/life_memory/routing.py` 中过滤 `MemoryManager.on_memory_write` mirror 和 holographic `auto_extract`，避免生活记忆双写入 `memory_store.db`
- [x] T069 在 `tests/unit/test_routing.py` 和 `tests/unit/test_classification.py` 中覆盖生活、技术、用户画像、临时状态四类路由，并运行全量测试

---

## Dependencies & Execution Order（依赖与执行顺序）

### Phase Dependencies

- **Phase 1 Setup**: 无依赖。
- **Phase 2 Foundational**: 依赖 Phase 1，并阻塞所有用户故事。
- **Phase 3 US1**: 依赖 Phase 2。
- **Phase 4 US2**: 依赖 Phase 2，并使用 US1 classification。
- **Phase 5 US3**: 依赖 US2 persisted memories。
- **Phase 6 US4**: 依赖 US2 storage 和 US3 recall behavior。
- **Phase 7 US6**: 依赖 Phase 2 和 repository data；在 US2 产生真实 memories 后最容易验证。
- **Phase 8 US5**: 依赖 US2/US3，也可利用 US4 的 conflict/supersede behavior。
- **Phase 9 Polish**: 依赖已选择实现的用户故事。
- **Phase 10 Runtime Routing**: 依赖 Phase 3/4 classification 和 store handler；保持不修改 Hermes core。

### User Story Dependency Graph

```text
Foundation
  └── US1 Classify
        └── US2 Store
              ├── US3 Recall
              │     └── US4 Feedback/Forget
              │           └── US5 Reflect
              ├── US6 Export Review
              └── Runtime Memory Routing
```

### MVP Scope

实际可验证的 MVP 是 **US1 + US2 + US3**：

1. 正确分类候选记忆。
2. 把符合条件的生活记忆保存到 SQLite。
3. 用有界、可解释的结果召回相关记忆。

`US4` 和 `US6` 建议紧随其后，因为“能忘掉”和“能看懂系统记住了什么”对长期记忆插件的可信度很关键。`US5` 可以在核心闭环稳定后实现。

---

## Parallel Execution Examples（并行示例）

### Foundation

```text
T006 models.py
T007 time_utils.py
T008 contracts.py
T009 safety.py
T012 contract tests
T013 repository tests
T014 integration smoke tests
```

### User Story 1

```text
T016 tests/unit/test_classification.py
T017 tests/fixtures/evaluation_cases.json
```

### User Story 2

```text
T021 tests/contract/test_tool_contracts.py
T022 tests/unit/test_repository.py
T023 tests/unit/test_safety.py
T024 tests/integration/test_plugin_handlers.py
```

### User Story 3

```text
T029 tests/contract/test_tool_contracts.py
T030 tests/unit/test_recall.py
T031 tests/integration/test_plugin_handlers.py
```

### User Story 4

```text
T036 tests/contract/test_tool_contracts.py
T037 tests/unit/test_repository.py
T038 tests/integration/test_plugin_handlers.py
```

### User Story 6

```text
T044 tests/contract/test_tool_contracts.py
T045 tests/integration/test_export_review.py
```

### User Story 5

```text
T050 tests/unit/test_session_adapter.py
T051 tests/unit/test_reflection.py
T052 tests/integration/test_plugin_handlers.py
```

---

## Implementation Strategy（实现策略）

### MVP First

1. 完成 Phase 1 和 Phase 2。
2. 完成 US1、US2、US3。
3. 运行 classification、store、recall、repository、safety、contract、integration 相关测试。
4. 停下来验证端到端原型，再继续 correction、export 和 reflection。

### Incremental Delivery

1. Foundation ready。
2. US1 classify。
3. US2 store。
4. US3 recall。
5. US4 feedback/forget。
6. US6 export review。
7. US5 reflection。
8. Polish and full quickstart validation。
9. Runtime memory routing for Hermes default memory writes。

### Notes

- 同一用户故事中，应先写 tests，再写 implementation。
- `[P]` 任务只有在不改同一文件、且前置任务完成后才适合并行。
- 不要修改 `/Users/oliver/.hermes/hermes-agent` 或 `/Users/oliver/Projects/hermes-workspace/hermes-agent`。
- Runtime data 必须留在 `$HERMES_HOME` 下；测试必须使用临时 `HERMES_HOME`。
- MVP 中 Markdown export 是只读视图，不实现 Markdown-to-SQLite reverse sync。
