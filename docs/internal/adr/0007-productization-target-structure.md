# ADR-0007：产品化参考体系与目标结构（v3 定稿）

- 状态：Accepted
- 日期：2026-11-11
- 伴随计划：[../plans/2026-11-11-productization-roadmap.md](../plans/2026-11-11-productization-roadmap.md)（分阶段执行顺序与验收）
- 证据文件：[../notes/2026-11-11-structure-debt-review.md](../notes/2026-11-11-structure-debt-review.md)、
  [../notes/2026-11-11-reference-session-digest.md](../notes/2026-11-11-reference-session-digest.md)
  （均入库；原始存档为仓库外工作区文件，仅作 provenance：`D:\DEVELOP\Solis\session-ses_e406.md`、
  `D:\DEVELOP\Solis\_review-baldric-coding-notes.md`）

## 背景

baldric 的产品定位从「pi 血统的可读实现」转向「完整产品」：网页版优先，桌面壳后置
（Electron 或 Tauri 届时决策），单用户 local-first。为此评估了本地工作区内的参考项目
（pi、gptme、Raven、EverOS、opencode、basic-memory、smolagents 等），并合并三份独立
评审的结论：逐文件代码评审（结构债清单已入库为 notes）、参考会话存档（能力盘点与
专题决议已提取入库为 notes）、以及一次合并裁决评审。

本 ADR 记录随之确定的长期决策：参考体系分工、目标结构、命名法与治理规则、时序
决策门，以及被否决的替代方案。分阶段执行顺序见伴随计划，不复述于此。

前置核对：会话存档中的两条命名决议已在此前落地——单命名空间 `baldric.*` 子包
（否决平铺裸 `agent/ai/mcp`，避免与官方 `mcp` PyPI SDK 撞名）与应用包改名
`baldric_coding` → `baldric.runtime`。命名窗口已用掉，本 ADR 不再重开命名议题。

## 决策

### 1. 参考体系分工

| 参考系 | 角色 |
| --- | --- |
| pi | 架构与内核主线（血统源头；wire / RPC / extension / skills 面保持 pi 对齐） |
| gptme | 产品形态实现模板（Python 同栈；工具、hooks、server、eval 的实现细节参照） |
| Raven | 多代理编排、轨迹可观测（trajectory）、web UI 骨架的架构参照（搬模式不搬代码） |
| EverOS | 记忆运行时参照（Markdown 真相源 + 可重建索引 + 契约测试纪律） |
| opencode | client/server 分离与生成式 SDK 的模式参照（TS 栈） |
| basic-memory | 分层 Markdown 记忆与知识库的落地形态参照（P7 记忆/知识批次） |

### 2. 内核政策

内核（`baldric.protocol` / `baldric.agent` / `baldric.ai`）分两档管理：

- **改既有行为**（修改现有内核文件的控制流、语义、wire）只允许出现在计划 P2 / P7 / P8。
- **增件**（新文件、新钩子位、新端口，不改既有行为）允许在 P1 / P3 / P6 出现
  （如 `agent/hooks.py` 确认链、`agent/spans.py`）。

允许的结构性改动仅两处：

1. `baldric.agent.contracts/`：运行时端口层（`memory.py` / `sandbox.py` /
   `subagent.py`），依赖反转用；实现在上层（`baldric.memory`、
   `baldric.runtime.sandbox`、`runtime/subagents`）。P1 起建位（turn-time 权限
   绑定接口先落），P2 落全。
2. `baldric.server/`：headless server 作为顶层子包。`runtime` 永不 import 它，
   它只向下 import——import 边界由 `scripts/check_import_graph.py` 机械强制。

### 3. 目标结构 v3

