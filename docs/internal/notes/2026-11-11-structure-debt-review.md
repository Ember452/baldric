# baldric_coding 逐行审读笔记（2026-11-09）

只读审读，不改 baldric 仓库。分支 design/tui-visual-system（ahead 22），工作树有 rendering/{diffs,theme_schema,themes} 未提交改动。

## 模块覆盖清单

- [x] __init__.py — 纯 re-export，无问题
- [x] events.py / events_dispatch.py / version.py — 干净
- [x] utils/ — atomic.py/self_docs.py 干净
- [x] config/ — paths.py/shell_config.py 干净
- [x] tools/（base, registry, bash, shell, write, edit, read, truncate, output_accumulator, image_processing）
- [x] trust/（approvals.py, policy.py）— 质量高；policy.py 日志式原子写+fail-closed 设计严谨
- [x] auth/（types, registry, credentials, oauth, flows/anthropic, flows/device, flows/github_copilot）
- [x] commands/（base, registry, core, config, resources, session, formatting）
- [x] context/（gitignore, project, resources, prompts, system_prompt, thinking, skills/skills）
- [x] backends/contracts.py（1276 行全读）
- [x] providers/ catalog.py, loader.py, runtime.py, config/（__init__, credentials, settings, catalog, models, selection, validation）
- [x] providers/stores/（models_dev, models_dev_store, codex_version, codex_model_store）
- [x] session/ 全部读完（含 usage.py 972 行、compaction/context_window.py、export/html.py 1846 行、writer、jsonl）

### session/ 补充（usage/compaction/export）
- usage.py：HTML dashboard，转义齐全，JS 自包含；estimated_request_cost 只查 builtin catalog（自定义 provider 回退 provider-reported cost，合理）。
- compaction/context_window.py：provider-anchored 估算+时间戳防陈旧 usage，逻辑严谨。增量摘要链路接通（_split_previous_compaction_summary 识别前缀）。
- export/html.py：XSS 防护到位（_escape/_attr 区分文本/属性，pygments nowrap 转义，base64 内嵌 JSONL）；_visible_export_entries 隐藏 display=False 条目并重挂父链。
- [P3·死代码] export/html.py:1496 `_render_list` 全仓无调用者。`default_session_export_path` 公开导出但无生产调用者（SDK 表面）。

### session/（核心链路接通，工程细节扎实；结构性问题突出）
**功能链路验证**：prompt→input hooks→expand（template/skill）→commit_preview→auto_compact→harness.prompt_message→with_auto_retry_events→persist_on_message_end（push 持久化）→reconcile（finally 兜底）→settled。overflow/HF-failover/tool-recovery 三条重试路径分离（AGENTS 声明刻意）。模型切换 candidate-first：先建 provider、写 ModelChangeEntry 成功后才同步赋值，失败关 candidate。trust staged→adopt commit。链路参数对应无误。
1. [P2·结构] session 包是"一个类拆九文件"：session.py 末尾 ~500 行纯委托方法；branching/lifecycle/runtime/model_selection/model_runtime 直接读写 CodingSession 20+ 私有属性；`_session_module()` 动态 import 破循环依赖（provider_helpers/lifecycle/runtime 各一份）。模块边界是名义上的，实为 partial class。拆分动机是 structure ratchet 文件大小门禁，不是内聚设计。
2. [P2·重导出样板] session.py/model_selection.py/lifecycle.py/runtime.py 四个文件各有 200-360 行 `import X as X` 重导出块（合计 ~1000 行），只为保住旧导入面（测试从这些模块 import 私有名）。同一常量 SESSION_NAME_SYSTEM_PROMPT/TREE_RUNNING_MESSAGE/StreamingBehavior 在 3-4 个文件重复定义，改一处会漂移。
3. [P2·测试接缝继续] model_selection.toggle_scoped_model:530 hasattr 分支注释明说 "narrowly supports lightweight host/test session doubles"；runtime._attach_persistence_listener:688 getattr 探测 subscribe 注释 "Command-only tests construct sessions with stub harnesses"。生产逻辑为测试替身分叉。
4. [已修复·2026-11-12 复核] [P3·绕过存储协议] resource_helpers._append_session_entry_sync:392 直接 open("a") 写 transcript，绕过 JsonlSessionStorage 的跨进程锁+torn-tail 修复+fsync；被 runtime._ensure_session_file_initialized:963 使用。崩溃留下断尾时此路径会把新行粘到坏行上。现实现改为委托 `storage.append_sync(entry)`（resource_helpers.py:391-398），锁/torn-tail/fsync 全部生效。
5. [P3·维护陷阱] lifecycle.resume:706-750 手工逐字段重建 CodingSessionConfig（~45 字段），_adopt_replacement:947-998 手工搬运 ~50 私有字段——新增字段必须记得同步两处，否则静默丢失（堵未来）。
6. [P3·死代码] prepare.SessionPreparationRequest 全仓无构造者。
7. [P4] 错误 docstring 复制粘贴："Persistent coding-session wrapper built on AgentHarness" 出现在六个不相干文件头。lifecycle.new_session:861-875 条件分支两边调用等价。_persist_thinking_level_choice 静默吞 ProviderConfigError。
8. 亮点：storage.py torn-tail 修复+缓存隔离；runtime._persist_message 幂等重试+O(1) tip 追加；_await_cleanup_completion shield containment；auto-name 绑定旧 provider 防串会话；stats 含 1h cache-write 分层计价。
9. usage.py（前半）：collect_session_usage 逻辑正确；注意它 import rendering.themes（session→rendering 方向允许）；estimated_request_cost 只查 BUILTIN catalog，自定义 provider 无估价（回退 provider-reported cost）——合理。

