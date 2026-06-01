# Feature Specification: Hermes 分层生活记忆插件

**Language Versions**: 中文主版本 `spec.md` / `spec.zh.md`; English version `spec.en.md`

**Feature Branch**: `001-life-memory-plugin`

**Created**: 2026-06-01

**Status**: Draft

**Input**: 用户描述：“为 Hermes 构建分层记忆系统，区分技术项目记忆、生活记忆、用户画像记忆和抽象经验记忆。`life_memory` 部分要作为 Hermes standalone plugin 实现，不要做成 memory provider，也不要修改 Hermes core。”

## Overview（概览）

本功能为 Hermes 引入一个分层长期记忆模型，让不同类型的记忆保持清晰、可检索、可控制。Hermes 现有记忆继续主要承担技术和项目相关信息。新的 `life_memory` 插件负责管理持久的个人生活上下文，例如日常规律、习惯、人际关系、非技术偏好、重要生活事件，以及反复出现的个人模式。

本功能的目标是：在存储前先对候选记忆进行分类，从而减少记忆污染，避免过度记录，并提升后续召回的可靠性。

## Problem Statement（问题陈述）

Hermes 已经有多种记忆机制，但技术项目记忆、生活记忆、用户画像偏好、临时对话细节和抽象经验之间的边界可能变得不清晰。当这些领域混在一起时，记忆会更难检查、更难纠正，也更容易召回无关或过期的信息。

用户需要一个分层系统，能判断一条候选记忆应该属于生活记忆、技术记忆、用户画像记忆、临时工作上下文、抽象经验，还是根本不应该保存。

## Goals（目标）

- 将生活记忆与 Hermes 的技术/项目记忆分离。
- 提供清晰的分类规则，用来判断什么信息应该保存、应该保存到哪里。
- 保存个人生活记忆时记录结构化元数据，例如 `primary_category`、`tags`、importance、confidence、classification_confidence、source、timestamps、status、promotion_path 和 trace。
- 召回相关生活记忆，同时避免注入无关记忆或技术记忆。
- 允许用户纠正、标记过期、强化、合并、归档或遗忘记忆。
- 通过基础 reflection 维护记忆质量，包括 deduplication、merging、`recent_state` TTL、archiving 和基于重复证据的 pattern generation。
- 提供只读 Markdown review/export，让用户能查看已确认记忆、会话提取摘要、daily report、待复核项和归档项。
- 默认避免保存琐碎、不确定、临时或敏感信息；敏感信息必须先请求明确长期保存授权。
- 用一个小而可验证的原型验证现代 agent memory 的 `write -> manage -> read` 循环：selective write、structured metadata、scoped retrieval、update/forget、lightweight reflection 和 audit trace。

## Non-Goals（非目标）

- MVP 不实现 standalone MCP server。
- MVP 不要求 PostgreSQL、pgvector、多模态记忆或知识图谱记忆。
- MVP 不做缺少用户可见控制的复杂 autonomous LLM-based reflection。
- MVP 不替换 Hermes 现有记忆系统。
- MVP 不修改 Hermes core 源码。
- MVP 不把插件安装或开发在 Hermes bundled `hermes-agent/plugins` 目录里。
- MVP 不把 `hermes-agent` 当作 PyCharm 中用于插件安装的 workspace folder；workspace folder 应该是上层 Hermes home 目录 `.hermes`。
- MVP 不引入单独的 memory-router plugin。
- MVP 不实现完整 Agent Memory OS；project memory、skill promotion、跨工具共享和多 agent 共享记忆都属于未来范围。
- MVP 不把 daily report / daily memory 当作事实源，也不让它改变 `promotion_score`；第一版 daily report 只作为 report-only audit artifact。
- MVP 不训练 learned memory policy，也不让模型自动决定所有长期记忆治理动作；原型阶段优先使用可检查的规则、显式用户操作和轻量 reflection。

## Conceptual Memory Layers（概念记忆分层）

- **L0: Conversation Context（对话上下文）**：只存在于当前对话中的短期细节，例如用户刚刚提出的问题、临时澄清、一次性讨论细节。这些内容不应该永久保存。
- **L1: Temporary Working Memory（临时工作记忆）**：与当前任务相关、可能很快过期的上下文，例如“用户正在设计 Hermes life-memory plugin”。MVP 默认不把它保存进生活记忆。
- **L2: Technical Project Memory（技术项目记忆）**：技术、学术、项目和工程相关信息，例如代码结构、调试历史、SSH 配置、Hermes/OpenClaw 设置、课程进度、实验结果、工具链配置。这些内容不能由 life-memory 插件保存。
- **L3: User Profile Memory（用户画像记忆）**：稳定身份和全局长期偏好，例如用户姓名、语言偏好、写作风格偏好、长期学术或职业目标、稳定回答格式要求。life-memory 插件可以识别这类内容，但不应把它当作普通生活记忆保存。
- **L4: Life Event Memory（生活事件记忆）**：个人非技术生活上下文、作息、习惯、人际关系、重要生活事件、生活方式偏好和日常模式。这是 life-memory 插件的主要职责。
- **L5: Abstract Experience Memory（抽象经验记忆）**：从重复事件或重复行为中推断出的更高层模式。不能从一条随口消息创建，只有在有足够证据时才可以保存。

