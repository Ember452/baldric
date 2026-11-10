# 预期项目结构（蓝图）

> **状态：蓝图，不是契约。** 本文件描述的是随着项目成长，Baldric 的代码*预期*
> 落在哪里。它刻意不描述代码今天落在哪里，也不是合规检查清单。在你把任何一处
> 对不上的地方当成问题之前，请先读下面的「阅读规则」一节。

## 这份文档要解决什么

Baldric 的应用包目前在其根目录并列放着将近五十个模块，另外还有几个非常大的文件。
这个形状是继承来的，不是选出来的，而它让一个反复出现的问题很难回答：
*一个新功能要进来——它该放哪个目录？*

这份文档提前把这个问题的答案定下来。它是一张**落位地图**，不是现状报告。

覆盖范围是整个仓库：三个包、测试树、以及仓库根那些容易各自生长的目录。

## 阅读规则：这是一张蓝图

下列规则是文档的正文部分，不是角落里的免责声明。在使用下面的目录树之前先读它们。

1. **蓝图服务下一个决定，不评判上一个决定。** 现有代码待在别处，本身不是缺陷，
   也不因为位置不同就需要被搬动才算"正确"。
2. **不一致是预期的，也是被允许的。** 某个模块不在蓝图为它准备的位置、某个包还
   没被创建、某个包的内部文件切分和这里写的不一样——这些都是一个活着的项目的
   正常状态。不要为此开 issue。
3. **搬移需要它自己的理由。** 当某个模块真的要被改动，而这次改动让搬移变得顺手或
   值得时，再搬它——修 bug、加功能、职责确实长大了，都算。"蓝图里它在别处"
   这一条本身不是充分理由。
4. **更好的实现高于本文件。** 如果现实证明比蓝图更清晰，就改蓝图，不要为了让图
   对上而改代码。
5. **命名可以漂移。** 单数还是复数（`session/` 与 `sessions/`）、子包嵌几层，
   都不承重。承重的是「两条承重的规则」那一节里的两条。
6. **本文件不做任何强制。** 现在没有任何 CI 检查读这份文档。如果将来要加机械
   检查，它需要自己的一篇 ADR，而且只钉住那条最值得钉的规则。

## 依据

下面的形状不是为本项目凭空发明的。它取自 Pi 的组织方式，以及同量级的成熟 Python
agent 项目如何组织自己。

所参考的项目（只到项目级，不列具体路径）：

- **Pi** —— 本项目所翻译的上游 TypeScript monorepo；`modes` 这条轴、
  tools/renderers 成对、session/runtime/services 三分法都来自它。
- **OpenHands software agent SDK** —— 被调查项目中最大的一个；包根保持接近空，
  能力包一路细分到约 27 个。
- **gptme** —— 范围上最接近的 Python 同类项目；provider、tools、CLI、TUI、MCP、
  skills、hooks 各自成命名包。
- **SWE-agent**、**atomic-agents** —— 包根最小的两个；一切都通过能力包进入。
- **MetaGPT**、**mem0**、**smolagents**、**basic-memory** —— 佐证同一套
  "能力名词"词汇。

跨项目真正一致的发现**不是文件大小**。远超一千行的单文件在这些项目里很常见，
也被容忍。所有大项目共同具备的是**一个几乎为空的包根**：少量门面文件，
加上每一块业务逻辑都在某个命名能力包里。

## 分层边界不变

本文不动顶层架构，它保持原样：

```text
baldric_ai      provider/model streaming layer
baldric_agent   portable agent harness, loop, tools, events, sessions
baldric_coding  CLI app, resources, skills, extensions, commands, TUI integration
```

`baldric_agent` 继续承担不依赖 CLI、Textual、Rich 渲染、会话文件位置、以及
应用专属资源加载的义务。下面先给仓库整体，再逐包展开。

## 全局目标结构

### 仓库根

