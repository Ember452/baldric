---
title: "11 — Subagents 移植审计（Phase 2 飞行前）"
---

把 `tau-subagents` 移植进 Baldric 作为打包的
built-in extension 之前收集的证据。这里没有估算：每个数字都来自 AST 解析
或对照上游树做过改名归一化的 `git diff`。

## 为什么这次移植看起来便宜，以及核实了什么

`tau-subagents` 面向上游 Tau，而 Baldric 是 Tau `0.4.9` 的改名。
工作区还包含那份确切的上游树（`tau-main`，`pyproject.toml:
version = "0.4.9"`），所以分歧可以测量而不是假设。

方法：复制每个 Baldric 文件，把 `baldric|BALDRIC|Baldric` 替换为
`tau|TAU|Tau`（区分大小写：PowerShell 的 `-replace` 不区分大小写，
第一轮产出了错误的分歧报告——下面是修正后的结果），
归一化 CRLF，然后 `git diff --no-index -U0`。每个 hunk 经 `ast` 映射到其所在的
`def`/`class`，得到符号级分歧。

文件级结果：`tau_coding` 有 48 个顶层模块，`baldric_coding` 有 49。
唯一新增的文件是 `gitignore.py`（#473 移植）。

改名归一化后完全一致的模块：`paths.py`、`thinking.py`、
`session_stats.py`、`events.py`、`extensions/__init__.py`。

## extension 本体实际需要什么

用 `ast.walk` 解析 `src/tau_subagents/**/*.py`（包含函数内
延迟导入）：13 个模块，约 30 个符号。每一个都能在 Baldric 中解析。

| 需要 | Baldric 中的状态 |
|---|---|
| `tau_coding.TauResourcePaths` | 已改名：`BaldricResourcePaths`，由 `baldric_coding/__init__.py` 的 `__all__` 再导出 |
| `tau_agent.events.AgentEvent`、`tau_agent.messages.AgentMessage` | 以 PEP-695 `type` 别名存在（`events.py:73`、`messages.py:273`） |
| `provider_runtime.create_model_provider` | 签名字节级一致；唯一 diff 是 ruff 行宽 110 改动带来的一行折行 `raise` |
| `tui.state.TuiState` 中 `ui/viewer.py` 读取的属性（`show_tool_results`、`load_messages`） | 存在（`state.py:126`、`state.py:719`） |
| `on("session_start")` / `on("session_shutdown")` | `extensions/runtime.py:1173-1179`，名字声明于 `extensions/api.py:56-57` |
| `resources.parse_markdown_resource` | 相同签名 `(text) -> tuple[dict[str, str], str]` |
| `thinking.THINKING_LEVELS` | 相同的 7 级元组 |

结论：**移植不需要改动可复用内核**，也没有新的第三方依赖（`tau-subagents` 锁定 `tau-ai>=0.3.0` 加 `textual>=8.2.8`，Baldric 已原样声明）。

## 真正的耦合在哪：测试，不是本体

按目录拆分导入：extension 本体需要 13 个模块；其测试套件需要 22 个。深层/私有坐标只出现在测试里：
`tau_coding.tui.app._theme_css_variables`、`PromptInput`、`TauTuiApp`、
`tau_coding.session.ModelChoice`、`TerminalCommandResult`、
`tau_coding.tools.create_coding_tools`、`tau_coding.session_stats.SessionStats`、
`tau_coding.system_prompt.ProjectContextFile`、`tau_coding.events.QueueUpdateEvent`、
`tau_ai.FakeProvider`。

测试清单（AST 枚举，144 个测试）：`test_extension.py` 73、
`test_ui.py` 41、`test_schedule.py` 18、`test_integration_tui.py` 12。

决策记录在此：Baldric 为该特性自写测试而不导入上游套件，
用上面的上游清单作为覆盖对照表。上游测试深入了此后已经分歧的 TUI 内部
（`tui/state.py` +113/−48、`tui/widgets.py` +86/−97、`tui/app.py` +148/−203），
导入它们会连分歧一起导入。

## 两处有意的上游偏离

1. **项目信任。** 上游无条件读取 `<cwd>/.tau/agents/*.md` 与
   `<cwd>/.tau/subagents.json`。Baldric 的项目资源受项目信任门控
   （`session.py:576` 调用 `resource_paths_with_project_trust(...)`；
   `session.py:607` 只在受信任时加载项目 extension）。照原样移植上游行为会让不受信任的仓库注入 subagent 系统
   prompt 与工具允许列表——那是安全回归，不是风格选择。这扇门不需要新管线：`extensions/api.py` 已暴露
   `ExtensionContext.project_trust_resolution`（:977）与
   `ExtensionContext.project_trusted`（:991），其 docstring 已经指示构建子 session 的宿主转发 `CodingSessionConfig(trust_override=...)`，让 child 继承决定而不是无头重新解析。移植消费它；不在 extension 内部重新推导信任。
