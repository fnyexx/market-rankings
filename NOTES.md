# 执行笔记

## 目标

做一个 OKX 永续合约行情排行榜 Web 程序，使用 SQLite 作为本地数据库，提供 Web 页面和无需鉴权的外部 API。

排行榜分两类：

排行榜只保留涨跌幅排行榜：统计 `1h`、`2h`、`4h`、`12h`、`24h` 的涨跌幅。
主流币模块单独统计配置合约的 `1m`、`5m`、`15m`、`30m` 分钟级涨跌幅。

## 总体架构

系统分三层：

- 采集层：获取 OKX 永续合约列表和 1H K 线。
- 计算层：每 10 分钟基于本地 K 线池计算排行榜。
- 查询层：提供 Web 页面和 JSON API。
主流币模块使用独立 1m K 线池和独立排行榜表，默认每 10 秒刷新一次。

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
funding_enabled: true
ws_reconnect_initial_seconds: 5
ws_reconnect_max_seconds: 60
major_coin_inst_ids:
  - BTC-USDT-SWAP
  - ETH-USDT-SWAP
  - SOL-USDT-SWAP
major_coin_poll_interval_seconds: 10
major_coin_candles_limit: 30
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
- `volume_quote`：当前窗口内的成交额，单位为计价货币
- `avg_hourly_volume_quote`：当前窗口内的 1 小时平均成交额，单位为计价货币
- `open_price`
- `close_price`
- `start_ts`
- `end_ts`
- `calculated_at`

### major_coin_candles_1m

保存主流币模块的 1m K 线池，字段与 `candles_1h` 一致，但数据表独立。

### major_coin_rankings

保存主流币分钟级排行榜：

- `metric`：固定为 `pct_change`
- `window`：`1m`、`5m`、`15m`、`30m`
- `inst_id`
- `direction`
- `pct_change`
- `volume_quote`
- `avg_minute_volume_quote`
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

## 主流币分钟级模块

主流币模块独立于全币种 1H 涨跌幅模块：

- 配置项 `major_coin_inst_ids` 指定要采集的 OKX 合约 ID，可配置多个。
- 配置项 `major_coin_poll_interval_seconds` 控制轮询间隔，当前默认 `10` 秒。
- 配置项 `major_coin_candles_limit` 控制每个合约每次拉取的 1m K 线数量，当前默认 `30` 条。
- 后台任务入口为 `major_coin_loop()`，在 FastAPI 启动时与全币种采集、排行计算、资金费率刷新任务一起启动。
- 行情接口使用 OKX `GET /api/v5/market/candles`，参数为 `bar=1m`。
- 数据写入 `major_coin_candles_1m`，排行写入 `major_coin_rankings`，不复用全币种 `candles_1h` 和 `rankings`。
- 计算窗口为 `1m`、`5m`、`15m`、`30m`。
- 分钟级排行使用最近 N 条本地 1m K 线参与计算，包含当前正在形成的最新分钟 K 线；这是为了让 `30m` 在每次只拉取 30 条时可以实时出结果。
- 页面和 API 不展示资金费率、结算周期、资金费时间等字段。

主流币页面展示字段：

- 排名
- 合约
- 方向
- 涨跌幅
- 成交额 USDT
- 1m 平均成交额 USDT
- 开始价
- 最新价
- 计算时间

## Web 页面

当前页面：

- `/`：统一排行榜页面。
- 页面顶部菜单：涨跌幅、主流币、K 线数据、API 文档。
- `/rankings/change` 保留为兼容入口，仍渲染同一个页面。
- `/rankings/major-coins`：主流币分钟级涨跌幅页面。

页面能力：

- 时间窗口切换：`1h`、`2h`、`4h`、`12h`、`24h`
- 表头排序
- 合约搜索
- 自动刷新
- K 线数据菜单默认选择 `BTC-USDT-SWAP`，只有选中合约后才查询本地 K 线数据
- 排行榜展示窗口成交额、1 小时平均成交额、资金费率、结算周期、当次结算时间、下次结算时间
- 排行榜标题区域展示当前窗口下所有币种的多方、空方、合计数量，计数由后端统计，不受页面 `limit=200` 限制
- 主流币页面支持分钟窗口切换、表头排序、合约搜索和 10 秒自动刷新。

## API

```text
GET /api/rankings/change?window=24h&limit=50&direction=long&sort_by_funding_rate=true
GET /api/major-coins/rankings/change?window=30m&limit=50
GET /api/major-coins/candles?inst_id=BTC-USDT-SWAP&limit=30
GET /api/instruments?query=BTC&limit=50
GET /api/candles?inst_id=BTC-USDT-SWAP&limit=100
```

参数：

- `window`：`1h`、`2h`、`4h`、`12h`、`24h`
- 主流币 `window`：`1m`、`5m`、`15m`、`30m`
- `limit`：返回数量，范围 `1` 到 `500`
- `direction`：多空方向，可选 `long`、`short`；不传则返回全部方向
- `sort_by_funding_rate`：是否按资金费率绝对值从高到低排序
- `sort_by_funding_time`：是否按当次资金费结算时间从近到远排序；若两个排序参数都为 `true`，优先按当次结算时间排序
- `query`：合约搜索关键词，用于合约列表接口
- `inst_id`：OKX 合约 ID，用于 K 线查询接口

## 2026-05-16 变更记录

- 新增涨跌幅排行榜成交额字段：`volume_quote`。
- 新增涨跌幅排行榜 1 小时平均成交额字段：`avg_hourly_volume_quote`。
- 新增主流币分钟级涨跌幅模块，配置项为 `major_coin_inst_ids`、`major_coin_poll_interval_seconds`、`major_coin_candles_limit`。
- 新增主流币独立数据表 `major_coin_candles_1m` 和 `major_coin_rankings`。
- 新增主流币页面 `/rankings/major-coins`。
- 新增主流币 API：`/api/major-coins/rankings/change` 和 `/api/major-coins/candles`。
- 将 OKX K 线客户端抽成通用 `get_candles(inst_id, bar, limit)`，原 1H K 线采集继续复用该方法。
- 新增 `funding_enabled` 配置项，用于控制资金费率后台刷新任务是否启动；关闭后 API 仍返回历史资金费率字段，但不再主动更新。

## 后续优化

- 增加 `/api/health`。
- 增加采集状态接口，展示合约数量、最后更新时间、最近错误。
- 增加日志文件输出。
- 增加 K 线池清理任务，只保留必要历史数据。
- 增加 Dockerfile 和部署说明。