```text
baldric/
├── pyproject.toml  uv.lock  .python-version
├── README.md  AGENTS.md  CONTRIBUTING.md  LICENSE
├── .gitignore
│
├── src/
│   ├── baldric_ai/         模型传输层
│   ├── baldric_agent/      可移植大脑
│   └── baldric_coding/     应用层
│
├── tests/                  镜像 src/ 的形状（见下）
│
├── dev-notes/              建造日志：设计、ADR、阶段记录（内部，作者读）
│   ├── architecture/  adr/  design/
│   └── INDEX.md 之类的人手指引
│
├── website/                发布文档：用户指南与参考（对外，用户读）
│   ├── content/  src/  assets/  static/  data/
│   └── tests/
│
├── examples/               可运行的扩展示例，是唯一来源（见下）
├── scripts/                开发期一次性脚本与代码生成器
└── .github/
    ├── workflows/          ci.yml  docs.yml  publish.yml
    └── CODEOWNERS  dependabot.yml
```

仓库根只放**分发与元数据文件**。任何只有开发者用、却住在根目录的东西，都会慢慢
变成下一个没人认领的文件。具体地：

- `docs/` 目前只装着一张 README 引用的图片。它的职责和 `dev-notes/`（内部日志）、
  `website/content/`（发布文档）重叠。蓝图倾向于：**要么**把它并进
  `website/assets/`，**要么**明确它是"仓库自有静态资源"的唯一位置并把
  `website/assets/` 的图片收进来。两者都行，第三处不行。
- `plans/` 只有一份计划，而 `dev-notes/design/` 装的是同类东西。同一目的的两个位置
  迟早要人猜哪个是最新的。
- `landing.html` 住在根目录，而站点在 `website/`。它的归属需要写明。
- 十六进制命名的导出物已经有一条 `[0-9a-f]*.html` 忽略规则，说明有测试把导出结果
  写进了仓库根。蓝图要求：**测试产物写入临时目录**，不要落在工作树里。
- `.venv313/` 没有被忽略（`.gitignore` 只写了 `.venv`）。建议改成 `.venv*/`。
- 三个包的根目录各有一份 `py.typed`。它是 PEP 561 的类型标记，
  必须留在包根，也不能进子目录——搬动包内文件时它是那个很容易被误搬的文件。

### `src/baldric_ai/`

这个包有 20 个文件平铺在根。作为对照，被调查项目里同一层的包既有扁平的
（gptme 的 llm 层就是二十多个带前缀的扁平文件），也有分层的（Pi 和 OpenHands 都
把 provider、auth、catalog 拆成了子目录）。所以这里属于**轻度过线**，建议温和地收：

```text
baldric_ai/
├── __init__.py  provider.py  events.py  content.py  stream.py
│                                ▲ 契约面，留在包根是合理的
├── providers/   anthropic.py  openai_compatible.py  openai_codex.py
│                google.py  mistral.py  fake.py
├── catalog/     model_catalog.py  model_limits.py
├── net/         http.py  http_errors.py  retry.py  env.py
└── internal/    openai_cache.py  tool_call_ids.py  _provider_events.py
```

一个命名提醒：`_provider_events.py` 与 `baldric_agent/provider_events.py` 同名不同
物，搬动时是最容易接错线的一对。

### `src/baldric_agent/`

**这个包已经基本达标**，蓝图对它只有一处建议。它有 11 个文件加一个已经成形的
`session/` 包，规模和组织都和它该有的样子接近。可移植大脑的文件越少动越好——
每次改动这里都等于改动可移植性契约。

```text
baldric_agent/
├── __init__.py  provider.py  types.py
├── harness.py  loop.py            ▲ 核心，刻意保持扁平且小
├── contracts/  messages.py  events.py  provider_events.py
├── tools/      tools.py  tool_arguments.py  tool_history.py
└── session/    entries.py  jsonl.py  storage.py  memory.py  tree.py   （已合规）
```

### `src/baldric_coding/`

> **阶段 1 更新（2026-11-05）：** A/B/O 类移动已落地；树中标注“第二阶段”的拆分项仍未实现，
> 仍属蓝图。`config/` 是阶段 1 新增的补充包（蓝图原文未列，已在树中补入）。
> 实际落地与提交级证据见 [layout-migration-log.md](./layout-migration-log.md)。