### providers/stores/
- 总体干净：缓存 schema 校验严格、account-scoped、ETag/304、BALDRIC_OFFLINE、先验证后落盘。
- [P3·重复加剧] 原子写 temp+replace 模式至此共 6 份变体（utils/atomic、loader、config/settings、models_dev_store、codex_version、codex_model_store），仅 utils 版带 fsync。应收敛到一个工具函数。
- [P4] BALDRIC_OFFLINE 以"变量存在"判断（空串也离线），两个 store 一致，属约定但无文档。

### providers/（config 子包问题较集中）
1. [P2·系统性测试接缝] `_provider_config_module()` 同一定义复制 4 份（settings/selection/credentials/catalog），生产调用路径绕道动态 import 包模块去取 environ/copy2/_write_provider_settings/save_user_catalog_entries，只为让测试 monkeypatch 包属性。config/__init__.py:5-6,45,60 四个 noqa F401 导入纯为测试存在（environ、copy2、_write_provider_settings、save_user_catalog_entries）。这是"为测试而写"的生产间接层，散布整个子包。
2. [P3·死代码] settings.py:389 `_EFFECTIVE_PROVIDER_CONFIGS` 声明后无任何使用（真正使用的同名缓存在 catalog.py:28）——复制残留。models.py:692 `_reject_unimplemented_thinking_config` 全仓无调用者（Codex thinking 已实现后的残留）。
3. [P3·重复实现] 原子写文本共 3 份：utils/atomic.py（带 fsync）、providers/loader.py:760、providers/config/settings.py:392（后两份几乎逐字相同、无 fsync）。credentials.py 还有第 4 种内联变体。同包内聚不足。
4. [P3·边界值] validation.py `_positive_float`/`_non_negative_float` 不拒绝 NaN/Infinity（nan<=0 为 False）；Python json.loads 默认接受 NaN/Infinity 字面量→providers.json 可注入 NaN timeout 直达 httpx。loader.py `_toml_value` 对 inf 输出 "inf" 非法 TOML（保存后再加载失败）。
5. [P3·持久化漏项] config/catalog.py:268 `_provider_definition_differs_from_catalog`：`getattr(provider,"api",None) != entry.api and entry.api is not None`——当 catalog entry.api 为 None 而用户设置了 api 时不算差异，仅改 api 的内置 provider 变更不会写入 catalog.toml，重载即丢。
6. [P4] selection.py `_thinking_format`:463-477 与 `_detected_compat`:190-234 重复同一套供应商启发式（前者 fallback 分支基本死）；config/catalog.py `_merge_anthropic_provider` 与 `_merge_openai_compatible_provider` 约 40 行近乎相同。models.py 三个 config dataclass 大量字段/验证重复（项目风格使然，可接受但维护面广）。
7. [P4] settings.py `upsert_provider:274` 丢弃返回值的 get_provider 调用当断言用，意图隐晦。loader.py save_user_catalog_entries 读-改-写无锁。
8. 亮点：runtime.py `_refresh_lock` 按事件循环缓存锁+锁内重读 store，注释记录了真实 refresh-token 竞态事故，工程严谨；resolve_startup_thinking_level 回退链清晰、CLI override 严格；validation.py 孤儿 preference 容错有注释有 rationale；schema v2 迁移路径完整（AGENTS.md 声明 load-bearing，确实在用）。