## Research-Informed Prototype Scope（研究启发的原型范围）

近期 agent memory 研究更强调记忆的 `write -> manage -> read` 闭环，而不是只把历史塞进 RAG 或向量库。这个原型采用保守垂直切片：写入前分类和筛选，写入后保留结构化元数据和审计痕迹，读取时按作用域、状态、敏感性和相关性过滤。

MVP 只验证 `life_memory` 这一层是否真的改善 Hermes 的个人生活连续性。它不尝试一次性实现完整 Memory OS，而是先验证六个问题：什么值得写入、如何更新旧记忆、如何避免错误召回、如何让用户删除/修正、如何从重复证据中形成有限的抽象经验、如何让用户用 Markdown 审查系统到底记住了什么。

原型需要吸收 A-MEM 和 Mem0 类工作的实际经验：记忆条目不应只是文本片段，而应包含 `primary_category`、tags、context、source、confidence、links 和 trace；同时也要吸收 LongMemEval/LoCoMo 的评估启发，测试 extraction、multi-session recall、temporal update、forget 和 abstention。

安全上，原型默认采用 local-first 和 user-controlled 设计。记忆内容在读取时只能作为数据使用，不能被当作新的系统指令；敏感信息、潜在 prompt injection 内容和来源不明的记忆不能自动晋升或自动注入。

## Lifecycle Status Model（生命周期状态模型）

MVP 使用以下生命周期状态，而不是一开始实现完整分代 Memory OS：

- **`young`**：新保存的生活记忆，尚未经过复用或用户确认。
- **`active`**：正常可召回记忆，已经通过基础分类和边界检查。
- **`reinforced`**：被用户确认、重复召回有用，或在多个场景中证明稳定的记忆。
- **`pattern_candidate`**：多条证据显示可能存在生活模式，但还不足以形成 `abstract_experience`。
- **`archived`**：低价值、过期、很少使用或被 reflection 降权的记忆；默认不参与普通召回。
- **`deleted`**：用户要求遗忘或明确删除的记忆；正常 recall 和 reflection 都不得使用。

状态变化必须可追踪。自动 reflection 可以建议状态变化；低风险 `pattern_candidate -> abstract_experience` 可以在 `apply=true` 且阈值满足时自动晋升。涉及敏感内容、冲突内容或高风险合并时，应优先保守处理，并在需要时要求用户确认。

`young` 记忆可以低权重参与 recall，但必须受限：默认 score multiplier 为 `0.50`，每次最多返回 2 条，不得包含 sensitive/restricted 内容，也不能作为行动边界依据。对人生影响重大且稳定的 `major_life_fact` 可以在严格条件满足时从 `young` 快速晋升为 `active`，但不能直接晋升为 `reinforced`、`personal_pattern` 或 `abstract_experience`。

## User Scenarios & Testing *(mandatory)*（用户场景与测试）

### User Story 1 - Classify Candidate Memory（优先级：P1）

作为 Hermes 用户，我希望 Hermes 在保存前先分类候选记忆，这样技术细节、用户画像偏好、临时上下文和生活记忆不会互相污染。

**Why this priority（为什么是这个优先级）**：分类是所有存储、召回、反馈、遗忘和 reflection 行为的入口。

**Independent Test（独立测试）**：提交覆盖每个记忆层的代表输入，并验证输出分类是否符合预期。

**Acceptance Scenarios（验收场景）**：

1. **Given** 用户说“My Hermes runs on Mac, and Windows is connected through SSH”，**When** 对候选记忆分类，**Then** 结果是 `technical_memory`，并且不保存到生活记忆。
2. **Given** 用户说“Remember that I prefer to work late at night and usually think better after midnight”，**When** 对候选记忆分类，**Then** 结果是 `life_memory`，并且可以保存到生活记忆。
3. **Given** 用户说“From now on, when you generate English content for me, include Chinese translation below”，**When** 对候选记忆分类，**Then** 结果是 `user_profile`，并且不作为普通生活记忆保存。
4. **Given** 用户说“I'm a bit tired today”，且没有要求 Hermes 记住，**When** 对候选记忆分类，**Then** 结果是 `no_save`。
5. **Given** 多次证据显示一个持久行为模式，**When** 对该模式做 reflection 分类，**Then** 只有在有足够支持证据时，结果才可以是 `abstract_experience`。

---

### User Story 2 - Store Life Memory（优先级：P1）

作为 Hermes 用户，我希望 Hermes 把重要个人生活记忆和技术项目记忆分开保存，这样我的长期个人上下文能保持有用，并且不会污染技术记忆。