```text
src/baldric_coding/
├── __init__.py            公开门面；对外兼容面就在这里
├── cli.py                 真实入口；pyproject 的 baldric = "baldric_coding.cli:app"
├── events.py              Pi 兼容的会话事件契约
├── version.py  py.typed
├── rpc.py                 C 类停车：第二阶段先整体搬到 modes/rpc.py，再拆分
│
│                          ▲ 根目录就是这六个（rpc.py 为阶段 1 的 C 类停车）
│                            （py.typed 是 PEP 561 标记，必须留在包根，不可进子目录）
│
├── modes/                 一个会话，多种外壳。这是 Pi 的思路（本阶段不建；第二阶段新增）
│   ├── interactive/       由 TUI 承载的模式：只做编排，不放 widget
│   ├── print.py           一次性文本输出
│   ├── json.py            机器可读的事件输出
│   └── rpc/               行分隔的控制协议
│
├── rendering/             事件 → 输出的渲染器（已存在，被 cli.py 与 __init__.py 引用）
│   ├── base.py  plain.py  json.py  transcript.py
│   └── themes/            主题数据与主题 json（从 tui/ 并入：它不是 UI）
│
├── session/               一切拥有会话状态的东西
│   ├── session.py         状态与历史（阶段 1 整文件停车）
│   ├── runtime.py         驱动 agent 循环（第二阶段拆出）
│   ├── services.py        被注入进来的能力（第二阶段拆出）
│   ├── manager.py  prepare.py  usage.py  stats.py  branch_summary.py
│   ├── compaction/        上下文窗口计量与摘要
│   └── export.py          会话导出（阶段 1 整文件停车；export/ 目录属第二阶段）
│
├── tools/                 模型可以调用的能力
│   ├── registry.py  base.py  truncate.py  output_accumulator.py（registry 为阶段 1 停车；其余第二阶段）
│   ├── read.py  write.py  edit.py  bash.py（第二阶段）
│   ├── image_processing.py
│   └── renderers/         每个工具一个渲染器，同名、同目录（第二阶段）
│
├── context/               提示词的周围环境如何拼出来
│   ├── project.py  gitignore.py  resources.py
│   ├── system_prompt.py  thinking.py
│   ├── skills/            技能的发现与调用
│   └── prompts.py         提示词模板
│
├── commands/              斜杠命令，一条命令一个文件（第二阶段的拆分）
│   └── registry.py  login.py  model.py  resume.py  compact.py  export.py  …
│
├── providers/             模型与端点配置
│   ├── config.py  catalog.py  runtime.py  loader.py  virtual_models.py
│   ├── stores/            缓存的与生成的模型元数据
│   └── compose/           provider 组合、远端目录覆盖（第二阶段）
│
├── auth/                  凭据与登录
│   ├── credentials.py  registry.py  types.py  oauth.py
│   └── flows/             每个 provider 的 OAuth 流程一个文件
│
├── trust/                 环境级项目信任策略与存储（它的 Textual 屏在 tui/trust.py）
├── backends/              provider 中立的本地后端契约（它的宿主屏在 tui/backends.py）
│
├── extensions/            插件边界
│   ├── api.py  loader.py  runtime.py  providers.py  provider_registry.py
│   ├── installer.py  builtin_registry.py  （从根目录搬入的两个）
│   ├── package_manager.py            （预期新增，今天不存在）
│   └── builtins/          subagents/  llama_cpp/  …
│
├── tui/                   Textual 前端
│   ├── app/  widgets/  adapter.py  state.py  keybindings.py（app/ widgets/ 属第二阶段；config.py 为阶段 1 保留）
│   ├── autocomplete.py  footer.py  file_drop.py
│   ├── config.py
│   ├── trust.py  backends.py          （两个契约域的 Textual 屏，见下方说明）
│   └── terminal_title.py  terminal_notification.py
│
├── config/                paths.py  shell_config.py（阶段 1 补充包）
├── observability/         遥测、缓存统计、耗时、崩溃日志
├── update/                更新检查、updater、reload
├── mcp/                   Model Context Protocol（等它落地时）
├── security/              沙箱或权限边界（需要时）
├── data/                  打包资源，永远留在包根，不随模块移动
└── utils/
```