### backends/contracts.py（设计用心：generation 容器化、secret 擦除、有界 drain；但有两处实质问题）
1. [P2·为测试让步的生产代码] `_invoke`:1091-1110 docstring 明说 "accepting a no-context test double too"：用 inspect.signature 探测回调签名并按位置参数个数截断实参。后果：注册了错误签名的回调不会报错而是静默拿错参数——如 configure 只声明 (context) 一个参数时，`_invoke(configure, values, context)` 会把 values 当 context 传入。这正是"参数没对应上"的隐患，且动机是为了测试替身。
2. [P3·泄漏] `_run`:912-916 调用方被取消时 `await task` 抛 CancelledError，finally 把 operation 从 _operations 弹出，但内部 task 未被取消继续跑→脱离 registry 跟踪（retire/cancel 都够不到），成为孤儿任务。
3. [P4] `status()`:720-729 以 action="refresh" 注册运行槽：status 与 refresh 互踩（同键取消），backend 回调收到的 context.action 无法区分二者。LocalAction 集合里本来就没有 "status"。可能是刻意合并，但语义含混。
4. [P4] LocalConfigValues.__iter__ 用 type: ignore[no-untyped-def] 而非标注 Iterator[str]；effective/all_views 重复同一段 provider_layer_effective 计算。
- [ ] session/
- [x] extensions/ 核心：__init__, api.py(1350), loader.py(473), runtime.py(1476), providers.py(646), provider_registry.py(665), installer.py(428), builtin_registry.py(147)
- [x] extensions/builtins/ 全部：mcp/extension(307), subagents 18 文件全读（extension 1624、agents、settings、worktree、fork、group_join、memory、output_file、prompts、notification_format/render、cron、schedule、schedule_store、agents_menu、ui/controller+strip+viewer）, llama_cpp 5 文件全读（__init__、state 405、huggingface 211、router 331、service 1734）
- [x] modes/rpc（wire 271、session 120、server 455）, observability/（diagnostics 203、doctor 115、watchdog 114）, update/（check 419、reload 31、updater 387）
- [x] rendering/ 全部 16 文件（含工作树改动的 diffs/theme_schema/themes）
- [ ] tui/

### modes/rpc + observability + update
- rpc：协议完整。[P3] server._run_prompt 只捕获 RuntimeError/ValueError，存储 OSError 等会炸掉整个 task group；bash 响应硬编码 truncated=False（工具实际会截断，参数没传到位）；get_state isCompacting 硬编码 False。[P3] wire._tree_wire 递归 build，>1000 条单链会话 RecursionError（tree_helpers 已刻意非递归，这里没有）。
- observability：diagnostics 只抄 scalar 分类字段防泄密；watchdog monotonic+faulthandler 设计正确。无问题。
- update：installer 归属检测、Windows detached handoff argv quoting 正确。无问题。

### rendering/（当前分支改动区，总体质量高）
- diffs.py：hunk 计数器判定行类型（防 --/++ 内容行误判文件头）设计正确；word-level emphasis 偏移计算核对无误。_changed_word_ranges 每对行算两遍 SequenceMatcher（P4 性能）。
- theme_schema.py：引用解析带环检测；okhsl 移植有 ground-truth 测试钉住。无问题。
- themes/__init__.py：双格式解析、Rich+Textual 双重颜色校验、builtin shadow 拒绝。
- [P2·潜在崩溃] activity.py:_blend_hex_colors/_hex_to_rgb 假定 accent/screen_background 是 #rrggbb，但主题校验允许 Rich/Textual 颜色名（如 "red"）→ 合法自定义主题用命名色时 spinner 渲染 ValueError。
- [P2·待验证] tool_state.tool_row_role_style：schema 主题 role body 可省略→""，foreground=None 时拼出 "None on #144922" 非法样式串（需在 widgets 确认调用路径）。
- [P3·耦合] rendering.themes 模块级 import Textual（color/theme），而 session/usage.py、session/export 依赖它 → CodingSession 导入链拉入 Textual。门禁只查 baldric_coding.tui 包边界所以绿，但"print 模式不碰 Textual"的意图被绕过。themes 里数据层与 Textual 映射（textual_theme_for_tui_theme/theme_css_variables）应拆分。
- 其余（transcript/plain/json/tool_calls/grouping/thinking/tool_preview/widths/approval_card）干净；FAILED_STOP_REASONS 统一 exit code 语义有事故注释。

