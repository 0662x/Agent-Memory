---
layout: post
title: "从分代记忆到 Agent Memory OS：长期记忆的生命周期治理"
date: 2026-05-28 21:50:00 +1000
categories: ai-agent memory architecture
lang: zh
description: "从分代记忆出发，讨论 Agent Memory OS 的生命周期治理：存储、检索、晋升、压缩、归档、遗忘与 skill 化。"
translation_key: agent-memory-os-lifecycle-governance
primary: true
permalink: /posts/agent-memory-os-lifecycle-governance-zh/
---

# 从分代记忆到 Agent Memory OS：长期记忆的生命周期治理

上一篇文章里，我用 JVM 分代回收来类比 Agent 的长期记忆机制。核心想法很简单：Agent 的记忆不应该只是“把东西存下来”，而应该像一个有生命周期的系统。新信息先进入短期区域，被观察、被使用、被验证；真正有长期价值的信息再被压缩、晋升、沉淀；重复执行的流程则应该进一步整理成 skill；过期、错误、低价值的信息则应该被归档或遗忘。

这篇文章想继续往下走一步。

如果上一篇更像是一个设计直觉：为什么 Agent 记忆应该分代，那么这篇想讨论的是：这个想法和现有 Agent Memory 研究有什么关系？它和 RAG、向量数据库、长期记忆库、文件式记忆有什么区别？它和 OpenClaw、Hermes、Claude Code、Letta/MemGPT、Mem0/OpenMemory 这类现成系统相比，补的到底是哪一层？如果真的要实现一个分代记忆系统，工程上大概应该怎么做？

我越来越觉得，长期 Agent 的记忆问题，真正难的不是保存信息，而是治理信息。

它不是一个单纯的数据库问题，而是一个 Memory OS 的问题。

## 1. Agent 记忆不只是“存储”，而是“管理”

很多人在讨论 Agent 记忆时，第一反应是：那就把聊天记录存下来，或者放进向量数据库，需要的时候检索出来。

这当然是有用的。没有持久化，Agent 每次都会像第一次见面一样；没有检索，历史信息就算存在，也很难重新进入当前任务。

但这仍然只解决了一半问题。

因为长期记忆的核心不只是：

```text
这段信息能不能被保存？
```

而是：

```text
这段信息值不值得保存？
它应该保存多久？
它属于当前任务、某个项目，还是全局长期偏好？
它是事实、偏好、流程、错误经验，还是技能候选？
它是否已经过期？
它是否和新的信息冲突？
它是否应该被压缩？
它是否应该被晋升？
它是否应该被遗忘？
```

如果没有这些判断，记忆系统很容易变成一个越来越大的仓库。看似什么都记住了，但真正需要的时候，Agent 反而更容易被噪声干扰。

这就像一个人不是因为记住了所有细节才变聪明，而是因为他能从经历中提炼经验，忘掉无用噪声，保留重要模式，并把反复做的事情变成能力。

所以，一个成熟的 Agent 记忆系统，不应该只是 memory storage，而应该是 memory management。

## 2. 现有研究其实已经走向了“记忆管理”

近几年很多关于 LLM Agent Memory 的研究，其实都在从不同角度靠近这个问题。

MemGPT 是一个很典型的例子。它把 LLM 类比成操作系统，用分层记忆和虚拟上下文管理来解决上下文窗口有限的问题。它关心的是：哪些信息应该留在当前上下文里，哪些信息应该放到外部记忆中，什么时候再把外部信息调回当前上下文。

这和操作系统的内存管理很像，也和我前面用 JVM 分代回收做类比有相通之处。区别在于，MemGPT 更关注“上下文窗口如何扩展”，而分代记忆更关注“记忆如何随着使用过程被筛选、晋升和沉淀”。

MemoryBank 则更接近人类长期记忆。它不仅让模型从历史交互中召回相关记忆，还引入了类似遗忘曲线的思想：记忆会随着时间衰减，但重要记忆可以被强化。这一点非常关键，因为它说明 Agent 不应该机械地永久保存所有信息，而应该允许遗忘。

Generative Agents 里的 memory stream 也很有启发。它不是简单按时间顺序取最近几条记忆，而是在检索时综合考虑近期性、重要性和相关性。也就是说，一段记忆是否应该被召回，不只取决于它是不是最近发生，还取决于它对当前情境有没有意义。