**阶段 1 后的实际状态（2026-11-05）：** 根目录实际为 `__init__.py`、`cli.py`、
`events.py`、`version.py`、`rpc.py`（外加 `py.typed`）。已落地的包与文件：
`rendering/themes/`；`session/{session,manager,prepare,usage,stats,branch_summary}.py`、
`session/compaction/context_window.py`、`session/export.py`；`tools/{registry,image_processing}.py`；
`context/{project,gitignore,resources,system_prompt,thinking,prompts}.py`、`context/skills/skills.py`；
`commands/registry.py`；`providers/{config,catalog,runtime,loader}.py`、`providers/stores/*`；
`auth/{credentials,oauth,registry,types}.py`、`auth/flows/*`；`trust/policy.py`；`backends/contracts.py`；
`extensions/{installer,builtin_registry}.py`；`config/{paths,shell_config}.py`；
`observability/diagnostics.py`；`update/{check,updater,reload}.py`；`utils/self_docs.py`。
仍属第二阶段的内容：`tools/registry.py` 内的单工具文件与 renderers、`session/session.py` 的
runtime/services 拆分、`session/export/`、`commands/` 的其余命令文件、`tui/app/`、
`tui/widgets/`、以及整个 `modes/` 子树。

关于这个包的四处选择：

> **读这棵树的方法**：它里的名字是**目标名**，不是当前名。很多条目是对现有模块的
> 改名加归包，所以今天的文件名大多不会在树里直接出现：
> `tools.py` → `tools/registry.py` 与每个工具一个文件；`session_manager.py` →
> `session/manager.py`；`provider_config.py` → `providers/config.py`；
> `oauth_anthropic.py` → `auth/flows/anthropic.py`；`rpc.py` → `modes/rpc/`。
> 判断"某个现有模块是不是被遗忘了"，请看它能不能对应到树里的某个目标位置；
> 对不上才是真的缺口（本轮修订前的 `cli.py` 与 `rendering/` 就是这种情况）。
> 树中确实不存在、也未标注为预期的名字，属于缺陷，应该修文档。

- **主题不属于 `tui/`，但也不单独成一个顶层包**，它住在 `rendering/themes/`。两件事各自有证据：
  其一，主题数据被 **3 个非 UI 模块**读取（`commands.py`、会话导出、用量统计），把它留在 `tui/`
  等于把整个终端前端拖进非 UI 代码——这是那两组环的根因。其二，已核实 `tui/themes/` 自身
  对 `tui` 其他部分**零引用**，而 `tui/` 对 `rendering/` **零引用**，所以并入渲染层不产生新环。
  主题与 plain/json/transcript 渲染器同属“输出样式”，放在一处比开一个顶层包更贴合职责，
  也少一个顶层包。
- `mcp/` 是顶层包而不是内置扩展。被调查的 Python 项目都把它放在顶层；Pi 把它
  藏成 extension，那是它的 JavaScript 打包方式决定的。这两种选择将来改动都只是
  一次搬移，所以这是个低风险决定。
- `rendering/` 与 `modes/` 是两层东西，不是重叠。`rendering/` 是事件到文本的
  渲染器（已存在，含 base/plain/json/transcript）；`modes/print.py` 与
  `modes/json.py` 是薄薄的驱动：跑会话、把事件交给 `rendering/`。
  依赖方向只能有一个：`modes/ → rendering/`，渲染器不得反过来知道模式。
- `trust/` 与 `backends/` 各自裂成两半，这是有意为之。策略与契约住在顶层包，
  它们的 Textual 屏住在 `tui/trust.py` 与 `tui/backends.py`。今天已经是这个
  形状（根目录一份契约，`tui/` 一份适配），蓝图只是把位置名字写清楚。
  依赖方向是 `tui/ → trust/` 和 `tui/ → backends/`，单向的。承重规则 2 禁止的
  不是这种依赖，而是把跨前端必需的逻辑写进 `tui/` 里。

**`modes/` 与 `cli/` 的分界（这条比包名本身重要）。** 两者读起来都带“命令行”的味，不划清
就会反复摇摆：

| | 负责什么 | 特征 |
|---|---|---|
| `cli/` | 解析参数、校验、**决定用哪个模式**、装配所需对象，然后把控制权交出去 | 只在“进程被启动”这一刻成立，**不跑会话** |
| `modes/` | 持有一次会话，把事件流变成该外壳的输出 | 从会话开始之后，**不碰 argv** |

