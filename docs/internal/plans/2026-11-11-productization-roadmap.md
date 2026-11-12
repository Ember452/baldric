# 产品化路线图（P0-P10）

**目标：** 把 baldric 从 pi 血统的终端 coding agent 推进为完整产品——信任安全、
可测量、事件源会话、headless server、ui-web、记忆与上下文引擎、多代理编排、
插件生态与分发，全部落在 [../adr/0007-productization-target-structure.md](../adr/0007-productization-target-structure.md)
定义的目标结构 v3 内。

**决策依据：** ADR-0007（参考体系分工、内核政策、治理规则、时序决策门）。
证据文件（均已入库）：
[2026-11-11-structure-debt-review.md](../notes/2026-11-11-structure-debt-review.md)
（结构债事实清单）、
[2026-11-11-reference-session-digest.md](../notes/2026-11-11-reference-session-digest.md)
（参考盘点与批次排序依据；原始会话存档为仓库外 `D:\DEVELOP\Solis\session-ses_e406.md`，
仅作 provenance）。本文只写执行顺序与验收，不复述决策；每阶段落位以 ADR-0007
目标结构树为准。

## 全局约束

- 每阶段闭箱条件：既有质量门全绿（ruff / mypy / pytest / coverage floor）+
  import graph 门 + 结构 ratchet；P3 起新增「benchmarks 基线不回归」。
- **内核改动两档**：改既有行为（现有内核文件的控制流/语义/wire）只在 P2 / P7 / P8；
  增件（新文件、新钩子位、新端口）允许在 P1 / P3 / P6（如 `agent/hooks.py`、
  `agent/spans.py`）。见 ADR-0007 §2。
- 每阶段独立可发布；**P2 完成前，P3 与 P4a 并行推进**（server 不改会话格式，
  不被 cassette 基线阻塞）。
- 每阶段标注工作量级（S/M/L/XL，单人节奏估算）；逐条 sizing 在转任务卡时做。
- 本计划取代 GitHub issue #2 的 tau 上游移植路线顺序；P0-P1 完成后重写 issue #2。

## 执行原则（硬性，覆盖本计划全部任务；与全局约束同级生效）

> 以下六条原则约束本路线图内每一项任务的执行方式。它们不替换
> `AGENTS.md` 的质量门槛与硬规则，而是在其之上叠加执行纪律；与
> `AGENTS.md` 冲突时以更严格者为准。通用工作规则（重扫 / 影响面 / 分层守恒 /
> 打断）在根 `AGENTS.md` 有同一表述，两者意图一致。

1. **参照而非照搬**

   借鉴 pi / opencode 任何设计前，先读其完整实现与上下文，回答三个问题：
   它为什么这样设计？它在自己的架构里依赖了什么前提？搬到 baldric 的分层
   （`ai` / `agent` / `runtime` 三层 + 事件契约）里这些前提还成立吗？

   - 只有**设计意图**可移植；实现代码必须按 baldric 的结构、命名、测试习惯重写
     （可搬性三问与实测案例见 ADR-0007 §5）。
   - 例外是显式 vendored 的小文件，必须文件头标注出处与版本。
   - pi / opencode 做法与 baldric 现有设计冲突时，不默认改 baldric 去适应它们——
     先评估哪边更对；拿不准 → 打断问维护者。

2. **计划不是真理：动手前重扫**

   每个任务动手前，重新扫描当前代码（文件可能已被其他会话或工作改动）：接口
   签名、字段、调用方全部实读确认。计划里写的行号、签名、路径、fixture 名一律
   视为"上次快照"，以实读为准。

   - 计划与代码现实冲突时：小冲突（命名、行号、fixture 位置）以现实为准并回写
     本计划；大冲突（涉及架构或需求理解）→ 停下问。

3. **影响面分析：改动前必须完成**

   改 baldric 任何共享模块（`protocol`、`events`、`session`、`providers`、
   `tools`、`trust`）前，先 grep 全部引用方（import、字段使用、事件消费、测试
   断言），列出受影响清单再动手。

   - 允许动内核（`ai` / `agent` / `runtime` 任何层），条件是：影响面已列清、
     改动能说明理由、补齐测试、层边界守恒（`uv run python scripts/check_import_graph.py`
     必须绿）。
   - 过程中发现 baldric 现有设计有问题（不只"与计划不符"）→ 打断问维护者，不
     擅自顺手重构。

