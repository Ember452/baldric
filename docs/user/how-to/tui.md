---
title: 交互式会话
description: 用熟 Baldric 的终端 UI——prompt、steering、命令面板、工具输出与 picker。
---

不带参数运行 `baldric` 打开交互式终端 UI（TUI）。大部分工作发生在这里。本指南讲各部件；确切按键见[键盘快捷键](/reference/keybindings/)。

## 发送 prompt

在底部 prompt 框输入并按 **Enter** 提交。编辑器没有高亮背景；上下两条细线框住它并随 shell 模式变色，而不是框死它。agent 工作时，prompt 旁的 `τ` 变成轻柔脉动的布莱叶盲点 spinner（`⣾⣽⣻⢿`），运行结束恢复 `τ`。
**Shift+Enter** 为多行 prompt 插入换行。终端区分不了它与 Enter 时，在 `~/.baldric/tui.json` 重映射 `insert_newline`；见
[键盘快捷键](/reference/keybindings/#输入)。Baldric 把 assistant 回复流式显示在 prompt 上方，工具调用运行时实时可见。OpenAI 返回多个 reasoning-summary 片段时，Baldric 把它们保留为独立的 Markdown 段落，而不是把标题连在一起。在支持的终端模拟器里，Baldric 还会更新标签页标题：命名 session 显示为
`τ | <name>`，活跃运行加动画的运行指示，从另一个标签页也能看到工作在继续。当一次运行完全落定而 Baldric 的终端表面失焦时，Baldric 在支持的终端上默认发出桌面通知：Ghostty、iTerm2 与 MinTTY 用 OSC 9，Kitty 用 OSC 99。未知终端保持原样。设 `turn_notification` 为 `"bell"` 让终端标记标签页或按其配置的铃行为，或 `"off"` 禁用通知。BEL 与操作系统桌面通知可能按用户终端与系统设置发声；见
[Configuration](/reference/configuration/#tui-设置)。

Chat Completions 类 provider 可能交错推理与回答片段（例如经 Hugging Face 的 DeepSeek）。Baldric 在流式与保存回复时把每个 channel 保持在连续块里，而不是在 channel 切换处拆句。此前保存的回复保留原块布局。

点击窗口任意处把焦点交还 prompt，你可以滚动 transcript 并继续打字，不用切回去。

provider 请求重试后仍失败时，Baldric 把失败显示为 transcript 里显式的错误块，使用 provider 自己的错误消息（例如 `server_is_overloaded` 的细节而非笼统失败）。块里含诊断日志路径与运行已结束的提醒。你可以不新开 session 直接提交下一个 prompt；空的失败 provider 轮为诊断保留，但不会作为无效对话历史回放给模型。

## 取消与 steering 一次运行

agent 工作时你不必干等：

- **Esc** 取消活动运行。取消被视为有意停止，不是错误。
- **Enter**（运行中）把你的文本排队为 **steering**——应用到当前运行的追加指引。
- **Alt+Enter** 排队 **follow-up**——等到当前运行本会结束之后才执行的 prompt。
- 运行中在空 prompt 上按 **Up** 把最近排队的 follow-up 拉回输入框编辑。

## 命令面板与 slash 命令

会话内命令以 `/` 开头。用 **Ctrl+K** 打开**命令面板**搜索并运行。常用的：

- `/session` — 显示 session 的 model、tools、skills 与 context 用量。此弹窗中选中的文本自动复制到剪贴板。
- `/diagnostics` — 检视资源加载警告与错误，包括资源种类、名字、来源路径、严重度与补救消息
- `/system` — 按来源分组显示活动 system prompt，不加入 context 或 session 历史
- `/model` — 选择活动模型
- `/tools` — 按来源搜索活动工具并查看完整描述
- `/compact` — 总结并缩小 context
- `/resume`、`/tree` — 打开之前的 session 或从历史分支
- `/prompts` — 搜索 prompt template、插入调用，或用 **Ctrl+E** 编辑模板文件
- `/hotkeys` — 显示键盘快捷键
- `/local` — 选择并管理已注册的本地 backend
- `/sidebar` — 显示或隐藏本 session 的侧栏

slash 命令补全打开时，**Enter** 应用高亮建议而不提交；先用方向键换一条再应用。**Tab** 同样应用高亮建议。

完整列表见 [slash 命令参考](/reference/slash-commands/)。本地推理见[本地 backend 指南](/how-to/local-inference/)。

### 本地 backend

`/local` 先打开显式的 backend 选择器。一个 backend 预选但仍需确认；推荐 backend 只是标记。Baldric 内置的 `llama.cpp` backend 自动探测它唯一有效的
已保存/环境/默认端点；**Configure** 接受别的 URL 和
可选的 secret key。它把模型与 backend 动作渲染为独立的
方向键导航区块。只有聚焦区块显示 `focused` 标记、
accent 边框与高亮行；Tab 直接切换区块。Enter
从聚焦区块选择，Escape 关闭。昂贵的
加载/下载操作要求带模型细节的单独确认，
活动下载显示路由上报字节进度的整宽块状进度条，重开 `/local` 后亦然。actions 区块提供
Hugging Face 搜索/下载、显式的活动下载
取消、状态、刷新、Doctor 与 reset；model 区块负责加载、
使用与卸载。

Configure、刷新、状态、Doctor 与 reset 异步工作，显示结构化进度/诊断，并在屏幕关闭时取消。服务端下载在 `/local` 关闭后改由 llama.cpp 继续。
服务器宕机期间，缓存的模型快照保持可见并标为过期。
改状态的动作要求 agent 空闲。reset 不停止 llama.cpp 也不
删除模型文件；凭据删除单独确认。显式
启动与排障见[本地推理指南](/how-to/local-inference/)。

## 直接运行 shell 命令

你可以不经模型自己跑 shell 命令：

- `!<命令>` 在 session 的工作目录运行它，**并把**
  命令与输出记进对话 context。
- `!!<命令>` 运行并显示输出，**不**加入 context。

shell 命令是非交互的：它们的 stdin 与 TUI 断开。
需要交互终端的程序请另开终端运行。

输入一以 `!` 开头，整条输入及其上下细线在运行期间变成与工具相同的琥珀/橙色，`τ` prompt
前缀变为匹配的 `$`，一眼可见提交的将是 shell 命令而不是给模型的消息。

`!`/`!!` 之后输入路径时按 **Tab** 从
工作目录补全文件名。`.env`、`.agents/` 这类点前缀路径也包含在内。

> [!NOTE] 别名
> 这些命令（和 agent 的 `bash` 工具）运行在非交互 shell，所以
> 你的 `~/.zshrc`/`~/.bashrc` 别名不会自动加载。用自己的别名，设 `shellCommandPrefix`——见
> [Shell 设置](/reference/configuration/#shell-设置)。

## 用 `@` 引用文件

在 prompt 里输入 `@` 打开项目树的文件建议，并插入如 `@src/app.py` 的路径。用显式的父级相对路径如 `@../` 补全项目根之外的文件与目录。外部补全只跟随你输入的路径，不扫描周边文件系统。
`.env`、`.agents/` 这类点前缀内容同样包含。Baldric 仍跳过
`.git`、`.venv`、`node_modules`、`__pycache__`、`build`、`dist` 等已知元数据与生成目录。按 **Tab** 插入高亮路径。
目录带尾部 `/` 显示，插入即提交为 `@src/` 这样的目录引用；要引用目录内文件，继续输入路径或从同一列表选文件。按 **Enter** 原样提交而不插入。同一条
规则适用于 skill 与自定义 prompt 参数文本里的 `@` 建议。

## 把文件拖进 prompt

把一个或多个文件从文件管理器拖到终端窗口，Baldric 在光标处插入其文件系统路径，以空格分隔。含空格的路径自动加引号，已输入的文本保留。这在整个 TUI 生效，不只在输入框上方，因为终端把拖放作为文本输入送达。

来自不会先给终端键盘焦点的来源的拖放同样接受，例如 macOS Dock 的"下载"堆栈。

## 工具输出

工具调用运行时在 transcript 里保持静态标记：橙色进行中，绿色成功，红色失败。该状态色作用于语义描述（如 `Running tests` 或 `Read 5 files`）；命令
片段、参数与文件列表保持中性灰。prompt 区的活动
指示器提供整次运行的动画，不给每个工具行加第二个 spinner。

同一模型响应里相邻的内置工具调用共享一个 transcript 块，
每个逻辑动作一行紧凑显示。每行保留自己的状态色，
相邻的 read、edit 或 write 聚在同一标题下并列出每个文件路径。`read` 与 `edit` 调用的文件路径
相对 session 工作目录显示，即使模型传了绝对路径，transcript 因此保持紧凑。展开的组保留每次调用与结果：edit 与 write 行显示其 patch 或写入内容，
read 行显示每个文件的预览。折叠的路径列表把每个 read 的行范围记为 `file:start-end`。整个块保持一个可选中的
文本面，包括跨行边界。

同工具的运行跨连续无旁白的响应延续，串行发出调用的
provider 也只产出一个块。assistant
文本或 thinking、不同的工具、失败的调用、新的用户 prompt 都会结束该运行。八行后运行停止增长，下一次调用开启新块。文件组每个成员都计入此限，包括混合工具块内的组。Extension 工具、自定义渲染的调用卡片与 skill 加载
保持独立。

工具结果（如长的 `read` 或 `bash` 输出）渲染为紧凑预览，保持 transcript 可读。Baldric 要求模型给每个 `bash` 调用
一个如 `Running tests` 的简短描述。Baldric 完整显示该描述；
折叠行从不显示命令文本。按 **Ctrl+O** 保持描述可见，并在其下展开确切命令
与结果。畸形 provider 输出、
自定义集成与旧 session 仍可能缺描述；那些调用
显示通用 `Running shell command` 标签直到展开。

一个模型响应读或编辑多个文件时，同类型相邻调用共享一个组。组列出每个路径，结果到达时报告进度，需要时显示聚合失败数。连续
无旁白的响应延续同一组；shell 调用与 extension 工具
保持独立。

用 **Ctrl+O** 把组切换为逐个调用列表。展开的 read 行
显示每个文件的预览，组仍回答读了什么而不是藏起来。同一开关对其他工具
显示确切 shell 命令与完整输出。compaction 与分组只影响 TUI 显示；执行、
session 历史与 print-mode transcript 保留每次完整的调用与
结果。

预览有损：长的工具结果或 `!` shell 命令输出截断到
固定行数与字符数，Baldric 在丢弃处追加
`[Preview only: … hidden from the TUI.]`。**Ctrl+O** 展开渲染未截断文本，调试 `!` 命令（例如配置 sandbox profile 时）不再需要 session 导出。
要让整个 transcript 起始即展开，启动 `baldric` 时传
`--show-full-output`。两个控件只影响显示；
session 历史始终保存完整输出。

Markdown 链接的悬停样式只给链接文本加下划线，不波及该行其余部分。用户消息块与 prompt 字段、侧栏使用同一主题背景，
上下留少量内边距，读作块而不是高亮行。
这在视觉上把已提交的 prompt 与输入区绑定。

## 长 session

Baldric 通过一次只在终端挂载一个消息窗口保持长 transcript 响应迅速。完整 session 保存在显示状态与持久历史中。较旧或较新的消息在当前窗口之外时，出现一个小的边界行；朝它继续滚动即可翻阅其余对话。

翻页不总结、不删除、不压缩 context。想减少发给模型的内容，单独用 `/compact`。

## 选择模型与主题

- **`/model`** 立即从缓存/内置模型打开模型 picker，
  然后在 picker 首次渲染后于后台刷新目录。
  其模型列表只渲染可见行并更新打开的列表。关闭
  任一模型 picker 会停止进行中的目录刷新；取消 scoped-model picker 不必重建侧栏。账户级
  Codex 快照也跨 session 复用，`/model` 会刷新它。
- **`/scoped-models`** 打开收藏模型 picker 并同样在后台刷新 provider
  目录，新发现的 Codex 模型因此可以不先开 `/model` 就收藏。用 `baldric update --models` 强制
  刷新公共目录，或 `BALDRIC_OFFLINE=1` 禁用目录网络访问。
- **Ctrl+P** 快速向前轮换你的 *scoped*（收藏）模型；
  **Shift+Ctrl+P** 向后。都不打开 picker。用 `/scoped-models` 管理列表，或在 `/model` picker 里对模型按 `Space`。
- 模型与 thinking 选择立即更新状态显示。Baldric 在你发送下一条消息时、该消息进入 session 历史之前才记录最终选择。未发送的选择重启后消失；轮换不改变未来 session 的默认。无法准备所选模型时，Baldric 报错而不是用旧模型发送。
- **`/theme`** 在 `baldric-dark`、`baldric-light`、`high-contrast` 与
  已安装的自定义主题之间切换。每个主题对 prompt 补全与 `/resume` 之类的弹窗列表使用同一套选择
  配色。`baldric-dark` 中，水色选择色也是标题、prompt 活动与其他强调 UI 的全局 accent。`baldric-light` 在白底上用深青 accent 做标题与列表标记。见
  [Themes](/how-to/themes/)。

## 侧栏

在足够宽的终端上，Baldric 显要地显示 session 名而不用多余的区块标签，其后是活动分支的
轮次与工具调用总数、provider 上报的 token 用量、平均有效
输出速度与 TTFT、最近请求与 session 的 prompt 缓存命中率、预估成本、
自动 compaction 阈值，
以及已加载的 tools、skills、prompt templates、extensions 与 `AGENTS.md` 之类 context 文件。工具与 extension 名用紧凑的逗号分隔列表，限
三行。skill 与 prompt template 按资源来源分组（例如 `./.baldric/skills`、`~/.agents/skills`、
`./.baldric/prompts`）。这两节起始折叠并在标题里显示已加载项
数。skill 标题还显示已加载 skill 索引在 system prompt 中的估算 token 成本；完整 skill 指令只在调用该 skill 时进入 context。点击任一标题（或聚焦后按
**Enter**）独立展开或收起该区块，两个列表都能保持展开。区块展开时显示每个已加载的 skill 或 prompt。点击 skill、prompt template 或 context 文件行会把 transcript 替换为主区编辑器。用**方向键**移动编辑
光标。**Ctrl+S** 把编辑内容写盘并报告成功或失败，不关闭编辑器。Baldric 拒绝覆盖打开后已在磁盘上变化的文件，并在当前编辑器有未保存修改时阻止切换到另一个侧栏文件。先保存或关闭那个文件。
**Escape** 关闭编辑器并恢复 transcript。保存后想让活动 session 用上新资源就运行 **`/reload`**。
skill 行只打开该 skill 的
主 `SKILL.md`；skill 目录里的支撑文件暂不在侧栏暴露。可编辑行悬停时高亮并加下划线。模型可见的 skill
用实心圆点（`•`），设了
`disable-model-invocation: true` 的用户专用 skill 用空心圆点（`◦`）。侧栏内容
高于可用空间时滚动查看其余资源组；
Baldric 版本标记钉在底部。context 文件
用每行一条路径的列表，限五条。Baldric 从用户或项目
`.baldric` 目录加载 `SYSTEM.md` 替换或 `APPEND_SYSTEM.md` 追加时，单独的 **system prompt** 区块列出每个活动文件。
没有活动的 system prompt 文件时 Baldric 省略该区块。被截断的区块
以 `...(X more)` 结尾，显示隐藏了多少条。项目资源路径
相对工作目录；从 home 目录加载的资源以 `~/` 开头，从项目外加载的其他资源用完整路径。

更宽的无边框侧栏使用 prompt 字段的背景色、明亮的
区块标题、更安静的灰阶，并把 Baldric 带版本的 `τ = 2π` 标记
钉在其底边。Baldric 不渲染独立的
顶部 header 或快捷键 footer 行。命名 session 在侧栏
和终端标签页标题中保持可见；需要时 `/hotkeys` 列出快捷键。终端过小时侧栏自动隐藏，标签页标题继续
标识 session。

`avg TPS` 用 provider 上报的输出 token 除以 Baldric 累计等待 provider 流事件的时间。它包括 provider 排队、网络
等待、prefill 与首输出前的时间，但排除两次流拉取之间 Baldric 的渲染与
持久化工作。TPS 按计时响应做 token 加权，而不是各响应速率的算术平均。`avg TTFT` 是 Baldric 第一个文本、thinking 或
工具调用输出事件之前 provider 等待时间的算术平均。计时持久化在新 assistant 消息上。更早的
历史仍计入累计 token 用量与成本，但不计入这两项性能指标。

累计用量与成本覆盖活动分支，包括被 compaction 替换的历史与生成 compaction 或分支摘要所用请求。启发式摘要回退没有 provider 用量，不加任何数。输入用量
统计每次 provider 请求处理的 token，所以可能远大于下一次请求用到的 context。成本是基于 provider 上报用量与已配置
目录费率的估算；Baldric 缺少完整定价数据时侧栏显示 `$N/A`。

缓存行区分最近一次模型请求与整个累计 session。
两个比率都是 provider 直接从缓存服务（而非重新处理）的 prompt token 份额。最近比率让缓存未命中立刻可见，并且
在工具使用后描述最近一次模型续请求。session 比率
包括活动分支上的每个请求，包括最初那次冷请求。
最近比率低通常意味着请求早期有东西变了，例如重载的工具列表或 thinking 级别，或一次超过 provider 缓存的停顿。
Baldric 对不上报缓存使用的 provider 隐藏这两项。

prompt 下方的紧凑状态块第一行显示工作目录与 Git
分支，第二行是 `provider:model (thinking)` 加右对齐的
`used/limit`，其中 `used/limit` 是 provider 锚定的活动 context。尚无有效的 provider 用量时——例如 compaction 刚结束——它显示
`?/limit` 直到新响应报告用量。与累计用量不同，这个
活动计数描述 Baldric 预期在下一次请求发送的 system prompt、工具
与活动消息。compaction 后它可能下降而累计用量继续上升。工作目录名与模型被强调，父路径、Git
分支与 provider 用更安静的元数据色。

侧栏默认出现在**右侧**。可以移到**左侧**
或用 `~/.baldric/tui.json` 里的 `sidebar_position` 设为**关闭**——
见 [Configuration](/reference/configuration/#tui-设置)。
会话中用 `/sidebar` 切换可见性。这是临时的：它
保留已配置的左/右位置，不改 `tui.json`，Baldric 重启后遗忘。已配置为 `off` 的侧栏可以
临时在默认右侧显示。

## Herdr 兼容

prompt 编辑器里，Option/Alt+Left 与 Right 按词移动，在 Herdr 里同样有效（无论转发为 Alt 方向键还是 Kitty 的 Alt+b/Alt+f）。Alt+b/Alt+f 也按词移动。方向键加 Shift 按词选择。不需要 macOS Ctrl-方向键的改动。
既有的 Ctrl-方向键与终端 Esc+b/Esc+f 导航照常工作。

Baldric 检测到 TUI 运行在 Herdr 内时，默认让 Textual 使用
单元格坐标鼠标输入与标准终端 resize 信号。这规避一个 Herdr 0.9.0 互操作 bug——它会把点击、悬停、选择与滚动折叠进窗格左上角。其他终端保持 Textual
常规的带内 resize 与像素鼠标行为。显式配置的
`TEXTUAL_SMOOTH_SCROLL` 环境变量优先于 Baldric 的兼容默认。

## 下一步

- [Sessions](/how-to/sessions/) — 恢复、分支、重命名、导出。
- [Providers & models](/how-to/providers-and-models/) — 切换与添加模型。
- [管理 context](/how-to/context/) — compaction 与 thinking 模式。