**Why this priority（为什么是这个优先级）**：正确保存信息是后续生活记忆召回的基础。

**Independent Test（独立测试）**：让 Hermes 记住范围内和范围外的事实，并验证只有符合条件的生活记忆被接受。

**Acceptance Scenarios（验收场景）**：

1. **Given** 用户明确要求 Hermes 记住一个生活相关事实，**When** 该事实符合 L4 life memory，**Then** 插件保存该记忆，并记录 `primary_category`、tags、importance、confidence、classification_confidence、source、timestamps、status、promotion_path 和 trace。
2. **Given** 记忆内容是技术、项目、学术实现细节、工具配置或调试历史，**When** 请求保存，**Then** 插件不把它保存进生活记忆。
3. **Given** 内容是琐碎、临时、不确定，或只对当前对话有用，**When** 用户没有明确长期保存意图，**Then** 插件拒绝保存。
4. **Given** 内容是敏感个人信息，**When** 用户没有明确要求长期保存，**Then** 插件返回 `needs_confirmation`，不创建 durable memory，并询问是否长期保存、保存摘要还是完整内容。
5. **Given** 内容是稳定且影响重大的生活事实，且用户明确要求记住，**When** 满足 `major_life_fact` 快速晋升条件，**Then** 该记忆可以从 `young` 直接晋升为 `active`，并记录 `promotion_path=major_life_fact`。

---

### User Story 3 - Recall Relevant Life Memory（优先级：P1）

作为 Hermes 用户，我希望 Hermes 在当前问题需要个人上下文时召回相关生活记忆，从而让回答具备连续性和个性化。

**Why this priority（为什么是这个优先级）**：召回是已保存生活记忆最直接的用户价值。

**Independent Test（独立测试）**：保存多条生活记忆后，提出定向和宽泛召回问题，验证返回结果。

**Acceptance Scenarios（验收场景）**：

1. **Given** 用户问题与之前的生活记忆相关，**When** 请求召回，**Then** 插件返回相关记忆，并带有 identifier 或 reference。
2. **Given** 存在无关生活记忆，**When** 请求召回，**Then** 无关记忆不会被注入回答。
3. **Given** Hermes 其他地方存在技术记忆，**When** 请求 life-memory recall，**Then** 技术项目记忆被排除。
4. **Given** 多条记忆匹配查询，**When** 对召回结果排序，**Then** 高 importance、高 confidence、最近使用、语义更相关的记忆优先。
5. **Given** 匹配结果包含 `young` 记忆，**When** recall 返回结果，**Then** `young` 记忆低权重参与、最多返回 2 条、标记为 candidate/low_confidence，且 sensitive/restricted young 记忆不返回。

---

### User Story 4 - Correct And Forget Memory（优先级：P2）

作为 Hermes 用户，我希望能够纠正错误或过期记忆，也能遗忘指定记忆，这样 Hermes 不会继续使用不准确或我不想保留的个人上下文。

**Why this priority（为什么是这个优先级）**：长期记忆必须保持用户可控，才值得信任。

**Independent Test（独立测试）**：保存一条记忆后，对它应用 feedback 或 deletion，再验证未来召回是否变化。

**Acceptance Scenarios（验收场景）**：

1. **Given** 用户说某条记忆是错的，**When** 记录反馈，**Then** 根据用户指令将该记忆标记为 corrected、stale、deleted 或 replaced。
2. **Given** 用户提供替代事实，**When** 记录反馈，**Then** 插件更新已有记忆，而不是创建不必要的重复记忆。
3. **Given** 用户要求遗忘一条具体记忆，**When** 目标明确，**Then** 该记忆被标记为 deleted 或 inactive，并且不会出现在正常召回中。
4. **Given** 一个 forget 请求可能匹配多条记忆，**When** 目标有歧义，**Then** 插件要求用户消歧，而不是静默删除多条记忆。

---

### User Story 5 - Reflect And Maintain Memory Quality（优先级：P3）

作为 Hermes 用户，我希望生活记忆能被周期性整理和清理，使记忆库长期保持有用。

**Why this priority（为什么是这个优先级）**：reflection 能在有足够记忆后提升质量，但它依赖正确分类、存储、召回和反馈。

**Independent Test（独立测试）**：创建重复、过期、低价值和重复模式类记忆，然后验证 reflection 输出和记忆状态变化。

**Acceptance Scenarios（验收场景）**：

1. **Given** 存在重复或高度相似记忆，**When** reflection 运行，**Then** 插件识别 deduplication 或 merging 候选项。
2. **Given** 多条兼容记忆描述同一个持久生活事实，**When** reflection 合并它们，**Then** 合并后的记忆保留有用 source 和 trace 信息。
3. **Given** 存在过期 `recent_state` 记忆，**When** light reflection 运行，**Then** 插件将其归档，并记录 `decay_reason=ttl_expired`。
4. **Given** 重复证据支持一个 abstract experience memory，**When** reflection 创建 insight，**Then** 该 insight 标记为 inference，并引用支持记忆。
5. **Given** 只有一条随口消息，**When** reflection 评估它，**Then** 不创建 abstract experience memory。
6. **Given** 用户运行 daily reflection，**When** 生成 daily report，**Then** report 只作为 audit artifact，不创建 durable memory，也不改变 `promotion_score`。

