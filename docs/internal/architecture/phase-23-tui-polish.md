---
title: "Phase 23：高级 TUI 与产品打磨"
---

Phase 23 改进 Textual frontend，同时让可复用的 agent harness 保持对 UI 事务独立。

边界不变：

```text
CodingSession emits AgentEvent values
        ↓
TuiEventAdapter updates TuiState
        ↓
Textual widgets render the transcript and controls
```

## 当前打磨片

活动工具结果现在在 transcript 里渲染成功输出的预览，与还原的 session 历史一致。TUI 显示前几行并在有更多内容被隐藏时给出预览提示，这样大的 `read` 或 `bash`
结果不会淹没对话，而持久 session 仍为模型 context 与回放保留完整的工具结果。

transcript 块现在在同样的 Pi 式堆叠消息块内用 Rich 语法 renderable 渲染围栏代码与持久化的 edit patch。
transcript 状态仍存纯 role/text 项；这是 Textual frontend 里仅渲染层面的打磨。

transcript 表面是可选中消息组件的滚动容器，不是一张大 `RichLog`。每个消息组件为其渲染块拥有选中文本提取，因此部分鼠标选择限定在目标消息内，相邻消息的复制不会意外扩成整段对话。

assistant transcript 块现在还经 Rich Markdown 渲染常见 Markdown 结构：标题、列表、引用、链接、行内代码与强调。user、tool、status 与 error 块保持字面，除非由显式的代码或 patch 渲染器处理——粘贴的 prompt 与工具输出因此可预测。

活动的 `edit` 工具结果现在在工具块里包含 unified patch。文件编辑由此获得内联 diff 视图，同时事件适配器与
Textual 组件保持解耦。工具结果元数据现在保留在
`ToolResultMessage`，还原的 session 历史因此能从持久化 JSONL entry 渲染同样的 edit patch 块。

TUI 还有命令面板入口。按 `Ctrl+K` 聚焦 prompt、插入 `/`，并用既有补全引擎显示全部 slash 命令补全。选择使用与普通 slash 命令补全相同的
`Tab`、`Up`、`Down` 绑定。高亮补全会改变 prompt 时按 `Enter`，现在应用该补全而不提交 prompt，与常见终端 picker 行为一致。

slash 命令输出现在是瞬态 UI 而非 transcript 内容。短的命令结果用 Textual 通知，多行输出如
`/help`、`/skills`、`/resume`、`/status`、`/resources`、`/context` 打开可关闭的弹窗。命令参考材料因此不进 agent 对话，信息仍可访问。

同一补全引擎现在为 `/model` 与 `/login` 参数建议可用值。`/model` 也可以为已配置的
provider/模型选项打开弹窗 picker，而 `/login` 仍是添加 provider 的路径。

prompt 还为 `/resume <session-id>` 建议已索引 session id，纯 `/resume` 打开与 session-picker 键位相同的弹窗 session picker。那些行包含标题、模型与工作目录等 session 元数据，并按 `SessionManager` 保持当前项目最新优先的顺序。提交命令经 `CodingSession` 重载所选 session 并就地重建可见 transcript。

TUI 还有绑定到默认 `Ctrl+R` 的小弹窗 session picker。它以 resume 补全相同的元数据列出已索引 session，然后经 `CodingSession.resume()` 恢复所选 session。picker 完全住在 Textual frontend；可移植 harness 仍没有 session 选择政策。

内置 Textual frontend 现在从 `~/.baldric/tui.json` 读取可选键位设置。用户可以重映射命令面板、补全导航、session picker、取消与退出键，而配置留在
`baldric_coding.tui`，不进可复用 agent harness。

同一份 TUI 设置文件现在支持具名内置主题。`baldric-dark` 仍是默认，`high-contrast` 提供更亮的深色调色板。默认主题受 Toad 的 Textual UI 启发：更暗的表面、透明镶边、安静的分隔线、聚焦的底部 prompt，以及用窄左侧 accent 而非盒装卡片的堆叠对话行。主题选择供给 Textual CSS 变量加 Rich transcript/侧栏渲染器，应用镶边与消息块视觉一致，而不给 `baldric_agent` 加 UI 政策。

侧栏现在是响应式的。中等及以上大小的终端窗口保持可见，终端过窄或过矮时自动隐藏，让对话与 prompt 有足够呼吸空间。可见性规则住在 Textual frontend；session 元数据与 agent 状态不变。
可见时侧栏包含已加载 context 文件，`AGENTS.md` 之类的项目指令无需打开单独的命令弹窗即可检视。

状态行现在在运行活动时显示小的动画活动指示器，运行完成、取消或失败时重置为 `Ready`。排队的 prompt 等待注入时，它还显示待处理的 steering/follow-up 队列计数。

thinking 控件现在含两种不同的 TUI 行为：当前 provider/model 支持时 `Shift-Tab` 轮换活动 thinking 模式，`Ctrl-T`
切换流式 thinking token 的显示。thinking token 的 transcript 块默认隐藏，显示时以自己的角色样式渲染。