4. **计划外行动的许可条件**

   允许做计划外的事、允许修改现有代码，条件：确有必要 + 影响面已分析清楚 +
   在任务产出中说明偏离原因与后果。

   - 严禁为图省事引入低内聚高耦合的结构；严禁"不考虑全面就动手"。

5. **质量底线**

   高内聚低耦合：新增单元单一职责；跨层只走事件 / 协议契约，不走内部字段直读。
   每个任务交付可独立 review、可独立测试的单元；测试不过不提交，断言不许弱化
   （baldric 硬规则）。

6. **打断规则（何时必须停下来问）**

   需求不清、设计冲突、影响面存疑、发现现有 bug 或坏味道——立即打断问维护者，
   不要脑补。宁可多问一次，不可错改一处。

## MVP 切线（最小可发布网页版）

```text
P0 → P1（批次 B/C 可先于 A）→ P2 → P4a → P4b   ⇒ 网页版闭环可发布
```

P3（评测底座）在上述切线执行期间**并行**完成——它是后续 P6/P7/P8 动内核的
资格线，但不是网页版的发布门槛。P1 批次 A（治理/onboard）建议与 P4a 并行补齐，
随网页版首发一起出。

## 非目标（明确不做）

多租户 / 云服务；A2A 立即落地（P9 决策门）；evolver / curator 自演进；12 渠道
矩阵（首发 1-2 个）；SSH fleet / 远程 node；computer use / 语音实时；LSP；
litellm 化 provider 层；pi codemode 式沙箱 JS 执行（QuickJS，沙箱需求由
`runtime/sandbox/` 承担，工具暴露模型保持四级）；Gradio UI；dspy；遥测面板。

---

## P0｜结构还债与仓库清理（不碰行为）｜量级 M

| # | 功能 | 参照 | 落位 |
| --- | --- | --- | --- |
| 0.1 | session 包真拆分：去 partial-class、消重导出样板（四文件 ~1000 行 `import X as X`）、手工字段搬运改声明式 | [notes/2026-11-11-structure-debt-review.md](../notes/2026-11-11-structure-debt-review.md) | `runtime/session/` |
| 0.2 | 原子写收敛：六处手写 `os.replace` 并入统一实现 | review notes | `runtime/utils/atomic.py` |
| 0.3 | `resource_helpers` 绕过存储协议直写修复（`_append_session_entry_sync` 绕过锁+torn-tail+fsync） | review notes | `runtime/session/` |
| 0.4 | NaN/Infinity 校验补齐：`providers/config/validation.py` + `providers/loader.py`（TOML inf）+ `protocol/session/`（第二处） | review notes | 三处 |
| 0.5 | 测试接缝复制清理（四份重复测试接缝） | review notes | `tests/` |
| 0.6 | 仓库根清理：backup zip / landing.html / hex html / interview 笔记移出 | — | 仓库根 |
| 0.7 | 发布流水线复活：publish / docs workflow、正式 wheel 重建 | gptme release 流程 | `.github/workflows/` |
| 0.8 | Windows TUI 稳定性专项（asyncio 挂起 + suite 隔离） | — | `tests/runtime/tui/` |

**依赖：** 无。**验收：** 快速套件全绿；结构 ratchet 基线收紧一次；`uv build`
产出干净 wheel。

---

## P1｜治理、信任安全与工具一批｜量级 L（批次 A:S / B:M / C:S）

### 批次 A：治理与发布化

| # | 功能 | 参照 | 落位 |
| --- | --- | --- | --- |
| 1.1 | 非交互退出码分类学（75=限流 / 76=鉴权 / 77=模型不可用；76/77 为自定义段，sysexits.h 无对应——文档明注）+ 退出成本统计 | gptme `cli/main.py` | `runtime/cli.py` |
| 1.2 | 全局 config 版本水位 + run-once 迁移框架，迁入 providers/mcp/tui 配置面 | Raven config（CURRENT_CONFIG_VERSION） | `runtime/config/` |
| 1.3 | `baldric onboard` 首次运行向导（provider 连接→凭证→工作区信任） | Raven onboard、gptme onboard | `runtime/onboard/` |
| 1.4 | 启动性能 CI 门（cold / warm import / `--help` 时间上限） | gptme `benchmark.yml` | `scripts/bench_startup.py` |
| 1.5 | `--doctor` 扩充：ripgrep 可用性、uv、MCP 端点全配置面自检 | Raven ops/doctor | `runtime/observability/` |