A-MEM 进一步强调了记忆组织。它借鉴 Zettelkasten 卡片盒方法，把记忆做成带有标签、关键词、上下文描述和关联关系的知识网络。这样记忆不再是孤立条目，而是可以互相连接、互相更新的结构。

AgeMem 这类更新的研究则把记忆操作本身变成 Agent 可以主动选择的动作。Agent 不只是被动使用一个外部记忆库，而是可以决定什么时候存储、什么时候检索、什么时候更新、什么时候总结、什么时候丢弃。

这些研究虽然侧重点不同，但共同指向一件事：Agent 记忆不是简单的“存储历史”，而是一个持续变化的管理系统。

## 3. 现有 Agent 系统已经做到了哪一步？

如果只从概念上讨论分代记忆，很容易显得像一个抽象设计。但现实中，很多 Agent 项目其实已经在不同程度上做了类似的事情。它们没有完全使用“分代记忆”这个名字，但已经分别实现了文件记忆、项目记忆、会话检索、自动总结、后台整理和外部记忆提供商等能力。

所以更准确的说法不是：分代记忆要从零发明一套全新的记忆系统。

相反，它更像是对现有 Agent 记忆机制的一种重新组织和解释。

### OpenClaw：最接近分代记忆的工程实现

OpenClaw 的记忆机制和分代记忆非常接近。它使用 Markdown 文件作为记忆的真实来源，其中 `MEMORY.md` 用来保存长期事实、偏好和重要决定；`memory/YYYY-MM-DD.md` 用来保存每日记录；`DREAMS.md` 则用于保存 dreaming sweep 的总结，方便人类审查。

这个设计已经很像：

```text
MEMORY.md
= 长期记忆 / 老年代

memory/YYYY-MM-DD.md
= 每日记忆 / 新生代

DREAMS.md
= 记忆整理日志 / GC 日志
```

OpenClaw 更进一步的地方在于，它不只是保存文件，还提供 memory search，用关键词检索、向量检索和混合检索索引这些记忆文件。也就是说，它既保留了 Markdown 的可读性，又引入了数据库和向量检索的召回能力。

更值得注意的是 OpenClaw 的 dreaming 机制。它会把短期记忆中的强信号整理出来，通过不同阶段进行处理，再把足够重要的内容晋升到 `MEMORY.md`。这已经非常接近我所说的 memory GC 和 memory consolidation。

不过，OpenClaw 的重点仍然更偏“工作区文件 + 检索 + 后台整理”。它已经有了短期到长期的晋升机制，但如果从分代记忆角度看，还可以进一步明确不同记忆对象的生命周期状态，比如 young、survivor、old、archived、skill_candidate。这样每条记忆不只是放在某个文件里，而是有更清楚的状态和晋升路径。

### Hermes：轻量、克制、适合随身 Agent

Hermes 的内置记忆机制更克制。它主要使用两个核心文件：`MEMORY.md` 和 `USER.md`。前者保存 Agent 学到的环境事实、项目约定、工作流经验；后者保存用户偏好、交流风格和个人资料。

这个设计的优点是非常轻量。它强迫 Agent 只保存真正重要、紧凑、信息密度高的内容，避免长期记忆无限膨胀。

同时，Hermes 还提供 session search。完整会话被存入 SQLite，并通过 FTS5 做全文搜索。这样，`MEMORY.md` 和 `USER.md` 只负责保存关键事实；更完整、更冷的历史记录则留在 session database 中，需要时再检索。

从分代记忆角度看，Hermes 的结构可以理解成：

```text
USER.md
= 用户长期偏好 / Permanent Memory

MEMORY.md
= Agent 长期工作记忆 / Old Generation

SQLite session search
= 历史会话归档 / Cold Archive
```

Hermes 的优势是边界清晰、成本低、容易运行。它的问题是内置层次相对少，daily memory、project memory、dreaming、skill candidate 这些层需要依赖外部 provider 或用户自己设计。

如果要把 Hermes 扩展成更完整的分代记忆系统，最自然的方向就是在现有 `MEMORY.md` / `USER.md` / session search 之外，增加 daily notes、project memory 和 skill promotion 机制。

### Claude Code：项目级自动记忆

Claude Code 的 auto memory 更偏 coding agent 场景。它会在项目目录下维护自动记忆，让 Claude 记住构建命令、调试经验、架构笔记、代码风格偏好和工作流习惯。