### extensions/builtins/
- mcp：薄胶水，trust gate 正确（未信任项目忽略 project mcp.json）；fire-and-forget start/toggle 任务无监督（P4）；_supervisor_factory 模块级测试注入（显式声明）。
- subagents：移植质量高，注释记录大量 pi 语义与事故修正。问题：
  1. [P2·链路缺口] extension._execute:575 `load_provider_settings()` 只读 durable 设置——父会话用动态 provider（如 llama.cpp）时子代理 resolve_provider_selection 报 Unknown provider；动态 provider 无法被 subagent 继承/指定。runtime model catalog（Codex live 模型）同样不继承。
  2. [P3·越界耦合] extension.py:765,772 直接改 `session._harness.config.tools`（noqa SLF001）——CodingSessionConfig.allowed_tool_names 就是为此设计的公开接缝，却绕私有属性。
  3. [P3·误导提示] prompts.py SUB_AGENT_BRIDGE 指示用 find/grep 工具——Baldric 默认工具集没有这两个工具（pi 移植残留）；"parallel tool calls" 也不被 loop 支持（execution_mode parallel 未实现）。
  4. [P4] get_subagent_result wait=True 忽略 signal（del signal），纯 50ms 轮询无超时（Esc 硬取消可兜底）；agents_menu options.index(choice) 相同描述的行会选错 run；_MemoryStorage 重复实现 InMemorySessionStorage；schedule_store PID 锁 stale-takeover 有 TOCTOU 竞态（上游同款）。
- llama_cpp：事务式 configure（credential 先写、state 失败回滚删 credential）、router build 范围门禁、取消后 reconcile 不重放 mutation、stale selected model 保留引用不静默替换。质量高，无重大问题。state.py 是第 7 份锁+原子写变体（带 fsync/权限，合理但应收敛公共 helper）。

### extensions/ 核心（全读，质量最高的子系统之一）
- api.py：generation staleness guard 全覆盖、API_VERSION 拒绝不匹配、capabilities 声明、Textual 仅 TYPE_CHECKING。设计纪律强。
- runtime.py：setup 失败进 shutdown-only roster 防资源孤儿；renderer 失败每类型只诊断一次；tool_call hook 失败 fail-safe 阻塞工具；live tool 注册与 compose 同形包装。_runtime_diagnostics 无上限（炽热事件反复失败会膨胀，P4）。
- providers.py：scoped credential reader + provider-id 归属校验 + Authorization 头拒绝 + repr 排除秘密 + 深冻结 JSON——扩展拿不到别人的密钥。无问题。
- provider_registry.py：禁止动态层 shadow 内置/durable id（防凭据劫持）；refresh coalesce+shield+bounded containment；诊断 categorical 不含 exc 文本（防泄密）。无问题。
- loader.py：source identity 先冻结后 import；sys.modules 卸载只碰自己前缀。无问题。
- [P3·installer] update_extension:262-273 用 rev-parse HEAD 对比 recorded commit 判定"local modifications"——未提交的工作区修改检测不到，update 会静默丢弃用户未提交编辑（docstring 承诺保护）。应查 git status/diff。
- [P4·陈旧注释] api.py InputEvent docstring 称 "Baldric has no RPC mode"（modes/rpc 已存在）；loader.extension_dirs docstring 称 trust store 尚不存在（已存在）。
- [x] modes/rpc（wire/session/server 全读）
- [x] observability/（diagnostics/doctor/watchdog 全读）
- [x] rendering/ 全部 16 文件（含工作树改动的 diffs/theme_schema/themes）
- [x] tui/ 全部（app 4557、state 1055、widgets 全部、screens 全部 15 文件、mixins、adapter 等）
- [x] update/（check/reload/updater 全读）
- [x] cli.py（1539 行全读）
- [x] data/examples/extensions 4 示例全读；1 行 __init__ 经 grep 确认仅 docstring
- [x] 横切检查（死代码/测试钩子/参数对应）——完成，见下