```text
baldric/
├── src/baldric/
│   ├── protocol/                  现有｜格式契约：messages/tools/provider/provider_events
│   │   ├── extension.py           A0｜扩展契约形状（事件 payload/类型别名/能力元数据，纯形状）
│   │   ├── ports.py               A0｜跨域 port（修订 2026-11-13：仅保留有真实消费方的 ProviderCatalog/EffectiveProviderView；原列 HookDispatcher/FeatureSetup 为零消费抽象已删除，见结构计划 §0.2）
│   │   └── session/               现有｜会话文件格式 + 版本化迁移
│   ├── ai/                        现有｜provider 流层
│   │   ├── catalog/               P2｜schema+默认目录自 runtime/providers 上浮（用户覆盖留 runtime）
│   │   ├── cache_optimizer.py     P7｜Anthropic cache 断点优化
│   │   └── rotor.py               P7｜多端点轮询 + 首字前故障转移
│   ├── agent/                     现有｜内核（loop/harness/events）
│   │   ├── contracts/             P1 建位 / P2 落全｜运行时端口：memory.py / sandbox.py / subagent.py
│   │   ├── hooks.py               P1｜确认链协议（confirm|skip|edit，编辑重跑 guard）
│   │   └── spans.py               P3｜span 触发（purpose 标签区分主对话与侧面任务）
│   ├── mcp/                       现有｜client；P6 增 server/（对外暴露工具）
│   ├── memory/                    P7｜独立子包：backends/markdown + recall/match/policy/roots
│   │   │                          ／lessons/ + consolidate/；包内 contract-test 基类
│   ├── runtime/                   现有｜应用层
│   │   ├── cli.py / events.py     P1｜非交互退出码分类学（75/76/77 自定义段，文档注明）+ 退出成本
│   │   ├── onboard/               P1｜首次运行向导（provider→凭证→工作区信任）
│   │   ├── config/                现有 + P1｜全局版本水位 + run-once 迁移
│   │   ├── permissions/           P1｜gate / rules / shell_policy / session_grant（自 trust/ 拆出）
│   │   ├── security/              P1｜wrap_untrusted / ssrf / redact / secret_reach
│   │   ├── trust/                 现有｜保留工作区信任语义（不扩权）
│   │   ├── sandbox/               P1｜direct / 容器(extra) / wasm(后置)；契约在 agent/contracts
│   │   ├── tools/                 现有 read/write/edit/bash
│   │   │   ├── P1｜glob / grep(ripgrep-bin+fallback) / todo / clarify / choice /
│   │   │   │        background / web_fetch(SSRF-safe) / web_search(多后端 extra)
│   │   │   └── P6｜hashline / shell_persistent /（browser 为 builtin 扩展，Playwright）
│   │   ├── session/               P0 重组 + P2｜三写原语(atomic_replace/locked_append/
│   │   │                          write_transaction) / fsync 屏障 / events checkpoint cell
│   │   │                          ／CAS 附件 / channel 守卫(sub:, imported:) / 存储 conformance 基类
│   │   ├── context/               现有 + P7｜assembler / curator / compacting(阶梯压缩) /
│   │   │                          headroom / turn-scratch / scout
│   │   ├── context/skills/        现有 + P7｜gate.py（按需选技能，失败退 top-k）
│   │   ├── observability/         现有 doctor/watchdog
│   │   │   ├── tracing/           P3｜spans JSONL + 内容寻址存储
│   │   │   └── trajectory/        P3｜bundle / redact(三层) / replay / regression / bugreport
│   │   ├── snapshots/             P6｜workspace 影子快照 + 自动回滚
│   │   ├── subagents/             P8｜自 extensions/builtins 搬家升一级：backends(进程内/
│   │   │                          CLI-agent/远程) / dag(graph,runner,store,tools) / playbook / stint
│   │   ├── schedule/              P8｜cron stale-claim TTL + 心跳 wakeup
│   │   ├── extensions/            现有 + P9｜manifest(TOML 七贡献) / discovery(entry-points) /
│   │   │                          单插件回滚 / PluginContext 冻结上下文 / API v2(活把手)
│   │   │   └── builtins/          P9 验收｜只剩「实现已有 port + 拿掉产品不变」者（llama_cpp 留驻）
│   │   ├── providers/ auth/ backends/ rendering/ tui/ modes/rpc/ commands/ update/
│   │   │   utils/ data/           现有
│   ├── server/                    P4a｜app / dependencies / exception_handlers / middleware(cors,
│   │   │                          request_id, metrics) / routes(每资源一文件) / schemas(envelope)
│   │   │                          ／auth / sse / openapi / brokers(approval, question) / spine(lane)
│   │   │                          ／gateway(outlet) / cli（`baldric-server`）
│   ├── acp/                       P6｜agent / adapter / dialects(claude_code, codex)（`baldric-acp`）
│   ├── importer/                  P9｜scanners(claude_code, pi)，批次有界
│   └── channels/                  P9｜intake 合同（spec.py 发现 + sender allowlist 空=全拒）
│                                  ／adapters(telegram, feishu 首发)
├── ui-web/                        P4b｜rpc/(transport 三实现 + generated.ts) + features/
│                                  （Raven ui-web 骨架；React/Vite；客户端自 OpenAPI 生成）
├── benchmarks/                    P3｜suites / execenv / cassettes(expect.yaml) / baselines.json
│                                  （不进 wheel）
├── schemas/                       P4a｜rpc.json（生成 + `--check` 漂移契约测试）
├── docker/                        P4b｜server 镜像 + compose
├── i18n/                          P10｜messages.json 单一源，前端编译消费
├── desktop/                       P10 决策门｜Electron 或 Tauri（两案并列，见下）
├── tests/                         现有 + server/ acp/ channels/ memory/
├── docs/ website/ examples/ scripts/（+ gen_rpc_schema.py / bench_startup.py）
├── hatch_build.py                 P4b｜条件 force-include ui-web dist（Raven 模式：dist 缺失走源码回退）
└── pyproject.toml                 extras: server / sandbox / browser / everos / channels / web_search；
                                   入口: baldric / baldric-server / baldric-acp / baldric-mcp-server
```