---

### User Story 6 - Export Human Review Markdown（优先级：P2）

作为 Hermes 用户，我希望能把数据库里的生活记忆导出成容易阅读的 Markdown，这样我可以检查系统到底记住了什么、哪些还不确定、哪些已经归档。

**Why this priority（为什么是这个优先级）**：SQLite 适合运行时管理，但普通用户更适合通过 Markdown 审查长期记忆。

**Independent Test（独立测试）**：在临时 `HERMES_HOME` 中保存多类记忆，运行 `life_memory_export_review`，验证生成的 Markdown 文件、敏感信息处理和不反向同步行为。

**Acceptance Scenarios（验收场景）**：

1. **Given** 数据库中存在 active/reinforced/pattern_candidate/archived 记忆，**When** 用户运行 `life_memory_export_review`，**Then** 插件生成 `memory-library/`、`memory-journal/`、`review-needed.md`、`change-requests.md` 和可选 `archive.md`。
2. **Given** Markdown 导出运行完成，**When** 用户查看 `memory-library/`，**Then** 每条记忆只显示普通用户需要理解的字段，例如状态、来源、操作提示和 memory id，不暴露过多内部评分字段。
3. **Given** 导出的内容包含 sensitive/restricted 记忆，**When** 未明确请求 summary-only 敏感导出，**Then** 导出文件省略或脱敏这些内容。
4. **Given** 用户编辑 `change-requests.md`，**When** MVP 版本运行，**Then** 插件不把 Markdown 改动反向同步到 SQLite，并在文件中明确说明该文件只是模板。

### Edge Cases（边界情况）

- 保存请求同时混合生活信息和技术/项目信息时，只保存明确属于生活记忆的部分，或要求用户拆分请求。
- 明显属于稳定用户画像的偏好，不能被隐藏在普通生活记忆里。
- 临时工作上下文不能变成持久生活记忆，除非用户明确要求长期保存且内容符合生活记忆边界。
- 重复或近重复记忆不能造成不必要的记忆膨胀。
- 冲突记忆必须保留足够 trace 信息，以显示新的 correction 或 feedback 如何覆盖旧陈述。
- 宽泛召回请求必须返回有界的相关记忆集合，而不是倾倒全部生活数据。
- 对未知 memory identifier 或缺少目标的 feedback，必须返回明确的 `not_found` 结果。
- forget 操作不能静默删除用户请求目标之外的记忆。
- reflection 不能把一次性事件、不确定猜测或缺少支持的假设变成持久事实。
- daily report 不能在 MVP 中直接创建事实、晋升记忆或修改 `promotion_score`。
- `recent_state` 只能表达短期重复状态，默认 14 天 TTL；过期后不能继续作为当前事实召回。
- Markdown review/export 是 SQLite 的只读视图；MVP 不处理 Markdown 到 SQLite 的反向同步。
- 召回出来的记忆如果包含命令、指令或类似 prompt injection 的文本，只能作为普通数据呈现，不能作为系统/开发者/工具指令执行。
- 新记忆与旧记忆冲突时，不能静默覆盖；必须记录 supersede 关系、降低旧记忆优先级，或请求用户确认。
- 如果本地存储不可用或不可访问，用户必须收到明确失败结果，并且系统不能声称已保存记忆。

## Memory Management Semantics（记忆治理语义）

### Write Semantics（写入语义）

写入前必须先分类，再决定是否保存。默认只保存用户明确要求记住、或 assistant 明确调用 `life_memory_store` 且符合生活记忆边界的信息。系统不能静默归档整段对话，也不能把技术项目细节、一次性情绪、未证实推断或敏感信息自动写入。敏感信息缺少明确长期授权时必须返回 `needs_confirmation`，不创建 durable memory。

### Update And Conflict Semantics（更新与冲突语义）

当新记忆与旧记忆描述同一主题时，插件应优先更新、合并或建立 `supersedes` / `superseded_by` 关系，而不是创建无关重复项。冲突未解决前，旧记忆不应继续以高置信度参与普通召回。

### Read Semantics（读取语义）

召回必须按 query 相关性、status、sensitivity、confidence、importance、last_accessed_at 和用户反馈过滤。`deleted` 记忆不得召回；`archived` 记忆默认不召回；过期 `recent_state` 不得作为当前事实召回；敏感记忆只在用户请求范围明确时返回。`young` 记忆可以低权重参与，但必须标记不确定性并限制数量。

### Audit Semantics（审计语义）

每次 store、recall、feedback、forget、reflect、merge、archive、reinforce、export_review 和 conflict resolution 都必须留下可解释 trace：操作类型、时间、触发原因、来源、涉及记忆、状态变化、用户是否确认。