一句话判据：**“换个前端还要不要重写一遍？”** 要重写 → 属于 `modes/` 下那个具体外壳；
不需要重写、只跟启动有关 → 属于 `cli/`。这条是承重规则 2 在启动路径上的具体形态。

注意 `modes/` 这个包名来自 Pi，**被参考的 Python 项目里没有先例**（gptme 把这类逻辑
分散在 `cli/`、`tui/`、`server/` 顶层包）。保留它是为了“一个会话、多种外壳”这个意图
能被直接读出来，以及和 Pi 的上游 PR 能一一对号——这是取舍，不是证据结论。
改名很容易（纯目录改名），所以这不是一个需要现在定下的决定。

今天 `cli.py`（1409 行）同时承担上表两件事。而入口名 `baldric_coding.cli:app` 是
pyproject 里的已发布入口点，改动它等于改动安装契约，所以**这不是一个可以顺手做的
重命名**。蓝图想要 Pi 那种“参数解析 / 起动装配”分离，但那是本蓝图之外的阶段。

### `tests/`

测试树跟 src 同形。这是被调查项目里最一致的观察之一：包结构变了而测试仍然
一个目录平铺，新人写测试时就没有地方可放。

```text
tests/
├── conftest.py  helpers/
├── ai/                       对应 baldric_ai
├── agent/                    对应 baldric_agent
├── coding/                   对应 baldric_coding，内部再按包分
│   ├── providers/  session/  tools/  commands/  context/  extensions/
│   └── tui/  modes/  auth/  trust/
└── fixtures/
```

几个具体项：

- `tests/website/copy-code.test.mjs` 和 `website/tests/site.test.mjs` 是同一件事的
  两个家。网站测试应该只住在 `website/tests/`。
- `pyproject.toml` 的 `testpaths = ["tests"]` 递归收集，建子目录不需要改配置。
  真正需要同步的是 `test_package_metadata.py` 这类会钉住打包路径的测试。
- 搬移时测试的 import 单独一次改完，**断言一字不动**——否则测试会从安全网
  变成共犯。

### `examples/` 与打包资源

`examples/extensions/` 与 `src/baldric_coding/data/examples/extensions/` 现在是
两份拷贝，且已经出现漂移：其中一个比另一个多出 `permission_gate.py`。蓝图要求：

- **根目录的 `examples/` 是唯一来源**，随包分发的那一份由脚本生成，禁止手改。
- `data/` 跟它的归属模块住在一起（所以它在 `baldric_coding/` 里）。搬动
  读取它的代码时，必须把 `data/` 一起搬，并跑一次真实读取来验证
  `importlib.resources` 路径——不要等到打包才发现。

## 落位指引

要加东西时，按这个顺序问。

```text
0. 它会改变 agent 循环本身的含义吗？
      → baldric_agent。动它就是动可移植性契约，
        因此值得本指引里最重的审视。
1. 它只是模型 wire 协议上的差异吗？
      → baldric_ai/providers/
2. 它是只有某一个前端才有的行为吗？
      → 该前端：modes/interactive、modes/print.py、modes/json.py、
        modes/rpc/，或者 tui/ 下的一个 widget
3. 它是所有前端都该有的行为吗？
      → tools/        模型能调用它
        commands/     用户能敲出它
        session/      它拥有会话数据
        context/      它塑造提示词
        providers/    它选择或配置模型
        auth/         它获取或保存凭据
4. 它是可选的、可卸载的、不属于默认产品的吗？
      → extensions/builtins/<name>/
5. 以上都不是，但它确实是一块能力领域？
      → 在 baldric_coding/ 下开一个新的同级包，而不是往根目录再扔一个文件
6. 它根本不是 Python 代码（文档、脚本、示例、静态资源）？
      → 按「仓库根」一节的分工选家：dev-notes/（内部）、website/content/（对外）、
        examples/（唯一来源）、scripts/（开发期），而不是新建根目录条目
```

举几个实例：

