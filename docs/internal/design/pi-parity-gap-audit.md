# Pi 对齐差距审计：孤儿命令与 RPC 分帧

一次评审标记了三个疑似与 Pi 的差距。每一项都先对照代码核实再动手；两项属实，一项需要修正范围。

## 1. 孤儿命令 handler

`_thinking_command`（`commands/config.py`）、`_context_command`
（`commands/resources.py`）与 `_help_command`（`commands/core.py`）已实现且有单测覆盖，但从未被导入或注册，因此 `/thinking`、`/context`、`/help` 表现为未知命令。

处置：

- **`/thinking` 已注册。** Pi 有它（`/thinking [level]`），handler
  处理状态、设置、模型不可用与非法级别四种情况，且 TUI
  已经消费 `CommandResult.thinking_level`。
- **`/context` 与 `/help` 保持不注册。** `test_non_pi_commands_are_not_registered`
  有意断言 `/provider`、`/resources`、`/context`、`/help` 不属于 Pi 对齐命令集。注册它们是偏离 Pi 的产品决策，不是修 bug。它们的 handler 仍是未用代码；移除是单独的清理，应随那个决策一起做。

## 2. 配置面

`settings.json`（`config/shell_config.py`）只有 `defaultProjectTrust`
与 `shellCommandPrefix`；`tui.json` 有键位、主题、侧栏
位置、通知模式、自动复制与编辑器命令。对照 Pi 的 settings/keybindings/models/auth 文件，把 `providers.json` 与凭据存储算上，覆盖面相当。真正的差距是 **MCP**：
Baldric 完全没有 MCP 客户端，因此没有 `mcp.json`——因为没有 MCP 支持。那是功能缺失，不是配置 schema 差异，超出对齐修复的范围。

## 3. Windows 上的 RPC 分帧

怀疑：Windows CRLF 会破坏 Pi 的字节级 LF 分帧，而测试只用内存流。先对照代码、再用真实文本流验证：

- **读侧本来安全。** `RpcServer.run` 先剥离尾部 `\n` 再剥离尾部 `\r`，CRLF 对端解析正确。
- **写侧不安全。** `stdout` 是 `newline=None` 的文本流，Windows 上 `payload + "\n"` 会写成 `\r\n`。字节级对端会看到协议未定义的回车符。
- **还存在第二个未上报的问题：** `_force_utf8_streams` 只重配 stdout/stderr，Windows 的 `stdin` 保持系统代码页，非 ASCII JSON 可能解码失败。

修复：`_configure_rpc_stream` 对两条流强制 UTF-8、输出强制 `newline="\n"`，在 `run()` 开头调用。没有 `reconfigure` 的流（测试替身）不动。

`tests/coding/cli/test_rpc_streams.py` 的新覆盖用平台默认（`newline=None`、`cp1252`）的 `TextIOWrapper` 包 `BytesIO` 复现两种行为。移除修复后 LF 测试被证明会失败，因此它守护行为而不只是走过场。