## Requirements *(mandatory)*（需求）

### Functional Requirements（功能需求）

- **FR-001**：本功能 MUST 提供用户可访问能力：`life_memory_store`、`life_memory_recall`、`life_memory_feedback`、`life_memory_forget`、`life_memory_reflect` 和只读 `life_memory_export_review`。
- **FR-002**：本功能 MUST 在保存前把候选记忆分类为 `technical_memory`、`life_memory`、`user_profile`、`temporary_working_memory`、`abstract_experience` 或 `no_save` 之一。
- **FR-003**：`life_memory_store` MUST 保存 L4 life memory，并至少记录 content、`primary_category`、tags、importance、confidence、classification_confidence、source、creation time、update time、last accessed time、access count、status、sensitivity、promotion_path、related memory ids、supersedes/superseded-by 关系和 trace information。
- **FR-004**：`life_memory_store` MUST 避免保存 L2 technical project memory，包括 programming projects、code structure、runtime environment、dependency configuration、debugging history、experiment results、academic coursework、report progress、tool configuration，以及 Hermes/OpenClaw/Codex/SSH/TTS/QQ bot technical setup。
- **FR-005**：`life_memory_store` MUST 默认避免保存 L0 conversation context、trivial one-off messages、temporary emotions、uncertain guesses、unsupported inferences 和 current-conversation-only details。
- **FR-006**：除非用户明确授权长期保存，`life_memory_store` MUST NOT 保存敏感个人信息；缺少授权时 MUST 返回 `needs_confirmation`，并且不得创建 durable memory。
- **FR-007**：本功能 MUST 单独识别 L3 user profile candidates，避免将 stable identity、language preferences、writing format requirements、long-term goals 和 stable response constraints 混入 life-memory records。
- **FR-008**：`life_memory_recall` MUST 基于当前 query 或 conversation context 检索相关生活记忆，同时排除技术记忆和无关生活记忆。
- **FR-009**：召回结果 MUST 区分 direct stored memories 和 reflected abstract experience insights，并提供足够 reference information 供用户 correction 或 deletion。
- **FR-010**：`life_memory_feedback` MUST 支持 feedback types：useful、wrong、outdated、important、duplicate、delete 和 merge。
- **FR-011**：feedback MUST 影响未来 recall、reflection、deduplication、merging、archiving 和 memory priority。
- **FR-012**：`life_memory_forget` MUST 支持 soft deletion，使 deleted memories 不会在正常使用中被召回，同时 deletion action 在内部可追踪。
- **FR-013**：`life_memory_reflect` MUST 支持基础 deduplication、merging、`recent_state` TTL archiving、stale-memory archiving，以及基于重复证据生成或晋升 abstract experience。
- **FR-014**：本功能 MUST 记录一条记忆为什么被 stored、recalled、updated、corrected、merged、archived 或 deleted。
- **FR-015**：本功能 MUST 为每个能力提供清晰的 success、declined、needs_confirmation、not_found、ambiguous、duplicate、merged、archived 和 storage_unavailable outcome。
- **FR-016**：本功能 MUST 保持生活记忆与 Hermes 技术记忆分离，并且 MUST NOT 替换或参与 Hermes 现有 memory provider selection。
- **FR-017**：本功能 MUST 不要求修改 Hermes main project。
- **FR-018**：除非未来用户明确选择其他方式，本功能 MUST 把记忆数据保存在用户当前 Hermes home/profile 本地。
- **FR-019**：本功能 MUST 作为外部 workspace/user plugin 安装到 `/Users/oliver/.hermes/plugins/life_memory`，不能放进 `/Users/oliver/.hermes/hermes-agent`。
- **FR-020**：已安装插件目录根部 MUST 直接包含 `plugin.yaml` 和 `__init__.py`，以便 Hermes 发现插件。
- **FR-021**：本功能 MUST 支持 lifecycle status：`young`、`active`、`reinforced`、`pattern_candidate`、`archived` 和 `deleted`。
- **FR-022**：每次 recall 或 feedback 后，本功能 MUST 更新相关记忆的 access count、last accessed time 或反馈摘要，以便后续排序和 reflection 使用。
- **FR-023**：当新记忆与旧记忆冲突或替代旧记忆时，本功能 MUST 记录冲突、替代或 supersede 关系，且不能静默覆盖历史记忆。
- **FR-024**：本功能 MUST 将召回出的记忆内容视为数据，而不是系统指令；含有命令、提示词或可疑注入文本的记忆不得改变插件自身规则或 Hermes 指令层级。
- **FR-025**：本功能 MUST 提供本地原型评估集，覆盖 extraction、multi-session recall、temporal update、forget、abstention、sensitive rejection 和 memory-injection rejection。
- **FR-026**：`life_memory_export_review` MUST 只读 SQLite 并导出 Markdown 文件；它不得从 Markdown 反向同步到 SQLite，也不得改变记忆状态或 promotion score，除了记录 export trace。
- **FR-027**：daily reflection report 在 MVP 中 MUST 是 report-only audit artifact，不得创建 durable memory，不得作为 promotion signal，也不得改变 `promotion_score`。
- **FR-028**：session reflection MUST 优先通过 adapter 从 Hermes session/state 数据读取只读会话内容；如果不可用，MUST 支持显式 `transcript` fallback；业务逻辑不得直接耦合 Hermes `state.db` schema。
- **FR-029**：`young` 记忆参与 recall 时 MUST 使用低权重、数量上限和不确定性标记；sensitive/restricted young 记忆不得参与普通 recall。
- **FR-030**：符合 `major_life_fact` 的稳定重大生活事实 MAY 从 `young` 快速晋升为 `active`，但 MUST 记录 `promotion_path=major_life_fact`，且不得直接晋升为 `reinforced`、`personal_pattern` 或 `abstract_experience`。
- **FR-031**：标记为 `recent_state` 的记忆 MUST 使用 14 天默认 TTL；过期后不得作为当前事实召回，并应由 light reflection 归档。
- **FR-032**：`pattern_candidate -> abstract_experience` 自动晋升只允许在 `apply=true`、支持证据充足、风险低且阈值满足时发生，并 MUST 记录 supporting memory ids。