| 功能 | 放哪 | 不放哪 |
|---|---|---|
| `grep` 或 `find` 工具 | `tools/grep.py` 加 `tools/renderers/grep.py` | 往 `tools/registry.py` 里堆 |
| MCP 支持 | `mcp/` | `providers/`（MCP 是工具来源，不是模型来源） |
| 新增一个模型 provider | `baldric_ai/providers/`，`providers/` 里加一条目录项，`auth/flows/` 里加一个流程 | 三处只改其中一处 |
| plan mode | `extensions/builtins/plan_mode/` 加一个薄薄的 `commands/plan.py` | `baldric_agent` |
| 新前端（IDE bridge、HTTP server） | `modes/<name>/`，只订阅 `events.py` | 任何触碰 `session/` 内部的地方 |
| 用量或成本遥测 | `observability/` | `tui/`（数字不是渲染） |
| 沙箱或权限边界 | `security/`，与 `trust/` 分开 | `trust/` |

## 两条承重的规则

上面所有内容里，真正承重的只有这两条，而其余结构都为它们服务。

**1. 包根保持接近空。** 少量门面文件，不放业务逻辑。今天三个包的根分别是
50、21、12 个文件（`baldric_coding`、`baldric_ai`、`baldric_agent`），而
OpenHands、SWE-agent、atomic-agents 的对应数字是 3、4、1。这是被调查的每一个
大项目都具备、而本项目当前不具备的性质。它守住了，整棵树会自己长成形；它一破，
根目录就会慢慢退回平铺堆，而本文其余所有约定都会变成装饰。

**2. 跨前端的逻辑不住在前端里。** 凡是在 TUI、print 模式、RPC 下必须表现一致的
东西，都属于 mode 边界之下。`session/` 和 `tools/` 必须能在没装 Textual 的情况下
被 import。今天有一处违反了这条，而那恰恰是前面所说的被允许的偏差——具体见
「蓝图尚未成为现实的阻碍」一节。

## 蓝图尚未成为现实的阻碍

下面这些就是这棵树今天还只是蓝图的原因。之所以记下来，是因为将来的迁移会先撞上
它们，也是因为知道它们才可能搬得安全。

| 阻碍 | 证据 |
|---|---|
| `commands` 与 `tui` 互相 import | **阶段 1 已消除**：`commands/registry.py` 不再 import `tui`（主题改由 `rendering.themes` 提供）；`tui → commands` 单向保留 |
| `session` 与 `tui` 互相 import | **阶段 1 已消除**：`session/` 包不再在顶层 import `tui`（主题改由 `rendering.themes` 提供）；`tui → session` 单向保留 |
| 主题数据被 3 个非 UI 模块读取 | **阶段 1 已解决**：`themes` 已从 `tui/` 移入 `rendering/themes/`，非 UI 导入不再拖入终端前端 |
| TUI 前端依赖几乎所有其他领域 | 终端层引用了大约二十七个不同的模块 |
| 有两个文件各自承担多份职责 | 会话包装器与 TUI 应用。Pi 在同等规模上是同样的形状，所以这是继承来的，不是本地写坏的；拆分属第二阶段 |
| 扩展示例已有两份并且在漂移 | `examples/extensions/` 与包内 `data/examples/extensions/` 共享四个文件，其中一份多出 `permission_gate.py` |
| 同类职责住在多处 | 文档有 `docs/`、`dev-notes/`、`website/content/` 三处；计划有 `plans/` 与 `dev-notes/design/` 两处；网站测试有 `tests/website/` 与 `website/tests/` 两处 |
| 入口文件同时承担参数解析与起动装配 | `cli.py` 一个文件 1409 行；而它是已发布的入口点 `baldric_coding.cli:app`，拆分时包名路径不能变。**阶段 1 按不动处理，拆分归第二阶段** |

**断环在任何搬移之前。** 拆那两个大文件放在最后，因为和搬移不同，它会改变行为，
需要先补上或扩展测试。

## 明确不要求的

这份蓝图不要求下面任何一项。

- 把 `baldric_coding` 拆成独立分发的包。
- 重命名 `tui/`；Pi 和被调查的 Python 项目都用这个名字。
- 镜像 Pi 的 `core/` 目录。Pi 自己的 core 区域已经长成一大堆平铺文件，
  它不是可以照抄的范本。
- 采用 TypeScript 特有的结构，例如生成的模型数据文件。
- 给单个文件设行数上限。
- 为了让代码对上某张图而搬动现有代码。
