# 参考体系决议证据摘要（自会话存档提取）

- 日期：2026-11-11
- 来源存档：仓库外工作区文件 `D:\DEVELOP\Solis\session-ses_e406.md`（2026-11-09 会话，
  1359 行）。本文件提取其中**仍承载"为什么"的证据与决议**；完整功能表已并入
  [../plans/2026-11-11-productization-roadmap.md](../plans/2026-11-11-productization-roadmap.md)，
  结构与治理决议已并入 [../adr/0007-productization-target-structure.md](../adr/0007-productization-target-structure.md)，
  本文不复述。结构债事实清单见 [2026-11-11-structure-debt-review.md](2026-11-11-structure-debt-review.md)。

## 一、参考项目能力盘点（事实摘要，均经源码核对）

### pi（pi-main，TS monorepo）
- packages: agent / ai / coding-agent / tui / mcp / schema / telemetry / chord（跨进程对象
  运行时：contracts、documents、store、web 与 terminal clients）/ durable（会话任务文档
  运行时 + codemode + env 远程执行）/ evals。
- coding-agent/src/core/tools 最小集：bash / edit / edit-diff / find / grep / ls /
  powershell / read / write / truncate + renderers/ + file-mutation-queue + output-accumulator。
- 扩展自由度三要素（`packages/coding-agent/docs/extensions.md`）：四级事件面（input /
  session 结构级 / turn·message·tool / provider 七事件）；活把手 ctx（sessionManager、
  fork/navigateTree、appendEntry 自定义 entry、setActiveTools、覆盖内建工具）；自定义
  类型的完整持久化 + renderer 管道。前提 = 事件源可回放会话。
- packages/durable：jsonl/sqlite/store/memory 四存储后端共跑同一 conformance 测试
  （fsync 顺序、原子替换、崩溃恢复）——"默认仍发 JSONL"的工程依据。

### gptme（gptme-master，Python，flat layout）
- tools/ 45+（browser 五实现、computer、tmux、python_kernel、gh、patch(_many)、
  hashline_edit、lessons、memory、rag、todo、shell_background、shell_validation、
  form/elicit/choice/clarify）；hooks/ 30+（cost/token/cache awareness、guardrails、
  injection_screening、auto_snapshots）。
- server/ 15.4k 行：REST /api/v2 + SSE + 三种鉴权 + Host 头校验 + metrics；
  webui/（React/Vite，pages/stores 旧分层）；tauri/（PyInstaller server sidecar +
  minisign 更新器 + `gptme://` deep-link）——参考系中唯一完整桌面分发配方。
- 会话持久化：每会话目录 conversation.jsonl + branches/ + events.jsonl（每 50 事件
  checkpoint cell）+ files/ CAS 附件；fsync 屏障先于 generation_complete 发出。
- 退出码分类学：75=限流(EX_TEMPFAIL) / 76=鉴权 / 77=模型不可用（76/77 为自定义段，
  sysexits.h 无对应）。eval/ 27k 行（suites、swebench、tbench、leaderboard、启动时间 CI 门）。
- 已知教训（不学）：tui/app.py 180KB、api_v2.py 158KB 单文件膨胀；Flask 栈。

### Raven（Raven-main，Python + TS，~93 万行）
- raven/ 291k 行，49 个子包。关键件：permissions/（gate.py 决策瀑布 ~3.5k 行、
  rules/session/turn/shell_policy）、security/（wrap_untrusted nonce 围栏、SSRF 防 DNS
  rebinding、redact 三层脱敏）、sandbox/（SandboxExecutor + direct executor env 白名单 +
  boxlite）、trajectory/（bundle/replay/regression cassette/redaction/bugreport）、
  context_engine/（段式装配 + Scavenger + 阶梯压缩 + headroom 学习）、memory_engine/
  （consolidate + off-turn 有界投递 + 契约测试基类）、agent_plugins/ + plugins/（TOML
  manifest 七贡献类型 + entry-points 发现 + 单插件回滚）、market/、playbook/、stint/、
  rpc/（OpenRPC 258 方法 + broker 模式 + spine/lane + gateway/outlet）、channels/（12 适配器）。
