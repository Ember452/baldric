# 启动更新检查

Baldric 现在在启动产品体验的 CLI 路径——Textual TUI 与 text print mode——做一次小的、尽力而为的更新检查。

## 加了什么

- `baldric_coding.update.check` 抓取已发布包（`baldric`）的 PyPI 元数据。
- 版本用 `packaging.version.Version` 比较，PEP 440 版本排序正确。
- 结果缓存在 `~/.baldric/cache/update-check.json`，每天最多刷新一次。
- 失败是安静的 no-op：网络错误、畸形 JSON、缺失字段与非法版本都不阻止启动。
- 失败的抓取也被缓存（`"failed": true`）并在一小时后重试，离线启动不必每次都等 1.5 秒请求超时。
- `BALDRIC_NO_UPDATE_CHECK=1` 禁用检查；设了 `CI` 时自动跳过。
- `baldric update` 用拥有当前 Baldric 环境的包管理器升级 `baldric`。

## 为什么属于这里

它住在 `baldric_coding` 而不是 `baldric_agent`，因为更新通知是 CLI 应用行为。可复用的 agent harness 保持对 PyPI、Rich/Textual UI 事务与 Baldric home 目录布局独立。

## 输出策略

- TUI 启动把缓存的更新提示渲染为第一条 transcript 项，固定亮黄加粗样式，先于 release notes、provider 错误、主题诊断或 session 历史。
- TUI 绝不等 PyPI。`cached_update_notice` 只读缓存；检查到期时，应用在 mount 后于守护线程运行 `startup_update_notice`，解析后追加提示（agent 轮流式中以 toast 呈现）。守护线程让提前退出不必等请求。
- print mode 对正常文本输出把提示写到 stderr。
- 结构化 print 输出（`--mode json`）抑制提示，避免破坏脚本化输出。
- 工具命令（`baldric --version`、`baldric update`、`baldric sessions`、`baldric export`、`baldric providers`、`baldric setup`）不运行更新检查。

## 更新命令

`baldric update` 在运行任何东西之前检查活动环境：

- 有 `uv-receipt.toml` 表示 uv 拥有该工具。Baldric 抓取最新稳定 PyPI
  版本并运行 `uv tool install baldric@<latest-version>`，显式替换安装工具时记录的任何版本 pin。Windows 上，Baldric 把该命令移交给一个分离的 PowerShell 进程。helper 等原 Baldric PID 退出后才调用 uv，防止 Windows 部分替换仍在运行的工具环境。Baldric 报告更新**已排期**而非已完成，并给出包含最终
  命令输出与退出码的日志路径。helper 把进程检视或等待错误视为致命：除非确认原 Baldric 进程不存在或其观察到的进程对象已退出，uv 绝不启动。更新可执行文件与一条 Microsoft 运行时加引号的参数行以 base64 编码 JSON stage。helper 用非 shell 的 `ProcessStartInfo` 启动它们，在 Windows PowerShell 5.1 与 PowerShell 7 上保留空格、
  元字符、内嵌引号、空参数与尾随反斜杠，不经过插值 shell 执行。
- 有 `pipx_metadata.json` 表示 pipx 拥有它，Baldric 运行 `pipx upgrade baldric`。
- 发行版的标准 `INSTALLER` 元数据标识普通 uv 与 pip 安装。Baldric 运行 `uv pip install --python <current-python> --upgrade baldric` 或 `<current-python> -m pip install --upgrade baldric`，以正在运行 Baldric 的环境为目标。

所选命令失败时 Baldric 不会落到另一个安装器。直连 URL 与 editable 安装被打回其原始来源；Conda/Pixi 管理与无法识别的环境得到手工指引，而不是被 pip 擅自修改。editable checkout 安装可用 `uv tool install --editable --force .` 刷新。

## 测试

运行：

```bash
uv run pytest tests/test_updater.py tests/test_update_check.py tests/test_cli.py tests/test_tui_app.py
```

`tests/test_updater.py` 还含 Windows+PowerShell 专属的集成
覆盖。Windows 上它对活的 fake 父进程与 fake 更新器启动生成的 helper，检查阻塞、确切的可执行文件与参数送达、
退出码记录，以及 fail-closed 的等待错误——不安装 uv、不替换
Baldric。每个已安装的受支持引擎（`powershell.exe` 与 `pwsh.exe`）都被测试；不可用的引擎被省略，运行时测试只在两者都没有时跳过。跨平台测试覆盖 Windows 引号算法、
编码载荷、脚本生成、分离启动选项、staging 失败
与清理。当前 Ubuntu CI 无法执行 Windows 运行时用例。