这个设计很适合代码项目，因为 coding agent 的记忆很多时候不是全局用户偏好，而是项目上下文。比如一个仓库怎么跑测试、某个模块为什么这样设计、某个 bug 之前怎么修过。这些信息不应该污染全局长期记忆，而应该被限制在项目范围内。

从分代记忆角度看，Claude Code 的强项是 project memory。它说明了一个重要原则：记忆必须有作用域。不是所有长期信息都应该全局可见，有些记忆只应该在当前 repo 或当前项目中生效。

但 Claude Code 的记忆更像“项目笔记 + 自动维护”。它解决了项目上下文延续问题，但对记忆如何跨 daily、project、long-term、skill 之间流动，并没有提供特别完整的分代生命周期模型。

### Letta / MemGPT：更接近 Memory OS 的研究路线

Letta/MemGPT 更像是从系统架构角度重新设计 Agent Memory。它把记忆分成 recall memory、archival memory 和 memory blocks。Recall memory 更接近完整对话历史，archival memory 更接近外部长期知识库，memory blocks 则是可以被放进上下文窗口并由 Agent 自我更新的结构化记忆。

这和分代记忆有很强的对应关系：

```text
memory blocks
= 当前可见的工作记忆

recall memory
= 可检索的会话历史

archival memory
= 外部长期知识库

context rewriting
= 记忆压缩和重写
```

Letta/MemGPT 的优势是理论更完整，也更接近“LLM Operating System”。它把有限上下文窗口当成需要管理的资源，让 Agent 主动把信息写入、移出、召回和更新。

不过，从分代记忆角度看，它更强调上下文管理和外部记忆调用，而不是特别强调“记忆对象从新生代到老年代再到 skill 的生命周期”。也就是说，它解决的是“Agent 如何拥有可管理的长期上下文”，而分代记忆进一步强调“长期上下文里的信息如何成熟、筛选、晋升和遗忘”。

### Mem0 / OpenMemory：跨工具共享的记忆层

Mem0 和 OpenMemory 更像是把记忆做成独立基础设施。OpenMemory 通过 MCP 给 Cursor、Claude、VS Code 等工具提供共享的持久记忆层，让不同 coding agent 能够访问同一套用户偏好、编码习惯和项目上下文。

这种方式的价值在于跨工具。用户今天用 Claude Code，明天用 Cursor，后天用 VS Code 插件，如果每个工具都有一套独立记忆，就会重复配置，也很难形成连续经验。OpenMemory/Mem0 想解决的就是这个问题：让记忆成为一个独立服务，而不是某个 Agent 的私有附属品。

从分代记忆角度看，这类系统更适合作为底层 memory infrastructure。它负责存储、检索、共享和管理记忆，但上层仍然需要一套规则来决定：

```text
哪些记忆只是短期观察？
哪些记忆应该成为长期偏好？
哪些记忆只属于某个项目？
哪些记忆应该跨工具共享？
哪些记忆应该被删除或降权？
哪些重复流程应该变成 skill？
```

所以，Mem0/OpenMemory 可以作为分代记忆的基础设施，但分代记忆仍然需要定义生命周期治理逻辑。

## 4. 对比之后，分代记忆的位置更清楚了

把这些系统放在一起看，可以发现它们各自解决了 Agent Memory 的一部分问题：

```text
OpenClaw
= 文件式记忆 + daily notes + dreaming + 检索

Hermes
= 轻量长期记忆 + 用户画像 + session archive + 外部 provider

Claude Code
= 项目级 auto memory

Letta / MemGPT
= Memory OS / 上下文窗口管理 / recall + archival memory

Mem0 / OpenMemory
= 跨工具共享的持久记忆基础设施
```

而分代记忆想补的不是某个单独功能，而是一个统一视角：

```text
记忆应该如何从短期记录变成长期经验？
如何从长期经验变成稳定技能？
如何判断一条记忆是否应该晋升、压缩、降级、归档或遗忘？
如何避免所有记忆都混在一个平面里？
```

所以，分代记忆不是要替代 OpenClaw、Hermes、Claude Code、Letta 或 Mem0。它更像是这些系统之上的一层解释框架和治理框架。

如果说 OpenClaw 给出了很好的文件和 dreaming 实现，Hermes 给出了轻量克制的随身记忆，Claude Code 强调项目记忆，Letta/MemGPT 强调 Memory OS，Mem0/OpenMemory 强调跨工具基础设施，那么分代记忆强调的是：