- ui-web/src：rpc/（transport 三实现 + generated.ts + capabilities）+ features/ 24 域
  （transcript/composer/dag/trajectory/subagents/tasks/memory/knowledge/model/settings/onboard…）。
- 教训（不学）：巨石聚合 runtime、evolver/curator 自演进、litellm 依赖。

### EverOS（EverOS-main，Python，~60K 行，Apache-2.0）
- 记忆运行时：Markdown 真相源（~/.everos/{agents,users,knowledge}/）+ SQLite 状态/审计/队列
  + LanceDB 向量/BM25；cascade watcher 编辑即同步；索引可从真相源全量重建。
- DDD 分层 + import-linter 强制方向：entrypoints(cli/api/tui) → service(bootstrap 单装配器
  + Memory/Knowledge/Ops facade) → memory(域) ← infra(适配器/引擎)。
- api 层即 FastAPI 标准层级（app/dependencies/exception_handlers/middleware/routes/schemas
  + envelope），能力分级：[llm]→关键词检索；[embedding]→混合检索+reflection；[rerank]→
  agentic 检索+Knowledge Wiki。
- everos-mcp（`uvx everos-mcp`）+ Claude Code plugin：记忆能力的两个外部消费形态。

### opencode（opencode-dev，TS，bun monorepo）
- packages/ 35+：server/client 分离、session-ui、plugin(-browser)、codemode、
  effect-drizzle-sqlite（会话存储迁 SQLite 的少数派样本）、desktop。
- 借鉴：模式（client/server、生成式 SDK、pair 配对码）；不搬代码。

### basic-memory（basic-memory-main，Python）
- Markdown 知识库 + MCP server + SQLite 同步 + importers + api(v2 routers)。
- 借鉴：分层 markdown 记忆的落地形态（P7.2 直接参照）；反面教材：services/ 30+ 文件过碎。

## 二、会话存档中已并入 ADR-0007 的决议（索引用）

| 决议 | 并入位置 |
| --- | --- |
| 单命名空间 `baldric.*`（否决平铺，`mcp` 撞名证据） | ADR-0007 背景 |
| 应用包名 `runtime`（`baldric_core` 否决：core=最底层本质通义） | ADR-0007 背景 |
| protocol=字节契约 vs contracts=运行时端口 命名法 | ADR-0007 §4 |
| extensions/builtins 三问准入（subagents 搬家、llama_cpp 留驻、mcp 桥退役） | ADR-0007 §4 |
| JSONL canonical（pi durable conformance 证据、Windows fcntl 前科）+ SQLite 两个合法位置 | ADR-0007 §4 |
| 事件源可回放 = 扩展自由度前提（把手×回放公式） | ADR-0007 §6（server 时序） |
| server 时点在事件源耐久会话之后 | ADR-0007 §6 |

## 三、已并入路线图的批次排序依据（索引用）

- 工具三梯队：glob/grep/todo/clarify/choice/后台命令（第一梯队，互不依赖）→
  hooks 类型学+确认链+shell 校验（第二梯队，持久 shell 前置）→ 持久 shell /
  python REPL / patch_many（第三梯队押后；patch_many 去留并入 hashline A/B）。
- glob/grep 喂养 context-scout（7.10）与 eval 场景；clarify/choice 是审批 UI 原语与
  subagent 问人通道前身；todo 是 task_board/DAG 的单 agent 雏形。
- DAG 最小路径：spec→graph→runner 三件套接管 FIFO 队列；裁决面板/resume 后置二期。
- 阶段 6/7 依赖（编排要 spine、DAG 后端走 RPC）；4/5 类可与 server 批并行。
- Raven 异域件（stint / playbook 编译器 / 裁决面板）标二期（视采用），与
  "不照搬 Raven 全量"裁决一致。