### tui/ + cli.py 发现
1. [已修复·2026-11-12 复核] [P1·实质 bug] app.py `_replace_tui_settings`:2493-2501 重建 TuiSettings 只复制 keybindings/theme/auto_copy_selection/sidebar_position/turn_notification，丢掉 editor_command 和 approval_mode。/theme 换主题→approval_mode 静默重置为 "auto"（关闭审批！）且 editor_command 清空，随后 save_tui_settings 持久化。安全设置被视觉操作悄悄关掉。现实现用 `dataclasses.replace`（app.py:2507-2514），docstring 记录了该事故。
2. [已修复·2026-11-12 复核] [P2·潜在崩溃] rendering/activity.py `_hex_to_rgb` 只认 #rrggbb，但 themes 校验允许命名色（"red" 合法）→ 命名 accent 的自定义主题在运行中 spinner ValueError。现实现改用 `Color.parse` 解析命名色与 hex（activity.py:91-99）。
3. [已修复·2026-11-12 复核] [P2·潜在崩溃] rendering/tool_state.tool_row_role_style：schema 主题 roles.tool.body 可省略→""，foreground=None 拼出 "None on #144922" 非法样式；widgets/core._chat_item_role_style:1507 确认调用路径。现实现显式处理空 body/无 foreground 分支（tool_state.py:72-80）。
4. [P3] app.py action_open_external_editor:2970-2972：PromptInput.cursor_position 是扁平 int 偏移，却赋 end_location[1]（列号）→多行文本编辑后光标错位；text_utils.text_end_location 对以 \n 开头文本行号少 1。
5. [P3] screens/login.py OAuthLoginScreen._select_option:643-645 静默选第一个选项，多账号场景用户无选择机会。
6. [P3] cli.py run_openai_rpc_mode 直接 CodingSession.load（非 prepare 候选优先）；只关 provider 不关 session（依赖 RpcServer.run 内部 aclose，run 前段抛错时 session 泄漏）。
7. [P2·结构] tui 同样"一个类拆多文件"：三个 Mixin 用 self: Any 读 app 私有状态；widgets/__init__.py 592 行重导出 ~150 私有名（__all__ 有重复项）；app.py 头部 ~370 行兼容 re-export；_app_module()/_widgets_package() 动态 import 测试接缝。
8. [P4] 十余个文件头 docstring 复制粘贴错误（"Minimal Textual app..."）；多处 `if TYPE_CHECKING: pass` 空块；core._render_chat_body:1794-1796 两分支相同；_MemorySessionStorage 三重重复（cli/session.storage/subagents）；_format_bytes 两处重复；PromptTemplatePicker 复用 SessionPickerSearchInput 靠 duck-typing cast。
9. 亮点：transcript DOM 窗口化+分页锚点、markdown 合帧、git branch 后台缓存、sidebar 编辑器快照冲突检测、approval fail-closed、扩展组件 quarantine、乐观 user 消息对账。

## 发现（详细）

### tools/（总体质量好，问题小）
1. [P3] tools/registry.py:5 `import asyncio  # noqa: F401 - tests monkeypatch this module's asyncio.to_thread`：纯为测试存在的生产导入。测试 monkeypatch 的是全局 asyncio 模块对象，测试自己 import asyncio 即可，生产代码此导入是死导入。
2. [P2·潜在] tools/truncate.py:96-120 `_truncation_result` 把 max_lines/max_bytes 硬编码为默认常量进元数据，忽略调用方自定义值。一旦未来有调用方传自定义限额，TruncationResult 元数据会撒谎。参数没接到位的隐患。
3. [P3] tools/base.py:138 `_file_locks` 只增不减，长会话内存缓慢增长。
4. [P3] tools/bash.py:219-226 超时/取消后 kill 再 `await communicate` 无截止时间：Windows taskkill 静默失败时可能无限挂起。
5. [P3] tools/read.py:120 `assert image_family is not None` 依赖跨函数隐式契约，-O 下被剥离。
6. [P3] output_accumulator.py delete=False 临时全量输出文件从不清理。
7. [P4] write.py utf-8-sig 读旧文件剥 BOM、无 BOM 写回（edit.py 保留 BOM，不一致）。edit.py ndiff 算两遍。image_processing.py:41 JXL 魔数依据存疑（无实际误伤）。