```text
记忆不是静态存储，而是动态生命周期。
```

这也是它和现有系统最大的区别。

现有系统大多在回答：

```text
记忆放在哪里？
如何检索？
如何注入上下文？
如何跨 session 保持连续？
```

而分代记忆更关注：

```text
记忆如何成长？
如何被验证？
如何晋升？
如何变成技能？
如何过期？
如何被遗忘？
```

这两个问题并不冲突。真正成熟的 Agent Memory，应该同时具备现有系统的存储和检索能力，也具备分代记忆的生命周期治理能力。

## 5. 分代记忆的核心价值：给记忆一个生命周期

我觉得“分代记忆”这个视角最有价值的地方，是它明确提出了记忆生命周期。

很多系统会讨论短期记忆和长期记忆，但中间过程往往比较模糊。信息是怎么从短期进入长期的？什么情况下应该晋升？什么情况下应该被遗忘？什么情况下应该从事实记忆变成 skill？这些问题如果不设计清楚，长期记忆迟早会变脏。

分代记忆可以把这个过程拆开：

```text
当前上下文
→ Daily Memory
→ Project / Topic Memory
→ Long-term Memory
→ Skill / Stable Procedure
→ Archive / Forgetting
```

这不是单纯按时间分层，而是按信息的成熟度和作用范围分层。

当前上下文只服务眼前任务。它很重要，但很短命。

Daily Memory 保存当天发生的重要过程，相当于把现场先接住。它不要求高度精炼，但需要保留足够的上下文，以便后续回顾。

Project / Topic Memory 保存某个项目或主题中持续有用的信息。它不一定适合进入全局长期记忆，但在相关项目里非常重要。

Long-term Memory 保存真正稳定、未来会反复影响 Agent 行为的信息，比如用户偏好、长期规则、常用技术栈、重要项目背景、高成本踩坑经验。

Skill 则是更进一步的沉淀。当某类任务被反复执行，Agent 不应该只是“记住做过”，而应该把它整理成“下次怎么做”。

Archive 保存完整历史或低频冷数据。它不常驻上下文，但需要时可以检索回来。

这套结构的重点是：记忆不是静态的。它会移动，会压缩，会晋升，会降级，会被重写，也会被遗忘。

## 6. 为什么只靠 RAG 不够

RAG 很有用，但 RAG 本身不是完整的记忆机制。

RAG 解决的是“如何从外部资料中找回相关内容”。它适合做召回，适合从大量历史、文档、网页、代码、日志里找到和当前任务相关的信息。

但 RAG 不天然解决这些问题：

```text
哪些内容应该进入长期记忆？
哪些内容只是临时噪声？
哪些内容已经过期？
哪些内容应该被合并？
哪些内容应该被压缩？
哪些内容应该被删除？
哪些流程应该变成 skill？
```

如果一个 Agent 把所有聊天记录都丢进向量数据库，然后每次 top-k 检索，它确实不会完全忘记过去。但问题是，检索出来的东西可能只是“语义相关”，不一定“当前可靠”。

比如用户三个月前配置过一个路径，但后来已经改了；Agent 检索到了旧路径，然后继续使用它，就会出错。

又比如某次 debug 过程里有很多错误尝试，如果这些错误尝试没有被整理，未来检索时可能会把失败路径也召回出来，干扰判断。

所以 RAG 更像记忆系统里的搜索工具，而不是治理机制。

分代记忆要解决的是更上层的问题：

```text
RAG 负责找回。
分代机制负责判断什么值得留下、如何留下、留下多久、何时更新、何时遗忘。
```

一个好的 Agent Memory 系统，应该把 RAG 放进更大的生命周期框架里，而不是把 RAG 当成全部答案。

## 7. 文件式记忆、数据库记忆和分代记忆并不冲突

有些系统喜欢用 markdown 文件保存记忆，比如 `MEMORY.md`、`CLAUDE.md`、project notes、topic files。这个做法的优点是透明、可编辑、可审计。用户可以直接打开文件看 Agent 记住了什么，也可以手动修改。

有些系统喜欢用 SQLite、向量数据库、全文检索或者图数据库保存记忆。这个做法的优点是结构化、可查询、可扩展，适合大量历史和自动化检索。

但我觉得二者不是对立关系。

