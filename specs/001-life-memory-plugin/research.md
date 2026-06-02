# Research: Hermes 分层生活记忆插件

## Decision: 使用 Hermes standalone user plugin

**Rationale**: Hermes 通用插件系统会扫描 `$HERMES_HOME/plugins/<name>/`，目录插件需要 `plugin.yaml` 和 `__init__.py::register(ctx)`。standalone plugin 可以通过 `ctx.register_tool()` 注册工具，符合本功能需要，也不会占用 Hermes `memory.provider` 的唯一 provider 槽位。

**Alternatives considered**:

- **MemoryProvider**：拒绝。它会进入 `memory.provider` selection，和“生活记忆不要做成 memory.provider”的约束冲突。
- **Bundled plugin under hermes-agent/plugins**：拒绝。会修改 Hermes main project，不符合外部插件开发目标。
- **MCP server**：拒绝。MVP 非目标，增加部署和权限面。

## Decision: 插件源码目录与 runtime mount 分离

**Rationale**: 源码仓库是 `/Users/oliver/Projects/hermes-life-memory`，但 Hermes 发现插件时要求已安装插件目录根部直接包含 `plugin.yaml` 和 `__init__.py`。因此开发期 symlink 应指向 `/Users/oliver/Projects/hermes-life-memory/plugins/life_memory`，而不是 repo root。

**Alternatives considered**:

- **Symlink repo root 到 `$HERMES_HOME/plugins/life_memory`**：拒绝。repo root 不直接包含 `plugin.yaml` 和 `__init__.py`，Hermes 无法按 directory plugin 加载。
- **放进 `/Users/oliver/.hermes/hermes-agent/plugins`**：拒绝。会污染 Hermes bundled plugin 目录。

## Decision: 使用 stdlib SQLite + 可选 FTS5

**Rationale**: SQLite 满足本地、单用户、可审计、易测试的 MVP 需求。结构化字段支持生命周期、反馈、trace、supersede/merge 关系；FTS5 可用时提供足够快的关键词召回，10,000 条规模下无需引入向量数据库。

**Alternatives considered**:

- **PostgreSQL/pgvector**：拒绝。超出 MVP，增加服务依赖。
- **Graph database**：拒绝。A-MEM 类 linked memory 可以先用 SQLite link table 表达。
- **纯 JSON 文件**：拒绝。查询、事务、状态迁移和 trace 维护会更脆弱。

## Decision: MVP 使用规则驱动分类与安全边界

**Rationale**: spec 要求先验证原型效果，且强调可解释、可测试、用户可控。规则驱动分类更容易覆盖技术记忆排除、用户画像分离、敏感信息拒存和 injection 防护。LLM-assisted classifier 可作为未来增强，但不应成为第一版治理动作的不可解释依赖。

**Alternatives considered**:

- **所有分类交给 LLM**：拒绝。测试不稳定，也容易把未授权内容自动写入长期记忆。
- **完全依赖用户手工分类**：拒绝。无法验证自动边界过滤价值。

## Decision: Forget 采用 tombstone/redaction

**Rationale**: spec 同时要求 soft deletion 可追踪和被遗忘内容不再召回。计划采用 tombstone：保留 memory id、状态、时间、哈希和删除 trace，但把 content/tags/context 从普通表中清空或替换为 redacted marker。这样后续 recall/reflection 不会使用内容，同时能审计“曾经删除过这条记录”。

**Alternatives considered**:

- **只把 status 改成 deleted，保留全文**：拒绝。容易通过 trace、debug 或错误查询再次暴露。
- **硬删除整行**：拒绝。无法满足内部 trace 和冲突链路追踪。

## Decision: Recall 输出 bounded structured results

**Rationale**: 生活记忆召回应返回有界结果，并附带 id、分类、状态、原因和 rank signals，方便用户纠正或删除。默认过滤 `deleted`、`archived`、敏感记忆和技术内容；宽泛查询不能倾倒全部数据库。

**Alternatives considered**:

- **自动注入所有匹配记忆到 prompt**：拒绝。容易造成污染和长期安全风险。
- **只返回文本列表**：拒绝。缺少 identifier 和 trace 会削弱 feedback/forget 可控性。

## Decision: Reflection 只做 lightweight maintenance

**Rationale**: 现代 agent memory 研究强调 manage 阶段，但 MVP 不应实现复杂 autonomous reflection。第一版只做重复检测、merge candidate、`recent_state` 14 天 TTL 归档、archive stale、pattern_candidate/abstract_experience 的规则化候选生成或低风险自动晋升。高风险动作优先 dry-run 或需要明确 apply。

**Alternatives considered**:

