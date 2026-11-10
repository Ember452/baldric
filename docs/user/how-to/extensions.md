---
title: Extensions
description: 用纯 Python 扩展 Baldric——自定义工具、slash 命令、hooks、对话框与消息渲染。
---

Extension 是定制 Baldric session 的 Python 模块：它们添加工具、slash 命令与进程级 provider 定义；观察 agent 事件流；并拦截 tool 调用、工具结果与用户输入。设计遵循 Pi 的 extension 系统，适配到 Python。

## 快速开始

创建 `~/.baldric/extensions/greet.py`：

```python
from baldric.protocol.messages import TextContent
from baldric.protocol.tools import AgentTool, AgentToolResult


async def run_greet(tool_call_id, arguments, signal=None, on_update=None):
    return AgentToolResult(
        content=[TextContent(text=f"Hello, {arguments.get('who', 'world')}!")],
    )


def setup(baldric):
    baldric.register_tool(
        AgentTool(
            name="greet",
            label="Greet",
            description="Greet someone.",
            parameters={
                "type": "object",
                "properties": {"who": {"type": "string"}},
            },
            execute_fn=run_greet,
            prompt_snippet="Greet someone by name.",
        )
    )
```

启动 `baldric`，模型就能调用 `greet`。每个 extension 都是定义了 `setup(baldric)` 的模块，`setup` 在启动时以 extension API 运行一次。

## 安装 extension

用与 Pi 相同的命令形状从 Git 安装受信任的 extension：

```bash
baldric install git:github.com/owner/repository
baldric install git:github.com/owner/repository@v1.2.0
baldric install https://github.com/owner/repository.git
```

Baldric 把仓库克隆进 `~/.baldric/extensions/<repository>` 并在下次启动时加载。固定 ref 可以是 tag、branch 或 commit。替换既有安装需要显式同意：

```bash
baldric install git:github.com/owner/repository@v1.3.0 --force
```

本地文件与包目录也可以：

```bash
baldric install ./my_extension.py
baldric install ./my-extension
```

本地文件被复制进 `~/.baldric/extensions/`。目录会被复制，且必须包含 `extension.py` 或在 `pyproject.toml` 里声明 `[tool.baldric].extensions`，这样不用 `-e` 也能被发现。本地虚拟环境、VCS 元数据与 Python 缓存目录不会被复制。

安装器在不导入 extension 的前提下校验发现元数据。它不安装 Python 依赖、不维护包注册表，也暂不提供 remove/update 命令。当 extension 需要依赖时，单独安装进 Baldric 的 Python 环境。Extension 以你的用户权限执行任意 Python，安装前请先审查源码。

## extension 放在哪里

| 位置 | 是否加载 |
|---|---|
| `~/.baldric/extensions/` | 默认加载 |
| `<project>/.baldric/extensions/` | 仅在项目获批**且**传入 `--project-extensions` 时 |
| 任意文件或目录 | 用 `baldric -e PATH`（可重复） |

### 受信任的内置 extension

Baldric 可以把产品能力打包为 `BuiltInExtension` 声明。内置项不是特殊的 provider 或命令分支：它的同步 `setup(baldric)` 接收普通的 extension API，并通过同一 runtime 注册工具、命令、进程级 provider、hook 或后续的 extension 能力。

Built-in 在每个 staged runtime 加载一次，先于用户、显式与受信任的项目来源。传 `--no-extensions` 时它们仍会加载，因为该旗标关闭的是文件系统发现，而不是 Baldric 自带的能力。它们的代码按已安装包代码对待，绝不计入环境项目输入，因此内置项自身无法触发项目信任。

声明默认隐藏。隐藏意味着不进入普通的 extension 计数，而不是不活动：详细的运行时元数据保留 `built-in` 来源、稳定的 `built-in:<name>` 来源 ID 与隐藏标志。setup 异常被隔离为诊断，该来源的所有部分注册会被移除。reload、resume、new-session 与 cwd 替换使用全新世代；退役旧世代会使捕获的 API 失效、移除其注册并取消世代所有的 provider 刷新任务。通用内核加载从不检查内置能力的名字。

目录内 `*.py` 文件都是 extension；包含 `extension.py` 的子目录是包式 extension——其兄弟模块以相对导入加载（`from . import helper`）。下划线开头的名字被跳过。

把代码放在包里（例如 `src/` 布局）的大型 extension 可以改为在 `pyproject.toml` 里声明入口文件，而不是把 `extension.py` 放在目录根部：

```toml
[tool.baldric]
extensions = ["src/my_ext/extension.py"]
```

manifest 优先于同目录的 `extension.py`；每个声明文件作为以其父目录为根的包加载，兄弟模块保持可相对导入。extension 以入口的父目录命名（入口不叫 `extension.py` 时以文件本身命名）。

一个注意点：对入口**文件**用 `baldric -e` 是独立加载——没有包，相对导入会失败。一旦 extension 有了兄弟模块，总是传目录：包目录本身，或 manifest 声明入口时的仓库根。

在项目决策之前，built-in、用户全局与显式 `-e` extension 可以处理 `project_trust` 事件。事件包含规范化的 cwd、模式、UI 可用性与有界的分类计数——绝不包含受保护内容。返回 `ExtensionTrustResult("approve" | "decline" | "defer", remember=...)`；第一个决定性的结果获胜，错误安全地 defer，remember 的结果只保存确切的 cwd。项目 extension 不能给自己批准。

