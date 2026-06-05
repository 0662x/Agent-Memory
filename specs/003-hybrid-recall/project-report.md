# Hybrid Recall 阶段项目报告

**项目阶段**：003 Hybrid Recall For Life Memory
**当前状态**：完成
**报告日期**：2026-06-06 Australia/Sydney
**最近自动化验证**：`uv run python -m pytest`，137 项测试全部通过

## 1. 阶段目标

`003-hybrid-recall` 的目标是把 `life_memory` 从主要依赖词面匹配的召回，升级为可解释的 hybrid recall：

- lexical candidate retrieval 继续作为稳定 fallback；
- semantic/vector candidate retrieval 负责补足 paraphrase、间接问法和中英文日常表达；
- SQLite `life_memories` 仍然是事实源；
- `memory_embeddings` 只是可重建的派生索引；
- lifecycle、sensitivity、deletion、expiry、supersession 和 automatic activation 的安全边界不能被 vector search 绕过。

这个阶段承接了前两个阶段：

- `001-life-memory-plugin` 已经完成分类、保存、召回、反馈、遗忘、导出、reflection 和 runtime routing；
- `002-memory-activation` 已经完成回答前自动判断是否需要生活记忆，并注入 bounded data-only context；
- `003-hybrid-recall` 让 explicit recall 和 automatic activation 都能在安全边界内处理 paraphrased memory lookup。

## 2. 已完成能力

### 2.1 派生语义索引

插件新增 `memory_embeddings` 相关能力：

- 为 accepted life memories 建立派生 embedding metadata；
- 记录 provider、model id、dimension、content hash 和 status；
- 检测 stale、missing、incompatible、skipped 和 failed embedding rows；
- 支持 rebuild/audit report；
- 对 restricted raw content 保持外部 provider guardrail。

当前实现使用 deterministic local fake embedding provider 和 SQLite JSON vector storage。这个选择避免新增运行时依赖，也让测试在无网络、无外部模型的环境下可重复。

### 2.2 Hybrid Candidate Merge

召回路径现在可以合并两类候选：

- lexical candidates：来自现有 keyword/CJK n-gram/FTS 或 fallback search；
- semantic candidates：来自 fresh compatible embeddings 的 vector similarity。

合并按 `memory_id` 去重，并在结果中保留 `recall_sources` 和 score components。这样可以看出一条 memory 是由词面命中、语义命中，还是两者共同支持。

### 2.3 Time-Aware Rerank

最终排序不只看相似度，还会综合：

- lexical score；
- semantic score；
- confidence；
- importance；
- feedback score；
- evidence count；
- lifecycle status；
- `valid_until` / recent-state expiry；
- supersession links；
- current/historical mode。

这避免了“旧事实因为语义相似而排在当前事实前面”的问题。例如旧的 coconut-water memory 被新的 soy-milk memory supersede 后，正常 recall 会偏向当前事实。

### 2.4 Privacy And Lifecycle Boundary Preservation

Hybrid recall 继承并强化已有边界：

- `deleted` 不返回；
- expired recent state 不作为当前事实返回；
- archived 默认排除；
- restricted 和未授权 sensitive 不进入 automatic injection；
- stale/incompatible embeddings 不参与 active vector search；
- superseded current facts 不会作为当前事实优先返回；
- activation 仍然在 recall 后执行 stricter-than-recall injection filter。

这保证 vector retrieval 只是候选发现机制，不是事实权威。

### 2.5 Automatic Activation Integration

`002-memory-activation` 现在可以通过 narrow adapter 使用 hybrid recall：

- activation gate 的决策语义不变；
- hook failure 仍然 fail closed；
- injection block 仍然 data-only；
- max memory count 和 character budget 不变；
- hybrid score fields 不改变注入契约；
- embedding provider failure 时 fallback 到 lexical 或 no context，不抛出到 LLM call path。

## 3. 测试和验证

最近全量测试：

```text
2026-06-06 Australia/Sydney
uv run python -m pytest
137 passed in 0.75s
Python 3.11.15, pytest 9.0.3
```

覆盖范围包括：

- embedding vector validation、normalization、cosine similarity；
- fake provider determinism 和 provider metadata；
- repository embedding schema、upsert、fetch、stale detection、rebuild report；
- lexical/vector candidate merge；
- English 和 Chinese paraphrase fixture；
- privacy/lifecycle filtering；
- supersession-aware rerank；
- automatic activation hybrid regression；
- 10,000-row scale smoke；
- existing store/recall/feedback/forget/export/reflection/routing regression。

### 3.1 手动 Hermes Smoke

`specs/003-hybrid-recall/quickstart.md` 记录了 2026-06-03 的手动 Hermes smoke：

- Hermes CLI：`/Users/oliver/.local/bin/hermes`
- Hermes version：`Hermes Agent v0.15.1 (2026.5.29)`
- 通过真实 Hermes 对话保存中文生活偏好；
- memory 写入 `life_memory.db`；
- embedding row 处于 `ready`；
- paraphrased query 通过 pre-LLM activation 注入相关 memory；
- smoke memory 最后通过 `life_memory_forget` soft delete 清理。

这验证了从真实 Hermes runtime 到 plugin store、embedding index、activation、hybrid recall、context injection 和 cleanup 的闭环。

## 4. 当前边界

这个阶段完成的是 hybrid recall 架构和本地可重复实现，不是生产级 embedding 平台：

- 默认 provider 仍是 deterministic fake/local provider；
- SQLite JSON vector storage 足够支撑当前 prototype 和测试，但不是大规模 ANN index；
- 尚未接入真实本地 embedding 模型或外部 embedding API；
- 尚未实现后台自动全库周期性 reindex 调度；
- semantic retrieval 不参与事实决策，事实 currentness 仍由 SQLite lifecycle/evidence/supersession 状态决定；
- Markdown review 仍然是只读导出，不支持 reverse sync。

这些边界是有意保留的：当前阶段优先验证安全可解释的 hybrid recall，而不是引入不可控外部依赖。

## 5. 阶段结论

`003-hybrid-recall` 已经完成阶段目标：

- paraphrased English/Chinese life-memory query 可以通过 hybrid recall 命中；
- lexical fallback 保持可用；
- semantic index 是可审计、可重建的派生索引；
- privacy、lifecycle、deletion、expiry、sensitivity 和 supersession 边界没有被削弱；
- automatic activation 可以使用 hybrid recall，同时保持 bounded data-only injection；
- 全量测试和真实 Hermes smoke 均已通过。

下一阶段建议转向 `004-review-sync`：让用户在 Markdown `change-requests.md` 中表达删除、修正、合并、确认等审查意见，并通过安全解析和确认流程同步回 SQLite。