### 批次 B：信任与执行安全

| # | 功能 | 参照 | 落位 |
| --- | --- | --- | --- |
| 1.6 | hook 点位类型学定稿（dots 命名，事件允许 block/transform，不做纯通知）——增件（新文件） | pi 四级事件清单、gptme hooks | `agent/hooks.py` |
| 1.7 | 确认 hook 协议：`ConfirmationResult = confirm|skip|edit`，编辑重跑 guard，auto-confirm ContextVar | gptme `hooks/confirm.py` | `agent/hooks.py` + `runtime/permissions/` |
| 1.8 | permissions 拆分：决策瀑布（内置硬拒绝→用户规则→模式分级）+ session grant（"不再询问"写入 exec 规则） | Raven `permissions/gate.py`、`session.py` | `runtime/permissions/` |
| 1.9 | shell 逐段校验：pipeline 段白名单、敏感路径短路、shellcheck 可选 | Raven `shell_policy.py`、gptme `shell_validation.py` | `runtime/permissions/shell_policy.py` |
| 1.10 | turn-time 权限绑定接口（子代理可继承、无人值守表面禁问）——只留接口位，增件 | Raven `permissions/turn.py` | `agent/contracts/`（P1 建位） |
| 1.11 | permission 判定进审计日志（含理由） | Raven observability/audit | `runtime/observability/` |
| 1.12 | `wrap_untrusted`：nonce 标签围住工具结果 / 技能正文 / 记忆正文 | Raven `security/trust.py` | `agent/security.py` + `runtime/security/` |
| 1.13 | secret reach 守卫 + 发布面凭据脱敏 | gptme `_secret_reach.py`、Raven `redact.py` | `runtime/security/` |
| 1.14 | SSRF 防 DNS rebinding（解析一次→连接同址）——为 1.22 web_fetch 铺路 | Raven `security/network.py` | `runtime/security/` |
| 1.15 | SandboxExecutor 契约 + direct executor（最小 env 白名单）；容器后端走 optional extra | Raven `sandbox/` | `agent/contracts/sandbox.py` + `runtime/sandbox/` |
| 1.16 | `clarify` / `choice` 结构化问询工具（审批 UI 原语 + subagent 问人通道的前身） | gptme `clarify.py` / `choice.py` | `runtime/tools/` |

### 批次 C：工具一批

| # | 功能 | 参照 | 落位 |
| --- | --- | --- | --- |
| 1.17 | `glob` 工具（pathlib 级） | pi `find.ts`/`ls.ts`、通行做法 | `runtime/tools/` |
| 1.18 | `grep` 工具（ripgrep-bin 多平台捆绑 + Python fallback，输出带行号） | Raven ripgrep-bin 捆绑式、pi `grep.ts` | `runtime/tools/` |
| 1.19 | `todo` 工具（agent 可 TodoWrite，**per-session 持久 + 跟随 fork**，TUI 侧栏） | gptme `todo.py`、Claude Code 惯例 | `runtime/tools/` |
| 1.20 | 后台命令（detached spawn + 截断日志追加 + 轮询拉取） | gptme `shell_background.py` | `runtime/tools/` |
| 1.21 | 工具输出统一截断策略复查（总预算） | Raven context_engine 概念 | `runtime/tools/` + `runtime/context/` |
| 1.22 | `web_fetch` 工具（SSRF-safe，直接消费 1.14；markdown 化输出） | opencode webfetch、gptme browser 轻量路径 | `runtime/tools/` |
| 1.23 | `web_search` 工具（多后端可配：tavily / serper / brave，optional extra） | opencode websearch | `runtime/tools/` |

**依赖：** P0。**验收：** 批次 A 全部落地后发一版；确认链有 terminal 实现 +
server/auto 桩；`clarify`/`choice` 可被 fake provider 的 e2e 覆盖；grep/glob/todo/
web_fetch 进入 eval 场景素材。