### Key Entities（关键实体）

- **Memory Classification**：把候选内容分配到 `technical_memory`、`life_memory`、`user_profile`、`temporary_working_memory`、`abstract_experience` 或 `no_save` 的判断，包含 reason 和 confidence。
- **Life Memory**：一个持久 L4 个人生活记忆项。关键属性包括 identifier、content、`primary_category`、tags、importance、confidence、classification_confidence、source、timestamps、access_count、last_accessed_at、lifecycle status、sensitivity、promotion_path、valid_until、related_memory_ids、supersedes、superseded_by 和 trace。
- **Recall Result**：针对查询的有界结果。关键属性包括 matching memory references、relevance reason、rank signals，以及每项是 direct memory 还是 reflected insight。
- **Feedback Entry**：用户对记忆给出的 correction、rating 或 classification change。它会影响后续 recall、reflection 和展示。
- **Forget Request**：用户针对一条或多条记忆发起的 soft deletion 操作。包含 target reference、ambiguity status 和 completion outcome。
- **Reflection Insight**：从多条符合条件的生活记忆中综合出的 L5 pattern。它必须包含 supporting memory references，并标记为 inference。
- **Review Export**：从 SQLite 生成的只读 Markdown 审查视图，包含 `memory-library/`、`memory-journal/`、`review-needed.md`、`change-requests.md` 和可选 `archive.md`。
- **Reflection Report**：reflection 运行产物。MVP daily report 只用于审计，不作为事实源或 promotion signal。
- **Memory Trace**：记录一条记忆为什么被 stored、recalled、corrected、deleted、merged、archived 或 reflected。
- **Lifecycle State**：记忆当前所处的治理状态，决定它是否参与普通召回、是否需要复核、是否可被 reflection 晋升或归档。
- **Evaluation Case**：本地原型验证用例，包含输入、预期分类、预期状态变化、预期召回/拒答行为和安全边界预期。

## Memory Boundary Rules（记忆边界规则）

### Store In Hermes Built-In Technical/Project Memory（留给 Hermes 内置技术/项目记忆）

以下内容不能由 life-memory 插件保存：programming projects、code structure、runtime environment、dependency configuration、debugging history、experiment results、academic coursework、report progress、tool configuration，以及 Hermes/OpenClaw/Codex/SSH/TTS/QQ bot technical setup。

### Store In Life Memory Plugin（保存到生活记忆插件）

以下内容可以进入 life-memory plugin：personal routines、habits、non-technical preferences、life events、relationship context、emotional patterns over time、lifestyle context，以及 repeated personal behavior patterns。

### Classify As User Profile（分类为用户画像）

以下内容应与普通生活记忆分开分类：stable identity、long-term response preferences、language preferences、writing format requirements、long-term goals 和 stable constraints。

### Do Not Store By Default（默认不保存）

以下内容默认不保存：trivial one-off messages、temporary emotions、uncertain guesses、缺少足够证据的信息推断、未经明确要求保存的敏感信息，以及只对当前对话有用的细节。

## Example Scenarios（示例场景）

- **Technical Memory**：“My Hermes runs on Mac, and Windows is connected through SSH.” 预期分类：`technical_memory`。预期行为：不保存到 life memory。
- **Life Memory**：“Remember that I prefer to work late at night and usually think better after midnight.” 预期分类：`life_memory`。预期行为：保存为 `primary_category=personal_preference`，并使用 routine/habit 相关 tags。
- **User Profile**：“From now on, when you generate English content for me, include Chinese translation below.” 预期分类：`user_profile`。预期行为：不作为普通 life memory 保存。
- **No Save**：“I'm a bit tired today.” 预期分类：`no_save`，除非用户明确要求记录。预期行为：不永久保存。
- **Abstract Experience**：重复证据显示用户拒绝 over-engineered solutions，并偏好 MVP-first implementation。预期分类：`abstract_experience`。预期行为：只有在重复证据充分后保存。
- **Sensitive Confirmation**：用户要求记录敏感生活信息但没有明确长期授权。预期行为：返回 `needs_confirmation`，不创建 durable memory。
- **Recent State**：多日会话显示用户最近很累。预期行为：如果保存，只能作为 `tag=recent_state` 的短期状态，默认 14 天 TTL，过期后不作为当前事实召回。