- **自动合并和自动生成所有抽象经验**：拒绝。单条或弱证据容易变成错误长期事实。
- **完全不做 reflection**：拒绝。无法验证 spec 中的 memory quality 目标。

## Decision: Daily report 只做 report-only audit artifact

**Rationale**: 用户担心 daily memory 如果记录过多会退化成会话历史，如果压缩过强又会丢失语义。MVP 采用“会话有效信息抽取优先，daily report 审计优先”的设计：daily report 可以帮助用户查看一天内有哪些候选信息和整理动作，但它本身不创建 durable memory，不作为 promotion signal，也不改变 `promotion_score`。

**Alternatives considered**:

- **把 daily summary 作为主要事实源**：拒绝。容易把总结偏差写成长期事实。
- **完全不做 daily report**：暂不采用。会降低用户审查系统行为的可见性。

## Decision: 增加只读 Markdown review/export

**Rationale**: SQLite 适合运行时管理、查询、事务和状态机，但普通用户更容易通过 Markdown 审查“系统记住了什么”。`life_memory_export_review` 将 SQLite 导出为只读 Markdown 视图，包括 `memory-library/`、`memory-journal/`、`review-needed.md`、`change-requests.md` 和可选 `archive.md`。MVP 不做 Markdown 到 SQLite 的反向同步，避免人工编辑和数据库状态冲突。

**Alternatives considered**:

- **只保留 SQLite，不提供 Markdown**：拒绝。人工审查成本太高。
- **Markdown 与 SQLite 双向同步**：暂缓。第一版容易引入冲突处理和权限问题。

## Decision: Session extraction 通过 adapter 访问 Hermes 会话数据

**Rationale**: 会话有效信息是比 daily summary 更可靠的候选事实入口。MVP 先通过 adapter 只读读取 Hermes session/state 数据，显式 `transcript` 作为 fallback。业务逻辑不直接依赖 Hermes `state.db` schema，以免 Hermes 内部结构变化破坏 life-memory。

**Alternatives considered**:

- **直接在业务逻辑里读 state.db 表结构**：拒绝。耦合过深，后续维护风险高。
- **只接受手动 transcript**：拒绝。自动化程度不足，无法验证会话有效信息抽取。

## Decision: 敏感信息采用 confirmation-first

**Rationale**: 敏感生活信息不能因为模型抽取或用户含糊表达就进入长期记忆。缺少明确长期授权时，`life_memory_store` 返回 `needs_confirmation`，不创建 durable memory，并询问是否长期保存以及保存摘要还是完整内容。默认倾向保存摘要；如果用户明确选择完整保存，原文只作为敏感 SQLite 内容处理，召回和 Markdown 导出仍必须更保守。

**Alternatives considered**:

- **完全拒绝所有敏感信息**：拒绝。用户可能确实需要长期记住某些重要事实。
- **只要用户说了就保存**：拒绝。长期记忆和普通对话的风险不同。

## Decision: 本地 evaluation fixture 覆盖长期记忆能力

**Rationale**: LongMemEval/LoCoMo/A-MEM/Mem0 等工作说明，长期记忆系统的关键不只是 recall，还包括 extraction、temporal update、abstention、forget 和安全边界。MVP 使用小型手写 fixture，足以在不复刻完整 benchmark 的情况下测试原型有效性。

**Alternatives considered**:

- **接入完整公开 benchmark**：拒绝。规模过大，不适合作为 Hermes 插件第一阶段验收。
- **只测单个 happy path**：拒绝。无法验证边界和安全目标。

## Decision: 暂不注册 slash command 或 CLI command

**Rationale**: spec 明确的能力是五个核心 life-memory tools 加一个只读 `life_memory_export_review`。为了保持 MVP 聚焦，第一版只通过 `ctx.register_tool()` 暴露工具，测试中直接调用 handler。后续如果用户需要交互式 inspect UI，再增加 `/life-memory` slash command。

**Alternatives considered**:

- **同时做 CLI/slash 管理界面**：暂缓。会扩大任务面，且当前原型重点是工具契约、数据治理和召回质量。

## Research References

- A-MEM: Agentic Memory for LLM Agents, https://arxiv.org/abs/2502.12110
- Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory, https://arxiv.org/abs/2504.19413
- LongMemEval, https://arxiv.org/abs/2410.10813
- LoCoMo, https://arxiv.org/abs/2402.17753
- AgeMem, https://arxiv.org/abs/2601.01885
- Memory for Autonomous LLM Agents survey, https://arxiv.org/abs/2603.07670
- Privacy and memory safety references, https://arxiv.org/abs/2502.13172 / https://arxiv.org/abs/2503.03704 / https://arxiv.org/abs/2605.17830