2. **Worktree 清理失败。** 上游 `worktree.py` 的清理以
   `except Exception: _remove_worktree(); return WorktreeResult(has_changes=False)` 结尾，即失败的 commit/branch 被报告为"什么都没变"，child 的工作被静默丢弃。Baldric 经 #477 移植加入的资源诊断路径显式报告该失败。

## 路径根

上游使用八个 `.tau` 根（`agents/`、`subagents.json`、`subagents/` transcript、`agent-memory/` 加
`agent-memory-local/` 的用户与项目范围）和一个安装文档字符串。它们映射到新的
`BaldricPaths` 属性，而不是在 extension 内手工拼装，
这样 `BALDRIC_HOME` 覆盖继续有效，命名也与 llama.cpp 内置使用的既有
`extension_state_dir` 约定一致。

## 移植 `prompts.py` 时发现的悬而未决项

`(Skill "x" not found)` 是上游占位文案，在一种情况下会变成假话：项目不受信任时，`BaldricResourcePaths.skills_dirs`
（`resources.py:86-104`）直接省略项目目录，于是仓库里确实存在的 skill 被报告为缺失，模型往往再把它转述为"你没有这个 skill"。

修复属于 `extension.py` 的调用点——它同时持有
`project_trusted` 与 `definition.skills`：发一条说明，指出预加载因缺乏信任而跳过。它**不属于** `resolve_skill_blocks` 内部。
**已推迟，未做：** 落地的 `extension.py` 保持该调用点原样，
因此不受信任的项目仍不会对被跳过的预加载发出任何消息。
本移植的早期草稿在那里加了 `diagnostics` + `missing` 拆分，理论是区分"仓库未授权"与"打错字"。
该理论与事实不符：不受信任场景根本不产生诊断，
而 `_load_skills_from_dir_with_diagnostics`（`skills.py:176-177`）对缺失或非目录路径返回
`([], [])`，它的诊断报告的是裸 `.md` 文件与优先级覆盖——不是不可读目录。调用者已经知道信任决定，在这里加通道至多冗余，最坏误导。

## 第二个悬而未决项，来自 `schedule.py`

`_execute_job` 只记录 `last_status="error"`：`manager.spawn` 外的 `except Exception` 与等待运行任务外的那一圈都丢弃了异常，于是一个连错一周的每晚任务只有状态、别无他物。保留消息需要在存储的 job 上加 `last_error` 字段，那是 schema 变更而非适配，所以不进本次移植、记录于此。决定它也意味着决定存储文件应保留历史还是只留最近一次失败。

## thinking 级别：继承默认，以及旧默认为什么错

该能力曾为 frontmatter 或参数中没有级别的任何非 fork child 选 `DEFAULT_THINKING_LEVEL`（`thinking.py:21`，即 `medium`），而 provider 与 model 早已继承父级。在不提供 `medium` 的模型上 spawn 直接死亡：`create_model_provider` 把级别转发给宿主，级别超出
`provider_thinking_levels(provider, model=...)` 时宿主抛错（`provider_config.py:1787-1792`、
`1821-1826`）。硬编码默认在良性场景也是错的——它让 child 以一个没人选过的级别思考，还低于孵化它的那段对话。

现在的回退是：显式 frontmatter 或参数优先；否则在 child 仍运行父级 provider 与 model 时用父级的活动级别；否则什么也不传，宿主定义为"不发送 thinking 参数"，让模型自己的默认生效（`provider_config.py:1775`、`1809`）。显式值仍原样透传，因为明说的意图应当浮出，而不是被静默改写。

这一点只有在该能力默认启用后才能看见：最初用模型总是支持 `medium` 的 fake 测试，于是优先级用例把默认值当设计断言了。

## 成本是测出来的，不是猜的

`baldric_coding` 被 `[tool.mypy] strict = true` 覆盖。`tau-subagents` 完全没有 mypy 配置。用 Baldric 的 mypy 2.1.0 以 `--strict
--ignore-missing-imports` 跑上游源码，报告 **8 个文件 44 个错误**：`schedule_store.py` 16、`extension.py` 16、`prompts.py` 3、
`notification_render.py` 3、`ui/viewer.py` 2、`agents_menu.py` 2、`fork.py` 1、
`ui/controller.py` 1——按代码分：`no-untyped-def` 14、`arg-type` 11、
`no-untyped-call` 6、`type-arg` 5、`no-any-return` 3、`union-attr` 2、
`assignment`/`unused-ignore`/`attr-defined` 各 1。

44 个全部作为本次移植的一部分修复。不加任何每模块 `strict = false` 覆盖，移植不留新的豁免。

## 全量拷贝后的落地状态

