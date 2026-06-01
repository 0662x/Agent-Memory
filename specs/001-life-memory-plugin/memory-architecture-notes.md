# Memory Architecture Notes: 自动化优先的生活记忆系统

**Date**: 2026-06-01  
**Status**: Discussion Record  
**Related Spec**: [spec.md](./spec.md)  
**Related Plan**: [plan.md](./plan.md)

## 0. 整体设计总览

`life_memory` 是 Hermes 的 standalone user plugin，用来保存 **生活记忆**，并和 Hermes 现有技术/项目记忆分离。它不修改 Hermes core，不实现 `MemoryProvider`，也不把插件做成 `memory.provider`。插件入口仍然是：

```text
plugins/life_memory/plugin.yaml
plugins/life_memory/__init__.py::register(ctx)
```

运行时数据放在：

```text
$HERMES_HOME/life_memory.db
```

开发期挂载目标是：

```text
/Users/oliver/.hermes/plugins/life_memory
```

### 0.1 核心目标

系统要解决的问题不是“把所有事情都记住”，而是：

```text
从对话中抽取值得长期保留的生活信息
把短期候选、稳定事实、抽象经验分开
避免技术记忆、临时闲聊、敏感信息污染生活记忆
让系统能自动运行，同时保留人工审计入口
```

核心原则：

```text
自动化运行是主路径
人工审核是旁路和调试工具
事件级 evidence 是事实来源
模型输出只是候选和解释
SQLite 状态机决定是否真正保存、晋升、召回或删除
```

### 0.2 总体数据流

整体流程分成四层：

```text
raw conversation / session transcript
  -> effective memory candidates
  -> young memory / memory_evidence / declined trace / conflict candidate
  -> active / reinforced / pattern_candidate
  -> reflected abstract_experience
```

更通俗地说：

```text
会话历史不是记忆
会话有效信息候选才是记忆入口
每日 report 只是审计和晋升参考
长期记忆必须经过 evidence、阈值、冲突检查和 safety gate
```

### 0.3 五个核心工具 + 一个只读导出工具

MVP 的工具面保持小而明确。前五个是记忆核心闭环，第六个是只读的人类可见导出：

```text
life_memory_store
  对话热路径写入。快速分类、过滤、去重、写入 young 或拒绝。

life_memory_recall
  根据当前查询召回相关生活记忆。默认排除 deleted/archived，降低 young 权重。

life_memory_feedback
  记录 useful/wrong/outdated/important/duplicate/delete/merge 等反馈。

life_memory_forget
  软删除记忆，保留 tombstone/hash/trace，普通召回不再返回内容。

life_memory_reflect
  后台 dreaming/reflection。负责 session extraction、去重、证据统计、
  冲突候选、晋升、归档、daily report 和 abstract_experience 草案。

life_memory_export_review
  只读导出 Markdown review 视图。生成 memory-journal、memory-library、
  review-needed、archive 和 change-requests 模板；不读取 Markdown 修改，
  不反向同步，不修改数据库。
```

### 0.4 Hot Path 与 Background

设计分成热路径和后台：

```text
hot path:
  用户正在对话时运行
  只做低延迟分类、拒绝、写入 young、基础 trace
  不做复杂 reflection

background:
  对话后或手动触发
  做 session extraction、light/REM/deep/daily reflection
  负责整理、去重、晋升、归档、冲突分析、report
```

`life_memory_reflect` 的 phase：

```text
session:
  从完成的会话中抽取 effective memory candidates。

light:
  低成本整理、去重、补标签、统计 evidence。

REM:
  发现主题、冲突、重复模式、pattern_candidate、reflection report 草案。

deep:
  保守晋升、归档、supersede、abstract_experience 草案或生成。

daily:
  生成每日 reflection report。MVP 中 report 只用于审计，不是事实源，
  也不参与 promotion_score；MVP+ 才允许作为晋升信号。
```

### 0.5 记忆分层

本插件只负责生活记忆相关层：

```text
technical_memory:
  技术项目事实，交给 Hermes 现有技术/项目记忆，不进 life_memory。

user_profile:
  稳定全局偏好，如语言、输出风格、长期目标，不作为普通生活记忆。

life_memory:
  日常习惯、生活事件、非技术偏好、人际关系、生活背景。

temporary_working_memory:
  当前任务临时上下文，默认不长期保存。

abstract_experience:
  从多条证据反思出的稳定模式，必须标记为 inference。

no_save:
  一次性闲聊、短期情绪、不确定猜测、未授权敏感信息。
```

### 0.6 生命周期状态

SQLite 中的 lifecycle status 表达“分代”：

```text
young
  新写入或新抽取的候选，低权重参与 recall。

active
  通过基础门控或已有证据支持的稳定生活记忆。

reinforced
  多次证据、正反馈或多场景有效召回后的强记忆。

pattern_candidate
  多条证据显示可能存在模式，但还未形成抽象经验。

archived
  低价值、过期、被替代或长期不用的记忆，默认不召回。

deleted
  用户明确遗忘或删除，保留 tombstone，但不普通召回。
```

典型晋升路径：

```text
young -> active -> reinforced -> pattern_candidate -> reflected abstract_experience
```

但所有晋升都必须受 evidence、confidence、importance、conflict、sensitivity 和 injection_risk 约束。

### 0.7 会话有效信息，而不是每日记忆本体

“每日记忆”不作为主记忆来源。真正的来源是 **会话有效信息抽取**：

```text
会话历史 raw transcript             = 原始材料，不直接进入 life_memory 主库
会话有效信息 effective candidates   = 从会话中抽取出来的候选事实/事件/偏好/纠错/模式
每日 reflection report              = 对当天候选和 evidence 的结构化审计报告
长期 life memory                    = 通过阈值晋升后的稳定事实或模式
```

这样可以避免两个问题：

- 全量日记变成会话历史副本；
- 自由文本压缩导致语义丢失或总结错误。