## Project Constraints For Planning（规划约束）

- 交付物是名为 `life_memory` 的 Hermes standalone plugin。
- 插件必须使用 Hermes directory-plugin entrypoints：`plugin.yaml` 和带 `register(ctx)` 的 `__init__.py`。
- 插件不能实现为 `memory.provider`。
- 插件源码仓库是 `/Users/oliver/Projects/hermes-life-memory`。
- 插件源码包目录是 `/Users/oliver/Projects/hermes-life-memory/plugins/life_memory`，不是仓库根目录。
- Hermes runtime home/workspace folder 是 `/Users/oliver/.hermes`。
- 在 PyCharm workspace 中，Hermes 文件夹应暴露为 `/Users/oliver/Projects/hermes-workspace/.hermes`，并指向 `/Users/oliver/.hermes`。
- PyCharm workspace 不能把 `/Users/oliver/Projects/hermes-workspace/hermes-agent` 当作 Hermes plugin workspace，因为该路径指向 `/Users/oliver/.hermes/hermes-agent` 内部。
- Runtime plugin installation 必须指向 `/Users/oliver/.hermes/plugins/life_memory`。
- 如果开发期使用 symlink，`/Users/oliver/.hermes/plugins/life_memory` 必须指向 `/Users/oliver/Projects/hermes-life-memory/plugins/life_memory`。
- Runtime plugin installation 不能把 `/Users/oliver/.hermes/plugins/life_memory` 指向仓库根目录 `/Users/oliver/Projects/hermes-life-memory`，因为 Hermes 要求 `plugin.yaml` 和 `__init__.py` 直接位于已安装插件目录根部。
- 通过 PyCharm workspace 访问时，同一个目标路径是 `/Users/oliver/Projects/hermes-workspace/.hermes/plugins/life_memory`。
- Runtime plugin installation 不能指向 `/Users/oliver/.hermes/hermes-agent/plugins/life_memory`。
- Runtime plugin installation 不能指向 `/Users/oliver/Projects/hermes-workspace/hermes-agent/plugins/life_memory`。
- 插件必须通过 Hermes 插件配置启用，例如把 `life_memory` 加入 `/Users/oliver/.hermes/config.yaml` 的 `plugins.enabled`，或使用 Hermes plugin enable command。
- 持久化存储必须位于 `HERMES_HOME` 本地，计划中的 backing store 是 `$HERMES_HOME/life_memory.db`，例如 `/Users/oliver/.hermes/life_memory.db`。
- `/Users/oliver/.hermes/hermes-agent` 下的 Hermes source files 仅作为参考，本功能不能修改它们。

## Planning Decisions（规划决策）

- MVP 中 temporary working memory 仍保留在对话内；除非用户明确要求长期保存，且内容符合 life-memory 边界。
- Abstract experience memory 从显式 reflection、重复证据规则和 `apply=true` 的低风险自动晋升开始；完全 autonomous high-risk reflection 是未来范围。
- MVP 中 life-memory retrieval 通过 recall 行为暴露；是否在每次回答前自动注入记忆留到后续评估。
- MVP 中 memory inspection 通过带 identifiers 的 recall results、feedback/forget actions，以及只读 `life_memory_export_review` Markdown 导出处理。
- MVP 中 technical-memory routing 采用 rule-based classification；单独的 memory-router plugin 是未来范围。
- MVP 不引入向量数据库或图数据库作为硬依赖；结构化 SQLite、全文/关键词检索和轻量相关性排序足够用于第一轮原型验证。
- `pattern_candidate` 替代技术向的 `skill_candidate` 进入 life-memory MVP；真正 skill promotion 留给 Hermes 技术记忆或未来插件。
- 原型评估以小型手写测试集为主，不追求直接复刻 LongMemEval/LoCoMo，但覆盖它们强调的长期记忆能力类别。
- 对话有效信息抽取优先于“每日记忆”作为事实入口；daily report 在 MVP 中只做审计。
- 会话抽取通过 adapter 读取 Hermes session/state 数据，显式 `transcript` 作为 fallback。
- SQLite 是运行时事实源；Markdown 是只读人工审查视图，MVP 不做反向同步。

## Research References（研究参考）