---

## P2｜内核对齐与事件源会话｜量级 L

**现状核查（每项动工前先做）**：内核存储已具 locking / fsync / torn-tail 修复
（CHANGELOG 0.3.0）；`session_before_compact` 事件已存在
（`runtime/extensions/runtime.py`，补否决/改写语义即可）。以下条目只补"差什么"，
不重做"已有什么"。

| # | 功能 | 参照 | 落位 |
| --- | --- | --- | --- |
| 2.1 | provider 级事件补齐：before_provider_headers / request / after_response / stream_event / cache 决策 | pi 扩展事件面 | `ai/` |
| 2.2 | 会话结构级事件补齐：before_fork、before_tree 等缺失项；`session_before_compact` 已存在，补否决/改写语义 | pi | `agent/` + `runtime/extensions/` |
| 2.3 | 截断安全：length 停止时同消息全部 tool call 标失败，不执行可能截断的参数 | pi | `agent/` |
| 2.4 | 通用嵌套工具调用走同一 hook 管道 | pi nested-tool-calls | `agent/` |
| 2.5 | 工具暴露模型四级（direct / model-only / deferred / hidden）+ tool_search（codemode 级明确不做） | pi | `runtime/tools/` + `agent/` |
| 2.6 | RPC 对齐 pi 35 条 | pi modes/rpc | `runtime/modes/rpc/` |
| 2.7 | `appendEntry(customType)` + 自定义 entry 三类 + per-type renderer 注册（扩展写的 entry 重启存活、回放不失真） | pi custom entry 管道 | `protocol/session/` + `runtime/extensions/` |
| 2.8 | 三写原语命名化：`write_transaction` / `locked_append` / `atomic_replace`——**先核查既有 locking/fsync/torn-tail，只补缺口** | Raven `utils/atomic_io` | `runtime/session/storage.py` |
| 2.9 | fsync 耐久屏障核查与补齐：任何"生成完成"事件发出前落盘同步 | gptme transcript-persistence 设计 | `runtime/session/` |
| 2.10 | events 耐久日志：每 50 事件打 checkpoint cell（崩溃后快回放） | gptme eventlog | `runtime/session/` |
| 2.11 | Pi 式存储 conformance 基类（所有未来后端共用一套崩溃语义测试） | pi packages/durable | `tests/runtime/session/` |
| 2.12 | catalog 数据上浮：schema + 默认目录进 `ai/catalog/`，用户覆盖加载留 runtime | 会话存档决议 | `ai/catalog/` + `runtime/providers/` |
| 2.13 | `agent/contracts/` 端口层落全（memory / sandbox / subagent 三个 Protocol；1.10 已建位） | 会话存档决议 | `agent/contracts/` |
| 2.14 | CAS 附件（16 位 SHA-256 键 `files/`，不可变引用 + 去重）——自 P3 移入（server 不依赖它，归耐久批次） | gptme `file_storage.py` | `runtime/session/` |
| 2.15 | 工具调用解析加固：native 参数解析 + 文本协议路径（llama_cpp 本地模型需要）；不做 markdown/xml 通用语法 | gptme `ToolUse.iter_from`（缩 scope） | `agent/tool_calls.py` |

**依赖：** P1 批次 B（hook 类型学）。**验收：** wire 快照更新走 reviewed diff；
conformance 基类对现有 jsonl 存储全绿；扩展写自定义 entry 的 e2e 用例通过。

---

## P3｜可测量性底座（P6/P7/P8 动内核的资格线；与 P4a 并行）｜量级 M