Agent 可以读会话历史，但只能用于抽取候选和 evidence。普通 recall 不直接读 raw transcript。

### 0.8 模型介入边界

模型不是记忆数据库管理员。更准确的定位是：

```text
规则/SQLite 负责状态变化和安全约束
模型负责语义判断、抽取、候选生成、反思草案
高风险动作先生成建议，不直接落地
```

热路径中，模型只在语义边界不清时可选介入，例如判断：

- 是否属于生活记忆；
- 是否是技术记忆或用户画像；
- 是否只是一次性闲聊；
- 初始 primary_category/tags/importance/confidence；
- 是否含敏感信息或 prompt injection 风险。

后台中，模型主要用于：

- session extraction；
- REM/deep reflection；
- pattern_candidate 和 abstract_experience 草案；
- daily reflection report。

模型输出不能绕过 classification、safety、sensitivity、conflict、injection-risk 和 deletion 规则。

### 0.9 SQLite 与 Markdown 的分工

本插件采用：

```text
SQLite   = 自动化状态机 + 结构化事实库 + 检索索引 + trace ledger
Markdown = 人工可读审计视图 + reflection report + 可选修正入口
```

SQLite 是 runtime source of truth。Markdown 不参与正常运行主路径。

给普通用户看的 Markdown 视图使用更接近日常语言的名字：

- `memory-journal/sessions/`：会话记忆，按会话看系统抽取了什么；
- `memory-journal/daily/`：每日记忆报告，按日期看当天发生了什么候选变化；
- `memory-library/`：长期生活记忆库，MVP 只按事实、偏好、模式三类展示；
- `review-needed.md`：需要用户确认或修正的内容；
- `change-requests.md`：后续同步功能中，用户表达“修改/删除/合并已确认记忆”的入口；
- `archive.md`：已归档或过期内容摘要。

MVP 中通过 `life_memory_export_review` 实现只读 Markdown review/export：

```text
life_memory_export_review
  只读导出给普通用户看的 memory-journal、memory-library、review-needed、archive
  生成 change-requests.md 模板，但不读取它
  不读取 Markdown 修改
  不反向同步
  不修改数据库
```

反向同步属于后续增强，因为它会带来解析、冲突、安全校验和误改风险。

### 0.10 MVP 边界

MVP 做：

- Hermes standalone plugin；
- SQLite schema、repository、trace；
- 五个核心工具 + `life_memory_export_review` 只读导出工具；
- deterministic classification/safety gate；
- young/active/reinforced/pattern_candidate/archived/deleted 状态；
- session extraction 和 reflection report 的基础支持；
- `daily report` 在 MVP 中只做 report-only，不参与 `promotion_score`；
- recall ranking 和 abstention；
- feedback、forget、soft delete；
- focused tests/evaluation cases。

MVP 不做：

- Hermes core 修改；
- `MemoryProvider`；
- MCP server；
- PostgreSQL/pgvector/graph database；
- 多用户/跨设备同步；
- 完整知识图谱；
- 自动读写 Markdown 双向同步；
- 把 daily report 当长期事实源。

## 1. 当前结论

`life_memory` 的目标不是做一个需要人频繁审核的手工记忆库，而是做一个 **自动化优先、人类可审计** 的生活记忆系统。

核心原则：

```text
自动化运行是主路径
人工审核是旁路和调试工具
```

因此，Markdown 不应该成为正常运行的必经环节。用户不审核 Markdown 时，系统仍然应该高概率正确地保存、召回、更新、遗忘和整理生活记忆。

## 2. 和 OpenClaw 的经验对照

OpenClaw 的成熟经验可以概括为：

```text
Markdown = 人类可读的记忆源
SQLite   = 检索索引和搜索加速
```

它的典型层次是：

```text
MEMORY.md             长期精炼记忆
memory/YYYY-MM-DD.md  日常工作层/流水层记忆
DREAMS.md             dreaming/reflection 候选和审核记录
SQLite index          FTS/vector/hybrid search
```

我们不完全照搬这个设计，因为 Hermes `life_memory` 需要更强的结构化能力：

- 精确 `memory_id`
- lifecycle status
- feedback score
- access count
- last accessed time
- supersedes/superseded_by
- deleted tombstone
- sensitivity filtering
- trace/audit log
- automated promotion/decay/reflection

这些状态机和关系用 SQLite 管更稳。

所以本插件采用的方向是：

```text
SQLite   = 自动化状态机 + 结构化事实库 + 检索索引 + trace ledger
Markdown = 人工可读审计视图 + reflection 报告 + 可选修正入口
```

## 3. 主架构

### 3.1 SQLite 是运行时主路径

Hermes 正常运行时，五个核心工具直接操作 SQLite；`life_memory_export_review` 只读 SQLite 并导出 Markdown：

```text
life_memory_store    -> 写入/分类/拒绝/trace
life_memory_recall   -> 检索/排序/过滤/更新 access signals
life_memory_feedback -> 纠错/强化/替代/合并/删除
life_memory_forget   -> soft delete + tombstone/redaction
life_memory_reflect  -> light/REM/deep dreaming：去重/归档/晋升/模式候选
life_memory_export_review -> read-only SQLite -> Markdown review files
```

SQLite 负责保证：

- `deleted` 不被普通召回；
- `archived` 默认不进入普通召回；
- 敏感记忆默认保守召回；
- 新旧冲突通过 `supersedes` 关系处理；
- 召回、反馈、遗忘、reflection 都有 trace；
- 自动晋升和自动降级可测试、可回放。

### 3.2 Markdown 是可选审计层

Markdown 文件用于人类查看和修正，不是系统运行的强依赖。

建议后续导出目录使用普通用户更容易理解的名字，而不是直接暴露 `young/active/pattern_candidate` 这些内部状态：

