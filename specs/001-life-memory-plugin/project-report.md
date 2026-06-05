# Hermes 分层生活记忆插件项目报告

**项目名称**：Hermes Life Memory Plugin
**项目类型**：面向个人 AI agent 的长期记忆插件原型
**当前状态**：001 基础闭环完成，002 自动激活和 003 hybrid recall 已补齐
**最近验证**：2026-06-06 Australia/Sydney，`uv run python -m pytest`，137 项测试全部通过

## 1. 项目背景

Hermes 原本已有记忆能力，但不同类型的记忆容易混在一起。例如技术项目配置、用户回答偏好、临时任务上下文和个人生活习惯，如果都进入同一个记忆系统，后续会出现三个问题：

1. 召回时容易拿到无关或过期信息。
2. 用户难以检查系统到底记住了什么。
3. 敏感生活信息和技术项目记忆边界不清，增加误存和误用风险。

本项目的目标是为 Hermes 增加一个独立的 `life_memory` 用户插件，专门管理个人生活记忆，同时让技术/项目记忆继续留在 Hermes 原生记忆系统中。项目强调本地运行、结构化存储、可解释分类、可删除、可审计和不修改 Hermes 主程序源码。

## 2. 解决的问题

本项目重点解决“AI agent 应该如何长期记住个人生活信息”的工程问题。具体包括：

- 哪些内容值得长期保存；
- 一条候选信息应该进入生活记忆、技术记忆、用户画像，还是不保存；
- 生活记忆如何保存、召回、纠错、遗忘；
- 敏感信息如何确认和保护；
- 如何让用户用普通 Markdown 文件检查系统记住了什么；
- 如何在不改 Hermes 源码的情况下，把默认记忆写入按类型分流。

因此，这不是简单地把聊天记录写进数据库，而是实现了一个带有分类、状态、审计和安全边界的生活记忆管理系统。

## 3. 总体设计

项目采用分层记忆模型：

- **L2 技术/项目记忆**：代码结构、依赖、调试、运行环境等，保留在 Hermes 原生记忆中。
- **L3 用户画像记忆**：语言偏好、回答风格、长期职业目标等，进入 Hermes 原生用户画像路径。
- **L4 生活记忆**：生活习惯、饮食偏好、关系、日常模式、生活事件等，进入本插件的 `life_memory.db`。
- **临时上下文和 no-save 内容**：默认不长期保存。

插件采用 SQLite 作为运行时事实源，Markdown 只作为人工审计导出视图。这样既方便自动化运行，也能让用户查看和纠错。

核心工具包括：

- `life_memory_store`：保存生活记忆；
- `life_memory_recall`：召回相关生活记忆；
- `life_memory_feedback`：记录有用、错误、过期、重复等反馈；
- `life_memory_forget`：软删除和遗忘；
- `life_memory_reflect`：后台整理、去重、晋升、归档和报告；
- `life_memory_export_review`：导出只读 Markdown 审查文件。

此外，插件还注册了 `pre_llm_call` hook，并通过运行时 patch 的方式改写 Hermes 默认记忆路径的行为提示和部分写入逻辑，实现不改源码的记忆分流。

## 4. 已完成的主要功能

### 4.1 候选记忆分类

系统会先判断候选内容属于哪一类，而不是直接保存。当前可以区分：

- 技术/项目记忆；
- 用户画像记忆；
- 生活记忆；
- 临时任务上下文；
- 抽象经验候选；
- 不应保存的闲聊、短期情绪或不确定内容。

实现上采用 rule-first 的确定性分类，优点是可解释、可测试、行为稳定。中文日常表达也做了覆盖，例如饮食偏好、周末习惯、运动习惯、长期目标等。

### 4.2 生活记忆保存

符合条件的生活记忆会写入本地 SQLite 数据库 `$HERMES_HOME/life_memory.db`，并记录结构化元数据，包括：

- `memory_id`
- 内容
- 主分类和标签
- 重要度、置信度、分类置信度
- 生命周期状态
- 敏感性等级
- 来源和时间
- trace 审计记录

系统支持 `young -> active -> reinforced -> pattern_candidate` 等生命周期状态。重大且稳定的生活事实可以在严格条件下快速从 `young` 晋升为 `active`，短期状态则使用 `recent_state` 14 天 TTL，避免“最近很累”变成永久画像。

### 4.3 召回机制

当前召回已经从早期可解释词面召回，升级为 lexical + semantic hybrid recall。核心包括：

- 英文 token 匹配；
- 中文 CJK n-gram；
- 派生 `memory_embeddings` 语义索引；
- lexical/vector candidate merge；
- time-aware rerank；
- 标签和主分类参与搜索；
- importance、confidence、feedback score、evidence count 等参与排序；
- `young` 记忆降权且每次最多返回 2 条；
- `deleted`、过期、默认 archived、未授权 sensitive/restricted 记忆不参与普通召回；
- 含 prompt injection 风险的内容只作为普通数据，不作为指令。

