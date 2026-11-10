# 项目信任：兼容性研究与 Baldric 设计

状态：**仅设计**。Baldric 尚未实现该策略。

本笔记是 [issue #535](https://github.com/huggingface/tau/issues/535) 文档优先阶段的实施计划。它从第一性原理解释问题，记录 Pi 的生产行为，审计 Baldric 的
当前行为，并在运行时代码变更之前敲定 Baldric 的预期设计。

一个仓库今天可以影响 Baldric，仅仅因为 Baldric 在那个仓库里启动。项目信任将在这个隐式输入
加载之前放一个决定。它不是"仓库里每个文件都安全"的判断。

## 兼容性基线与研究方法

Pi 于 **2026-08-03** 在下列确切修订处检视：

- 仓库：[`earendil-works/pi`](https://github.com/earendil-works/pi)
- commit：[`fa07e7bd92c90a0210a269354733c274e9fc11e6`](https://github.com/earendil-works/pi/commit/fa07e7bd92c90a0210a269354733c274e9fc11e6)
- commit 日期：2026-08-03 19:57:44 UTC

以下引用均 commit 钉死、可检视：

- [`docs/security.md`](https://github.com/earendil-works/pi/blob/fa07e7bd92c90a0210a269354733c274e9fc11e6/packages/coding-agent/docs/security.md)
  是 Pi 简明的面向用户契约。
- [`core/trust-manager.ts`](https://github.com/earendil-works/pi/blob/fa07e7bd92c90a0210a269354733c274e9fc11e6/packages/coding-agent/src/core/trust-manager.ts)
  检测资源、规范化键、搜索祖先、读写
  `trust.json`。
- [`core/project-trust.ts`](https://github.com/earendil-works/pi/blob/fa07e7bd92c90a0210a269354733c274e9fc11e6/packages/coding-agent/src/core/project-trust.ts)
  定义决定顺序、默认值、extension 参与与启动
  选项。
- [`core/resource-loader.ts`](https://github.com/earendil-works/pi/blob/fa07e7bd92c90a0210a269354733c274e9fc11e6/packages/coding-agent/src/core/resource-loader.ts)
  实现信任前与最终资源加载两遍。
- [`core/settings-manager.ts`](https://github.com/earendil-works/pi/blob/fa07e7bd92c90a0210a269354733c274e9fc11e6/packages/coding-agent/src/core/settings-manager.ts)
  在不受信任时阻止项目 settings 加载。
- [`src/main.ts`](https://github.com/earendil-works/pi/blob/fa07e7bd92c90a0210a269354733c274e9fc11e6/packages/coding-agent/src/main.ts)
  确立引导与 session-cwd 顺序。
- [`cli/project-trust.ts`](https://github.com/earendil-works/pi/blob/fa07e7bd92c90a0210a269354733c274e9fc11e6/packages/coding-agent/src/cli/project-trust.ts)
  把暴露给 extension 的信任 UI 限制在交互式启动。
- [`interactive-mode.ts`](https://github.com/earendil-works/pi/blob/fa07e7bd92c90a0210a269354733c274e9fc11e6/packages/coding-agent/src/modes/interactive/interactive-mode.ts)
  包含 `/trust`、reload 与 resume 集成。
- [`core/agent-session-runtime.ts`](https://github.com/earendil-works/pi/blob/fa07e7bd92c90a0210a269354733c274e9fc11e6/packages/coding-agent/src/core/agent-session-runtime.ts)
  在替换 session 时重建 cwd 绑定的服务。
- [`examples/extensions/project-trust.ts`](https://github.com/earendil-works/pi/blob/fa07e7bd92c90a0210a269354733c274e9fc11e6/packages/coding-agent/examples/extensions/project-trust.ts)
  演示 extension 决定与仅 session 结果。
- [`test/trust-manager.test.ts`](https://github.com/earendil-works/pi/blob/fa07e7bd92c90a0210a269354733c274e9fc11e6/packages/coding-agent/test/trust-manager.test.ts)
  验证持久化继承与触发检测。

这些引用描述的是该修订，不是一个假定的永恒 Pi 契约。

## Pi 的生产行为

### 什么触发决定

Pi 先问 cwd 是否有需要信任的资源。裸 `.pi`
目录不触发任何东西。在被检视修订处，这些条目会触发：

- `<cwd>/.pi/settings.json`
- `<cwd>/.pi/extensions`
- `<cwd>/.pi/skills`
- `<cwd>/.pi/prompts`
- `<cwd>/.pi/themes`
- `<cwd>/.pi/SYSTEM.md`
- `<cwd>/.pi/APPEND_SYSTEM.md`
- cwd 或任何祖先的 `.agents/skills`，用户自己的
  `~/.agents/skills` 除外

对 `.pi` 目录，存在即触发；不需要含有有效资源。这就是为什么只有裸 `.pi` 目录被显式忽略。

没有触发时，`resolveProjectTrusted()` 直接返回 true，不查存储也不提示。Pi 为该 cwd 记住这个进程内结果。
其交互式 reload 有特殊处理：先前为空的项目获得了受保护资源后，Pi 在 reload 后保存一个隐式的信任决定。Baldric
将刻意在此不同；见 [Reload](#reload)。

### 受门控与不受门控的输入

受信任时，Pi 可以加载项目 settings、项目 `.pi` extension、skill、
prompt、主题、`SYSTEM.md`、`APPEND_SYSTEM.md`、项目包资源，并安装缺失的项目包。因此项目 extension 与包 extension 只能在批准之后执行。

决定之前，Pi 只加载：

- 全局 `AGENTS.md`/`CLAUDE.md` 与祖先 context 文件；
- 用户/全局 extension；
- CLI `-e` 显式传入的 extension；
- 内联应用 extension。

这些信任前 extension 可以参与决定。项目 extension
不能决定自己是否应当运行。

Pi 有意让 `AGENTS.md` 与 `CLAUDE.md` context 不设门，除非禁用 context 加载。CLI 显式资源路径同样保持合格；
它们代表用户的直接指令，而不是环境性发现。

### 规范路径、祖先与持久化

Pi 把决定存于 `~/.pi/agent/trust.json`。键是规范化的绝对 cwd
路径。`resolvePath()` 把路径变为绝对并归一化；`canonicalizePath()`
用 `realpathSync()` 跟随符号链接，realpath 失败时回退归一化原始路径。

查找从规范 cwd 走到文件系统根。最近的值为 `true` 或 `false` 的条目获胜。因此子决定覆盖父决定。选"信任父目录"会为直接
规范父目录写信任并移除确切的子决定，让继承生效。

文件是排序后的 JSON 对象，值可为 `true`、`false` 或 `null`；
查找忽略 `null`（普通移除即删除键）。Pi 校验整个
对象并用锁文件处理并发。被检视版本直接写目标而不是原子替换，也没有
schema-version 字段。读取/解析/校验/锁/写失败都是错误；不会被转化为批准。

### 决定顺序、范围与无头行为

Pi 按此顺序解析：

1. 单次运行的 `--approve`/`-a` 或 `--no-approve`/`-na` 覆盖；
2. 无触发即受信任；
3. 第一条决定性的信任前 extension 结果；
4. 最近的已存 cwd/祖先决定；
5. 全局 `defaultProjectTrust`，默认 `ask`；
6. 仍为 `ask` 时，有 UI 则提示，否则拒绝。

启动提示提供：

- 信任这个确切文件夹并保存；
- 信任直接父目录并保存；
- 仅本 session 信任；
- 不信任这个确切文件夹并保存；
- 仅本 session 不信任。

取消是安全拒绝。交互式 `/trust` 选择器稍后编辑已保存的确切/父决定，但声明需要重启；它不改当前
session 已加载的集合。

print、JSON 与 RPC 模式从不提示。没有 extension 或已存决定时，
`ask` 与 `never` 拒绝，`always` 批准。CLI 覆盖只作用于一次调用且不持久。参数解析器拒绝同时给出 approve 与 no-approve。

### 引导、extension 与 cwd 变更

Pi 初始创建 `projectTrusted: false` 的 settings 管理器，所以第一次代理引导只来自全局 settings。该修订有一个重要的实现警告：迁移之后，`main.ts` 创建第二个启动 cwd settings 管理器，默认 `projectTrusted: true`，并在最终信任解析之前用它做启动 session 目录查找。
最终的 cwd 绑定运行时加载确实强制下述信任切分，
但这个早期启动 settings 读取不是 Baldric 应照抄的模式。

Pi 在创建最终 cwd 绑定运行时服务之前选择 session——包括来自其他项目的 session。因此最终信任针对
session 的实际 cwd 解析，而不是盲目针对进程的启动目录。

资源加载器的第一遍强制关闭项目 settings，加载全局、
CLI 与内联 extension。它发出 `project_trust`；第一个返回 yes/no 的 extension 获胜，`undecided` 落空。`remember: true` 保存确切 cwd 决定。handler 错误是诊断、不批准。第二遍应用决定、重载 settings、解析包、加载
最终 extension 集，然后加载 skill、prompt、主题、context 与 system
prompt 文件。

session 替换重建 cwd 绑定服务。TUI resume 为目标 cwd 提供
交互式信任 context。Pi 还在进程内按 cwd 缓存结果，
既避开无关 cwd 的决定，也避免同一 cwd 重复提示。

### 安全边界

Pi 自己的安全文档写得很明确：项目信任只是输入加载守卫。Pi 仍以用户权限运行。它不是文件系统、
进程、shell、工具、网络、包管理器、extension、凭据、模型或
prompt 注入沙箱。真正的隔离需要 OS、容器、VM 或
类似边界。

## 当前 Baldric 在 `main` 上的行为

本节描述**现在**存在什么，与提案分开。
审计于 2026-08-03 在当前 Baldric `main` commit
[`9fffc6938e1873e5430b66117b7ade078d779030`](https://github.com/huggingface/tau/commit/9fffc6938e1873e5430b66117b7ade078d779030) 进行。
下文行为源链接用其父提交 `cc179435`，即仅发布版本提交之前。

Baldric 没有统一的项目信任决定或信任库。它不暴露
`--approve`、`--no-approve` 或 `defaultProjectTrust`。启动、reload 或
resume 可以不经信任提示加载项目 Markdown。

当前来源可在以下位置检视：

- [`resources.py`](https://github.com/huggingface/tau/blob/cc179435a4e4fb934d51c0032c36f8d46fcd811c/src/tau_coding/resources.py)
- [`context.py`](https://github.com/huggingface/tau/blob/cc179435a4e4fb934d51c0032c36f8d46fcd811c/src/tau_coding/context.py)
- [`session.py`](https://github.com/huggingface/tau/blob/cc179435a4e4fb934d51c0032c36f8d46fcd811c/src/tau_coding/session.py)
- [`paths.py`](https://github.com/huggingface/tau/blob/cc179435a4e4fb934d51c0032c36f8d46fcd811c/src/tau_coding/paths.py)
- [`extensions/loader.py`](https://github.com/huggingface/tau/blob/cc179435a4e4fb934d51c0032c36f8d46fcd811c/src/tau_coding/extensions/loader.py)
- [`shell_config.py`](https://github.com/huggingface/tau/blob/cc179435a4e4fb934d51c0032c36f8d46fcd811c/src/tau_coding/shell_config.py)
- [`cli.py`](https://github.com/huggingface/tau/blob/cc179435a4e4fb934d51c0032c36f8d46fcd811c/src/tau_coding/cli.py)

### 当前资源矩阵

| 当前 `main` 上的输入 | 当前行为 |
|---|---|
| `~/.baldric/settings.json` | 仅用户的 shell 设置如 `shellCommandPrefix`；没有项目 `.baldric/settings.json` 加载器。 |
| `.agents` settings | Baldric 没有用户或项目 `.agents` settings 加载器。 |
| 其他用户 provider/TUI 设置 | 从用户 `~/.baldric` 文件读取；没有项目等价物。 |
| `<cwd>/.baldric/skills/*/SKILL.md` | 自动发现并加载。 |
| `<cwd>/.agents/skills/*/SKILL.md` | 自动发现并加载。Baldric 检查 cwd 位置，不像 Pi 检查每个祖先 `.agents/skills`。 |
| `<cwd>/.baldric/prompts/*.md` | 自动发现并加载。 |
| `<cwd>/.agents/prompts/*.md` | 自动发现并加载。比 Pi 的信任触发更宽的 `.agents` 支持。 |
| `<cwd>/.baldric/themes/*.json` | 由 TUI 加载并优先于用户主题。`.agents/themes` 不支持。 |
| `<cwd>/.baldric/SYSTEM.md` | 自动读取并替换默认 prompt，除非显式 CLI system prompt 获胜。 |
| `<cwd>/.baldric/APPEND_SYSTEM.md` | 自动读取并追加，除非显式 CLI 追加值获胜。`.agents` system prompt 文件不支持。 |
| 普通 `AGENTS.md` | 从检测到的项目根一路加载到 cwd。 |
| `<cwd>/.baldric/AGENTS.md` | 作为项目 context 加载。 |
| `<cwd>/.agents/AGENTS.md` | 作为项目 context 加载。 |
| `CLAUDE.md` | Baldric 目前不发现。 |
| `<cwd>/.baldric/extensions` | Python 代码，默认禁用，仅带 `--project-extensions` 加载。 |
| `~/.baldric/extensions` | Python 代码，默认发现，除非 `--no-extensions`。 |
| `-e/--extension PATH` | 显式加载，`--no-extensions` 下也加载；不受信任门控。 |
| Extension `pyproject.toml` | `[tool.baldric].extensions` 只在被发现的 extension 目录内解析；它是 extension manifest，不是通用项目包管理器。 |
| 项目包 | Baldric 今天没有 Pi 式的项目包资源/安装系统。 |

用户 `~/.baldric` 与 `~/.agents` 的 skill、prompt 与 `AGENTS.md` 作为
用户拥有的资源加载。skill 与 prompt 优先级递增：用户
`.baldric`、用户 `.agents`、项目 `.baldric`、项目 `.agents`。项目 context 分层
根到 cwd 的普通 `AGENTS.md`，然后 cwd 的 `.baldric/AGENTS.md` 与
`.agents/AGENTS.md`。项目 system prompt 文件优先于用户文件。

`/reload` 重新发现资源，可以在没有信任检查的情况下执行选择加入的项目
extension。`CodingSession.resume()` 为记录的 cwd 创建替换并在采纳前加载其资源；没有目标
信任步骤。显式启动 system-prompt 文本/路径与显式 extension 路径
已表达用户意图，覆盖或增强环境性发现。

既有的 `--project-extensions` 开关是窄的安全选择加入，不是
持久化的项目信任系统。已发布文档对项目资源的警告正确，但在运行时阶段落地前不得声称存在强制执行。

## 提议的 Baldric 策略

以下一切都是未来契约。实施 PR 可以分阶段交付，
但不得静默弱化它。

### 目标与不变量

1. 在其规范 cwd 的决定之前，任何受保护项目文件不被读取内容、解析、导入、安装或执行。
2. 检测只能检查文件类型/名字/存在。不得为决定是否询问而解析项目 manifest。
3. 拒绝产出一份连贯的无保护资源快照，绝不是失败的部分加载拼出的混合物。
4. 全局策略不能来自项目 settings；项目不能给自己批准。
5. 信任结果限定于一个规范 cwd，只可以从最近的规范祖先决定继承。
6. `baldric_agent` 对信任、本地路径、CLI、Textual 保持无知。
7. Textual 经既有适配器边界渲染 Baldric 自有的决定请求；它不拥有信任策略。

### 受保护资源矩阵

"项目"指因活动 cwd 而发现的环境性资源，不是用户在本次调用中显式提供的路径。

| 资源 | 提议策略 | 触发规则 |
|---|---|---|
| 内置打包资源 | 不设门 | 永不。 |
| 用户 `~/.baldric` 与 `~/.agents` 资源 | 不设门 | 永不；它们是用户管理的输入。 |
| 显式 CLI system/追加 prompt、extension 与未来的显式 skill/prompt/主题路径 | 不设门 | 永不；直接调用即同意。既有的类型/读取/加载错误照常适用。 |
| `<cwd>/.baldric/settings.json`（若加入项目 settings） | **受保护** | 文件存在。只有全局 settings 能选信任默认。 |
| `<cwd>/.baldric/skills` 与 `.agents/skills` | **受保护** | 至少一个候选 `*/SKILL.md` 存在。 |
| `<cwd>/.baldric/prompts` 与 `.agents/prompts` | **受保护** | 至少一个候选非保留 `*.md` 存在。 |
| `<cwd>/.baldric/themes` | **受保护** | 至少一个 `*.json` 候选存在。 |
| `<cwd>/.baldric/SYSTEM.md` 与 `APPEND_SYSTEM.md` | **受保护** | 文件存在。 |
| 普通祖先到 cwd 的 `AGENTS.md`、cwd `.baldric/AGENTS.md` 与 cwd `.agents/AGENTS.md` | **受保护** | Baldric 会纳入的任何文件存在。 |
| `CLAUDE.md` | 当前不支持；日后若被发现，与 `AGENTS.md` 一样**受保护**。 | 文件存在于未来发现集。 |
| `<cwd>/.baldric/extensions` | **受保护且初始仍需选择加入** | 至少一个候选 `.py`、`*/extension.py` 或 extension 包 manifest 存在。 |
| 未来的项目包声明、包托管资源或自动安装元数据 | **受保护** | 声明/manifest 存在；批准前不解析、不下载、不安装。 |

空的 `.baldric`、`.agents` 与空的受保护子目录不触发
决定。一个本可加载但损坏/不可读的候选**确实**触发；检测不得把检视失败当作"无受保护输入"的证明。符号链接候选按目录条目触发，内容访问等批准。

目录扫描器应与真实加载器共享候选谓词，触发矩阵才不会漂移。检测返回类型化的资源类别与
路径供内部策略/诊断使用，但 UI 只报告类别/计数——不报文件
内容。详细路径必须设上限，避免启动洪泛。

### 与 Pi 的刻意差异

Baldric 不应盲目照抄 Pi：

- **保护所有项目 `AGENTS.md` 式 context。** Pi 让 `AGENTS.md` 与
  `CLAUDE.md` 不设门。Baldric 会对项目的普通、`.baldric` 与 `.agents`
  指令文件设门，因为它们成为高优先级模型输入并可能间接引发动作。用户级 context 保持不设门。这是
  输入加载守卫，不是"受信任 context 安全"的断言。
- **保护 `.agents/prompts` 与 `.agents/AGENTS.md`，连同 `.agents/skills`。** Baldric 有意支持比 Pi 更多的 `.agents` 位置。只把 skill 当受保护会让等价的项目 prompt 输入留在边界之外。
- **不要顺带放宽祖先资源发现。** 初始信任强制只覆盖 Baldric 加载器今天发现的东西：cwd 的 `.baldric` 与
  `.agents` 资源加既有的根到 cwd 普通 `AGENTS.md`。加 Pi 的
  祖先 `.agents/skills` 发现是单独的兼容性变更。若日后加入，那些祖先资源受保护并成为触发器。
- **迁移期保留 `--project-extensions`。** 初始时项目 extension 只在项目受信任*且*既有选择加入在场时加载。信任绝不能让当前禁用的可执行代码自动启动。更晚的、单独记载的版本可以重新考虑。
- **版本化并原子替换 Baldric 的存储。** 被检视的 Pi 存储是无版本、直接写入的对象。Baldric 应让迁移显式并防止撕裂写。
- **绝不因 reload 隐式保存信任。** 若项目原本没有受保护输入而后获得了，Baldric 询问（交互式）或遵循确定性的
  无头策略。仅仅在空项目里启动过不是对未来输入的持久同意。

### `baldric_coding` 类型与所有权

加一个小的 `baldric_coding.project_trust` 策略层。建议的类型化值：

```python
TrustDefault = Literal["ask", "always", "never"]
TrustDecision = Literal["trusted", "untrusted"]
TrustOverride = Literal["approve", "decline"]
TrustScope = Literal["exact", "parent", "run"]

@dataclass(frozen=True, slots=True)
class CanonicalProjectPath:
    value: Path

@dataclass(frozen=True, slots=True)
class ProtectedResourceSummary:
    cwd: CanonicalProjectPath
    categories: tuple[str, ...]
    counts: Mapping[str, int]

@dataclass(frozen=True, slots=True)
class SavedTrustEntry:
    path: CanonicalProjectPath
    decision: TrustDecision

@dataclass(frozen=True, slots=True)
class ProjectTrustRequest:
    cwd: CanonicalProjectPath
    resources: ProtectedResourceSummary
    inherited_entry: SavedTrustEntry | None
    choices: tuple[TrustChoice, ...]

@dataclass(frozen=True, slots=True)
class ProjectTrustResolution:
    trusted: bool
    source: Literal["override", "empty", "extension", "saved", "default", "ui"]
    saved_path: CanonicalProjectPath | None
```

确切名字可以变，但这些分离保持：

- `ProjectTrustStore`：校验、加锁、读取、最近祖先查找与原子更新；
- `ProtectedResourceDetector`：仅元数据的触发检测；
- `ProjectTrustPolicy`：纯优先级/默认解析；
- `baldric_coding` 里面向 extension/UI 请求的异步协调器；
- 在既有加载器之前过滤项目输入的资源计划/快照。

协调器接收抽象的回调/协议来获取决定。TUI 代码
把 `ProjectTrustRequest` 映射为 Textual 弹窗并返回选择。没有 Textual
导入进入策略模块。`baldric_agent` 照旧只接收已构建的
system prompt、工具与资源。

### 规范路径规则

信任键不是仓库根。它是 session 选择/替换后的活动 cwd。规范化必须：

1. 展开 `~`、以显式提供的基路径变绝对、归一化 `.`/`..`；
2. 要求活动 cwd 存在且是目录；
3. 解析所有符号链接（`Path.resolve(strict=True)`）；
4. 平台大小写不敏感时，为比较/存储应用平台的大小写归一化，同时按需单独保留显示路径；
5. 序列化一条归一化的本机绝对路径字符串。

不要用原始字符串前缀判断：`/work/app2` 不是 `/work/app` 的子目录。从规范 cwd 沿 `Path.parent` 走到根。第一个确切的存储
条目获胜。因此子目录的显式拒绝覆盖受信任父范围。不同符号链接拼写解析到同一个决定。移动过的项目有新键；过期条目保持可检视且无害，直到存在显式清理功能。

活动 cwd 规范化失败时，受保护资源不受信任，启动发出可执行的错误。不要像 Pi 那样回退到非规范键。已存条目必须绝对且归一化；非法条目让存储畸形而不是被静默跳过。

### 版本化、可检视的持久化

使用 `~/.baldric/trust.json`（即 `BaldricPaths.home / "trust.json"`），初始形状：

```json
{
  "version": 1,
  "decisions": [
    {"path": "/home/alex/src", "decision": "trusted"},
    {"path": "/home/alex/src/example", "decision": "untrusted"}
  ]
}
```

要求：

- 拒绝未知版本、重复规范路径、未知字段、相对
  路径与未知决定；
- 按路径排序决定，diff 稳定；
- 读-改-写全程加锁，并发 Baldric 进程不丢更新；
- 支持处，以仅用户权限创建 Baldric home；
- 替换目标之前，持久地装好同目录的受限撤销日志；日志还在时读取者一律 fail closed；
- 写同目录临时文件、flush 并 `fsync`、设受限权限、`os.replace()` 覆盖目标，支持处再 `fsync` 父目录；
- 只在该提交点之后移除日志；上报失败时恢复先前存储，任何恢复操作失败都保留 fail-closed 日志，让新授予的字节永远无法成为生效的已存决定；
- 清理无关的失败临时文件，而不替换最后一份有效存储。

畸形/不可读存储意味着没有已存决定能授予信任。发一条清晰诊断，受保护资源 fail closed，除非用户经 UI 或 `--approve` 给出显式仅本次批准。已保存的 UI 选择必须在授予信任**之前**成功写入；持久化不可写时，报告失败并保持不受信任，同时提供单独的"仅本次"选择。`remember=True` 的 extension 结果遵循同一规则。显式单次批准不写存储并保持可用，附存储错误诊断，因为它是直接同意而非推断状态。

不要自动重命名畸形存储或静默重置它；那会掩盖决定消失的原因。未来 schema 迁移必须解析旧的完整文档、原子写 v1、保留备份并报告变化。

### 解析优先级

对每个规范的目标 cwd：

1. 显式的单次运行 CLI 覆盖；
2. 无受保护资源候选：允许环境性加载（因为没有受保护物），但不记录持久决定；
3. 第一条决定性的合格信任前 extension；
4. 最近的已存确切/祖先决定；
5. 用户全局 `defaultProjectTrust`（缺失时 `ask`）；
6. `ask` 的交互式内置选择；否则安全拒绝。

这与 Pi 的有效顺序一致。项目 setting 既不能设
`defaultProjectTrust` 也不能改变前面的步骤。按规范 cwd 缓存已完成的运行解析，包括拒绝，一个 cwd 不反复提示。
绝不复用给另一个 cwd。reload 时重新做元数据检测，"空"结果不会在新文件出现后变成同意。

### 启动序列

未来的引导应当显式且可测试：

1. 解析 CLI 参数。在文件系统资源加载之前拒绝 `--approve` 与 `--no-approve` 同用。
2. 只加载 built-in 与用户全局 settings。只在这里读 `defaultProjectTrust`。不读 `<cwd>/.baldric/settings.json`。
3. 只用用户全局 session 配置解析最终 session 目标与规范目标 cwd。缺失 cwd 处理后，被恢复记录的 cwd 获胜。
4. 仅按元数据检测受保护候选。
5. 加载含 built-in、用户
   `~/.baldric/extensions` 与显式 `-e` 路径的信任前 extension runtime。此遍绝不导入项目 extension 或解析项目包。
6. 用上述优先级解析信任。交互式启动经适配器询问；无头启动不问。
7. 构建完整资源计划：全局与显式输入始终；项目输入仅在受信任时；迁移期项目 extension 还需既有选择加入。
8. 只有现在才解析项目 settings/manifest、解析/安装未来项目包、导入项目 extension、读取项目 Markdown/JSON、创建
   provider/runtime、组装 system prompt。
9. 完整计划成功后才发布新 coding session。对跳过的类别或失败发出有界诊断。

provider 构建很要紧：步骤 8 之前，受保护的项目 setting 不得影响 provider、代理、凭据、shell 前缀、模型、session 目录、extension
旗标或工具配置。

### 交互式 TUI 选择

内置弹窗应陈述规范文件夹、解释将加载的类别，并说明"这控制项目输入；它不是沙箱。"选项：

- **信任此文件夹** — 原子保存确切受信任，然后继续；
- **信任父文件夹（`…`）** — 一个事务里保存直接父目录受信任并移除确切子条目，然后继续；
- **仅本次运行信任** — 不写直接继续；
- **不信任此文件夹** — 原子保存确切不受信任，然后继续并跳过受保护资源；
- **仅本次运行不信任** — 不写直接跳过。

Esc/取消在初始启动时退出 Baldric；用户必须显式选择仅运行拒绝才能不带项目输入继续。reload 或 session
替换期间，取消保留活动快照。父范围绝不在不显示确切宽范围并要求同样显式选择的情况下默认 `$HOME`
或文件系统根。无障碍、焦点与按键处理属于
Textual 适配器/弹窗；可用选项与语义属于 `baldric_coding`。

未来的 `/trust` 命令可检视/编辑决定。与 Pi 一样，编辑不应
悄悄改动已加载资源。它应声明需要重启或 `/reload`。它必须分开显示继承来源与当前运行结果。

### 无头模式与显式覆盖

加 `--approve`/`-a` 与 `--no-approve`/`-na` 为互斥、仅本调用的覆盖。它们不写 `trust.json`。它们作用于该调用进入的每个目标
cwd，包括恢复/替换的 session，但每个 cwd 仍得到自己的诊断与资源计划。

print、JSON、transcript、导出相关运行时模式与自动化绝不等待 UI。没有更早的决定性结果时：

| 全局默认 | 无头结果 |
|---|---|
| `ask` | 不受信任 |
| `always` | 受信任 |
| `never` | 不受信任 |

结构化模式必须把诊断送进既定的诊断通道，不污染 stdout 协议。无头模式允许 extension 参与，但 `has_ui` 为 false 且 UI 方法不能提示。试图提示的 handler 得到确定性的错误/undecided 结果，拿不到 stdin。

### Extension 参与

只在结果与顺序经过测试后，才加 Baldric 自有的 `project_trust` 事件。事件暴露规范 cwd、模式、`has_ui` 与类别/计数
摘要——绝无受保护内容。结果为 `approve`、`decline` 或 `defer`，加 `remember: bool`。

只有 built-in、用户全局与 CLI 显式 extension 可以收到它。第一条决定性结果获胜。错误成为诊断且解析继续。
项目 extension、项目包 extension 及其注册的资源在批准前不能加载或参与。最终加载应尽量复用已导入的合格 extension，setup 不跑两遍。

Extension 不能发明更宽的父级持久化：`remember` 只保存
确切 cwd。内置 UI 拥有父范围选择。存储畸形/不可写时，记住的 extension 批准按上文 fail closed。

### Reload

`/reload` 必须是事务性的：

1. 再次检测候选；
2. 若现在存在受保护候选且该 cwd 没有缓存的非空解析，在读它们之前解析信任；
3. 在替换快照中准备全部许可的资源与 extension；
4. 只在准备成功后交换；
5. 从被接受的 runtime 发出 reload/session 生命周期事件。

用户取消或信任/存储/加载错误发生时，保留先前有效的
资源/runtime 快照。刻意的拒绝可以在确认后成功替换为全局/仅显式快照。绝不因为空项目长了文件而隐式保存信任。未来 `/trust` 命令修改的已存决定只在显式 reload/重启后生效。

### Resume、替换与 cwd 变更

当前 Baldric 替换在采纳前加载但没有信任阶段。未来的
resume/new-session/fork 流程必须推导并规范化目标 cwd，在读取任何目标项目资源之前运行同一协调器。
不要把源 cwd 的信任带到目标。

交互式跨 cwd resume，在当前 session 保持有效时 stage 目标选择与信任。取消让既有 session 保持活动。
只有目标资源与 provider/runtime 就绪后，Baldric 才
拆除/采纳。无头替换使用确定性表，失败/跳过而不提示。缓存键是规范 cwd，不是 session id。

### 诊断与可观测性

诊断应回答：

- 规范 cwd，以及决定是确切的还是继承的；
- 结果来源（`override`、`extension`、`saved`、`default` 或 `ui`）；
- 被跳过的受保护类别及计数；
- 畸形/不可读/不可写存储与补救路径；
- 信任前 extension 错误；
- 尽管受信任但项目 extension 仍禁用的原因（缺少既有
  `--project-extensions` 选择加入）。

默认不打印信任存储内容、资源内容、凭据或每个路径。交互式状态可以一次性汇总。text/JSON/transcript 模式
必须保住其输出契约。调试视图只能按正常脱敏规则暴露有界路径。

### 迁移与兼容上线

强制执行改变既有行为，所以不要藏进重构里。建议的第一个运行时版本：

- 默认全局策略为 `ask`；
- 存在有意义受保护候选时交互式 session 询问；
- 无头未解析的 `ask` 拒绝并发出简洁迁移诊断，建议保存一个交互式决定或显式 `--approve`；
- 不自动信任任何既有仓库，也不从
  `--project-extensions` 历史推断决定；
- 用户/全局与 CLI 显式资源继续工作；
- `--project-extensions` 保持为额外要求；
- 只有强制执行与旗标真正发布时才更新 release notes 与已发布的安全/配置/CLI 文档。

没有 legacy Baldric 信任存储可导入。若 v1 之前发布过原型/无版本文件，迁移必须显式、经测试并有备份。

## 分阶段的未来实现

本设计 PR 不加运行时代码。后续变更应保持可评审：

1. **纯策略与持久化。** 加类型、严格规范化、检测器、
   版本化加锁原子存储、最近祖先查找与纯解析。
   尚无 CLI/TUI 集成。
2. **资源规划。** 引入受信任/不受信任资源快照，门控
   项目 settings、skill、prompt、主题、context 与 system prompt 文件。
   保留许可输入间既有的优先级。
3. **CLI/无头集成。** 加互斥覆盖、全局默认、
   确定性模式、结构化诊断、启动/session-cwd 顺序。
4. **TUI 适配器集成。** 加无障碍的启动弹窗与范围，
   不把 Textual 移进策略或 `baldric_agent`。
5. **Extension 与替换。** 加信任前 extension 事件、两遍复用、
   事务性 reload 与跨 cwd resume/替换。
6. **包，等 Baldric 真有包。** 在暴露特性之前门控项目包声明、
   解析、安装与包资源。
7. **已发布文档/release notes。** 只描述已落地的行为，含迁移指引，重申非沙箱边界。

实现发现无效假设时，各阶段应更新本笔记；刻意的策略变更需要理由，不能意外漂移。

## 确定性测试计划

所有测试必须用临时 home 与项目；没有测试读写操作者的真实 home 或调用活动 provider。

### 策略与存储

- 规范别名/符号链接映射到同一个键；缺失/非目录 cwd fail closed；
- 确切胜过最近父级；父级胜过全局默认；兄弟不继承；
- 宽父信任加确切子拒绝；移除子条目恢复继承；
- v1 往返排序且可检视；
- 畸形 JSON、错误版本/schema、重复/非规范路径、读取
  失败、锁失败、写/替换/fsync 失败都不授予信任；
- 被中断的原子写入保住先前有效文件；
- 并发 fake 写者不丢决定。

### 检测与矩阵

用临时目录覆盖矩阵每一行、`.baldric` 与 `.agents` 两侧、
根到 cwd 普通 `AGENTS.md`、空目录、保留/不匹配文件、
不可读条目与符号链接。断言检测不读任何受保护内容。
断言当前不支持的 `CLAUDE.md` 与包元数据不会意外加载，而未来的包 fixture 在该特性出现后触发一次。

### 解析与启动

表测覆盖：override、无资源、extension、确切/祖先已存决定、每个
默认、UI 选择、取消与存储错误优先级。资源读取之前校验冲突的 CLI 旗标。用记录构建与调用的 fake provider；断言它在批准前看不到任何受保护项目 setting/prompt，启动失败时收不到调用。

### 资源与 extension 顺序

用记录 import/setup/事件的 fake extension：

- 全局与显式 extension 可以处理信任；
- 项目 extension 在批准前绝不导入；
- 第一条决定性 handler 获胜，defer 继续，错误诊断并继续；
- 记住的批准必须在加载项目代码之前持久化；
- 拒绝只产出全局/显式资源；
- 受保护类别作为一份最终快照加载并保留既有优先级；
- 除信任外 `--project-extensions` 仍然是必需。

### frontend、reload 与 session

- Textual 试点测试覆盖每个范围、父标签、esc 即拒绝、焦点、
  键盘操作、持久化错误与非沙箱文案；
- print/JSON/transcript 测试证明 `ask` 从不提示且 stdout 保持干净；
- 最初为空的项目 reload 后询问/拒绝，而不是自动保存；
- 取消/失败的 reload 保留旧快照；被接受的拒绝换到全局/仅显式；
- 到第二个 cwd 的 resume/替换在采纳前独立解析；
  取消保留第一个 session；
- 相同规范 cwd 用其进程缓存，符号链接别名与无关
  cwd 行为确定性；
- fake provider 与 fake extension 证明不需要活动模型、网络、包
  安装、进程或真实凭据。

每个集成阶段都跑仓库完整的 Python 与网站检查。

## 非沙箱边界

**项目信任只是输入加载守卫。** 它不限制 Baldric、
模型、extension、包或工具在加载之后能做什么。它不是文件系统、写入、进程、shell、子进程、网络、工具、凭据、
provider、模型、包安装、prompt 注入或数据外泄
边界。受信任的项目仍可能是恶意的，不受信任的仓库
仍可能经用户明确要求 Baldric 阅读的内容或工具输出影响模型。

需要隔离的用户必须在合适的 OS 沙箱、
容器、VM、micro-VM、远程环境或策略受限的工具边界内运行 Baldric，限制文件、凭据与网络访问。本项目信任设计绝不能被当作替代品来宣传。