```text
$HERMES_HOME/life_memory_review/
├── README.md                    # 这个目录是什么、哪些文件可看、哪些不是事实源
├── memory-journal/
│   ├── sessions/
│   │   └── 2026-06-01-session-1030.md
│   └── daily/
│       └── 2026-06-01.md
├── memory-library/
│   ├── facts.md                 # 稳定生活事实、生活背景、重要事件、关系摘要
│   ├── preferences.md           # 非技术偏好、习惯、作息、生活方式倾向
│   └── patterns.md              # 多次证据总结出的长期模式，必须标记 inference
├── review-needed.md             # 需要用户确认的冲突、低置信、敏感或合并候选
├── change-requests.md           # 后续同步功能使用；MVP 可不生成或只生成模板
└── archive.md                   # 已归档/过期摘要；deleted 只显示 tombstone，不导出原文
```

如果用户不看这些 Markdown，系统照常运行。  
MVP 中这些 Markdown 只作为 export-only 视图，不读取用户修改。`change-requests.md` 在 MVP 中最多是说明/模板，不作为输入读取。后续如果要支持修改同步，可以通过 `life_memory_sync_review` 或类似能力把审核意见同步回 SQLite；这个同步能力不是 MVP 的必经路径。

## 4. 自动化流程

### 4.1 写入门控

写入前先分类和过滤：

```text
candidate
  -> classification
  -> safety check
  -> sensitivity check
  -> duplicate/conflict check
  -> store or decline
```

默认只自动保存满足这些条件的记忆：

- 属于生活记忆范围；
- 有长期价值；
- 不是技术项目记忆；
- 不是用户画像全局偏好；
- 不是一次性闲聊或短期情绪；
- 不是未证实猜测；
- 不是未经明确授权的敏感信息；
- 不包含可疑 prompt injection 或行为指令。

敏感信息需要单独的确认流程，不能只靠模型判断“用户可能想保存”。MVP 行为：

```text
if sensitivity in {sensitive, restricted}
and explicit_user_request is not clearly true:
  outcome = needs_confirmation
  message = 说明这是敏感生活信息，询问是否长期保存
  no durable memory is written
  write trace with redacted/hash input

if user confirms long-term storage:
  store summary-first, not raw detail by default
  set sensitivity = sensitive/restricted
  set action_boundary
  restrict normal recall and Markdown export
```

用户确认时应该问清楚两个问题：

```text
1. 是否长期保存？
2. 保存摘要还是保存完整内容？
```

例如：

```text
“这属于敏感生活信息。要长期保存吗？如果保存，我建议只保存摘要。”
```

### 4.1.1 生活记忆分类策略

分类分两层，不要一步到位直接决定写到哪个 Markdown 文件：

```text
第一层：memory boundary
  这条信息该不该进入 life_memory？

第二层：life primary_category
  如果能进入 life_memory，它主要属于哪类生活记忆？
```

第一层只判断边界：

```text
technical_memory            技术/项目/工具/课程/部署/调试事实
user_profile                稳定全局偏好、身份、语言、输出格式、长期目标
temporary_working_memory    当前任务短期上下文
life_memory                 生活事件、习惯、关系、非技术偏好、生活背景
abstract_experience         多条证据反思出的长期模式
no_save                     一次性闲聊、短期情绪、不确定猜测、未授权敏感信息
```

第二层才决定用户可见类别。MVP 不追求细分类，主类只保留 3 个：

```text
personal_fact:
  稳定生活事实、生活背景、重要事件、关系摘要。
  重点是“发生了什么 / 用户生活背景是什么”。

personal_preference:
  非技术偏好、习惯、作息、生活方式倾向。
  重点是“用户喜欢什么 / 倾向怎么做 / 习惯什么”。

personal_pattern:
  从多条证据总结出的抽象经验或长期模式，必须标记为 inference。
  重点是“多次证据说明了什么长期规律”。
```

用户可见 Markdown 和分类的默认映射是：

```text
personal_fact        -> memory-library/facts.md
personal_preference  -> memory-library/preferences.md
personal_pattern     -> memory-library/patterns.md

life_event:
  先进入 memory-journal/sessions 或 memory-journal/daily；
  如果事件长期重要，再摘要进入 memory-library/facts.md。

relationship:
  MVP 不单独建文件，先作为 personal_fact + tag: relationship。
  敏感内容只导出摘要，不导出原文。

habit/routine:
  MVP 不单独建文件，先作为 personal_preference + tag: habit/routine。
```

注意：Markdown 文件只是展示视图，不是分类真相。SQLite 中应保存：

```text
primary_category
tags
classification_reason
confidence
review_status
```

### 4.1.2 边界模糊时怎么处理

分类模糊是正常情况，不应该强行精确。处理原则是：

```text
宁可低权重候选，不要高置信误存。
宁可多标签辅助检索，不要多个主类互相打架。
```

具体规则：

- 每条记忆只能有一个 `primary_category`，但可以有多个 `tags`；
- 如果两个类别都像，优先在三类主类中选择更通用、风险更低的主类；
- 如果主类置信度低于阈值，保存为 `young/pending` 或进入 `review-needed.md`；
- 如果是 technical/user_profile/life_memory 边界不清，默认不要写入稳定 life memory；
- 如果含敏感信息、强行为偏好或关系信息，默认更保守；
- 如果只是文件归属不清，但内容明显值得保存，可以先保存为 `personal_fact` 或 `personal_preference`，用 tags 记录细分；
- 反复出现后，background reflection 可以重新分类或移动展示视图。

建议阈值：

```text
classification_confidence >= 0.75:
  可按 primary_category 正常保存。

0.50 <= classification_confidence < 0.75:
  保存为 young/pending，显示为“新发现”，必要时进入 review-needed.md。

classification_confidence < 0.50:
  不保存为长期记忆；只写 declined trace，或等待更多证据。
```

模糊例子：