在 built-in 之后，文件系统 extension 保持既有优先级；名字冲突（extension 名、tool 名、command 名）先注册者获胜。`--no-extensions` 禁用目录发现（显式 `-e` 路径与受信任 built-in 仍加载）。`/reload` 会对即将退场的 extension 世代 `await session_shutdown(reason="reload")`，清空其 UI，重新导入每个 extension 并重跑 `setup`，然后在新世代上 `await session_start(reason="reload")`。用这些生命周期 hook 停止并重启后台工作、重挂 UI。

> **安全。** Extension 在你的 session 里执行任意 Python。因此项目 extension 默认关闭。信任批准与 `--project-extensions` 缺一不可。项目信任不是进程、文件系统、网络、凭据、工具、模型或 prompt 注入沙箱。

在 TUI 里运行 `/extensions` 打开可搜索的清单。每个已加载 extension 显示名字、入口路径、来源范围（`project`、`user`、`explicit` 或 `built-in`）与加载状态。发现、导入、setup 与运行时诊断出现在同一视图。清单刻意只读：Baldric 不对手工放置、项目或 `-e` 的 extension 文件声明所有权，也绝不删除它们。

## 管理已安装的 extension

`baldric install SOURCE [--force]` 把本地文件或包复制、或把 Git 仓库克隆进 `~/.baldric/extensions/`，安装前会校验普通用户目录发现能加载它。Git 安装在受管安装注册表里记录来源、ref 与 commit，Baldric 据此区分手工放置的文件。

- `baldric extensions [list]` 显示每个已安装 extension 及其是否由 Baldric 管理（含来源、ref、commit）。
- `baldric extensions update <name> [--force]` 按记录的来源重新克隆受管 Git extension。checkout 与记录的 commit 不再一致时它拒绝静默丢弃；传 `--force` 丢弃本地修改。
- `baldric extensions remove <name>` 删除受管 extension 及其注册表条目。非受管目录永不触碰。

## extension API

```python
def setup(baldric):
    # registration
    baldric.register_tool(agent_tool)            # baldric.protocol.tools.AgentTool
    baldric.register_provider(dynamic_provider)  # process-local
    baldric.register_command("name", handler, description="...")
    baldric.add_prompt_guideline("Never commit directly to main")
    baldric.add_prompt_section("Review procedure", "Read the diff, then run tests.")
    baldric.on("event_name", handler)            # or @baldric.on("event_name")

    # message rendering (register in setup; send once running)
    baldric.register_message_renderer("my-ext:status", render_status)

    # actions — valid once the session is bound, not during setup
    baldric.send_user_message("text", deliver_as="follow_up")  # or "steer"
    baldric.send_custom_message("text", custom_type="my-ext:status", details={...})
    await baldric.append_entry("my-ext:records", {"key": "value"})
    await baldric.set_label(entry_id, "checkpoint")  # None or empty clears
    baldric.notify("message", "info")            # "info" | "warning" | "error"
    baldric.set_inference_provider("deepinfra")   # Hugging Face route; None resets

    # read-only context
    baldric.context.cwd, baldric.context.model, baldric.context.provider_name
    baldric.context.available_providers             # callable provider IDs
    baldric.context.available_model_choices         # ModelChoice(provider_name, model)
    baldric.context.inference_provider             # current Hugging Face route, or None
    baldric.context.inference_provider_mode        # "automatic" or "fixed"
    baldric.context.session_id, baldric.context.session_name
    baldric.context.thinking_level, baldric.context.system_prompt
    baldric.context.paths                 # resolved BaldricPaths snapshot
    baldric.context.project_trusted       # bool: were this cwd's project inputs approved?
    baldric.context.project_trust_resolution  # full ProjectTrustResolution, or None
    baldric.context.is_running, baldric.context.has_ui
    baldric.context.transcript   # parent conversation, deep-copied AgentMessages

    # host-framed sidebar sections (see "Sidebar sections" below)
    sidebar = getattr(baldric.context.ui, "sidebar", None)
    if sidebar is not None and sidebar.supported:
        sidebar.set_section("status", title="Status", content=["[green]ready[/green]"])

    # interactive UI dialogs (async; see "UI dialogs" below)
    await baldric.context.ui.select("Title", ["a", "b"])   # -> str | None
    await baldric.context.ui.confirm("Title", "message")   # -> bool
    await baldric.context.ui.input("Title", "placeholder") # -> str | None
    baldric.context.ui.notify("message", "info")           # same as baldric.notify
```

`context.available_providers` 与 `context.available_model_choices` 暴露与 Baldric 模型 picker 相同的有效运行时清单。没有可用凭据的 provider 被省略。模型选项包含动态 extension provider 与运行时刷新的账户级目录。每个选项都是冻结的 `ModelChoice(provider_name, model)`，extension 可以在接触不到 provider 凭据或可变 session 内部的情况下过滤返回的 ID。

`set_inference_provider(route)` 让 provider 专属的 extension 为活动 session 选择 Hugging Face inference-provider 路由。传 provider 名会把 `context.inference_provider_mode` 设为 `"fixed"`，Baldric 尊重显式选择、不做自动 failover。传 `None` 选择 `"automatic"` 模式：下一个成功响应成为粘性路由，Baldric 可能在可重试的输出前失败耗尽后替换它。其他 provider 拒绝该操作。当前已解析的路由可从 `context.inference_provider` 读取。

`setup` 必须是普通 `def`（不能是 `async def`）。事件 handler 可以是同步或异步，总是接收 `(event, context)`；context 每次派发都是新建的。在 session 绑定之前调用动作方法会抛 `ExtensionError`——在 `setup` 里注册 handler，通过事件行动。