分代记忆不是在说“一定要用文件”或者“一定要用数据库”。它更像是一套组织原则。你可以用 markdown 实现，也可以用 SQLite 实现，也可以用向量数据库实现，还可以混合使用。

比如：

```text
MEMORY.md
= 当前项目的轻量索引

SQLite / FTS
= 可检索的历史事实和事件记录

Vector DB
= 语义召回历史会话和文档

Topic files
= 人类可读的项目经验总结

Skill files
= 可复用操作流程

Archive
= 原始 session logs 和冷数据
```

这样就比较合理。

文件负责透明性，数据库负责查询能力，向量检索负责语义召回，分代机制负责生命周期治理。

真正重要的不是存储介质，而是系统有没有能力回答：

```text
这条记忆现在处于哪一代？
为什么它在这里？
它什么时候被验证过？
它未来什么时候应该被检查、压缩或删除？
```

## 8. 一个可落地的分代记忆结构

如果真的要实现，我会把每条记忆都看成一个带元数据的对象，而不是一段普通文本。

一条记忆至少应该包含：

```text
id: 唯一标识
content: 记忆内容
type: fact / preference / project / procedure / warning / skill_candidate
scope: global / project / topic / session
source: user_explicit / task_result / observation / imported_doc
created_at: 创建时间
last_accessed_at: 最近访问时间
access_count: 使用次数
importance: 重要性评分
confidence: 置信度
status: young / survivor / old / archived / skill_candidate
related_files: 相关文件或证据
conflicts: 可能冲突的记忆
```

这样 Agent 才能管理记忆，而不是只保存记忆。

比如用户说：

```text
以后生成英文内容时，英文下面都附中文翻译。
```

这类信息应该是：

```text
type: preference
scope: global
source: user_explicit
importance: high
confidence: high
status: old 或 permanent
```

再比如今天 debug 了一个 Hermes skill，发现某个路径写错会导致工具加载失败。这条信息刚出现时可以进入 daily memory：

```text
type: warning
scope: project
source: task_result
importance: medium
confidence: medium
status: young
```

如果后续这个问题反复出现，或者这个经验被多次用于修复类似问题，它就可以晋升为 project memory，甚至整理成 skill 的 troubleshooting 部分。

## 9. 记忆晋升规则：不能只看频率

一个常见误区是：反复出现的信息才重要。

确实，高频信息通常值得保存。比如用户反复要求某种写作风格，或者某个项目反复使用同一套部署命令，这些都应该进入长期记忆。

但有些信息只出现一次，也非常重要。

比如用户明确说“以后都按这个结构写”；或者某次任务中确定了一个项目的核心技术路线；或者某个配置是整个系统后续运行的基础。这些信息不需要反复出现，也应该直接进入长期记忆。

所以我觉得记忆晋升至少应该有两条路径。

第一条是普通晋升：

```text
出现
→ 被保存到 daily memory
→ 多次被访问
→ 多次对任务有帮助
→ 被压缩总结
→ 晋升为 project / long-term memory
```

第二条是特殊晋升：

```text
出现一次
→ 但用户明确要求或意义重大
→ 直接进入 long-term / permanent memory
```

这和 JVM 分代回收里的某些对象直接进入老年代很像。有些对象不是因为活得久才重要，而是它一开始就很特殊。

工程上可以用一个简单的 promotion score 来辅助判断：

```text
promotion_score
= importance
+ access_count
+ user_confirmation
+ task_success_signal
- age_decay
- conflict_penalty
```

但这个公式只是辅助，不应该机械化。Agent 记忆里最重要的信号永远是：用户明确表达、任务成功结果、反复复用价值和现实证据。

## 10. 记忆压缩：从事件变成经验

长期记忆不能保存太多原始过程，否则它会变成另一个聊天记录仓库。

一条好的长期记忆，应该是压缩后的经验，而不是完整流水账。

比如原始记录可能是：

```text
用户今天尝试通过 SSH 连接 Windows，第一次密码失败，后来确认 OpenSSH Server 已安装，Parsec 路径是 C:\Program Files\Parsec\parsecd.exe，双击可以打开，最终判断可以通过该路径启动。
```

压缩后应该变成：

```text
用户的 Windows 上 Parsec 可执行文件路径为 C:\Program Files\Parsec\parsecd.exe；如果需要远程启动 Parsec，可以优先尝试该路径。
```