```text
“我最近晚上效率比较高。”
  如果只是今天状态：no_save 或 temporary_working_memory
  如果用户说“记住”：life_memory + personal_preference + tag:routine + young
  如果多次出现：personal_preference -> reinforced
  如果跨多场景重复：pattern_candidate -> personal_pattern

“以后英文内容都帮我附中文。”
  user_profile，不进 life_memory/preferences.md。

“我不喜欢复杂架构，先做 MVP。”
  如果是当前项目：technical/project preference，不进 life_memory。
  如果跨生活/工作方式多次出现：personal_pattern candidate。

“我和某人关系不好。”
  personal_fact + tag:relationship + sensitive/needs_review，默认不导出敏感原文。
```

### 4.1.3 给用户看的分类要少

内部可以有 `primary_category`、`tags`、`confidence`、`review_status`，但 Markdown 默认不要显示太多数据库字段。

用户默认看到：

```text
状态
来源
操作
ID
```

调试或展开时才显示：

```text
内部状态
分类
标签
置信度
证据数量
支持证据
使用边界
```

这样 `memory-library` 看起来像“记忆卡片”，而不是数据库导出。

### 4.2 分代和晋升

当前 MVP 的“分代”通过 lifecycle status 表达：

```text
young
  -> active
  -> reinforced
  -> pattern_candidate
  -> reflected abstract_experience

active / reinforced
  -> archived

any non-deleted
  -> deleted
```

普通自动晋升需要证据，而不是靠单条消息：

- `young -> active`：通过边界检查，或后续再次出现相同/相近证据；
- `active -> reinforced`：被用户确认 useful/important，或多次召回有效；
- `active -> pattern_candidate`：多条证据指向同一生活模式；
- `pattern_candidate -> abstract_experience`：支持证据足够，且无明显冲突；
- `active/reinforced -> archived`：长期不用、低价值、低置信或被新事实替代。

但需要保留一个特殊路径：**重大事实快速晋升**。

有些生活事实不是“反复出现才证明”的习惯或模式，而是用户一次明确声明后就可能长期有效、对未来个性化很重要的事实。例如：

```text
用户长期搬到某个城市居住
用户结婚/离婚/有孩子
用户长期照顾某位家人
用户有需要长期注意的健康限制
用户发生了重大生活阶段变化
```

这类信息如果满足条件，可以快速从 `young` 晋升到 `active`：

```text
young -> active
review_status = auto_promoted
promotion_path = major_life_fact
promotion_reason = major_life_fact
```

重大事实快速晋升的条件：

```text
explicit_user_request == true
primary_category == personal_fact
classification_confidence >= 0.85
confidence >= 0.85
importance >= 0.80
injection_risk < 0.10
no unresolved conflict
not technical_memory
not temporary_working_memory
not speculative/conditional/future plan
if sensitive: user explicitly authorized long-term storage
```

它不能直接晋升为 `reinforced`，也不能直接生成 `personal_pattern` 或 `abstract_experience`。后续仍然需要通过反馈、再次出现或有效召回继续强化。

不能快速晋升的例子：

```text
“我今天很崩溃。”              短期情绪
“我可能要搬家。”              不确定计划
“如果我以后有孩子……”          假设
“我以后再也不想做这个了。”      可能是短期情绪或上下文相关
```

### 4.2.1 MVP 最小衰减机制

MVP 不实现完整 forgetting curve、复杂 decay score 或模型判断过期。第一版只支持一个简单特例：`recent_state`。

`recent_state` 表示短期重复状态，例如：

```text
用户最近几天很累
用户这几天睡不好
用户近期压力比较大
用户最近在搬家
```

这类内容可以从 session extraction 的 evidence 中形成记忆，但不能变成永久事实。MVP 中 daily report 只能展示这类候选，不直接创建或晋升它们。MVP 规则：

```text
tag = recent_state
default_ttl = 14 days
primary_category = personal_fact
status <= active
not allowed: reinforced
not allowed: personal_pattern
not allowed: major_life_fact fast path
```

写入规则：

```text
on_store:
  if tag contains recent_state:
    valid_until = now + 14 days
```

召回规则：

```text
on_recall:
  if valid_until exists and now > valid_until:
    exclude from normal recall
```

重复证据规则：

```text
on_new_supporting_evidence:
  if matches existing recent_state:
    evidence_count += 1
    days_seen_count += new day if applicable
    valid_until = now + 14 days
```

用户否定规则：

```text
on_user_resolution:
  examples: “现在不累了”, “最近好多了”, “那个已经过去了”
  status = archived
  decay_reason = resolved_by_user_update
  valid_until = now
```

后台整理规则：

```text
reflect(light):
  if tag contains recent_state and valid_until expired:
    status = archived
    decay_reason = ttl_expired
```

这套最小机制的目标是避免把短期状态写成长期画像。未来如果需要，再扩展 `temporary_life_event = 30 days`、`ongoing_transition = 60 days` 或 MemoryBank-style strength curve；MVP 不做这些扩展。

### 4.3 不审核时的行为

如果人类不审核 Markdown：

- 普通低风险生活记忆仍可自动运行；
- `young` 记忆以较低权重参与召回；
- 多次证据或正反馈可以自动晋升；
- 长期无用或低价值内容会自动归档；
- 高风险内容不会自动晋升。

高风险内容包括：

- 敏感信息；
- 与旧记忆冲突的内容；
- 抽象经验；
- 多条记忆合并；
- 可能影响未来行为的强偏好；
- 含有 prompt injection 或命令式文本的内容。

这些内容可以进入 `needs_review` 或保持低权重，但不应自动变成强长期事实。

### 4.4 Dreaming 机制

本插件中的 dreaming 不是一个单独的大系统，而是 `life_memory_reflect` 的内部 background 流程。它对应 OpenClaw 的经验：hot path 只快速捕获，background 再整理、评分、晋升。

建议分成三个 phase：