#### 解析后的文件系统路径

`baldric.context.paths` 是活动 session 的只读 `BaldricPaths` 快照。若宿主提供 `BaldricResourcePaths.paths`，该对象是权威，保留自定义的 `BaldricPaths.home` 与 `BaldricPaths.agents_home`。否则 Baldric 推导
`BaldricPaths(home=resource_paths.root, agents_home=resource_paths.agents_root or ~/.agents)`。换言之，`root`/`home` 控制 Baldric 的用户数据与 extension 目录，`agents_root`/`agents_home` 控制 `.agents` 资源；项目 `cwd` 保持独立。`ExtensionRuntime(paths=custom_paths)` 在 `load` 之前立即暴露构造路径；之后的 `load` 使其 `BaldricResourcePaths` 快照成为权威。

快照属于 extension 世代。`/reload`（及其他全新世代替换流程）之后，从旧世代捕获的 context 已过期：连读 `context.paths` 都会抛 `ExtensionError`。从新世代的 context 重新读取。

#### 构建子 session

extension 可以在进程内构造自己的 `CodingSession`（例如 subagent 工具），用 `CodingSession.load(CodingSessionConfig(...))`。两个配置字段是接缝：

- **信任。** 无头的 child 自行解析项目信任，在默认 `trust_default="ask"` / `trust_interactive=False` 下落为不受信任——即使用户已为父级批准了该仓库，子代理也会静默失去项目的 skill、`AGENTS.md` 与项目 extension。改为你转发父级的决定：

  ```python
  child = await CodingSession.load(
      CodingSessionConfig(
          ...,  # provider, model, storage, cwd, resource_paths for the child
          trust_override="approve" if baldric.context.project_trusted else "decline",
      )
  )
  ```

  `baldric.context.project_trust_resolution` 暴露完整的冻结 `ProjectTrustResolution`（`trusted`、`source`、`saved_path`……）供诊断。不要无条件批准：被用户拒绝的仓库否则会把它的项目输入装进每个 child。

- **工具允许列表。** `CodingSessionConfig.tools` 只替换内置工具集；extension 注册的工具在此之后叠加。`CodingSessionConfig.allowed_tool_names=frozenset({"read", "bash"})` 按名字过滤*最终*组合列表——初始加载时和每次 `/reload` 时——限制无法被 extension 工具绕过，也不需要宿主重复应用。`None`（默认）保留所有工具；未知名字被忽略。搭配 `skills_enabled=False` 得到同样没有 skill 的 child。

### 本地 backend 注册

extension 可以把 provider 层与 provider 中立的本地 backend 配对：

```python
def setup(baldric):
    baldric.register_provider(provider)
    baldric.register_local_backend(backend)
```

backend 声明结构化的文本、secret 与 choice 字段，以及异步的配置、刷新、状态与可选的 doctor/reset/模型管理操作。宿主渲染值并拥有确认、取消与空闲检查；backend 代码永不接触 Textual 组件。配置是一次事务，校验或安全态失败不会替换先前的配置。secret 不进入表示与宿主诊断。

backend 与 provider 必须由同一来源与世代注册。若另一来源遮蔽了 provider，backend 可以保持可检视，但不能通过被遮蔽的层使用、reset 或管理模型。退役或重载的世代取消其 backend 工作并忽略迟到结果。见[本地 backend 指南](/how-to/local-inference/)。

### 动态 provider

`register_provider` 安装一个完整的 `DynamicProvider` 层，由调用的 extension 来源与当前运行世代拥有。provider 可以以无模型的休眠状态启动，并且只提供一种运行时机制：`OpenAICompatibleTransport` 描述符或自定义运行时工厂。已知元数据用 `ProviderModel` 值；未知字段留 `None`。

认证是显式的：`RequiredApiKey`、`OptionalApiKey` 或 `NoAuth`。已存凭据胜过配置的环境变量。可选或缺失的 key 不发送 `Authorization`；Baldric 绝不合成假 key。静态 transport/model headers 不能提供 `Authorization`；自定义 scheme 必须由运行时的 auth strategy 解析。已解析的 key、headers 与任意 auth 来源不会进入 provider 表示与诊断。运行时创建把自定义认证异常降为类别化的宿主错误；Baldric 的 required-key 提示仍然给出可执行的缺凭据指引。嵌套的 JSON 兼容元数据在注册期间深度冻结，仅在创建运行时 transport 时拷贝到普通 JSON 容器。

发现是快照导向的。`refresh_models` 回调返回完整的 `ProviderModelSnapshot`；registry 校验并原子发布。并发调用者只在层与 `allow_network` 策略一致时共享工作，且每个调用者保留自己的超时。相反的网络策略绝不互相别名。最后的超时与显式取消会在返回前离开合并表，因此立即重试触发全新的发现。Baldric 请求一次任务取消，然后在请求后等待最多 0.25 秒而不重复取消回调的 `finally` 清理。reload、session 替换与最终 close 会等待这次协作排水。一旦 reload/替换发布了新状态，调用者取消被包容，直到退场清理结束、操作返回采纳的结果；它绝不把取消报告得像发布回滚了。发布之前，替换者是其候选 provider 的显式所有者。退场关闭或进场启动期间的取消或失败，会恰好关闭一次那些候选而不关闭活动 provider；成功恰好移交一次所有权。最终 close 使用一个持久 close 任务，只在 extension registry 与每个 session 持有的运行时 provider 都各关闭一次之后传播取消。超时仍在运行的回调被报告为 contained 而非 drained——进程所有的 supervisor 保持其任务与世代注册表可达直到它真正结束；它不能在来源替换或退役之后发布。超时、畸形输出与其他失败保留当前快照。