这就是从 episode 到 semantic memory 的转化。

Daily Memory 保存事件，Long-term Memory 保存经验。

如果没有压缩，Agent 会记住很多细枝末节；如果压缩太狠，又会丢掉重要上下文。所以更合理的方式是保留两层：

```text
长期记忆：保存精炼结论
历史归档：保存完整证据
```

这样平时用长期记忆即可，需要追溯时再去 archive 里查原始记录。

## 11. 从记忆到 Skill：Agent 真正变强的地方

我觉得很多长期记忆系统低估了 skill 的重要性。

如果 Agent 只是记住“之前做过什么”，它的能力增长是有限的。真正有价值的是，它能从反复执行的任务中沉淀出稳定流程。

比如用户经常让 Agent 做这些事：

```text
写 Hermes skill
配置 SSH 远程控制 Windows
处理 Git 分支冲突
整理技术博客
把中文内容改成人话
把论文方法论变成 SOUL.md
```

这些内容如果每次都重新推理，就很浪费。

更好的方式是：当某类任务反复出现，系统应该把它标记为 skill_candidate，然后在 review 阶段整理成 skill。

一个 skill 不只是记忆，而应该包含：

```text
触发条件
适用场景
前置检查
执行步骤
常用命令
失败处理
回滚方案
用户偏好
示例输出
```

这和 JVM 的 JIT 类比也很自然。反复执行的逻辑不应该一直停留在解释执行阶段，而应该被优化成更高效、更稳定的路径。

对于长期 Agent 来说，事实记忆让它“知道更多”，而 skill 让它“做得更好”。

## 12. Review / Dreaming：记忆系统真正的核心

如果只保存，不整理，任何记忆系统都会腐烂。

Daily Memory 会越来越长，Project Memory 会混入过期内容，Long-term Memory 会保留旧偏好，Skill 也可能因为环境变化而失效。

所以 review 或 dreaming 是整个系统的核心。

它可以每天、每周或者在项目结束后运行，主要做几件事：

```text
清理低价值 daily memory
把重复信息合并
把重要事件压缩成长期经验
把项目内信息限制在项目范围
把全局偏好提升到 long-term memory
把重复流程标记为 skill_candidate
检查旧记忆是否过期
发现冲突记忆并请求用户确认
```

这一步相当于 memory GC。

没有 GC 的长期记忆，迟早会变成垃圾堆。没有 dreaming 的 Agent，也很难真正从经验中成长。

人类不是在每一刻都整理记忆。很多整理发生在事后：复盘、睡眠、总结、写笔记、形成习惯。Agent 也应该有类似机制。

## 13. 记忆也需要可解释和可审计

越强的记忆系统，越需要透明。

因为 Agent 如果会长期记住用户偏好、项目细节、操作路径、账号环境、写作习惯，它就必须让用户知道：

```text
它记住了什么？
为什么记住？
从哪里来的？
什么时候最后验证过？
能不能修改？
能不能删除？
会不会跨项目使用？
```

否则长期记忆会从能力变成负担。

一个好的 Agent Memory UI 应该允许用户查看不同层级的记忆：

```text
Global Memory
Project Memory
Daily Memory
Skill Candidates
Archived Sessions
Conflicting Memories
```

并且支持用户直接操作：

```text
确认
修改
删除
降级
晋升
限制作用范围
整理成 skill
```

这点非常重要。

因为很多记忆判断不能完全自动化。Agent 可以建议，但用户应该有最终控制权。尤其是涉及隐私、身份、长期偏好和项目规则时，记忆系统必须可编辑、可撤销、可审计。

## 14. 分代记忆的风险

当然，分代记忆不是万能方案。

第一个风险是复杂度。

如果系统设计得太复杂，可能还没带来明显收益，就先增加了一堆维护成本。尤其是个人 Agent，如果每条记忆都要打分、分类、迁移、验证，系统很容易过度工程化。

第二个风险是错误晋升。

有些信息只是临时情况，却被 Agent 当成长期规则保存下来。比如用户某次为了赶作业要求“写得简单一点”，这不一定代表用户永远喜欢简单风格。如果错误晋升，就会影响未来所有回答。

第三个风险是错误遗忘。

有些低频信息虽然不常用，但非常重要。如果只按访问频率清理，可能会删除关键配置、重要偏好或长期项目背景。