```text
light:
  低成本整理。收集 young 记忆、去重、补 tags、更新 evidence_count，
  识别明显重复、明显低价值、明显不该保存的内容。

REM:
  反思候选。发现跨多条记忆的主题、模式、冲突、替代关系，
  生成 pattern_candidate、conflict candidates、daily reflection draft。

deep:
  晋升/归档。根据阈值把高置信、低风险、多证据记忆晋升为 active/reinforced，
  把低价值或过期内容归档，把足够稳定的 pattern_candidate 晋升为 abstract_experience。
```

phase 的核心原则：

- `store` 不做复杂推理，保证对话中快速写入和低延迟；
- `reflect(light)` 可以频繁运行，成本低；
- `reflect(REM)` 可以较少运行，负责模式和冲突；
- `reflect(deep)` 最保守，只做高置信晋升和归档；
- 高风险内容即使在 deep phase 也不能自动强晋升。

建议 deep phase 的晋升信号包括：

```text
frequency              出现次数
relevance              召回相关性
query_diversity         被不同查询/场景命中的多样性
recency                 最近是否仍然有效
multi_day_consolidation 是否跨多天重复出现
concept_richness        是否有清晰 primary_category/tags/context
feedback_score          用户反馈
conflict_penalty        是否和旧记忆冲突
safety_penalty          是否敏感或疑似注入
```

这套机制对应我们的自动化目标：人工不审核时，系统也能通过多信号门控提高正确率。

### 4.5 会话有效信息与每日 reflection report

不建议把“每日记忆”做成主记忆来源。更稳妥的设计是把源头改成 **会话有效信息记忆**：

```text
会话历史 raw transcript             = 原始材料，不直接进入 life_memory 主库
会话有效信息 effective candidates   = 从会话中抽取出来的候选事实/事件/偏好/纠错/模式
每日 reflection report              = 对当天候选和 evidence 的结构化审计报告
长期 life memory                    = 通过阈值晋升后的稳定事实或模式
```

原因：

- 如果把所有日记都保存，就和会话历史没有本质区别，噪音太大；
- 如果只做自由文本压缩，容易发生语义丢失或总结错误；
- 固定模板是有用的，但模板应该承载“候选记忆和证据”，不是写流水账；
- 每日层适合做聚合、审计和反思，不适合作为长期事实源；
- 只要每条候选能反查到原始 session/message/evidence，就能兼顾自动化和可审计。

因此建议：

```text
MVP:
  不做“每日记忆本体”；
  先做会话有效信息抽取；
  抽取结果变成 young memory、memory_evidence、declined trace 或 conflict candidate；
  daily report 只作为手动/按需触发的 report-only 审计结果；
  可以写入 reflection_reports 表，但不自动成为晋升信号。

MVP+:
  增加自动定时 daily/weekly reflection report；
  report 可以作为 promotion signal 和 audit artifact；
  不能单独把一条总结晋升为长期事实，必须引用支持它的 memory/evidence ids。
```

会话有效信息抽取可以使用固定模板，避免自由总结失真：

```text
session_id:
time_range:
messages_reviewed:

personal_fact_candidates:
  - content:
    tags:
    evidence_refs:
    confidence:
    suggested_action: store/update/ignore

personal_preference_candidates:
  - content:
    tags:
    evidence_refs:
    scope:
    action_boundary:
    suggested_action: store/update/ignore

personal_pattern_candidates:
  - content:
    tags:
    repeated_evidence:
    supporting_memory_ids:
    status: young/pattern_candidate
    suggested_action: keep_candidate/needs_review

corrections_or_conflicts:
  - old_memory_id:
    new_evidence:
    suggested_action: supersede/needs_review

do_not_store:
  - content_summary:
    reason:

notes:
  tags can include event, relationship, habit, routine, lifestyle, food,
  family, work_style, emotion_pattern, or other narrow meanings.
```

Agent 可以读会话历史，但边界必须清楚：

- 对话热路径只处理当前用户请求和明确记忆意图；
- 会话结束后可以读取本次 session transcript，抽取 effective memory candidates；
- 每日 reflection 不应重新读所有原始历史，而应读当天 candidates、evidence、traces；
- 长期晋升只看 evidence links、反馈、重复出现次数、冲突状态和阈值；
- raw transcript 不应成为普通 recall 的内容来源。

会话内容来源需要在实现里显式处理，不能假设插件天然拥有完整 history：

```text
优先来源:
  Hermes session lifecycle hook 提供的 session_id/session_ref；
  插件用只读方式查询 Hermes state.db 或已有 session search 能力；

备选来源:
  调用 life_memory_reflect(mode="session") 时显式传入 redacted transcript；

不可用时:
  返回 not_found/unsupported；
  不静默伪造 session report；
  写 trace 说明 session transcript unavailable。
```

无论来源是哪一种，session extraction 只产生候选和 evidence，不把 raw transcript 复制进 life_memory 主库。

如果后续要导出 report，建议目录是：

```text
$HERMES_HOME/life_memory_review/memory-journal/
├── sessions/
│   ├── 2026-06-01-session-1030.md
│   └── ...
├── daily/
│   ├── 2026-06-01.md
│   └── ...
└── ...
```

session report 中应该区分：

```text
effective_candidates      本次会话中可能值得记忆的有效信息
stored_young              已低延迟写入 young 的内容
corrections               用户纠错或替代旧记忆的内容
conflicts                 和旧记忆冲突的内容
do_not_store              明确不应进入长期记忆的内容
source_refs               可追溯的 session/message/evidence ids
```

daily report 中应该区分：

```text
candidate_memories        当天出现过的候选记忆
evidence_added            当天新增 evidence
conflicts                 和旧记忆冲突的内容
promotion_candidates      建议晋升的内容
archive_candidates        建议降权/归档的内容
do_not_promote            不应晋升的临时内容
```

关键规则：会话有效信息候选可以进入 `young` 或 `memory_evidence`；MVP 中 daily report 只帮助审计，不提高 `promotion_score`，不能创建 durable memory，也不能绕过分类、安全、敏感信息和冲突检查。MVP+ 才允许 daily/weekly report 作为 promotion signal。

