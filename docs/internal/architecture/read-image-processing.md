# 有界的 read 图片处理

## 加了什么

`read` 工具现在在附加图片前用 Pillow 校验图片字节。它
接受从文件内容识别的 JPEG、静态 PNG、GIF、WebP 与 BMP。BMP
归一化为 PNG，因为 provider API 对 BMP 的接受度不一致。任一边超过 2,000 像素或 5 MB 的图片会被缩放并重新编码；宽高比保留，小图绝不放大。

处理有明确上限：

- 源编码：50 MB
- 源尺寸：4000 万像素
- 输出尺寸：最大 2,000 × 2,000
- 输出编码：5 MB
- 图片头嗅探：加载超大本地文件前 64 KB
- 缩放/编码尝试：12 次

选 Pillow 是因为它持续维护跨平台 wheel、支持所需格式，并暴露解码校验与解压炸弹警告。Baldric 把那些警告与解码/编码失败转为纯文本
工具结果。在 Pillow 元数据 API 允许处，上限在加载像素数据之前检查。对默认本地操作，超过 50 MB 的文件从 64 KB 前缀分类，已知图片家族在读完整个文件前被拒。大文本文件保留既有 read 行为。

`ReadOperations` 把路径校验与字节读取同工具的分类与处理分开。可选的大小与前缀回调启用提前的图片拒绝；省略它们的实现保留全量读取回退。默认仍是本地文件系统。测试可以提供 fake 操作，未来的远程文件系统集成也可以，而不必把本地 I/O 挪进 `baldric_agent`。

## 为什么存在

第一版多模态实现正确地在 agent 与 provider 层传递规范 `ImageContent`，但拒绝每个超过 5 MB 的附件并信任浅层签名。真实截图与相机图片可能超过 provider 限制却很容易缩放。畸形或超大解码图片也需要可预测的失败行为。

这遵循 Pi 的分离：coding 专属的文件/图片工作发生在 read 工具边界，`baldric_agent` 存 provider 中立内容，`baldric_ai`
做序列化。Baldric 把共享能力 helper 保留在
`baldric_ai/content.py`；provider 适配器仍拥有各自 wire 特定的安放位置，因为工具结果图片的安放因 API 而异。

## 产品与交付决策

1. 已经安全的受支持字节保留原样。避免质量损失并保留受支持的 GIF/WebP 动画。
2. BMP 转 PNG，超大的静态图片缩放。超限的动画图片被省略，而不是悄悄压成单帧。动画 PNG 与 JPEG XL 输入收到明确的不支持格式提示，而不是落到 UTF-8 解码。
3. `ImageContent` 里只保留一份变换后载荷。原始字节与 base64 不拷贝进工具 `details` 或 session JSONL。
4. 在 `CodingSession` 与内置 `read` 工具之间共享可变的图片能力状态。纯文本模型在图片处理前收到强提示，模型变更就地更新该状态。provider 适配器对旧 session 与其他工具保留同样的防御性降级。
5. 把变换注记返回给模型，让它知道尺寸或编码何时变了。
6. 终端图片渲染不进范围。Textual 没有与 Pi 终端图片协议渲染器等价的内置物，所以 TUI 继续显示文字状态。自定义组件或第三方集成可以另行评估，不改工具结果契约。
7. 活动凭据检查留在 CI 之外。`TODO.md` 保留 provider/model 校验矩阵的后续。

## 怎么测试

聚焦行为：

```bash
uv run pytest tests/test_image_processing.py tests/test_coding_tools.py
```

全量验证：

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv build
```

手动验证应读一张小图、一张 BMP 和一张超过 2,000 像素的静态图片（配视觉模型）。确认模型看到每张图，BMP 被报告为已转换，大图报告其缩放后尺寸。