| # | 功能 | 参照 | 落位 |
| --- | --- | --- | --- |
| 3.1 | span 触发协议 v1（llm / tool / permission 事件 + purpose 标签）——增件 | Raven `tracing` | `agent/spans.py` |
| 3.2 | spans JSONL + zstd 内容寻址工件存储 | Raven `tracing/store.py` | `runtime/observability/tracing/` |
| 3.3 | trajectory 离线包（manifest/spans/artifacts/session 五件套） | Raven `trajectory/bundle.py` | `runtime/observability/trajectory/` |
| 3.4 | 三层脱敏（配置/环境 secrets → regex → 残留熵扫描） | Raven `redact.py` | `runtime/observability/trajectory/` |
| 3.5 | 确定性回放（ReplayProvider 重跑 harness）+ regression cassette（`expect.yaml` 断言首个分歧的 kind/index/field） | Raven `trajectory/replay.py`、`regression.py` | `runtime/observability/trajectory/` + `benchmarks/cassettes/` |
| 3.6 | bugreport 快照导出 | Raven `bugreport.py` | `runtime/observability/trajectory/` |
| 3.7 | golden-task eval 套件（10-15 个 practical 任务起跑） | gptme `eval/suites/` | `benchmarks/suites/` |
| 3.8 | eval 执行环境抽象（local / docker，可对比其他 agent） | gptme `execenv.py` | `benchmarks/execenv.py` |
| 3.9 | eval 基线入库与不回归面板（并入现有成本面板） | gptme trends/cost | `benchmarks/baselines.json` |

（CAS 附件已移至 2.14；本阶段不再写 `runtime/session/`。）

**依赖：** P2（与 P4a 并行）。**验收：** 一条真实会话录成 cassette 并在 CI 断言；
golden eval 首跑基线入库；从 cassette 修复一个真实回退（自证有效）。

---

## P4a｜server 核心（CLI → 平台分水岭）｜量级 L

| # | 功能 | 参照 | 落位 |
| --- | --- | --- | --- |
| 4.1 | wire schema 定稿（30-60 方法：sessions/turns/tools/approvals/config/update） | Raven `rpc-schema/openrpc.json` 缩版 | `schemas/rpc.json` |
| 4.2 | 类型生成 + `--check` 漂移契约测试 | Raven gen-rpc-client | `scripts/gen_rpc_schema.py` |
| 4.3 | FastAPI app 工厂 + routes/schemas/middleware 分层（envelope 信封） | EverOS `entrypoints/api/` | `server/` |
| 4.4 | server 鉴权：启动 token、HttpOnly cookie、Host 头校验、默认 loopback 绑定 | gptme `server/auth.py` | `server/auth.py` |
| 4.5 | 事件流：**SSE 先行**（单向足够，gptme 同款）+ `turn.subscribe` + message.complete 渲染屏障；WS 留决策门 | Raven rpc、gptme SSE | `server/sse.py`、`server/subscribe.py` |
| 4.6 | approval / question broker（提示路由到当前打开的入口，接上 P1 确认链的 server 实现） | Raven `rpc/*_broker.py` | `server/brokers/` |
| 4.7 | spine/lane：每会话一条 lane（并发与取消单位）；**origin 分池（USER/CRON/SUBAGENT）推迟到 P8**（届时才有真实 origin） | Raven `spine/` | `server/spine.py` |
| 4.8 | gateway/outlet：**最小实现，只做 TUI + web 两出口**；channels 槽位留给 P9 | Raven `gateway/outlet.py` | `server/gateway.py` |
| 4.9 | 现有 RPC pipe 降级为 server 的一个前端（CLI 保留 no-daemon 路径） | baldric 自身架构 | `runtime/modes/` |
| 4.10 | `baldric service init`（systemd/launchd 单位 + 失败率 guard；**Windows 用计划任务或托盘常驻**） | gptme `cmd_service.py` | `server/cli.py` |
| 4.11 | 健康端点 + `/metrics` + 进程级 lifecycle 单例锁 | gptme metrics、Raven gateway/lock | `server/` |

**依赖：** P2（事件源会话）。**验收：** OpenAPI 快照契约测试；RPC pipe 作为
server 前端自测通过（ui-web 未就绪时先闭环）；schema `--check` 进 CI。

## P4b｜ui-web v1 与交付｜量级 M

| # | 功能 | 参照 | 落位 |
| --- | --- | --- | --- |
| 4.12 | ui-web 最小视图：会话流 / 工具卡 / diff / 审批卡 / 模型选择；**React/Vite**（gptme webui 同栈）；客户端从 OpenAPI 生成；fixtureTransport 支持无后端开发。**验收含不可信工具输出渲染约定（XSS）：转义纪律平移自 `export/html.py` 的 `_escape`/`_attr` 区分** | Raven `ui-web/` | `ui-web/` |
| 4.13 | hatch 条件 force-include ui-web dist（缺失走源码回退） | Raven `hatch_build.py` | `hatch_build.py` |
| 4.14 | docker 交付（镜像 + compose + 健康检查） | Raven `docker/` | `docker/` |