## 5. 模型介入边界

模型不应该成为所有记忆操作的默认路径。更稳妥的定位是：

```text
规则/数据库负责状态变化和安全约束
模型负责语义判断、压缩总结、候选生成
高风险动作先生成建议，不直接落地
```

也就是说，模型不是“记忆数据库管理员”，而是“语义分析器”和“后台反思器”。

### 5.1 不需要模型介入的情况

这些操作应尽量走确定性规则和 SQLite 查询：

- 通过 `memory_id` 读取、反馈、删除、归档；
- `deleted`、`archived`、`sensitive` 的基础过滤；
- content hash 或高度相同文本的重复检测；
- FTS/keyword 的初步召回；
- access count、last accessed、feedback score 的更新；
- 基于明确阈值的衰减、归档、低风险晋升；
- trace 写入、tombstone 写入、schema migration。

原则是：凡是能用确定性规则稳定完成的事情，不要为了“智能”而调用模型。

### 5.2 对话热路径中的模型介入

`life_memory_store` 是热路径，目标是低延迟。它应先做便宜的规则门控：

```text
explicit remember intent?
life/technical/profile/no_save boundary?
sensitivity?
prompt-injection risk?
obvious duplicate?
```

只有在语义边界不清楚时，才调用一次小而快的模型。适合模型判断的内容包括：

- 这句话是不是生活记忆；
- 是不是技术项目记忆或用户画像；
- 是否只是一次性闲聊、临时情绪或不确定猜测；
- primary_category、tags、importance、confidence 的初始建议；
- 是否包含敏感信息或 prompt injection 风险；
- 用户是否明确要求长期保存。

热路径中的模型只能输出结构化建议，例如：

```text
classification
classification_confidence
primary_category
tags
importance
confidence
sensitivity
injection_risk
should_store
reason
```

它不应该在单条消息上直接生成 `abstract_experience`，也不应该直接做复杂合并、长期画像修改或强行为偏好修改。

如果模型超时或不可用：

- 明确、低风险、生活范围内的“请记住”内容可以先存为 `young/pending`；
- 边界不清楚的内容应保守拒绝或进入低权重候选；
- 所有 fallback 都要写 trace，说明没有使用模型或模型不可用。

### 5.3 后台 dreaming 中的模型介入

模型更适合放在 background，而不是对话热路径。

```text
light:
  默认不需要模型。做规则化清理、计数、明显重复检测、低价值归档候选。

REM:
  可以调用模型。用于发现主题、冲突、重复模式、pattern_candidate、
  session/daily reflection report draft，以及“这些记忆可能共同说明什么”。

deep:
  可以调用模型，但必须保守。模型可以解释候选、评估支持证据、
  生成 abstract_experience 草案；是否真正晋升仍由阈值、安全规则、
  evidence links 和 review_status 决定。

daily:
  可以调用模型写每日 reflection report，但 report 只是 derived evidence/audit artifact，
  不能单独创建长期事实。
```

### 5.4 必须保守处理的模型输出

下面这些场景里，模型最多只能给建议，不能直接强写入稳定记忆：

- 敏感信息；
- 和高置信旧记忆冲突的内容；
- 多条非完全重复记忆的合并；
- `pattern_candidate -> abstract_experience`；
- 会影响未来行为边界的强偏好；
- 用户没有明确表达保存意图的推断；
- 模型识别到 prompt injection、命令式文本或策略性指令；
- `forget` 查询命中多个候选，无法唯一定位。

这些情况应进入 `needs_review`、保持低权重，或返回 `ambiguous` 让用户确认。

### 5.5 模型输出不是事实源

模型输出应该被看作候选判断或反思结果，而不是原始事实。

因此：

- 模型生成的结论必须能追溯到原始 memory/evidence ids；
- `abstract_experience` 必须标记为 `inference`；
- session/daily reflection report 必须标记为 derived evidence/audit artifact；
- 模型不能绕过分类、安全、敏感信息、冲突和注入检查；
- 模型判断应写入 trace，至少记录 task、reason、confidence 和 redacted input/output。

最终原则是：

```text
原始 evidence 是事实来源
模型输出是解释和候选
数据库状态机决定能否晋升
```

## 6. 建议新增字段

为了支持“自动化优先 + 可审计”，后续 data model 可以补充：

```text
review_status:
  pending
  approved
  rejected
  needs_review
  auto_promoted

evidence_count
source_count
unique_query_count
days_seen_count
promotion_score
last_confirmed_at
valid_from
valid_until
scope
authority
action_boundary
injection_risk
promotion_reason
decay_reason
```

其中：

- `review_status` 表示人工/自动审核状态；
- `evidence_count` 表示有多少次证据支持；
- `source_count` 表示证据来源是否单一；
- `unique_query_count` 表示这条记忆被多少种不同查询或场景命中过；
- `days_seen_count` 表示它是否跨多天出现；
- `promotion_score` 表示 dreaming/deep phase 的自动晋升分数；
- `last_confirmed_at` 表示最近一次被确认；
- `valid_from` / `valid_until` 表示时间有效性；
- `scope` 表示适用范围；
- `authority` 表示来源权威性；
- `action_boundary` 表示这条记忆是否会影响未来行为，以及何时可以安全使用。
- `injection_risk` 表示这条记忆是否含有可疑命令、提示词或行为操控文本。

## 7. 召回策略

自动化系统最怕乱召回，所以召回应保守：

```text
宁可少召回，不要乱召回。
```

默认规则：

- `deleted` 永不普通召回；
- `archived` 默认不召回；
- 敏感记忆只有在用户请求范围明确时召回；
- `young` 记忆降低权重；
- 冲突旧事实如果被 superseded，不作为 current fact 返回；
- 抽象经验必须标记为 inference；
- 无相关记忆时返回 not_found/abstention，不编造生活背景。