项目中专门补了中文日常问法和 paraphrase 召回能力，例如用户用中文问“我运动完一般喝什么”，可以召回“周六下午慢跑后通常买无糖豆浆”这类不完全词面重合的生活习惯。

### 4.4 纠错、反馈和遗忘

系统支持用户对记忆进行维护：

- 标记有用或重要，提高后续优先级；
- 标记错误或过期，替换或归档旧记忆；
- 标记重复或合并；
- 按 memory_id 精确遗忘；
- 按查询遗忘时如果命中多条，返回 ambiguous，不静默误删。

遗忘采用软删除机制：普通召回不再返回内容，但保留 tombstone、hash 和 trace，便于审计系统发生过什么。

### 4.5 Markdown 人工审查导出

系统可以把 SQLite 中的记忆导出到 `$HERMES_HOME/life_memory_review`，生成普通用户可读的 Markdown 文件，例如：

- `memory-library/facts.md`
- `memory-library/preferences.md`
- `memory-library/patterns.md`
- `review-needed.md`
- `archive.md`
- `change-requests.md`

导出是只读的，不会反向修改数据库。敏感内容默认只导出摘要或元信息，不导出原文。

### 4.6 后台 reflection

插件实现了基础后台整理流程：

- `session`：从会话或显式 transcript 中抽取有效候选记忆；
- `light`：低成本整理、去重、过期 recent_state 归档；
- `rem`：发现冲突、重复和模式候选；
- `deep`：在低风险条件下进行保守晋升；
- `daily`：生成审计报告，但不把 daily report 当作事实源。

该部分目前是规则驱动，不依赖外部大模型，重点是先保证可测试和可控。

### 4.7 不改 Hermes 源码的运行时路由

项目实现了运行时记忆路由：

- L4 生活记忆进入 `life_memory_store`；
- L2 技术/项目记忆继续进入 Hermes 原生 memory；
- L3 用户画像进入 Hermes 原生 user profile；
- 临时状态和 no-save 内容直接拒绝。

实现方式是用户插件运行时 patch Hermes 已导入对象、memory tool schema、memory tool 调用、MemoryManager mirror 和 holographic provider 行为。这样可以实现记忆分流，同时避免直接修改 Hermes 主程序源码，降低后续更新 Hermes 时的冲突风险。

### 4.8 自动记忆激活和上下文注入

`002-memory-activation` 已经实现回答前自动判断是否需要生活记忆：

- 技术、项目、临时任务、用户画像和泛泛闲聊默认不触发生活记忆；
- 明确生活习惯、关系、偏好、日常模式等问题会触发 recall；
- 注入内容是 bounded data-only memory block；
- 注入条目带 `memory_id`、status、confidence、sensitivity 和 relevance reason；
- deleted、archived、expired、restricted、未授权 sensitive、superseded、低置信和高 injection-risk 记忆不会自动注入；
- hook payload 异常或 storage 不可用时 fail closed，只保留 routing guidance。

### 4.9 Hybrid Recall

`003-hybrid-recall` 已经实现 hybrid lexical/vector candidate retrieval 和可解释 rerank：

- SQLite `life_memories` 仍是事实源；
- `memory_embeddings` 是可重建的派生索引；
- 当前默认使用 deterministic local fake embedding provider，测试不依赖网络或外部模型；
- stale、incompatible、missing embedding 不参与 active semantic search；
- 召回结果包含 score components 和 recall sources；
- automatic activation 可以使用 hybrid recall，但仍执行 stricter-than-recall injection filter。

## 5. 安全和隐私设计

本项目是个人本地 agent 场景，因此不是简单拒绝所有敏感信息，而是采用 confirmation-first 策略：

- 未明确授权的敏感生活信息返回 `needs_confirmation`，不创建 durable memory；
- 用户可以选择不保存、保存摘要或完整保存；
- 精确地址等内容如果用户明确选择完整保存，可以保存在 SQLite 中，但必须标记为 sensitive；
- 普通召回和 Markdown 导出仍然默认保守，不泄露 sensitive/restricted 原文；
- 密码、API key、seed phrase 等 restricted 内容不允许原文保存；
- prompt injection 类内容会被拒绝或只作为普通数据处理。

这使系统既能服务个人真实使用场景，又保留安全边界。

## 6. 测试和验证情况

项目采用测试先行的方式，覆盖合同测试、单元测试、集成测试、拟真流程测试和性能 smoke 测试。

当前测试结果：

```text
2026-06-06 Australia/Sydney
uv run python -m pytest
137 passed in 0.75s
Python 3.11.15, pytest 9.0.3
```

测试覆盖内容包括：