**依赖：** P4a。**验收：** TUI 与 ui-web 同时接入同一会话且审批往返两端可达；
`uv build` 的 wheel 在无 node_modules 环境可用（回退路径生效）。

---

## P5｜ui-web v2｜量级 M

| # | 功能 | 参照 | 落位 |
| --- | --- | --- | --- |
| 5.1 | 会话树可视化 / fork / resume | pi 树、Raven features | `ui-web/features/sessions/` |
| 5.2 | 用量/成本 dashboard（平移现有 usage HTML 逻辑） | 现有 `runtime/session/usage.py` | `ui-web/features/usage/` |
| 5.3 | 命令 / 技能 / prompt template 面板 | Raven features | `ui-web/features/` |
| 5.4 | 移动端适配 + 配对码远程访问 | opencode pair 模式 | `ui-web/` + `server/auth.py` |
| 5.5 | onboard 向导 web 版复用 | — | `ui-web/features/onboard/` |

**依赖：** P4b。**验收：** 手机浏览器完成一次完整审批往返。

---

## P6｜工具二批与表面接入｜量级 M

| # | 功能 | 参照 | 落位 |
| --- | --- | --- | --- |
| 6.1 | hashline 编辑（read 快照 tag + PUT/CUT 多操作单调用、漂移即拒）与 exact-match 并挂 eval A/B，裁决 patch_many 去留 | gptme `hashline_edit.py` | `runtime/tools/` + `benchmarks/` |
| 6.2 | 持久 shell（session 级 env/cd 状态 + bg jobs；Windows PowerShell 方言单独测试） | gptme `shell.py` | `runtime/tools/shell_persistent/` |
| 6.3 | browser builtin 扩展（Playwright 优先 + 降级路径 + PDF） | gptme `_browser_playwright`、Raven browser | `runtime/extensions/builtins/browser/` |
| 6.4 | workspace 影子快照（per-workspace side-git，pre/post 工具执行、自动回滚）+ `/backtrack` 命名检查点 | gptme `workspace_snapshot.py` | `runtime/snapshots/` + `runtime/commands/` |
| 6.5 | **MCP server 模式**（对外暴露自家工具给 Claude Desktop/Cursor） | gptme `mcp/server.py` | `mcp/server/` |
| 6.6 | **ACP agent 侧**（Zed/JetBrains 驱动 baldric）+ `baldric-acp` uvx shim；dialect 适配入库 | gptme `acp/`、Raven `acp_client/dialects/` | `acp/` |

（原 6.7 工具调用解析已移至 2.15，scope 缩为 native + 文本协议。）

**依赖：** P1 批次 B（确认链稳定）、P4a（表面）。**验收：** hashline A/B 出数据；
Zed 经 ACP 完成一次会话；MCP server 被 Claude Desktop 消费成功。

---

## P7｜记忆与上下文引擎（动内核）｜量级 XL