- A-MEM：动态组织、链接和演化记忆，启发 tags、context、related memory links 和 memory evolution。https://arxiv.org/abs/2502.12110
- Mem0：生产型长期记忆强调 selective extraction、consolidation、retrieval 和低延迟/低 token 成本。https://arxiv.org/abs/2504.19413
- LongMemEval：长期记忆评估覆盖 extraction、multi-session reasoning、temporal reasoning、knowledge updates 和 abstention。https://arxiv.org/abs/2410.10813
- LoCoMo：长对话记忆暴露长期时间、因果和多会话理解困难。https://arxiv.org/abs/2402.17753
- AgeMem：把长期/短期记忆管理作为 agent 可选择的 store、retrieve、update、summarize、discard 行为。https://arxiv.org/abs/2601.01885
- Memory for Autonomous LLM Agents survey：把 agent memory 形式化为 `write -> manage -> read` 循环，并强调 contradiction handling、latency budget 和 privacy governance。https://arxiv.org/abs/2603.07670
- Privacy and safety papers：记忆可能被抽取、注入或随时间污染，因此原型必须默认保守、可审计、可删除。https://arxiv.org/abs/2502.13172 / https://arxiv.org/abs/2503.03704 / https://arxiv.org/abs/2605.17830

## Success Criteria *(mandatory)*（成功标准）

### Measurable Outcomes（可衡量结果）

- **SC-001**：代表性分类测试集中的 100% 用例，被分配到预期分类：`technical_memory`、`life_memory`、`user_profile`、`temporary_working_memory`、`abstract_experience` 或 `no_save`。
- **SC-002**：验收测试集中至少 95% 明确、范围内的 life-memory store 请求，在后续 session 中可保存且可召回。
- **SC-003**：100% 被排除的 technical/project/profile/temporary/no-save 测试项，被拒绝、被分类到 life memory 之外，或从保存中分离，而不是被保存成 life memory。
- **SC-004**：至少 90% 定向 recall queries 在前五个返回结果中包含预期相关 life memory。
- **SC-005**：100% 精确目标 forget requests 能阻止被遗忘记忆出现在后续正常 recall 和 reflection 结果中。
- **SC-006**：至少 90% feedback updates 能对相关记忆后续 recall、priority、status 或 reflection behavior 产生可观察变化。
- **SC-007**：验收测试中的 100% reflection insights 引用或关联 supporting memories，并把输出标记为 inference。
- **SC-008**：在包含 duplicate 和 stale memories 的测试集中，reflection 能识别至少 90% duplicate candidates 和至少 90% stale low-value candidates。
- **SC-009**：在 10,000 条记忆的数据集下，至少 95% 常见 store、recall、feedback、forget 和 reflect 请求在 2 秒内完成。
- **SC-010**：在 temporal update 测试集中，100% 被新事实明确替代的旧记忆不会以当前事实形式出现在普通召回结果中。
- **SC-011**：在 abstention 测试集中，至少 95% 无相关记忆的问题返回“没有匹配记忆”或等价结果，而不是编造生活背景。
- **SC-012**：在 sensitive rejection 和 memory-injection rejection 测试集中，100% 未经明确授权的敏感内容和可疑注入内容不会被自动保存、晋升或作为指令执行。
- **SC-013**：100% store、feedback、forget、reflect、merge、archive 和 conflict-resolution 操作都有可查看 trace，能说明来源、原因和状态变化。
- **SC-014**：`life_memory_export_review` 在验收测试中能生成预期 Markdown 文件，并且 100% 不改变 memory status、promotion score 或 SQLite 内容，除了 export trace。
- **SC-015**：100% daily report 验收用例不会创建 durable memory，也不会改变 `promotion_score`。
- **SC-016**：100% 未获明确长期授权的敏感信息 store 用例返回 `needs_confirmation`，且不创建 durable memory。
- **SC-017**：100% 过期 `recent_state` 测试项不会作为当前事实参与普通 recall，并会在 light reflection 后归档。

## Assumptions（假设）

- 初始功能面向单个当前 Hermes user/profile；共享多用户权限不在第一阶段范围内。
- 生活记忆只通过用户明确意图或 assistant 显式调用工具捕获；本功能不会静默归档每段对话。
- 敏感信息只有在用户清楚要求长期保存时才可以保存；缺少授权时必须请求确认，并且召回、导出或 reflection 应比普通生活记忆更保守。
- Forgetting 表示该记忆不再用于后续正常 recall 或 reflection；任何内部 operational trace 都不能向用户暴露被遗忘内容。
- Reflections 是可选的派生上下文，永远不能覆盖用户直接 correction。
- Daily report 是审计视图，不是事实源；事实入口应来自明确 store、session extraction 的候选项或经过 reflection 验证的重复证据。
- Markdown review/export 是人工检查入口，不是数据库编辑入口；MVP 中用户修改 Markdown 不会自动改 SQLite。
- 原型验证优先追求可解释、可测试和用户可控，不追求第一版达到复杂研究系统的自动化程度。
- 研究结论用于指导原型边界和评估设计；实际实现应服从 Hermes 插件约束、本地存储约束和用户隐私边界。