动态定义是运行时覆盖——不是持久配置。Baldric 绝不把它们拷贝进 `catalog.toml`、`providers.json`、session 或通用 extension 存储。provider 来源所有权来自宿主分配的规范入口路径，不是显示名。加载器在导入任何 extension 之前冻结所有发现的来源 ID，import/setup 代码无法通过改指向 entry 或父符号链接来改变所有权。存储的 ID 用于重复检查、每一次 API 注册以及完整的失败 setup 清理。分开加载的同名 extension 因此形成独立的 provider 层；在同一 runtime 重复完全相同的 entry 来源会被忽略，先加载者优先。工具与命令仍用先注册者优先的名字 registry。移除一个来源会露出前一个完整层，包括确切的持久 provider 基线。契约不含 frontend，回调不得返回 Rich/Textual 值。

Phase 6 用一个常驻的第二 fake backend 与一个小的仅测试 Ollama 适配器验证这些契约。受信任的内置 `llama.cpp` provider 走同样的接缝；不发布生产用 Ollama backend。provider 发现与 backend 状态可以使用不同协议端点，`NoAuth` 是一等选项。它的连接、缓存与排障行为见[本地推理指南](/how-to/local-inference/)。路由管理与 Hugging Face 模型变更仍在本阶段范围之外。

### 工具

`register_tool` 接受普通的 `baldric.protocol.tools.AgentTool`：名字、label、描述、手写的 JSON-schema `parameters` 映射，以及异步 `execute_fn(tool_call_id, arguments, signal=None, on_update=None)`。给工具一个 `prompt_snippet`，它会列在 system prompt 的 "Available tools" 区块；`prompt_guidelines` 提供与该工具绑定的使用指引。用内置名（`read`、`write`、`edit`、`bash`）注册工具会替换内置项。

工具运行前，agent loop 依据 `parameters` 校验调用的参数。不合的调用不执行：模型收到一条错误，列出每个问题（缺失必填键、错误类型、越界 `enum` 值、`additionalProperties` 为 `false` 时未声明的键）及其路径。检查覆盖 `type`、`required`、`properties`、`additionalProperties`、`enum` 与 `items`，忽略其他关键字。空的 `parameters` 映射不校验；作为 `null` 发送的可选参数视为未发送。不做任何类型强转。要接受其他形状，把 `prepare_arguments` 设为一个把参数改写成声明形状的函数；loop 校验其结果并传给 `execute_fn`。

长时间运行的工具可以流式汇报进度：额外使用 `on_update` 的执行器会收到一个接受 `AgentToolResult` 的回调；每次调用变成 `tool_execution_update` 事件，驱动 TUI 的实时进度行。没有该参数的执行器不受影响。

默认 TUI 把未识别的 tool 调用显示为 `name {arguments}`（截断）。给工具一个 `render_call`——`(arguments) -> str | None`——可以渲染友好的单行调用（Pi 的 `renderCall`）：例如 subagent 工具显示其 `description` 参数而非原始 JSON。返回 `None` 回退到通用行。渲染器错误被吞掉（每个工具诊断一次），绝不击溃 UI。

工具执行期间，TUI 给它的行加动画：布莱叶盲点 spinner 顶替行首标记（`→ ` / `▸ `），一秒后追加实时耗时（`… (1m 23s)`）。把 `render_call` 的输出保持为以 `▸ ` 之类标记开头的单行，spinner 才有东西可替换。

要给不绑定任何工具的行为指引，`add_prompt_guideline(text)` 向 system prompt 的 Guidelines 区块添加一行（构建时去重；guideline 变化时 `/reload` 重建 prompt）。

要注入结构化、始终在场的 context，`add_prompt_section(title, body)` 在累计的用户与项目 `APPEND_SYSTEM.md` 文件与 `--append-system-prompt` 内容之后追加自由格式区块。title 可以是 `None`；有 title 时渲染为二级 Markdown 标题。body 可以包含段落、列表与代码块而不被强行变成 guideline 条目：

````python
def setup(baldric):
    baldric.add_prompt_section(
        "Review procedure",
        """Read the complete diff before editing.

```bash
uv run pytest
```
""",
    )
````

区块按 extension 加载与注册顺序组合。空 body 与多行 title 被忽略并产生资源诊断。注册由来源拥有，因此失败的 setup、`/reload` 与世代退役会把它们连同 extension 的其他贡献一起移除。

### 命令

`register_command(name, handler, *, description, usage, aliases)` 添加 slash 命令。handler 是同步的，接收 `(args: str, context)`，可以返回展示给用户的 `str`。内置命令不可覆盖。extension 命令自动出现在 TUI 补全里。

### UI 对话框

`baldric.context.ui` 给 extension 提供宿主提供的交互对话框（Pi 的 `ctx.ui`）。三个对话框方法都是 `async`：

```python
choice = await baldric.context.ui.select("Deploy to", ["staging", "prod"])
ok     = await baldric.context.ui.confirm("Deploy?", "This ships to production.")
name   = await baldric.context.ui.input("Release name", "e.g. v1.2.0")
```

