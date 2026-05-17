# Market Rankings

OKX 永续合约行情排行榜 Web 程序。程序使用 SQLite 保存 1H K 线池，并计算 `1h`、`2h`、`4h`、`12h`、`24h` 的涨跌幅排行榜。

## 运行

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python run.py
```

打开：

- http://127.0.0.1:8000/

主页面有三个菜单：

- 涨跌幅
- 主流币
- K 线数据
- API 文档

兼容入口仍保留，并渲染同一个页面：

- http://127.0.0.1:8000/rankings/change

主流币分钟级涨跌幅页面：

- http://127.0.0.1:8000/rankings/major-coins

## 配置

配置文件使用项目根目录的 [config.yaml](D:/work_space/git/market-rankings/config.yaml)。

常用配置：

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

如需使用其他配置文件，可设置：

```powershell
$env:CONFIG_PATH = "D:\path\to\config.yaml"
```

环境变量仍可覆盖同名配置项，例如：

```powershell
$env:COLLECTOR_MODE = "websocket"
```

## 采集模式

### REST 模式

在 `config.yaml` 中设置：

```yaml
collector_mode: rest
```

REST 模式会：

- 通过 OKX REST 接口获取永续合约列表。
- 按 `quote_ccy` 过滤合约，默认 `USDT`。
- 按配置限速循环拉取每个合约最近 25 条 `1H` K 线。

### WebSocket 模式

在 `config.yaml` 中设置：

```yaml
collector_mode: websocket
```

WebSocket 模式会：

- 使用 REST 接口获取合约列表，因为订阅需要 `instId`。
- K 线数据只使用 WebSocket `candle1H` 推送。
- 不使用 REST 补历史 K 线。
- 新数据库刚启动时排行榜可能为空，需要等 WebSocket 数据自然积累。
- 断线后自动重连，每次重连会重新获取合约列表并重新订阅。

重连配置：

```yaml
ws_reconnect_initial_seconds: 5
ws_reconnect_max_seconds: 60
```

## API

涨跌幅排行榜：

```text
GET /api/rankings/change?window=24h&limit=50&direction=long&sort_by_funding_rate=true
```

合约列表：

```text
GET /api/instruments?query=BTC&limit=50
```

K 线数据：

```text
GET /api/candles?inst_id=BTC-USDT-SWAP&limit=100
```

K 线接口会按每根 K 线额外返回：

- `price_change`：涨跌额，`close - open`
- `pct_change`：涨跌幅，`(close - open) / open * 100`
- `amplitude`：振幅，`(high - low) / open * 100`

主流币分钟级涨跌幅：

```text
GET /api/major-coins/rankings/change?window=30m&limit=50
GET /api/major-coins/candles?inst_id=BTC-USDT-SWAP&limit=30
GET /api/major-coins/daily-rankings/change?window=30d&limit=50
GET /api/major-coins/daily-candles?inst_id=BTC-USDT-SWAP&limit=30
```

参数：

- `window`：可选 `1h`、`2h`、`4h`、`12h`、`24h`，默认 `24h`。
- 主流币 `window`：可选 `1m`、`5m`、`15m`、`30m`，默认 `30m`。
- 主流币日排行 `window`：可选 `1d`、`5d`、`15d`、`30d`，默认 `30d`。
- `limit`：返回条数，范围 `1` 到 `2000`，默认 `50`。
- `direction`：多空方向，可选 `long`、`short`；不传则返回全部方向。
- `sort_by_funding_rate`：是否按资金费率绝对值从高到低排序，默认 `false`。
- `sort_by_funding_time`：是否按当次资金费结算时间从近到远排序，默认 `false`。如果两个排序参数都为 `true`，优先按当次结算时间排序。
- `query`：合约搜索关键词，用于 `/api/instruments`。
- `inst_id`：OKX 合约 ID，用于 `/api/candles`，例如 `BTC-USDT-SWAP`。

返回示例：

```json
{
  "metric": "pct_change",
  "window": "24h",
  "direction": "long",
  "direction_counts": {
    "long": 120,
    "short": 80,
    "total": 200
  },
  "sort_by_funding_rate": true,
  "sort_by_funding_time": false,
  "limit": 50,
  "collector_mode": "rest",
  "data": [
    {
      "rank": 1,
      "inst_id": "BTC-USDT-SWAP",
      "direction": "long",
      "pct_change": 2.31,
      "abs_pct_change": 2.31,
      "volume_quote": 123456789,
      "avg_hourly_volume_quote": 5144032.875,
      "open_price": 62000,
      "close_price": 63432,
      "start_ts": 1777647600000,
      "end_ts": 1777734000000,
      "calculated_at": 1777737600
    }
  ]
}
```

## 配置项

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `host` | `127.0.0.1` | Web 服务监听地址 |
| `port` | `8000` | Web 服务监听端口 |
| `db_path` | `data/market_rankings.sqlite3` | SQLite 数据库路径 |
| `okx_base_url` | `https://www.okx.com` | OKX REST API 地址 |
| `okx_ws_url` | `wss://ws.okx.com:8443/ws/v5/public` | OKX 公共 WebSocket 地址 |
| `quote_ccy` | `USDT` | 计价货币 |
| `collector_mode` | `rest` | `rest` 或 `websocket` |
| `rest_requests_per_second` | `2` | REST 请求频率 |
| `candles_limit` | `25` | 每次拉取的 1H K 线数量 |
| `ranking_interval_seconds` | `600` | 排行榜计算间隔 |
| `instruments_refresh_seconds` | `3600` | 合约列表刷新间隔 |
| `funding_enabled` | `true` | 是否启动资金费率刷新任务 |
| `funding_refresh_seconds` | `600` | 资金费率刷新间隔 |
| `funding_requests_per_second` | `2` | 资金费率接口请求频率 |
| `ws_subscribe_batch_size` | `50` | WebSocket 每批订阅数量 |
| `ws_reconnect_initial_seconds` | `5` | WebSocket 初始重连等待秒数 |
| `ws_reconnect_max_seconds` | `60` | WebSocket 最大重连等待秒数 |
| `major_coin_inst_ids` | `BTC/ETH/SOL` | 主流币分钟级模块的 OKX 合约 ID 列表 |
| `major_coin_poll_interval_seconds` | `10` | 主流币 1m K 线轮询间隔 |
| `major_coin_candles_limit` | `30` | 主流币每次拉取的 1m K 线数量 |
| `major_coin_daily_candles_limit` | `30` | 主流币每次拉取的 1D 日 K 线数量 |
| `major_coin_daily_poll_interval_seconds` | `1200` | 主流币 1D 日 K 线轮询间隔，默认每 20 分钟获取一次全主流币行情 |