## 8. Markdown 同步定位

Markdown 同步不是第一版自动化的核心路径。它的定位是：

```text
export for review
optional edit surface
debug/audit report
```

如果未来实现同步，建议规则是：

- SQLite 仍是 runtime source of truth；
- `memory-library/*.md` 仍按只读展示处理，用户不要直接改这些文件当作数据库更新；
- 用户修改已确认记忆时，应在 `change-requests.md` 写修改意图，例如 update、forget、mark_outdated、merge、split；
- `change-requests.md` 中每条请求必须引用 `memory_id`，不能只靠自然语言模糊匹配；
- Markdown 修改只表达审核/修改意图，不直接绕过安全规则；
- sync 时重新做 validation；
- sync action 也必须写 trace；
- deleted 内容不应重新导出原文。

## 9. 外部参考设计调研

联网调研后，可参考的成熟方向如下：

- Generative Agents 把 agent memory 分为 observation、reflection、planning。它的关键经验是：原始经历先进入 memory stream，reflection 再从多条经历中合成更高层 insight；召回时综合 recency、importance、relevance。
  参考：https://arxiv.org/abs/2304.03442
- MemoryBank 用 memory strength/forgetting curve 处理记忆强化和遗忘，适合借鉴为 `promotion_score`、TTL/decay 和 archive 的规则来源；MVP 只落地 `recent_state` 14 天 TTL。
  参考：https://arxiv.org/abs/2305.10250
- LangGraph 明确区分 hot path 写记忆和 background 写记忆：hot path 立即可用但增加延迟；background 降低主流程延迟并把 memory management 和应用逻辑分离。
  参考：https://langchain-5e9cc07a.mintlify.app/oss/python/concepts/memory
- Mem0 的 add pipeline 是信息抽取、冲突解决、存储。它说明模型可以介入抽取和冲突判断，但如果跳过 inference，重复和冲突处理会变差。
  参考：https://docs.mem0.ai/core-concepts/memory-operations/add
- Zep 区分 facts 和 summaries，并明确不建议只靠 summaries grounding response；summary 应和可追溯 facts/timestamps 一起使用。
  参考：https://help.getzep.com/v2/facts
- A-MEM 借鉴 Zettelkasten，用结构化 note、keywords、tags、links 组织 agent memory。MVP 可借鉴 tags/links，不必第一版实现完整 graph/Zettelkasten。
  参考：https://arxiv.org/abs/2502.12110
- CoALA/LangGraph 的 memory taxonomy 把 semantic、episodic、procedural 分开。对本插件的启发是：生活记忆、技术事实、用户画像、行为规则不要混在同一层。
  参考：https://arxiv.org/abs/2309.02427

这些参考共同指向一个结论：

```text
事件级事实先保存
后台 reflection 再总结
summary/abstract insight 必须可追溯
召回必须有权重和过滤
模型可以参与语义处理，但不应绕过状态机
```

## 10. 对开放问题的当前建议

### 10.1 session 抽取的会话来源

已定：MVP 优先采用 **方案 A**，也就是插件在 `life_memory_reflect(mode="session")` 中通过 `session_ref` 只读 Hermes `state.db` 或已有 session search 能力获取会话内容。

规则：

```text
优先:
  session_ref -> Hermes state.db/session search -> redacted transcript

备选:
  调用方显式传入 transcript

失败:
  返回 not_found/unsupported
  不伪造 session report
  写 trace 说明 session transcript unavailable
```

这样自动化更高，也更符合“人工不干预也能运行”的目标。实现时要把 Hermes 会话读取封装在 adapter 层，避免业务逻辑直接依赖 Hermes state.db 的表结构。

### 10.2 young 记忆是否参与 recall

已定：参与，并且比原建议更宽松。刚记下的内容既然已经通过写入门控，就应该能较快影响后续回答，但仍不能和稳定记忆同权。

默认规则：

```text
young 可参与 recall
score multiplier = 0.50
每次最多返回 2 条 young
必须明显相关
不得返回 sensitive/restricted young
不得作为 action boundary 的依据
返回时标记为 candidate / low_confidence
```

理由：Generative Agents 和 LangGraph 都强调新信息要能尽快影响后续交互，但 LangGraph 也提醒 hot path 会带来质量和延迟风险。因此 `young` 可以进入召回，但不能和稳定长期记忆同权。

### 10.3 自动晋升阈值

建议第一版使用保守、可解释的阈值，而不是黑箱分数。

```text
young -> active:
  confidence >= 0.70
  importance >= 0.45
  injection_risk < 0.20
  sensitivity == normal
  no conflict
  and (
    explicit remember intent
    or evidence_count >= 2
    or useful recall once
  )

major_life_fact fast path:
  explicit_user_request == true
  primary_category == personal_fact
  classification_confidence >= 0.85
  confidence >= 0.85
  importance >= 0.80
  injection_risk < 0.10
  no unresolved conflict
  not speculative/conditional/future plan
  if sensitive: explicit long-term storage authorization
  result: young -> active, review_status = auto_promoted
  not allowed: direct reinforced or abstract_experience

active -> reinforced:
  evidence_count >= 3
  days_seen_count >= 2
  promotion_score >= 0.70
  no unresolved conflict
  and (
    positive feedback
    or unique_query_count >= 2
  )

active -> archived:
  low access + low importance + low confidence
  or valid_until expired
  or superseded by newer memory
```

`promotion_score` 第一版可以由规则线性组合，不需要模型学习：

```text
promotion_score =
  0.25 * confidence
+ 0.20 * importance
+ 0.20 * normalized_evidence_count
+ 0.15 * normalized_days_seen_count
+ 0.10 * feedback_signal
+ 0.10 * recall_usefulness
- conflict_penalty
- sensitivity_penalty
- injection_penalty
```

### 10.4 pattern_candidate 到 abstract_experience