- `select(title, options, *, timeout=None) -> str | None` — picker；返回所选选项，取消时 `None`。
- `confirm(title, message, *, timeout=None) -> bool` — 是/否对话框；只有确认时返回 `True`。
- `input(title, placeholder="", *, timeout=None) -> str | None` — 文本输入；空提交返回空串，取消时 `None`。
- `timeout` 单位是**秒**；到期时对话框自动关闭并返回取消默认值（`None`/`False`/`None`）。

没有交互 frontend（print mode、`-p`、测试）时每个对话框立即返回取消默认值，extension 可以无条件调用。想按是否连接了真实 UI 分支，检查 `baldric.context.ui.has_ui`（或 `baldric.context.has_ui`）。

**从 slash 命令驱动对话框。** 命令 handler 是同步的，不能直接 `await` 对话框。改为在运行中的事件循环上开任务并立即返回：

```python
import asyncio

def _handler(args, context):
    async def _menu():
        choice = await context.api.context.ui.select("Action", ["deploy", "cancel"])
        if choice and choice != "cancel":
            context.api.send_user_message(f"run {choice}")
    asyncio.get_running_loop().create_task(_menu())
    return None  # any returned text opens a modal the user must dismiss first

def setup(baldric):
    baldric.register_command("menu", _handler)
```

任务运行在与 session 相同的事件循环上，在那里 await 对话框是安全的。（tool 执行器本身是 `async` 的，可以直接 `await baldric.context.ui...`。）

### 侧栏区块

`baldric.context.ui.sidebar` 让 extension 向 Baldric 的交互 session 侧栏贡献一个区块，而无需查询私有组件 ID 或导入 `BaldricTuiApp`。在 frontend 桥接接好后的 `session_start` 里注册区块：

```python
def setup(baldric):
    turn_count = 0

    def show(context):
        sidebar = getattr(context.ui, "sidebar", None)
        if sidebar is not None and sidebar.supported:
            sidebar.set_section(
                "turns",
                title="extension status",
                content=[f"[green]{turn_count}[/green] completed turns"],
            )

    @baldric.on("session_start")
    def started(event, context):
        show(context)

    @baldric.on("turn_end")
    def finished(event, context):
        nonlocal turn_count
        turn_count += 1
        show(context)  # replacing the same key updates it in place

    @baldric.on("session_shutdown")
    def stopped(event, context):
        sidebar = getattr(context.ui, "sidebar", None)
        if sidebar is not None:
            sidebar.remove_section("turns")
```

- 支持旧 Baldric 版本时用 `getattr` 探测 `sidebar` 属性。在当前版本上，print/无头模式与 `sidebar_position` 为 `"off"` 时 `sidebar.supported` 为 `False`；调用是安全的 no-op，不会出现可见侧栏。
- `set_section(key, *, title, content)` 添加或替换本 extension 的 key。键按 extension 隔离，两个 extension 可以都用 `"status"`。更新既有 key 保留其位置；删除后重新添加会排在既有 extension 区块之后。
- `content` 是一串 Rich 标记显示行，或 `factory(theme) -> textual.widget.Widget`。尽量用行：它们不需要 Textual 导入，宿主负责换行、宽度、滚动、标题、分隔线与左右放置。factory 以活动主题重建，使用与其他 extension 组件相同的崩溃隔离。
- `remove_section(key)` 移除区块。reload、session 替换与关闭时宿主也会清空所有 extension 区块。响应式隐藏会保留区块，终端变大时恢复。

完整示例见 `examples/extensions/sidebar_status.py`。

### 组件挂载

> 这条接缝让 extension 把自己的 **Textual 组件**挂进 TUI，而不是发布字符串数据。它刻意把 Textual 纳入公开 extension 契约（"component" 类型*就是* `textual.widget.Widget`）：extension 针对 Baldric 锁定的 Textual 版本构建，Textual 大版本升级是对内核与 extension 的协同破坏。跑自己对话的 extension（如 subagent）用这条接缝构建自己的 agent 条与就地对话视图。够用就优先用字符串/数据（消息渲染器、工具渲染器、字符串槽组件）——它们在所有 frontend 包括 print mode 都工作；确需活交互 UI 时再用组件。

`baldric.context.ui.components`（一个 `ComponentBridge`）承载 extension 挂载的组件。总是先探测 `supports_components`——print mode 与没有这条接缝的宿主上它是 `False`，下面所有调用都是安全 no-op：

```python
def setup(baldric):
    components = baldric.context.ui.components
    if not components.supports_components:
        return  # print mode / older host: stay widget-less but functional

    # A persistent widget above or below the prompt. The factory runs on the UI
    # thread and receives the live theme.
    def build_strip(theme):
        return MyStripWidget(theme)          # a textual.widget.Widget

    components.set_slot_widget("my-widget", build_strip, placement="below_prompt")
    # set_slot_widget("my-widget", None) removes it again.

    # For plain text you can skip the factory (and the Textual import) entirely
    # by passing a list of display lines — the host renders them as Rich markup:
    #   components.set_slot_widget("status", ["[b]ready[/b]", "2 tasks queued"])

    # A pre-dispatch key hook (ports Pi's onTerminalInput): it is consulted
    # before the host's app-level priority bindings AND before the focused
    # widget, so returning True for "escape" preempts the turn-cancel and
    # returning True for "down" preempts completion nav. It fires for EVERY
    # main-screen key regardless of which widget has focus (never while a
    # modal dialog/picker is on top), so it MUST self-gate — e.g. on the
    # prompt text — and return True only for keys it actually consumes.
    def on_key(event, prompt_text):
        if prompt_text == "" and event.key == "down":
            ...            # activate your widget
            return True     # consume the key
        return False        # let it through
    unsubscribe = components.register_key_interceptor(on_key)
```

