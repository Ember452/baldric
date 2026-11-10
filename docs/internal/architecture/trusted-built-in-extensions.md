# 受信任的隐藏内置 extension

## Phase 2 加了什么

Issue #606 加了一种通用方式，让 Baldric 运行打包进已安装包的 extension 代码。它不加 llama.cpp、启动 provider 准备、
`/local`、本地 backend API 或网络工作。

声明刻意很小：

```python
BuiltInExtension(name="capability", setup=setup, hidden=True)
```

声明住在 `baldric_coding.extensions.builtin_registry.BUILT_IN_EXTENSIONS`。
后续阶段可以往那个元组加产品能力，而无需教加载器它们的名字。Phase 2 的生产元组为空；确定性测试注入一个最小 fake 声明。

## built-in 为什么用 extension

打包的能力仍需要正常的生命周期与失败边界。如果它经私有的宿主分支注册工具、命令或 provider，reload 与来源清理就会与用户 extension 不同，每个能力都会让内核更 provider 专属。

改为让 built-in 接收普通的 `ExtensionAPI`。Phase 2 的 fake 证明一个 setup 函数可以注册：

- 一个 `AgentTool`；
- 一个 slash 命令；
- 一个 Phase 1 `DynamicProvider` 层。

真实 `ExtensionRuntime` 组合全部三者。不使用任何仅供测试的加载器旁路。

## 加载顺序

`ExtensionRuntime.load()` 先调用其每世代一次的内置加载器，再执行正常文件系统发现：

```text
trusted built-in declarations
→ user extension directory
→ explicit -e paths
→ trusted, opted-in project extension directory (later staged call)
```

实现 `--no-extensions` 的 `include_resource_dirs=False` 跳过用户
与项目目录发现，但不跳过 built-in 与显式路径。session 现在总是调用 `ExtensionRuntime.load()`，即使发现被禁用，built-in 也不会在该模式下意外消失。

项目 extension 仍是信任后的单独加载。built-in 是直接安装包内可调用物，不是文件系统候选，因此既不加受保护输入类别也不引发信任提示。只有当项目已有受保护输入时，它们才可使用既有的
信任前 hook；本阶段的 fake 不会。

## 来源与 hidden 元数据

文件系统发现现在把每个来源标为 `user`、`explicit` 或
`project`。built-in 用：

```text
source      = built-in
source_id   = built-in:<declaration name>
path        = None
hidden      = declaration.hidden
```

runtime 把它保留在不可变的 `ExtensionSourceMetadata`。宿主自有的
来源 ID（而非显示名）拥有工具、命令、handler 与 provider 层。

`extension_names` 仍是普通可见清单并省略隐藏
built-in。`extension_metadata` 是详细诊断视图，同时包含可见与隐藏来源。hidden 因此意为"不作为已安装/被发现的 extension 宣传"，绝不是"未加载"。

## 失败隔离

built-in setup 走与导入 extension 相同的 `_setup_extension()` 边界。runtime 创建一个来源范围的 API、记录来源，
然后同步调用 setup。setup 抛异常时：

1. 失败来源从活动 extension 元数据移除；
2. 其工具、命令、guideline、渲染器与 handler 被移除；
3. 其全部动态 provider 层与刷新工作被注销；
4. 保留一条 `built-in setup failed` extension 诊断；
5. 下一个声明与正常启动继续。

这让 built-in 失败可见，而不变成宿主启动失败。

## 世代与清理生命周期

每个 staged `ExtensionRuntime` 对声明元组做快照，并创建全新的 `ExtensionGeneration` 加 Phase 1 provider registry。同一 runtime 上重复 `load()`
不重跑 built-in setup；这很重要，因为项目 extension 在第二次信任后调用中加载。

reload、resume、new-session 与 cwd 替换本就 stage 全新 runtime。
因此每个都以全新 API 与 provider 世代重跑 built-in setup。旧 runtime 退役时：

- 退役并分离每个动态 provider 层；
- 请求取消自有 provider 刷新/发现工作；
- 使全部捕获的 API/context/UI 门面失效；
- 取消订阅 harness 监听器；
- 移除 extension handler、工具、命令、guideline 与渲染器；
- 丢弃绑定 session 与轮次请求回调。

替换代码在后继者把 UI 挂上共享桥之前清空旧宿主 UI。退役刻意不再清一次桥：在后继者的 `session_start` 之后清会抹掉新组件。最终 session 关闭没有后继者，因此它在退役 runtime 前清空 extension 组件。

异步 close 然后排水协作的 provider 工作或报告 Phase 1 的有界包容结果。测试启动一个 fake 内置 provider 刷新、退役 runtime，并断言取消、过期 API 拒绝、空来源元数据，以及工具、命令与 provider 的移除。

## 安全边界

"受信任"指代码经评审并随 Baldric 发布。它不意味着沙箱。与其他所有 extension 一样，built-in 在 Baldric 进程内执行 Python。hidden
状态只是显示元数据。项目信任仍是环境性项目输入守卫，不对 built-in、provider、工具、网络、文件系统、凭据或子进程设沙箱。

## Pi 对齐与 Baldric 的有意选择

这遵循 Pi 的隐藏打包 extension 模式与 reload 时的来源失效。Baldric 刻意保留自己的 cwd/信任绑定全新 runtime staging、
感知来源/世代的 Phase 1 provider registry 与详细元数据视图。
没有进程级全局 built-in runtime，加载器里也没有能力名分支。

## 怎么验证

聚焦确定性覆盖：

```bash
uv run pytest tests/test_extensions.py tests/test_extension_providers.py \
  tests/test_project_trust.py
```

测试覆盖声明校验、真实 runtime 注册、hidden/来源
元数据、加载顺序、`--no-extensions`、setup 一次行为、setup 回滚、
无信任提示、全新的 reload/new/resume 世代、过期 API 失效与 provider 任务退役。

全仓门仍是：

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv build
```