第四个风险是旧记忆污染。

过去正确的信息，未来可能变错。软件版本会变，路径会变，项目需求会变，用户偏好也会变。长期记忆如果不更新，就会制造幻觉。

第五个风险是隐私和边界。

长期 Agent 越会记忆，越要谨慎处理用户数据。不是所有东西都应该被保存，也不是所有记忆都应该跨场景使用。

所以，分代记忆必须配合三个原则：

```text
可解释
可编辑
可删除
```

没有这三个原则，长期记忆越强，风险越大。

## 15. 分代记忆不是替代现有系统，而是组织它们

最后我觉得需要强调一点：分代记忆不是要替代 RAG、向量数据库、markdown memory、SQLite、FTS、session archive 或 skill system。

它更像是把这些东西组织起来的一套上层框架。

可以这样理解：

```text
RAG
= 召回机制

Vector DB / FTS / SQLite
= 存储和检索基础设施

Markdown Memory
= 人类可读的记忆界面

Session Archive
= 原始证据层

Project Memory
= 作用域隔离

Long-term Memory
= 稳定经验层

Skill System
= 流程能力层

Review / Dreaming
= 记忆治理和生命周期管理
```

分代记忆真正强调的是：信息不应该一进入系统就被永久保存，也不应该在任务结束后立刻消失。它应该先被接住，再被观察，再被筛选，再被压缩，再被晋升或遗忘。

这就是 memory lifecycle governance。

## 16. 一个理想中的 Agent Memory OS

如果把上面的想法合在一起，一个比较理想的 Agent Memory OS 可能长这样：

```text
Current Context
= 当前任务工作区，只服务眼前推理和执行

Daily Memory
= 每日记录，保存短期现场和过程性信息

Project / Topic Memory
= 项目级或主题级上下文，只在相关任务中加载

Long-term Memory
= 稳定事实、偏好、规则、重要经验

Permanent Memory
= 用户明确要求长期遵守的核心偏好和规则

Session Archive
= 完整历史会话，冷数据，需要时检索

Memory Search
= 关键词、全文、向量、混合检索

Review / Dreaming
= 定期整理、压缩、晋升、遗忘

Skill Candidate
= 反复出现但还没有固化的流程

Skill System
= 被沉淀出来的稳定操作能力
```

它背后的关键不是某一个数据库，也不是某一种文件格式，而是一套完整的记忆流动机制：

```text
发生
→ 记录
→ 检索
→ 验证
→ 压缩
→ 晋升
→ 归档
→ 遗忘
→ 技能化
```

Agent 真正变强，不是因为它保存了更多文字，而是因为它能让这些文字逐渐变成结构、经验和能力。

## 17. 结论：长期 Agent 需要的不是更大的记忆，而是更好的记忆治理

长期 Agent 的目标不是像硬盘一样保存一切。

保存一切看起来很安全，但实际上会让系统越来越臃肿。真正有用的记忆系统，应该像一个会整理经验的人：知道哪些只是临时细节，哪些是项目规则，哪些是长期偏好，哪些是高成本踩坑，哪些任务应该沉淀成技能，哪些旧信息应该被丢掉。

这也是我觉得分代记忆这个类比有价值的地方。

它提醒我们，Agent 的长期记忆不应该是一个静态仓库，而应该是一个动态系统。它有新生代，有项目层，有老年代，有归档层，有技能区，也有垃圾回收和记忆巩固。

从这个角度看，真正成熟的 Agent Memory 不只是：

```text
我能记住你说过什么。
```

而应该是：

```text
我能从我们一起做过的事情里整理出经验。
我知道什么该临时保留，什么该长期保存。
我知道什么该忘掉，什么该变成技能。
我会随着时间变得更顺手，而不是变得更臃肿。
```

这才是长期 Agent 真正值得期待的地方。

## 参考方向

这篇文章主要参考和对照了几类系统与研究方向：OpenClaw 的文件式记忆、daily notes 和 dreaming；Hermes 的 `MEMORY.md`、`USER.md`、session search 与 memory providers；Claude Code 的项目级 auto memory；Letta/MemGPT 的 recall memory、archival memory 和 memory blocks；Mem0/OpenMemory 的跨工具持久记忆层；以及 MemGPT、MemoryBank、Generative Agents、A-MEM、AgeMem 等关于长期记忆、分层记忆、记忆检索和记忆管理的研究。