- `set_slot_widget(key, content, *, placement="above_prompt")` 把 extension 组件挂进 prompt 相邻的槽（`"above_prompt"`——默认——或 `"below_prompt"`）。`content` 是 `factory(theme)` 可调用，或宿主按 Rich 标记渲染的纯显示行列表（纯文本组件因此不需要 Textual 导入）；传 `content=None` 移除该 key。同一 placement 的多个 key 按调用顺序挂载。
- `open_main_view(factory) -> handle` 把 `factory(handle, theme)` 挂为完整主区视图，*替换*transcript（一个可切换显示的兄弟视图，**不是**模态 screen），你的槽组件保持可见、prompt 保持焦点——想带输入框就自己嵌入。`handle.close()` 恢复 transcript；`handle.is_open` 报告状态。
- `register_key_interceptor(handler) -> unsubscribe` —— `handler(event, prompt_text)`；返回 `True` 消费该键。预派发：先于宿主优先级绑定与焦点组件，对每个主屏键生效（模态在最上方时除外）——必须自设门槛。抛异常的 interceptor 视为"未消费"。
- `theme` 是活动 `TuiTheme`；`get_prompt_text()` 读 prompt 编辑器（interceptor 的第二个参数已是它）；`request_render()` 重渲染你挂载的组件。推送实时更新请调用组件自己的 `refresh()`（Textual）——这条接缝不轮询。

宿主是防御性的：抛异常的 factory、在 `render`/`on_mount` 崩溃的组件、抛异常的 interceptor 都会被隔离（隔离并诊断），一个坏组件拖不垮 TUI。所有挂载组件在 session 重绑（`/resume`、`/new`）与 teardown 时强制清除；自己的组件也要在 `session_shutdown` 时清除。

### 事件

观察事件镜像规范的 agent/session 流。handler 接收 `(event, context)`，在 session 事件循环上运行，可以订阅单个 `type` 或用 `agent_event` 接收完整流。

| 事件 | 重要载荷 |
|---|---|
| `agent_start` | — |
| `agent_end` | `messages`、session 形态上的 `will_retry` |
| `agent_settled` | —；已启动的运行完成了 teardown，且没有遗留的自动重试、compaction 或续跑；即使取消中的 frontend 已无法消费流式事件，中断后也会派发给 extension |
| `turn_start` | `turn_index`、Unix 毫秒 `timestamp` |
| `turn_end` | 匹配的 `turn_index`、`message`、`tool_results` |
| `message_start` / `message_end` | `message`；assistant 用量在 `message.usage` |
| `provider_retry` | `attempt`、`max_attempts`、`delay_ms`、`message`；在重试的 provider 请求产出之前发出，与 coding-session 流上的 `auto_retry_start` / `auto_retry_end` 成对 |
| `message_update` | `message`、嵌套的 `assistant_message_event` |
| `tool_execution_start` | `tool_call_id`、`tool_name`、`args` |
| `tool_execution_update` | 调用字段加 `partial_result` |
| `tool_execution_end` | 调用字段加 `result`、`is_error`、`duration_ms`（工具从未运行时缺失） |
| `queue_update` | `steering`、`follow_up` |
| `compaction_start` | `reason`（`manual`、`threshold` 或 `overflow`） |
| `compaction_end` | `reason`、`result`、`aborted`、`will_retry`、`error_message` |
| `entry_appended` | 持久化的 session `entry` |
| `session_info_changed` | session `name`；自动命名或 `await session.set_session_name(...)` 之后发出 |
| `thinking_level_changed` | `level`；显式 thinking 模式变更后发出 |
| `auto_retry_start` | `attempt`、`max_attempts`、`delay_ms`、`error_message` |
| `auto_retry_end` | `success`、`attempt`、`final_error` |

`compaction_start` 与 `compaction_end` 界定 session 执行的 compaction。估算 context 越过配置上限、自动 compaction 运行时发出 `threshold`，extension 因此能观察到在一轮响应已送达之后发生的后台 compaction。`overflow` 用于 provider context 溢出错误的恢复。失败的 threshold compaction 仍会发出 `compaction_end`，`aborted` 置位并填充 `error_message`。手动 `/compact` 由 CLI 驱动，不发出这些事件。

`message_update.assistant_message_event` 是 provider 中立的增量流。其嵌套 `type` 是 `text_start`、`text_delta`、`text_end`、`thinking_start`、`thinking_delta`、`thinking_end`、`toolcall_start`、`toolcall_delta`、`toolcall_end` 之一。终结的 provider 事件变成 `message_end`，而不是又一条 `message_update`。

`context.session_name` 与 `context.thinking_level` 提供 extension 接入或替换 session 启动时的当前值。匹配的变更事件携带后续更新的快照；无变化的赋值不发出。模型变更、`/model` 与 `/local` 选择、scoped-model 切换、provider reload 与 branch/resave 可能把活动 thinking 级别收敛为所选模型支持的值而不发显式 `thinking_level_changed` 事件，因此处理其他事件时请读实时 context，别把变更事件当作完整的缓存供给。

Extension 轮次事件与 Pi 一样经 session 增强。`turn_start` 与匹配的 `turn_end` 携带相同的零基 `turn_index`；`turn_start` 还携带 Unix 毫秒 `timestamp`。runtime 在 `turn_end` 后递增索引，在下一个 `agent_start` 重置：

