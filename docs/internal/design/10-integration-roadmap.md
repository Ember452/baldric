---
title: "10 — 上游能力集成路线图"
---

本文规划 Baldric 的下一阶段：把相关
Tau 项目已构建的特性移植**进 Baldric 本体**——代码合并进主干，而不是作为独立安装外挂——同时保持 harness 小、分层、可读。

它与记录基础 pi→tau 移植（phase 0–23）的 [00 — Roadmap](./00-roadmap.md) 互补。那些阶段描述基底；本文件是新计划。共同的讨论枢纽是 GitHub issue #2。

## 调研的源项目

每行是一个位于 [huggingface/tau](https://github.com/huggingface/tau) 下游的项目（Basic Memory 与 SWE-agent 是同领域相邻项目，我们参考而非 fork）。所有项目的完整使用权均已从作者处获得，许可不构成障碍。

| 项目 | 是什么 | 对 Baldric 的价值 | 与当前 Baldric 的重叠 |
|---|---|---|---|
| [tau-subagents](https://github.com/rian-dolphin/tau-subagents) | Claude-Code 式 subagent：`agent` 工具委托给范围受限的进程内子 session | 最大的单项净新能力 | 无（今天没有 subagent 系统） |
| [MiniAgent](https://github.com/zhoushui521-alt/MiniAgent)（上游 PR tau#755） | (a) 畸形工具参数反馈；(b) 运行策略（cost/token/连续错误 → steer/cancel） | (b) 净新；(a) 是小增强 | (a) 大部分已被 `tool_arguments.py` 覆盖 |
| [tua-agent](https://github.com/anuphongsrinawong/tua-agent) | Rust 特化 fork；携带超出 Rust 的通用部件 | 自纠错循环、git checkpoint/回滚、后台评审、命令面板、diff 查看器、多 session 标签、权限提示、仪表盘 | 命令补全、transcript 选择、项目信任门、provider 重试、prompt 缓存已存在 |
| [basic-memory](https://github.com/basicmachines-co/basic-memory) | 本地优先的 Markdown 知识库：实体/观察/关系图、语义搜索、MCP | 持久记忆子系统（务实范围） | 无（今天只有内存 transcript） |
| [tau_hub](https://github.com/mmpouya/tau_hub) | 跨服务持久化/注册表；providers/agents/tools/skills/configs/sessions 存于可插拔 DB；API key 静态加密 | 可选基础设施：静态加密凭据、替代 session backend、注册表 | 本地 JSONL session + `credentials.py` 覆盖默认路径 |
| [tau-huggingface](https://github.com/alejandro-ao/tau-huggingface) | Hugging Face inference-provider 路由（`/hf route`）+ 侧栏 provider 状态 | 小众打磨 | API（`set_inference_provider`、侧栏）已存在 |
| [SWE-agent](https://github.com/SWE-agent/SWE-agent) | Princeton/Stanford 的自主 SWE 任务研究 agent（SWE-bench、EnIGMA）。**非 tau 系**——工具/agent-loop 设计的*相邻参考*，不是 fork 对象。已被 [mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent) 取代（以更简单的为模板） | 仅设计思想：提交前评审、编辑期 lint 反馈、窗口式搜索/编辑、单配置 agent、批处理/评测 harness | 仅参考；影响 Phase 4–5，不单独立阶段 |

## Baldric 已具备的能力（已核实）

这些事实降低移植风险，每次移植前逐 phase 重新核对：

- 打包 extension 是一等公民。`built_in_extensions.py` 声明
  `BUILT_IN_EXTENSIONS`，`extensions/runtime.py` 启动时自动加载（今天的 `llama.cpp` 内置就是这么工作的）。内置代码位于
  `src/baldric_coding/extensions/builtins/`，随 wheel 发布。
- extension API 已暴露较新衍生项目依赖的接缝：
  `context.ui.components`（`supports_components`、`set_slot_widget`、
  `open_main_view`、`register_key_interceptor`）、`context.ui.sidebar`，以及
  `set_inference_provider` / `inference_provider`。
- tool-call 参数在执行前对照每个工具的 JSON schema 校验
  （`baldric_agent/tool_arguments.py`）。
- session 支持分支、恢复、compaction 与导出。

## 集成原则

1. **extension 优先的混合。** 可插拔能力以打包的 built-in
   extension 交付。只有真正属于内核的才移入核心包（coding 层的运行策略、记忆存储原语、编辑后 hook）。
   这保持 harness 精简，**并保住创作路径——你以后可以在同样的接缝上加自己的功能**。
2. **尊重层边界。** `baldric_agent` 保持对 CLI、
   Textual、Rich、文件布局独立；UI 层消费事件。
3. **先证据后代码。** 每个 phase 先把上游源码与当前 Baldric 做差异对比，只移植真实差距，绝不重复添加已有之物。移植前确认所需的 extension API 已存在。
4. **原子、测试、文档。** 每次提交一个连贯变更；扩展前先增加/扩展确定性测试（fake provider/工具）；更新
   `dev-notes/`，行为面向用户时更新 `website/content/`。
5. **保持 CI 绿。** `uv run pytest`、`ruff check`、`ruff format --check`、`mypy`。

## 分发与开箱体验

普通安装（`pip install baldric`、`uv tool install baldric`）必须**完整**：打包 extension 随 wheel 发布并自动注册，用户不需要额外安装或启用任何东西。这正是今天 `llama.cpp`
内置的行为。

唯一的例外是拖入沉重或可选第三方依赖的能力。Baldric 当前声明**没有任何 extras**（每个依赖都是硬性基础依赖）。本路线图为真正可选、沉重的部件增加 `[project.optional-dependencies]`——缺失时优雅降级：

- `baldric[semantic-memory]` — 记忆搜索的 embedding / cross-encoder 重排
  （Basic Memory 的向量层）。默认记忆保持标准库 `sqlite3` FTS + 关键词
  召回，功能完整。
- `baldric[hub-postgres]` / `[hub-mongo]` / `[hub-redis]` — 外部 hub 数据库
  backend。默认 hub backend 是 TinyDB（纯 Python）/ SQLite（标准库）。

系统工具（非 pip 依赖）在相关处假定存在：worktree 隔离与 checkpoint 需要 `git`——对编码 agent 是合理前提。

## 阶段计划

每个 phase 独立可交付，作为各自经测试、有文档的变更落地。排序先低风险/高价值，依赖先于被依赖，最大、侵入最强的编辑（Textual 应用）与可选基础设施靠后。

### Phase 1 — 运行策略 + 畸形参数加固（MiniAgent）
- **参考：** MiniAgent（上游 PR tau#755）——运行策略监视器与畸形参数反馈。
- **形态：** coding 层特性（`RunPolicyMonitor`）+ 一个小的 provider 层审计。
- **范围：** 可配置的单次运行成本上限、累计 token 预算与
  连续错误轮阈值；动作 `steer`（请模型收尾）或
  `cancel`（当前轮后硬停）。配置穿透 CLI / TUI / RPC，
  并在 session 替换与关闭时管理监视器。默认关闭。
- **去重：** 审计 `tool_arguments.py` 与 provider 流解析器；只在 Baldric 当前覆盖薄弱处采纳 MiniAgent 的畸形参数原文反馈——不重复造。
- **验证：** 每个阈值与动作的 fake-provider 测试；每条 provider 路径的畸形参数测试；内部重试/steering 不重置运行策略。
- **文档：** dev-note + 配置参考小节。

### Phase 2 — Subagent（tau-subagents）
- **参考：** tau-subagents（其自身移植自 pi-subagents）——subagent 系统。
- **形态：** 打包的 built-in extension（经组件接缝的 Textual 组件）。
- **范围（子步骤，各自测试）：**
  1. 内核：`agent` 工具、前台/后台运行、`get_subagent_result`、
     `steer_subagent`、agent 类型 `general` / `explore`、并发队列、
     带宽限的轮次上限、resume。
  2. 隔离与保真：`fork`（继承完整对话、父级 model/tools/
     prompt）、`isolation: worktree`、`inherit_context` 摘要、`prompt_mode: append`。
  3. 调度：cron / interval / one-shot 任务，带每 session 存储。
  4. UI：agents 条 + 对话查看器 + `/agents` 菜单；通知卡片；
     用量上报。
- **推迟到 Phase 3：** 每个 agent 的 `memory:` frontmatter。
- **验证：** spawn、前台 vs 后台、fork 字节一致前缀、worktree commit/branch 命名、队列
   排序、轮次上限先 steer 后 cancel、调度解析的确定性测试（fake provider/工具）。
- **文档：** dev-note；"Use Baldric" 分区下的 "Subagents" 指南。

### Phase 3 — 持久记忆子系统（basic-memory + tau-subagents memory）
- **参考：** basic-memory 提供记忆存储/格式与检索；tau-subagents 提供每 agent 记忆接线。
- **形态：** 记忆存储原语（coding 层）+ `memory` 工具 + prompt
   注入；检索接口保持可插拔。
- **范围（先务实）：** 带 frontmatter 的 Markdown 笔记 + `MEMORY.md`
   索引；read/write/edit/search 工具；注入 system prompt 的记忆块；local/project/user 范围。先做关键词 + `sqlite3` 全文召回。
- **可选后置：** 知识图谱的观察/关系，以及 `baldric[semantic-memory]` 之后的语义搜索 +
   重排。
- **回写：** 存储就位后，给 Phase 2 的 agent 类型补上 `memory:` frontmatter。
- **验证：** 存储往返、索引重建、范围优先级、注入
   截断；每 agent 记忆的读写 vs 只读工具集。
- **文档：** dev-note；"Memory" 概念指南。

### Phase 4 — 通用 agent 智能（tua-agent，非 Rust 部分）
- **参考：** tua-agent 的自纠错 / checkpoint / 评审形态；SWE-agent 的提交前评审与编辑期 lint 反馈。
- **形态：** 与 loop、session 组合的 coding 层 hook。
- **范围：** 自纠错循环（编辑后运行验证命令，失败反馈回有限次数的自动修复轮）；编辑前后的 git checkpoint/回滚；可选后台评审。配置开关参考 tua 但保持领域中立。
- **范围外：** Rust 工具、Rust system prompt、Rust profiles/skill。
- **验证：** 纠错上限与停止条件的 fake-tool 循环；对临时 git 仓库的 checkpoint 创建/回滚；禁用时无自纠错。
- **文档：** dev-note。

### Phase 5 — TUI 生产力特性（tua-agent）
- **参考：** tua-agent 的命令面板 / diff 查看器 / 多 session 标签 / 权限提示；SWE-agent 的 diff/lint 交互模型。先与 Baldric 既有的补全、transcript 选择、项目信任门做差异对比。
- **形态：** Textual 层，适配器边界之后；**只补差距**。
- **范围：** 命令面板、diff 查看器、多 session 标签、交互式
   权限批准/拒绝提示——先对照既有补全、transcript 选择与项目信任门避免重复。
- **风险注记：** `tui/app.py` 非常大；优先用组件接缝与小而
   可回退的编辑；增加组件/交互测试。
- **文档：** dev-note；TUI 参考更新。

### Phase 6 — 可选基础设施（tau_hub）
- **参考：** tau_hub——静态加密、注册表、DB 支撑的 session。按下述范围，只回移静态加密与可插拔 session backend，不整体收编该包。
- **形态：** hub 层 + `BaseAgentStore` 式 backend，可选、默认关闭。
- **范围：** 静态加密的凭据处理（先核实
   `credentials.py` 已做什么）、作为 `JsonlSessionStorage` 替代的可插拔 session 存储，以及 providers/agents/tools/skills/configs 注册表。
- **backend：** 基础为 TinyDB/SQLite；Postgres/Mongo/Redis 藏在 extras 后。
- **验证：** 加解密往返、缺/错 key 报错、JSONL
   导入导出无损、并发写入者的原子追加。
- **文档：** dev-note；库/集成指南。

### Phase 7 — Hugging Face inference-provider 路由（tau-huggingface）
- **参考：** tau-huggingface——`/hf route` picker 与侧栏 provider 状态区块。
- **形态：** 打包的 built-in extension。
- **范围：** 固定存活 inference provider 的 `/hf route` picker，加上随模型/路由变化刷新、非 HF provider 活动时隐藏的侧栏
   provider 状态区块。Baldric 已暴露所需 API，预计是小而自足的移植。
- **验证：** 用 stub 模型 API 的路由获取解析、侧栏增删
   生命周期、provider 门控。
- **文档：** dev-note；providers 指南注记。

## 飞行前检查（Phase 1 之前）

- **同步状态：** 命令 shell 无法经 SSH 访问 GitHub（`publickey`
  被拒），因此从这里看 `main` 只与最后一次拉取的
  `origin/main` 相等（都在 `v0.2.0`）。开始前在自己的终端运行 `git fetch` 确认 `main` 最新。
- **上游漂移：** Baldric 主干是旧上游 tag 的改名（`v0.2.0` vs 上游 tau `0.4.9`）加上回移的较新 extension API。每次移植前，重新确认该 phase 依赖的具体 API 在 Baldric 中存在且行为符合上游预期；有分歧时适配 Baldric 的形状，而不是把内核掰弯去迎合衍生项目。

## 明确的范围外

- tua-agent 的 Rust 专属特化（工具、prompt、profiles、skill）。
- basic-memory 的云/托管面（其付费云、遥测、认证）。
- 让 subagent、hub 或 memory 成为可复用 `baldric_agent` 内核的依赖。