十三个模块加上 `ui/` 位于 `extensions/builtins/subagents/`：`cron`、
`settings`、`schedule_store`、`schedule`、`worktree`、`group_join`、`memory`、
`agents`、`prompts`、`fork`、`output_file`、`notification_render`、`agents_menu`、
`extension`、`ui/{__init__,controller,strip,viewer}`。最后五个以纯拷贝加机械改名（模块路径、`BaldricPaths`、
`BALDRIC_DARK_THEME`、`BaldricTuiApp`、`baldric-agent-`、`.baldric/`）到达，然后下面的冲突被逐一解决，每次对照一个声明的类型而非判断：加载器调用点的 `BaldricPaths` 与 `project_trusted`、
需要 paths 的 `resolve_store_path`、观察事件的 `CodingSessionEvent`
（`session.py:3227`）、存储协议的 `append_batch`（`storage.py:36`）、
block-list 消息与工具内容、宿主的 `ThinkingLevel` 参数、
渲染器必须返回文本的契约、用 `isinstance` 替代 `getattr` 角色检查以收窄联合、菜单协议的 `Literal` notify 级别，以及宿主的工具/命令 handler 签名。

回退都有记录，因为第一版是错的。关于 settings 合并顺序、memory prompt 路径、
静默 frontmatter 回退、尽力而为的 worktree 清理、被吞的
transcript 写错误与锁文件删除的"原始缺陷"主张全部是误判：
对应测试把这些行为断言为预期，或代码注释如此说明。每一处都回退为原形，
`group_join.py` 与 `schedule.py` 中的本地协议在 `extension.py` 出现并为真实运行记录命名后消失。

拷贝提交时的检查：mypy 处于其 14 错 `fcntl` 基线且 `subagents` 零错误、
`ruff check` 与 `ruff format --check` 干净，套件 2238 通过 / 119 跳过——与拷贝前相同，因为这些代码还没有被测试覆盖。

还剩什么：能力本身无事——它声明在
`built_in_extensions` 中并随每个 session 加载，assistant 可以自行委托，`/agents` 打开舰队。面向用户的文档页未动，那是产品文案，不是移植后果。

一个环境注记：一次全量套件运行在既有 TUI 测试中零 CPU 卡死，不得不杀掉。单独重跑该组（672 通过）与全量（2238 通过，134s）都未复现。这些模块没有被任何测试导入，本移植不是原因；保持原样不追。

## 套件就位后的完整再比对

在完成的树上重复该方法：每个文件归一化回源命名并逐 hunk diff——1867 行 diff、17 个文件 207 个 hunk（`ui/__init__.py` 完全一致）。每个 hunk 三选一定性，且必须可追溯到声明的类型、测试断言或基线树。

因宿主强制而保留：每个加载器处的 `BaldricPaths` 与信任旗标、基于 home 的 schedule 位置、session 组件上的 `validate_session_id`、观察事件的 `CodingSessionEvent`、存储协议的
`append_batch`、消息与工具结果的 block-list 内容、
`_int_field`（`JSONValue` 联合不能交给 `int()`）、类型化的渲染器与 handler 签名、
包住 `render_notification` 的必须返回文本适配器、以 `isinstance` 替代角色字符串测试，以及取自 provider 选择分支的 thinking 级别。

复查后回退，分四次变更：fork 的 thinking 级别恢复为可选（没有东西强制它，缺失有含义）、未知 schedule patch 键恢复为抛错而非过滤、
settings 读取只捕获 decode 错误而非所有 `ValueError`、通知卡以原始转换读取文本字段而非一个把非文本值清空的 helper。record loader 上的豁免注释也删了，所以本移植仍不加豁免。

作为有意简化保留：`load_available_skills` 被删除，因为它在这里恰好只有一个调用者、没有外部消费者；大量换行差异是本项目格式化器在 110 列下的产物——没有语句变化。

不是缺陷但值得记录：从源继承的注释仍点名它遵循的协议家族（指向此处不存在文档的"matching pi"、"pi parity"、"ADR 0003"式引用已移除）。
这些注释解释行为为何如此，所以保持原样，不为整洁而擦除。

本环境中两次测试侧的偶发观察，均不可复现：一次全量运行在既有 TUI 测试中零 CPU 卡死；一次移植套件运行在一个独立运行必过的 viewer 挂载检查上 `assert False is True`，两两组合、再两次全量（236 通过 ×2）都过。均记录而不追查。

第三起事故发生在该能力默认加载之后，表现相同：`test_tui_app.py` 里一个 Textual 用例失败，下一次全量运行同一文件里*另一个*用例失败而第一个通过。单独运行时失败用例五次全过，整个文件两次通过（457），文件加两个最重的新套件也通过（540）。可能起作用的机制在代码里核实过而非推断：舰队 interceptor 在没有运行挂载时不消费键直接返回
（`if strip is None or not strip.has_agents(): return False`），未 spawn 时普通方向键处理不受影响。