| # | 功能 | 参照 | 落位 |
| --- | --- | --- | --- |
| 7.1 | MemoryBackend 契约 + 包内 contract-test 基类 | Raven memory contract-test、EverOS ports | `agent/contracts/memory.py` + `memory/` |
| 7.2 | 分层 markdown 后端（project/agent/user 三层 roots、最近优先、supersede 双向链接、malformed 拒绝） | gptme `memory/`、basic-memory | `memory/backends/markdown/` |
| 7.3 | session start 注入各 root 索引（64KB 共享预算）+ `recall` CLI 与工具 | gptme prompts/workspace、cmd_memory | `memory/recall.py` + `runtime/tools/` |
| 7.4 | lessons 引擎：frontmatter 匹配（keywords/tools/patterns）+ 注入预算 + dropout 因果测量 | gptme `lessons/` | `memory/lessons/` |
| 7.5 | 分类学定稿：lessons=关键词注入、skills=名字触发；skill gate（按需选技能，失败退 top-k）+ 多源 fan-out | gptme skills-as-commands、Raven SkillForge | `runtime/context/skills/` |
| 7.6 | 段式 context assembler（并行段落 builders）+ Curator 有界归档/召回 | Raven assembler/curator | `runtime/context/` |
| 7.7 | 阶梯压缩：裁剪工具结果→删消息→8 段 checkpoint（retire 幂等）+ headroom 学习 | Raven compacting | `runtime/context/compacting/` |
| 7.8 | turn-scratch（易变内容移出系统前缀，保 prompt cache 有效） | Raven segments/scratch | `runtime/context/` |
| 7.9 | Anthropic cache 断点优化器（≤4 断点最优摆放）+ endpoint rotor；**可选：cache warmer（成本门控 ≥$0.05 才刷新，pi cache-warmer 做法）** | Raven token_wise、pi cache-warmer | `ai/cache_optimizer.py`、`ai/rotor.py` |
| 7.10 | token/cost awareness hooks（预算标注、用量警告、cache 失效警告）+ context-scout 预扫（便宜模型选 ≤20 文件，吃 1.17/1.18） | gptme awareness hooks、`context/scout.py` | `runtime/context/` |
| 7.11 | EverOS HTTP 后端（可选启用，验证外部记忆仓接盘） | Raven raven_everos 插件 | `runtime/extensions/builtins/` |
| 7.12 | 知识库 RAG：md/pdf 摄取管线 + LanceDB/SQLite 派生索引（可重建即弃）+ `context_retrieve` 工具 + 知识页 CRUD | Raven knowledge、EverOS 三件套 | `runtime/extensions/builtins/knowledge/` |

**依赖：** P2（contracts）、**P3 基线（资格线）**。**验收：** 记忆后端过
conformance 基类；阶梯压缩在 cassette 上不回归；lessons 注入的 dropout A/B 出数据。

---

## P8｜多代理编排（动内核）｜量级 XL

| # | 功能 | 参照 | 落位 |
| --- | --- | --- | --- |
| 8.1 | **subagents 搬家**：出 `extensions/builtins/` 升 `runtime/subagents/`（行为不变字节级证明） | ADR-0007 判据 | `runtime/subagents/` |
| 8.2 | SubagentBackend 契约（agent/contracts）+ 进程内默认后端抽取成可插拔 | Raven `contracts/subagent_backend.py` | `agent/contracts/subagent.py` + `runtime/subagents/backends/` |
| 8.3 | CLI-agent 后端：ACP 驱 Claude Code / Codex（dialect wire 怪癖入库） | Raven `acp_client/` | `runtime/subagents/backends/cli_agent/` |
| 8.4 | 会话 channel 键守卫：`sub:` 过滤选单 + `imported:` 拒写；fork 携带元数据白名单 | Raven session/manager | `runtime/session/` |
| 8.5 | DAG spec schema（id 字符集文件名安全）+ 结构校验 | Raven `dag_graph.py` | `runtime/subagents/dag/graph.py` |
| 8.6 | DAG runner：确定性 ready-set 调度（节点可跑任意 backend）+ run_subagent_dag 工具 + 隐藏工具渐进披露 | Raven `dag_runner.py`、`dag_tool.py` | `runtime/subagents/dag/` |
| 8.7 | DAG store（落盘可 resume）+ live 事件（dag_run/dag_node 流，前端 DAG 瀑布图；WS 决策门在此可视需要开） | Raven dag_store/dag_live | `runtime/subagents/dag/store.py` + `server/` + `ui-web/features/dag/` |
| 8.8 | 裁决面板：CONTINUE / REASSIGN / REPLAN / ABANDON——**二期（视采用）** | Raven `dag_adjudication.py` | `runtime/subagents/dag/` |
| 8.9 | cron 产品化（stale-claim TTL）+ 心跳 wakeup（HEARTBEAT.md 模板判空 + coalesce）+ spine origin 分池启用 | Raven proactive_engine | `runtime/schedule/` |
| 8.10 | stint 长途运行记录——**二期（视采用）** | Raven `stint/` | `runtime/subagents/stint/` |
| 8.11 | run→workflow 编译器 + playbook 库——**二期（视采用）** | Raven `workflow_compiler.py`、`playbook/` | `runtime/subagents/playbook/` |