### trust/
- approvals.py：Always 规则精确匹配、复合命令永不自动批准——设计正确。policy.py：fail-closed 日志协议、规范路径校验、Windows/msvcrt+POSIX/fcntl 双锁，质量高。无重大问题。
- [P4] policy.py:134 fcntl 魔数 50 (F_GETPATH) 硬编码有注释，可接受。

### auth/（总体扎实，个别问题）
1. [已修复·2026-11-12 复核] [P2·安全不一致] auth/oauth.py:375-381 `_required_token_field` 失败时 dumps(raw) 把整个响应放进错误消息——若响应缺 access_token 但含 refresh_token，refresh token 会进日志/TUI。flows/anthropic.py:177-198 专门做了 secret 擦除，Codex 路径没做，同包标准不一致。_token_expiry:397,402 同样。现实现只报字段名不报响应体（oauth.py:378-384），_token_expiry 同样已擦除（oauth.py:399-401）。
2. [P3·设计存疑] flows/anthropic.py:65,69 state=verifier：PKCE verifier 放进公开授权 URL（上游 Claude Code 如此，忠实移植但值得知晓）。
3. [P3] flows/anthropic.py:222 `_wait_for_input(server: Any)` 放弃类型（无循环导入障碍）。
4. [P3·竞态] oauth.py:474-475 服务器线程 future.done() 检查与 call_soon_threadsafe 有窗口竞态 → InvalidStateError。
5. [P3·阻塞] _LocalOAuthServer.close() 在 async 上下文同步调 shutdown()（至多 ~0.5s 阻塞事件循环）。
6. [P3] credentials.py 读-改-写全文件无锁（对照 trust.json 有锁+日志）；并发 set 丢更新。
7. [P4] set_api_key 仅测试使用的 set 别名。device.py 取消 task 不 await 可能留 pending-task 告警。
8. 备注：github_copilot expires=1 临时凭证强制 refresh——刻意，链路通。

### commands/ + context/
1. [P2·死代码链] commands/session.py:70 `_format_sessions` 无调用者；formatting.py:12 `_format_session_record` 因此也死（grep 全仓确认）。
2. [P2·双实现漂移] system_prompt.py 同一 XML 包装两套实现：format_project_context:255（公开导出但生产无调用者，仅 test_public_surface 钉住）vs 实际组 prompt 的 _project_context_sources:275，空白行处理已不同。format_skills_for_prompt:340 与 _skill_sources:300 平行，前者被 tui/widgets/sidebar.py:289 用于预览——预览与真实 prompt 可能不一致。
3. [P3·API 行为分裂] load_prompt_templates 无诊断版遇 warning 级诊断（reserved 名）直接 raise（prompts.py:242-247 不分 severity）；load_skills 对应版只抛非 info（skills.py:161-170）。口径不一致。
4. [P3·gitignore 语义] gitignore.py:79-80 剥掉根锚定前导斜杠→任意深度匹配（过度忽略）；! 否定规则静默丢弃；lru_cache 永不失效。仅用于 tui/autocomplete 补全，非安全边界，但语义错。
5. [P3·耦合] context/project.py:53 跨模块调 paths._paths() 私有方法。
6. [P4] skills.py format_skill_invocation:122 不转义 name/path 引号，含引号名字破坏 parse_skill_invocation 往返。resources.py parse_markdown_resource:336 find("\n---") 会误匹配 \n---- 等。
7. [P4] commands/config.py _theme_command 注释说懒导入避免拉 tui，实际导入 rendering.themes（待查是否间接拉 Textual）。_status_command getattr 探测协议外属性，隐式契约。
8. [P4·疑似死代码] build_skill_index 生产无调用者（仅测试+公开表面钉住），docstring 自称 "for future system prompt assembly"。
9. 备注：thinking.py 干净。/skill: 链路：registry 短路→lifecycle.py:1145 expand_skill_command→state.py:601 parse_skill_invocation，接通。