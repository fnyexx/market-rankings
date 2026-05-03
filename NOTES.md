# 执行笔记

## 目标

做一个 OKX 永续合约行情排行榜 Web 程序，使用 SQLite 作为本地数据库，提供 Web 页面和无需鉴权的外部 API。

排行榜分两类：

排行榜只保留涨跌幅排行榜：统计 `1h`、`2h`、`4h`、`12h`、`24h` 的涨跌幅。

## 总体架构

系统分三层：

- 采集层：获取 OKX 永续合约列表和 1H K 线。
- 计算层：每 10 分钟基于本地 K 线池计算排行榜。
- 查询层：提供 Web 页面和 JSON API。

## 配置方式

配置文件使用项目根目录的 `config.yaml`。

示例：

```yaml
host: 127.0.0.1
port: 8000
collector_mode: rest
quote_ccy: USDT
rest_requests_per_second: 2
ranking_interval_seconds: 600
ws_reconnect_initial_seconds: 5
ws_reconnect_max_seconds: 60
```

环境变量可以覆盖同名配置项，例如：

```powershell
$env:COLLECTOR_MODE = "websocket"
```

如果要使用其他配置文件，可以设置：

```powershell
$env:CONFIG_PATH = "D:\path\to\config.yaml"
```

## 采集模式

通过 `config.yaml` 切换：

```yaml
collector_mode: rest
```

或：

```yaml
collector_mode: websocket
```

### REST 模式

- 通过 OKX `GET /api/v5/public/instruments?instType=SWAP` 获取永续合约列表。
- 按 `quote_ccy` 过滤合约，默认 `USDT`。
- 循环请求每个合约的 1H K 线：

```text
GET /api/v5/market/candles?instId=BTC-USDT-SWAP&bar=1H&limit=25
```

- 默认限速为每秒 2 次请求。

### WebSocket 模式

- 使用 REST 获取合约列表，因为订阅 WebSocket 必须知道 `instId`。
- K 线数据只使用 WebSocket `candle1H`。
- 不使用 REST 拉历史 K 线。
- 新数据库刚启动时排行榜为空是预期行为。
- WebSocket 断线后自动重连。
- 每次重连都会重新获取合约列表并重新订阅。
- 重连等待时间从 `ws_reconnect_initial_seconds` 开始翻倍，最大不超过 `ws_reconnect_max_seconds`。

## SQLite 表

### instruments

保存 OKX 永续合约列表：

- `inst_id`
- `base_ccy`
- `quote_ccy`
- `settle_ccy`
- `state`
- `updated_at`
- `funding_rate`
- `funding_time`
- `next_funding_time`
- `funding_interval_hours`
- `funding_updated_at`

### candles_1h

保存 1H K 线池：

- `inst_id`
- `ts`
- `open`
- `high`
- `low`
- `close`
- `volume_contract`
- `volume_base`
- `volume_quote`
- `confirmed`
- `fetched_at`

主键：

```text
(inst_id, ts)
```

### rankings

保存计算后的排行榜：

- `metric`：固定为 `pct_change`
- `window`：`1h`、`2h`、`4h`、`12h`、`24h`
- `inst_id`
- `direction`：多空方向，`long` 表示多，`short` 表示空
- `pct_change`
- `abs_pct_change`：绝对涨跌幅，涨跌幅榜默认按这个字段排序
- `open_price`
- `close_price`
- `start_ts`
- `end_ts`
- `calculated_at`

## 排行榜计算

每 10 分钟执行一次，配置项：

```yaml
ranking_interval_seconds: 600
```

计算窗口：

```text
1h, 2h, 4h, 12h, 24h
```

涨跌幅公式：

```text
pct_change = (end_close - start_open) / start_open * 100
```

当前只使用 `confirmed = 1` 的已确认 K 线参与计算。

涨跌幅榜默认按绝对涨跌幅排序：

```text
ORDER BY ABS(pct_change) DESC
```

多空方向按涨跌幅判断：

```text
pct_change >= 0 => long
pct_change < 0  => short
```

## Web 页面

当前页面：

- `/`：统一排行榜页面。
- 页面顶部三个菜单：涨跌幅、K 线数据、API 文档。
- `/rankings/change` 保留为兼容入口，仍渲染同一个页面。

页面能力：

- 时间窗口切换：`1h`、`2h`、`4h`、`12h`、`24h`
- 表头排序
- 合约搜索
- 自动刷新
- K 线数据菜单默认选择 `BTC-USDT-SWAP`，只有选中合约后才查询本地 K 线数据
- 排行榜展示资金费率、结算周期、下次结算时间
- 排行榜标题区域展示当前窗口下所有币种的多方、空方、合计数量，计数由后端统计，不受页面 `limit=200` 限制

## API

```text
GET /api/rankings/change?window=24h&limit=50&direction=long&sort_by_funding_rate=true
GET /api/instruments?query=BTC&limit=50
GET /api/candles?inst_id=BTC-USDT-SWAP&limit=100
```

参数：

- `window`：`1h`、`2h`、`4h`、`12h`、`24h`
- `limit`：返回数量，范围 `1` 到 `500`
- `direction`：多空方向，可选 `long`、`short`；不传则返回全部方向
- `sort_by_funding_rate`：是否按资金费率绝对值从高到低排序
- `sort_by_next_funding_time`：是否按下次资金费结算时间从近到远排序；若两个排序参数都为 `true`，优先按下次结算时间排序
- `query`：合约搜索关键词，用于合约列表接口
- `inst_id`：OKX 合约 ID，用于 K 线查询接口

## 后续优化

- 增加 `/api/health`。
- 增加采集状态接口，展示合约数量、最后更新时间、最近错误。
- 增加日志文件输出。
- 增加 K 线池清理任务，只保留必要历史数据。
- 增加 Dockerfile 和部署说明。