**依赖：** P4a（spine/事件流）、P7（记忆可用）、**P3 基线（资格线）**。
**验收：** 三节点 DAG 崩溃后续跑成功；`extensions/builtins/` 里只剩 provider 级
可换实现（验收 8.1）。

---

## P9｜生态｜量级 L

| # | 功能 | 参照 | 落位 |
| --- | --- | --- | --- |
| 9.1 | 插件 manifest（TOML 七贡献类型，unknown kind 忽略向前兼容） | Raven `plugins/manifest.py` | `runtime/extensions/manifest.py` |
| 9.2 | 发现管线（bundled > user > project > pip entry-points）+ 单插件回滚 + PluginContext 冻结上下文 | Raven discover/registry | `runtime/extensions/` |
| 9.3 | extensions API v2（EXTENSION_API 1→2）：ctx.sessionManager 活把手、setActiveTools、覆盖内建工具、renderer 三件 | pi 扩展自由度清单 | `runtime/extensions/api.py` |
| 9.4 | 本地 market registry：原子多件安装 + 回滚 + 分件 uninstall 账目；远端 catalog + vetting（HTTPS-only、stdio 条目限可见 payload） | Raven `market/` | `runtime/extensions/` |
| 9.5 | skills hub（搜索/安装、allow-list、byte caps、审计日志） | Raven `skill_hub/` | `runtime/extensions/` |
| 9.6 | importer：Claude Code 扫描器（记忆 MD + 会话）→ pi 扫描器，批次有界 | Raven `importer/` | `importer/` |
| 9.7 | channels intake 合同（spec.py 自动发现 + sender allowlist 空=全拒）+ 首发 Telegram、飞书 | Raven `channels/` | `channels/` |
| 9.8 | A2A 双面（agent card + peer client）——**决策门，默认缓建** | Raven `a2a/`、gptme a2a_api | `channels/` 同批视 GTM |

**依赖：** P8（builtins 搬家完成）、P4a（gateway 就绪）。**验收：** 第三方
manifest 插件安装/回滚走通；importer 成功迁入一份真实 Claude Code 会话。

---

## P10｜分发与增长｜量级 M

| # | 功能 | 参照 | 落位 |
| --- | --- | --- | --- |
| 10.1 | 桌面壳：**决策门**——Electron（原始意向）或 Tauri（gptme PyInstaller sidecar + minisign 更新器是唯一完整先例） | gptme `tauri/` | `desktop/` |
| 10.2 | deep-link 回调（`baldric://` OAuth）+ 升级窗口 install guard + beta 渠道可选 | gptme deep-link、Raven install_guard | `runtime/update/` |
| 10.3 | i18n：单一 catalogue JSON，TUI/ui-web 编译消费 + zh prompt packs | Raven 根 `i18n/` | `i18n/` |
| 10.4 | 文档 audience 声明门（构建门）+ hub 页结构 | gptme conf.py | `docs/` |
| 10.5 | 对比页 / 演示 / 基准数据常态化发布 | gptme 官网 | `website/` |
| 10.6 | opt-in telemetry + 云形态**决策门**（不预置代码，只预留安全面）+ 版本兼容矩阵与迁移指南 | gptme.ai / EverOS Cloud 参照 | 决策文档 + `docs/` |

**依赖：** P4b（桌面打包 web 面）、P9（渠道走 gateway）。**验收：** 桌面壳
安装即用且自动更新走通；i18n 编译产物进两个前端。

---

## 依赖图（文字版）

```text
P0 → P1 → P2 ─┬→ P3（评测底座）─────────┐（P6/P7/P8 动内核的资格线）
              └→ P4a → P4b → P5         │
                  └───→ P6 ─────────────┤
P3 ──────────────↗ P7 ─────────────────┤
P4a ─────────────↗ P8 → P9 → P10       ┘
```

- **并行主线**：P2 之后 P3 ∥ P4a；P5 ∥ P6 ∥ P7；P8 需 P4a（spine）+ P7（记忆）+ P3（资格线）。
- **MVP 切线**：P0 → P1(B/C) → P2 → P4a → P4b 即发网页版；P3 并行补齐。
- P2/P7/P8 承载全部"改既有行为"级内核改动；P1/P3/P6 只做增件（新文件/新钩子位）。