模型控件现在有 Pi 风格的 scoped-model 流程。`/model` 仍打开
provider/模型 picker，但 `Space` 把高亮模型切换进持久 scoped 清单，`Tab` 让 picker 在全部模型与 scoped 模型间切换。`Ctrl-P` 直接从 prompt 轮换 scoped 清单。TUI 请
`CodingSession` 变更与轮换该清单；Textual 自己不读写 provider 设置。

活动指示器现在住在 prompt 正上方的稳定行里，而不是顶部状态行。agent 轮运行时底部输入区保持视觉活跃，顶部状态区聚焦 provider、模型、队列与 session 状态。

Textual footer 现在经普通可见绑定携带 Baldric 的快捷键提示。它描述活动的提交、换行、picker、thinking、
follow-up 与清空 shortcut，补全打开时切换到补全聚焦的绑定，agent 轮运行时再次切换。Baldric 不加单独的自定义提示行；内置底部工具栏仍是唯一的快捷键表面。

TUI 把 `Esc` 视为两步取消流程。第一次按经 `CodingSession.cancel()` 请求优雅取消，provider 或工具观察取消 token 期间活动 worker 保持可见。第二次按立即中断当前 Textual worker。这镜像
Pi 的取消边界：UI 代码请求取消，可移植 agent loop 携带取消 token，`bash` 之类的长运行工具遵守该 token 而不让 Textual 成为
`baldric_agent` 的依赖。因为取消是有意的用户动作，内置 TUI 把最终取消事件渲染为状态文本，而不往 transcript 加错误行。

assistant 代码块渲染现在更有防御性。已知的栅栏语言用
Rich/Pygments 语法高亮，未知或自定义栅栏标签回退为纯代码渲染，而不产出损坏的 transcript 块。

内置主题集现在在 `baldric-dark` 与 `high-contrast` 之外加入 `baldric-light`。主题选择留在 `baldric_coding.tui` 配置，供给
Textual CSS 变量加 Rich 渲染器，UI 政策不泄漏进可移植 harness。Textual 原生主题注册表被限制为同一批 Baldric 主题，Textual 的菜单/命令面板主题项因此改的是 Baldric 的持久
`~/.baldric/tui.json` 设置，而不是成为第二套不持久的主题系统。

session 现在可以从 TUI 用 `/name <new name>` 重命名。命令更新
`/resume`、resume 补全与 session picker 使用的已索引 session 元数据；底层的 append-only transcript 仍是对话事件的持久来源。

frontend 边界已文档化于 [构建你自己的 frontend](../../user/explanation/custom-frontend.md)。
该指南描述另一个终端 UI 如何消费 `CodingSession`、
`AgentEvent`、`TuiState` 与 `TuiEventAdapter` 而不耦合 Textual 内部。

## 手动验证清单

这些检查在 Textual TUI 里锻炼 Phase 23 打磨。使用
`origin/main` 的干净工作树，避免本地实验分支影响结果：

```bash
git fetch origin
git worktree add /tmp/baldric-tui-validate origin/main
cd /tmp/baldric-tui-validate
uv run baldric
```

1. 检查 `/name`：开一个 session，运行 `/name Manual validation`，再打开
   `/resume`。改名的 session 应出现在 resume picker 与
   `/resume <session-id>` 补全里。
2. 检查工作指示：提交一个耗时数秒的 prompt。轮运行期间
   prompt 边框应在活动色之间缓慢渐变，prompt 上方没有单独的 spinner 行。
3. 检查内置底部 footer 的快捷键提示。应显示提交、换行、命令、session、thinking、清空与退出等 prompt 动作。打开 slash 命令补全，确认同一 footer 切换为补全、选择与关闭动作。提交一个耗时数秒的 prompt，确认 footer 切换为 steer、follow-up、取消、thinking 与工具动作。footer 之上不应有第二行自定义快捷键。
4. 检查代码块渲染：请模型给一个 `python` 围栏块与一个未知语言的围栏块如
   `not-a-real-language`。Python 块应高亮，未知语言块应渲染为纯代码而不破坏 transcript。
5. 检查浅色主题：把此文件

   ```json
   {
     "theme": "baldric-light"
   }
   ```

   写进 `~/.baldric/tui.json`，重启 `uv run baldric`，确认应用使用浅色调色板，transcript、侧栏、footer 与 prompt 颜色可读。检查后恢复你偏好的主题。

## 边界

这些变更住在 `baldric_coding.tui`。命令注册表仍拥有命令
元数据，`baldric_agent` 保持对 Textual、键位、slash 命令与渲染无知。

## 仍然推迟

Phase 21 extension 仍有意未实现。未来打磨可能加更高级的 picker 表面，但当前 Phase 23 清单项已有基础实现。

## 测试

覆盖位于：

```text
tests/test_tui_adapter.py
tests/test_tui_app.py
tests/test_tui_config.py
```