已定：允许低风险自动晋升，但阈值要比普通记忆高，并且必须标记为 inference。MVP 不只做 dry-run；当 `apply=true` 且满足全部阈值时，可以自动创建 reflected abstract experience。

```text
pattern_candidate -> abstract_experience:
  evidence_count >= 4
  days_seen_count >= 3
  source_count >= 2
  promotion_score >= 0.85
  confidence >= 0.80
  sensitivity == normal
  injection_risk < 0.10
  no unresolved conflict
  all supporting memory/evidence ids recorded
```

不满足这些条件时，只生成 `pattern_candidate` 或 `needs_review`。

这借鉴 Generative Agents 的 reflection：高层 insight 来自多条 observation，而不是单条输入。

### 10.5 会话有效信息与 daily report 的 MVP 定位

建议 MVP 的事实入口是会话有效信息抽取，而不是 daily summary。Daily report 可以在 MVP 内做 report-only，不作为事实源。

```text
MVP:
  session effective extraction:
    从本次会话抽取候选事实、事件、偏好、纠错和冲突；
    能直接通过门控的内容进入 young memory 或 memory_evidence；
    不该保存的内容只写 declined trace。

  life_memory_reflect(mode="daily", apply=false)
  生成 daily reflection report 草案
  默认写入 reflection_reports 表
  Markdown 只通过 export 工具导出
  不创建 durable life memory
  不直接晋升 abstract_experience

MVP+:
  daily/weekly report 可作为 promotion signal
  但必须链接 source_memory_ids/source_evidence_ids
```

Zep 的 facts/summaries 设计支持这个方向：report 适合概览和审计，但 grounding 应依赖可追溯 facts/evidence。

### 10.6 Markdown review/export 是否 MVP 必做

已定：`life_memory_export_review` 要做，放进第一批 tasks。五个核心工具和 SQLite 状态机仍然优先，但 export review 不再推迟到未来版本。

第一版只做 export-only：

```text
读取 SQLite
导出 memory-journal、memory-library、review-needed、archive、change-requests 模板
不读取 Markdown 改动
不反向同步
不修改数据库
```

### 10.7 action-sensitive life memory 的表达

建议用四个字段组合表达：

```text
scope:
  适用范围，如 general / home / health / relationship:<id>

valid_from / valid_until:
  时间有效性和过期时间

authority:
  user_direct / assistant_inferred / session_extract / reflection_report / reflection

action_boundary:
  这条记忆可以影响什么，不能影响什么
```

例子：

```text
content: 用户晚上更适合处理复杂思考。
scope: general
authority: reflection
action_boundary: 可用于安排建议；不可自动改变日程、发送消息或执行工具。
```

### 10.8 是否需要 life_memory_export_review

已定：需要，第一批 tasks 要包含它，但只做导出，不做反向同步。

```text
life_memory_export_review:
  读取 SQLite
  导出 memory-journal、memory-library、review-needed、archive、change-requests 模板
  每条包含 memory_id、status、review_status、reason、supporting ids
  不读取 Markdown 改动
  不修改数据库
```

反向同步会引入解析、冲突、安全校验和误改风险，不适合作为第一版核心路径。

### 10.9 热路径是否允许模型调用

已定：第一版规则优先，模型可选，不做硬依赖；但 timeout 可以稍微放宽，避免边界模糊时过早 fallback。

```text
默认:
  hot path 规则分类 + 低延迟写入

可选:
  只有边界不清时调用小模型
  timeout = 1500ms
  失败就 fallback 到 conservative behavior

主要模型使用位置:
  session extraction / REM / deep / daily background reflection
```

LangGraph 的 hot path/background 对比支持这个选择：热路径写入能让新记忆立即可用，但会增加延迟和复杂度；background 更适合复杂 memory management。

## 11. 已定 MVP 决策

1. `session` 抽取优先读 Hermes `state.db`/session search；显式 `transcript` 作为备选。
2. `young` 记忆参与 recall，权重放宽到 `0.50`，每次最多 2 条。
3. `pattern_candidate -> abstract_experience` 允许低风险自动晋升，但必须满足高阈值、记录 supporting ids，并标记 inference。
4. `life_memory_export_review` 放进第一批 tasks，只做 export-only，不做反向同步。
5. 热路径模型调用可选，timeout 默认 `1500ms`；超时或失败走保守 fallback。

## 12. 用户视角审核

从普通用户角度，第一版最重要的问题不是内部状态机是否完整，而是用户能不能回答三个问题：

```text
你记住了我什么？
哪些记忆不确定或需要我确认？
我想让你忘记/修改时应该怎么做？
```

当前设计已经覆盖：

- 用户可以通过 `life_memory_export_review` 查看 `memory-library/`，知道系统长期记住了什么；
- 用户可以看 `memory-journal/sessions/` 和 `memory-journal/daily/`，理解最近会话抽取了什么；
- 用户可以看 `review-needed.md`，知道哪些内容系统不敢自动确认；
- 用户可以看到 `change-requests.md` 模板，知道未来修改入口在哪里；
- 敏感信息不会静默长期保存，必须先确认；
- 短期状态用 `recent_state` 14 天 TTL，避免“最近很累”变成永久画像。

第一版需要注意的用户体验风险：

```text
change-requests.md:
  MVP 不读取这个文件，必须在文件顶部明确写“当前版本不会自动处理这里的修改”。

review-needed.md:
  只放真正需要确认的内容，不能变成另一个杂乱 inbox。

memory-library:
  默认展示少量用户标签：状态、来源、操作、ID。
  详细字段放折叠区或调试区，避免像数据库导出。

sensitive memory:
  询问用户时必须说清楚“长期保存”和“摘要/完整内容”的区别。

daily report:
  MVP 中必须标明“这是审计报告，不是事实源，也不会直接改变长期记忆”。
```

产品结论：设计可以进入 tasks。第一版应优先验证“记得准、看得懂、能忘掉”，不要把重点放在复杂分类或复杂衰减上。
