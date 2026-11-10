# SOCKS 代理支持

Baldric 用 `httpx` 发起 provider 请求、OAuth token 刷新与启动更新检查。`httpx` 读取标准代理环境变量，如 `HTTP_PROXY`、`HTTPS_PROXY`、`ALL_PROXY` 与 `NO_PROXY`。

## 变更了什么

Issue #221 报告环境含通用 SOCKS 代理 URL 时失败，例如：

```bash
ALL_PROXY=socks://127.0.0.1:1080
```

`httpx` 不接受通用 `socks://` scheme。它接受 `socks5://`、`socks5h://` 这类显式 SOCKS scheme，且它们需要可选的 SOCKS 依赖。

Baldric 现在：

- 在基础包安装 `httpx[socks]`，使 `socksio` 可用；
- 在构建 Baldric 自有的 HTTP 客户端之前把 `socks://...` 归一化为 `socks5://...`；
- 把 provider 客户端、OAuth token 刷新客户端与更新检查抓取都路由经 `baldric_ai.http` 的共享 helper。

## 为什么 `socks://` 映射到 `socks5://`

通用 scheme 没有说明 DNS 解析应当本地做还是经代理做。Baldric 把它当作本地 DNS 解析的 SOCKS5，因为那是最接近的显式 `httpx` scheme，且除了让原本非法的 URL 可用之外，不静默改变 DNS 行为。

需要代理侧 DNS 解析的用户应设显式的 `socks5h://` URL。

## 未来改进：避免临时环境改动

当前 helper 在构建 Baldric 自有 `httpx` 客户端时临时归一化代理环境变量。对同步更新检查 helper，归一化目前包裹整个 `httpx.get(...)` 调用，因为 `httpx.get` 内部构建并使用短命客户端。

对当前低并发的启动更新检查路径可以接受，但环境变量是进程全局状态。若 Baldric 以后在这个 helper 周围做更多并发网络操作，另一线程或任务可能在请求进行中观察到归一化后的代理值。

若成为顾虑，优先在执行请求时避免改动进程环境：

1. 把代理值归一化进局部数据；
2. 以等价代理配置构建显式 `httpx.Client` 或 `httpx.AsyncClient`；
3. 经该客户端发起请求，请求执行期间不改 `os.environ`。

实现时要保留 `NO_PROXY` 语义。`httpx` 目前在内部处理环境代理发现与 no-proxy 匹配，用显式 mounts/代理配置替换它时应包含以下测试：

- `ALL_PROXY=socks://...` 归一化；
- `HTTP_PROXY` 与 `HTTPS_PROXY` 处理；
- 小写代理环境变量；
- `NO_PROXY=*` 旁路；
- 主机/域名/IP 的 `NO_PROXY` 条目；
- 显式 `socks5://` 与 `socks5h://` 值保持不变。