```python
from baldric.runtime import TurnEndEvent, TurnStartEvent


def setup(baldric):
    @baldric.on("turn_start")
    def on_turn_start(event: TurnStartEvent, context):
        context.api.notify(
            f"turn {event.turn_index} started at {event.timestamp}", "info"
        )

    @baldric.on("turn_end")
    def on_turn_end(event: TurnEndEvent, context):
        assert event.turn_index >= 0
```

这些增强载荷定义在 `baldric.runtime.extensions`。可移植的 `baldric.agent.events.TurnStartEvent` 与 `TurnEndEvent` 有意省略 session 元数据，可复用的 agent 代码保持独立于 session 政策。

生命周期与拦截 hook：

| 事件 | 载荷 | handler 可返回 |
|---|---|---|
| `session_start` | `SessionStartEvent(reason)` | — |
| `session_shutdown` | `SessionShutdownEvent(reason)` | — |
| `input` | `InputEvent(text)` | `InputHookResult(action, text, message)` |
| `tool_call` | `ToolCallHookEvent(tool_name, arguments)` | `ToolCallHookResult(block, reason, arguments)` |
| `tool_result` | `ToolResultHookEvent(tool_name, arguments, result)` | `ToolResultHookResult(content, details)` |

- `session_start` 在宿主 frontend 接上后触发一次（Pi 的顺序：UI 先于 extension 初始化启动），handler 里调 `baldric.notify(...)` 或打开对话框才会真正被看到。
- `input` 在 skill/template 展开之前对原始 prompt 文本运行。`action="transform"` 改写它（transform 链式连接），`action="handled"` 消费它、不启动 agent 运行并把 `message` 显示为通知。
- `tool_call` 在工具执行前运行。`block=True` 阻止执行并向模型报告 `reason`；返回 `arguments` 改写调用。崩溃的 `tool_call` handler 会挡下工具（fail-safe）。它在参数对照工具 schema 校验之后运行，因此不会看到被校验拒绝的调用，且它返回的参数不会再被校验。
- `tool_result` 可以改写结果的文本 `content` 或 `details`；执行错误状态属于宿主的工具生命周期，不属于结果载荷。

其余所有 handler 失败都被包容：记为诊断（在 `/session` 可见），绝不击溃 session。

### 消息与持久化

`send_user_message` 把用户消息送进对话。运行中它排队为 steering 或 follow-up；session 空闲时 TUI 用它开始新一轮——后台工作就是这样汇报的。`append_entry(namespace, data)` 把 extension 自有数据持久化为可回放的 durable session entry。`set_label(entry_id, label)` 用与 `/tree` 标签编辑器相同的校验与 append-only 存储在既有 session entry 上创建、修改或清除（`None`/空）书签。未知 entry ID 会抛错。

### 自定义消息渲染

要把注入的消息格式化而不是显示原始文本，在 `setup` 注册渲染器并用 `send_custom_message` 发送：

```python
from baldric.runtime.extensions import CustomMessageView, MessageRenderOptions

def render_status(view: CustomMessageView, options: MessageRenderOptions) -> str:
    icon = "[green]✓[/green]" if view.details and view.details.get("ok") else "[red]✗[/red]"
    line = f"{icon} [bold]{view.content}[/bold]"
    if options.expanded and view.details:
        line += f"\n[dim]{view.details}[/dim]"
    return line  # a Rich-markup string, never a widget

def setup(baldric):
    baldric.register_message_renderer("my-ext:status", render_status)

# once the session is running:
baldric.send_custom_message(
    "build finished",
    custom_type="my-ext:status",
    details={"ok": True, "duration_ms": 1200},
)
```

- 渲染器收到 `CustomMessageView(custom_type, content, details)` 与 `MessageRenderOptions(expanded)`，返回 **Rich 标记字符串**（如 `"[bold]text[/bold]"`）。不支持返回 Textual 组件——这保证 extension 不依赖任何 TUI 工具包。
- `send_custom_message(content, *, custom_type, details=None,
  deliver_as="follow_up", trigger_turn=True)` 行为类似 `send_user_message`（`content` 仍进入模型 context），但 transcript 经匹配的渲染器渲染它。`trigger_turn=False` 把它**在内存中**排队等下一次运行，空闲时不开启新轮——消息在这次运行发生前不显示也不持久化，session 先退出就丢失。需要不触发轮次的持久记录就配合 `append_entry`。
- 每个 `custom_type` 先注册者获胜。没有注册渲染器，或渲染器抛异常/返回非字符串时，消息回退为原始 `content`——坏渲染器不会击溃 UI。
- 自定义渲染在交互式 TUI 与 `-p` print transcript 中都工作，并能在 `/resume` 后存活。Baldric 把它持久化为一等 `custom_message` session entry，其 `custom_type` 与 `details` 无需解析通用消息载荷即可检视。TUI 中，自定义消息在其用户事件被运行确认后出现（送达后片刻），而不是像打字 prompt 的乐观回显那样即时。

### provider 接缝、渲染器与生命周期句柄（API v2）

API 版本 2 增加了镜像 Pi 的 provider 与渲染器 hook 的界面。它们以 `provider_hooks` / `renderers` 能力声明，并遵守与其他渲染器相同的规则：Rich 标记文本，绝不是 Textual 组件。