### 4. 命名法与治理规则

- **契约分界**：`protocol` = 格式契约（文件里的字节：wire 类型、会话文件格式、
  rpc schema 生成源）；`contracts` = 运行时端口（进程间依赖反转）。分界永远是
  「文件里的字节 vs 进程间」。
- **`extensions/builtins/` 准入判据（三问）**：核心能不能没有它照常运行；它是不是
  某个已存在 port 的可替换实现；它是否需要写入核心类型。按此判据：`llama_cpp`
  合法留驻；`subagents` 在编排阶段升为 `runtime/subagents/`（行为不变字节级证明）；
  `mcp` 桥退役并入 `baldric.mcp`。判据当前以本 ADR 为准；写入 AGENTS.md 需随
  agent-guidance ratchet 基线一起 `--init`（P9，或下次有意扩写指令文件时）。
- **表面 LOC 预算 ratchet**：每个新增表面（`server` / `channels` / `importer`）一条
  LOC 预算基线，防 Raven 式巨石聚合。
- **会话持久化**：JSONL 追加是 canonical（Pi 家族一致）。SQLite 只允许出现在
  (a) 可插拔后端之一（与 jsonl 过同一 conformance 测试），(b) 派生索引层（可从
  真相源全量重建：usage 统计、记忆状态层）。

### 5. 复用与移植判据

参考系分工（§1）回答"看谁"，本节回答"搬什么、怎么搬"。

- **没有整包可搬的参照对象。** 这是实测结论，不是判断：gptme 产品层完备，
  但 `gptme/tools/` 53 个文件中**没有 `grep.py`，也没有 `glob.py`**——它的源码级
  搜索靠 `shell` 工具跑 `rg`/`find`（`shell_flags.py` 对 rg/ag 做 flag 细分），
  不是独立工具。Raven 产品面最完备，但自带架构（49 子包、litellm、OpenRPC），
  剥壳约等于重写一半。**因此不存在"选一个项目对齐全部功能"的路径，只能逐功能
  挑最自包含的实现。**
- **可搬性三问**（与 §4 的 builtins 三问同构）：① 它 import 了源项目的内核吗？
  ② 它依赖源项目的事件 / 存储 / 渲染 / hook 体系吗？③ 拿掉它，baldric 的产品
  行为变不变？**任一为"是"→ 只搬设计意图，按 baldric 契约重写；三问全"否"→
  方可直接搬**（仍须按 AGENTS.md 记出处与版本）。
- **实证（不可搬的典型）**：gptme `tools/todo.py` 直接调 `LogManager.get_current_log()`
  并依赖 `HookType` / `ToolExecuteData` / `tool_format`；`tools/read.py` 绑
  `hooks._policy_block` / `util.context` / `util.tokens` / `.pruner`。baldric 的工具
  契约是 `AgentTool` + `AgentToolResult`（typed content blocks，原生 function-calling），
  与 gptme 的 markdown codeblock + IPython 函数 + `Message` 生成器模型不兼容，
  整文件拷入无法运行。
- **落到路线图**：每项的「参照」列取该功能最自包含的来源，而非统一某一项目——
  grep/glob 取 pi 设计（gptme 无）；server/ui-web 取 gptme（Flask→FastAPI、结构按
  baldric 重写）；memory 取 basic-memory / gptme；permissions / DAG / trajectory
  取 Raven 但只取规格与模式。

### 6. 时序与决策门