- 六个工具的 JSON schema 和返回 envelope；
- 分类边界：技术、生活、用户画像、临时上下文、no-save；
- 保存流程、敏感信息确认、prompt injection 拒绝；
- 召回排序、过滤、young 降权、中文 CJK 召回；
- 反馈、纠错、替换、遗忘、软删除；
- Markdown 导出和敏感内容脱敏；
- session adapter 和 reflection 各阶段；
- automatic memory activation、safe context injection 和 activation trace；
- embedding provider、derived semantic index、hybrid recall 和 time-aware rerank；
- 10,000 条记忆下的 store/recall 性能 smoke；
- runtime routing 对 L2/L3/L4 的分流测试。

除自动化测试外，也做过黑盒验证：在不限制 Hermes toolset 的正常 `hermes -z` 模式下，让 Hermes 记住中文生活偏好 marker，结果写入 `life_memory.db`，没有写入 `memory_store.db`、`MEMORY.md` 或 `USER.md`。003 阶段还验证了 smoke memory 被写入、indexed 到 `memory_embeddings`、通过 paraphrased 中文问题自动激活召回，并在测试后 soft delete 清理。

## 7. 当前做到的水平

从工程完成度看，项目已经超过最小 MVP，达到 **本地单用户可运行原型** 水平：

- 有完整插件结构，可以被 Hermes 作为 standalone user plugin 挂载；
- 有完整 SQLite schema 和 repository 层；
- 有六个明确工具接口；
- 有分类、保存、召回、纠错、遗忘、导出、reflection 和路由闭环；
- 有回答前 automatic activation 和 bounded data-only context injection；
- 有 hybrid recall、派生 semantic index 和 time-aware rerank；
- 有较完整的自动化测试和拟真测试；
- 不依赖修改 Hermes 源码；
- 个人数据库没有进入 Git 仓库；
- 文档、quickstart、任务清单和架构说明基本对齐。

但它还不是生产级长期记忆系统。当前更准确的定位是：

> 一个可运行、可测试、可审计的生活记忆插件原型，已经验证了分层记忆、结构化状态管理和不改源码运行时路由的可行性。

## 8. 当前局限

当前主要局限有：

1. **Embedding provider 仍是本地 deterministic fake 实现**
   003 已经验证 hybrid recall 架构和派生索引，但还没有接入真实本地 embedding 模型或外部 embedding API。

2. **AI 尚未参与边界判断**
   分类和召回目前是确定性规则。好处是稳定可解释，缺点是复杂语义边界仍可能判断不够细。

3. **尚未实现全库后台自动 reindex 调度**
   当前 semantic index 可写入、检测和重建，但还没有独立后台 scheduler 做周期性全库维护。

4. **运行时路由依赖 Hermes 内部模块名**
   插件不改 Hermes 源码，但 patch 了 Hermes 内部对象。如果 Hermes 后续升级内部结构，需要重新跑 routing 测试和一次黑盒验证。

5. **Markdown 仍是只读审查视图**
   用户不能直接编辑 Markdown 并自动同步回 SQLite。这样更安全，但交互便利性还可以继续提升。

## 9. 下一步工作建议

下一阶段最值得做的是 **Review Sync And Change Requests**，即“审查修改同步机制”。

目标是让系统不只是能导出 Markdown 审查视图，而是能安全处理用户在 `change-requests.md` 或等价入口中表达的修改意图：

- 删除某条记忆；
- 修正或替换某条记忆；
- 合并重复记忆；
- 确认低置信或敏感候选；
- 拒绝错误候选；
- 把人工审查意见写回 SQLite trace，而不是静默改库。

建议实现顺序：

1. 先定义 `change-requests.md` 的受限语法和 schema，不解析任意自然语言自由修改。
2. 实现 dry-run parser，输出将要执行的 delete/replace/merge/confirm 操作和风险提示。
3. 复用现有 `life_memory_feedback`、`life_memory_forget` 和 trace API apply 变更。
4. 对敏感、restricted、ambiguous、多命中和 supersession 场景强制人工确认。
5. 保持 Markdown reverse sync 默认关闭，只在用户显式运行同步工具时执行。

## 10. 总结

本项目已经完成了 Hermes 个人生活记忆插件的主要工程闭环。它不是简单的聊天记录存储，而是一个具有分层分类、结构化数据库、生命周期管理、敏感信息保护、可解释召回、反馈遗忘、Markdown 审查和运行时路由能力的本地长期记忆系统。

当前成果已经可以支撑导师层面的阶段性验收：项目目标清晰，架构边界明确，代码模块完整，测试覆盖较充分，真实 Hermes 场景下的写入路由、自动激活和 hybrid recall 都已经通过验证。后续重点应从“系统如何自动记住和使用记忆”转向“用户如何高信任地审查、修正和治理记忆库”。