```python
from baldric.runtime.extensions import CompactionSummaryResult, UserBashResult

def setup(baldric):
    # Provider request seams (observe or rewrite the outgoing request).
    baldric.on("context", lambda event, ctx: None)                # chained messages/system rewrite
    baldric.on("before_provider_headers", lambda e, c: e.headers.update({"X-App": "x"}))
    baldric.on("before_provider_request", lambda e, c: {**e.payload, "x-flag": True})
    baldric.on("after_provider_response", lambda e, c: None)      # status + headers
    baldric.on("provider_stream_event", lambda e, c: None)        # raw parsed events

    # Renderers for entries, tools, and markdown.
    baldric.register_entry_renderer("my-ext:card", lambda view, opts: f"[b]{view.data['title']}[/b]")
    baldric.register_tool_renderer(render_call=wrap_call, render_result=wrap_result)
    baldric.register_markdown_transformer(lambda md, ctx: md.replace(":warning:", "!"))

    # Lifecycle handles.
    baldric.on("user_bash", lambda event, ctx: UserBashResult(output="handled remotely"))
    baldric.on("session_before_compact", lambda e, c: CompactionSummaryResult(summary="..."))
    baldric.set_active_tools(["read", "write"])                   # restrict what the model sees
    result = await baldric.execute_tool("read", {"path": "README.md"})
    await baldric.set_model("fast-model")
    applied = await baldric.set_thinking_level("high")
```

- **链接与隔离。** `context` 与 `before_provider_request` 是链接的（返回替换值或 `None`）；`before_provider_headers` 原地修改；观察接缝只读。抛异常的 handler 被跳过并诊断——绝不破坏运行；没有注册任何 provider 接缝时请求路径原封不动（逐字节一致）。
- **工具解析器**接收 `(tool_name, next)` / `(tool_name, result, expanded, next)`；`next()` 产出更低优先级的答案（其他 extension，然后工具自己的渲染器），解析器因此能包裹、延后或接管任何工具——包括在它之后注册的工具。
- **Compaction** 只接受供给的摘要；不能否决，文本钳到 2 万字符，空白或失败的 handler 回退内置摘要器。
- **工具句柄。** `set_active_tools(names)` 限制可见工具集（`None` 恢复全部），限制同样约束之后注册的工具；`execute_tool` 让活动工具走与模型发起调用相同的管线，`tool_call`/`tool_result` hook 与项目信任同样适用。

## 养护一个 extension

Extension 有三种自然尺寸；每步都可选，全都不需要打包：

1. **单文件**（`greet.py`）——上面的快速开始。零配置。
2. **带 `extension.py` 的文件夹**——把 helper 拆进兄弟模块并相对导入（`from . import helper`）。零配置。
3. **带 `src/` 布局的仓库**——在 `pyproject.toml` 的 `[tool.baldric]` 下声明入口（见上）。Baldric 只读 `[tool.baldric]` 表；这个仓库是否同时是可安装的 Python 包完全由你决定（它方便 IDE 解析导入、让测试直接导入模块，但 Baldric 绝不安装、也绝不 `pip` 导入你的 extension）。

两条规则让三种形态都能加载：

- **自己的模块之间用相对导入。** 加载器以合成包名导入你的 extension（并且绝不碰 `sys.path`），`import helper` 不会解析——`from . import helper` 在所有加载模式下都可以。
- **对可选的 Baldric API 做特性探测**（`getattr`/`try: import`），让 extension 在旧版 Baldric 上加载而不是在 import 时失败。

**测试一个 extension。** 通过真实 runtime 加载而不是直接导入你的模块——那样会像 session 一样锻炼发现、合成包导入与 `setup` 注册：

```python
from baldric.runtime import BaldricResourcePaths
from baldric.runtime.extensions import ExtensionRuntime

def test_loads(tmp_path):
    paths = BaldricResourcePaths(
        root=tmp_path / "baldric", cwd=tmp_path / "project",
        agents_root=tmp_path / "agents",
    )
    runtime = ExtensionRuntime()
    runtime.load(paths, extra_paths=(EXTENSION_DIR,), include_resource_dirs=False)
    assert runtime.extension_names == ("my_ext",)
```

`extra_paths` 接收你的 extension 目录（或带 manifest 的仓库根）；`include_resource_dirs=False` 保持测试封闭——`~/.baldric/extensions` 的任何东西都不会漏进来。要在测试里 monkeypatch 模块全局，patch 被加载的合成模块（按 `baldric_extension_` 前缀在 `sys.modules` 里找），不是你包的导入身份——runtime 只看得到前者。

## 示例 extension

见 [`examples/extensions/`](https://github.com/Ember452/baldric/tree/main/examples/extensions)：

- **`ask_user_question.py`** — 让 agent 通过宿主 UI 问一个多选题。
- **`hello_tool.py`** — 最小自定义工具。
- **`permission_gate.py`** — 用 `tool_call` hook 拦截危险 bash 命令。
- **`sidebar_status.py`** — 添加并更新宿主框定的侧栏区块。
- **`prompt_section.py`** — 追加带标签的多行 system prompt 区块。

## 尚不支持

对照 Pi 的 extension 系统，Baldric 尚未包含完整的包管理器（安装器没有 registry、依赖安装、remove 或 package-update 命令）、声明式快捷键注册、CLI 旗标注册或 system prompt 替换。自定义 entry/工具/markdown 渲染器、provider 请求接缝、context 改写、`user_bash` 拦截与动态工具句柄自 API v2 起支持（见上）。extension 设计的架构文档（`docs/internal/architecture/phase-21-extensions.md`）持续跟踪。