- **server 在事件源耐久会话（P2）之后启动（P4a），与可测量底座（P3）并行**：
  server 不改会话格式（本 ADR §2），只消费事件流，因此不被 cassette 基线阻塞；
  cassette/eval 基线约束的是 P6/P7/P8 内核动土批。
- **A2A**：决策门，默认缓建（生态未起；与 channels 同批视 GTM 再定）。
- **桌面壳**：决策门，Electron 与 Tauri 两案并列。gptme 的 Tauri 配方
  （PyInstaller server sidecar + minisign 更新器）是参考系中唯一完整先例。
- **流协议**：ui-web 传输先 SSE（单向足够，gptme 同款）；WS 留决策门
  （编排/DAG live 若需双向再升）。

## 后果

变得更容易：

- 每个后续阶段只回答「这一项落到哪个框」，结构不再逐阶段重议。
- P2 是网页版闭环的唯一串行内核前置；P3∥P4a 并行使产品闭环不受评测底座阻塞。
- 评测基线（cassette / golden eval）成为 P6/P7/P8 动内核的资格线，回归风险可控。
- import 边界与结构纪律继续机械强制：新增包纳入 `scripts/check_import_graph.py`
  与 `scripts/check_structure.py` 的 LOC ratchet。

变得更难 / 代价：

- 五个新顶层目录（`ui-web/`、`benchmarks/`、`schemas/`、`docker/`、`i18n/`）进入
  开发者心智与 CI（schema `--check` 门、benchmarks 基线工作流）。
- 编排阶段需要搬移 `subagents` 并做行为不变证明。
- builtins 准入判据入 AGENTS.md 需要一次 ratchet 基线 `--init`。

强制执行：

- import graph 门扩展覆盖新包；结构 ratchet 收录新包基线。
- `schemas/rpc.json` 生成 + `--check` 漂移门。
- benchmarks 基线不回归作为内核动土批（P6/P7/P8）的阶段闭箱条件（P3 起）。
- `extensions/builtins/` 准入判据在 P9 验收时写入 AGENTS.md（随基线 `--init`）。

## 被否决的替代方案

| 替代方案 | 落选原因 |
| --- | --- |
| 以 gptme 为主参考 | 内核（generator loop、markdown 工具格式）弱于 pi 且与 baldric 分层不同构；换主参考等于内核重写，零收益 |
| 照搬 Raven 全量（litellm、evolver/curator、巨型聚合 runtime、12 渠道矩阵） | 论文主轴与产品主线无关；巨石 runtime 与 ratchet 文化冲突 |
| uv workspace / `packages/*` monorepo | 单维护者 + 单发行版模式（gptme/Raven 先例）已够；拆分设显式触发器（server 超 ~10K 行或需独立版本节奏） |
| 顶层平铺去前缀（`agent/`、`ai/`、`mcp/`） | 与官方 `mcp` PyPI SDK 撞名；单命名空间已落地，议题关闭 |
| `baldric_core` / `baldric_host` 等应用包改名 | 「core」在生态通义中最底层本质（langchain-core、SQLAlchemy Core）；`runtime` 已定案，命名窗口已用掉 |
| evals 作为包内子包 + `baldric-eval` 入口点 | 评测素材不是产品发行物；取 Raven/EverOS 顶层 `benchmarks/`（不进 wheel） |
| `web/` 命名 | 取 Raven 的 `ui-web/`，与将来桌面目录前缀统一 |
| `runtime/execution/` 命名 | 取 Raven `sandbox/`、gptme `sandbox.py` 先例；后台命令归 tools 不归执行器 |
| 会话存储迁 SQLite（opencode drizzle 路线） | agent 会话是尾部读 + 追加写负载；SQLite 引入 WAL / 单写者锁 / 跨平台文件锁（Windows fcntl 前科）；树分支用 parent-id 一列即可表达 |
| server 等待评测底座（P3 → P4 硬依赖） | server 不改会话格式、只消费事件流；cassette 基线约束的是内核动土批（P6/P7/P8），改并行，网页版闭环提前一个相位 |
| pi codemode 式沙箱 JS 执行（QuickJS） | 与原生 function-calling 内核重复；工具暴露模型保留四级（direct/model-only/deferred/hidden），沙箱需求由 `sandbox/` 承担 |
| 立即做 A2A / computer use / LSP / SSH fleet / 多租户 SaaS | 生态未起、维护成本、local-first 单用户定位不匹配；见伴随计划「非目标」 |
