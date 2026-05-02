# Market Rankings

OKX 永续合约行情排行榜 Web 程序。程序使用 SQLite 保存 1H K 线池，并计算 `1h`、`2h`、`4h`、`12h`、`24h` 的涨跌幅排行榜和计价货币成交量排行榜，例如 USDT 成交量。

## 运行

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python run.py
```

打开：

- http://127.0.0.1:8000/

主页面有四个菜单：

- 涨跌幅
- 交易量
- K 线数据
- API 文档

兼容入口仍保留，并渲染同一个页面：

- http://127.0.0.1:8000/rankings/change
- http://127.0.0.1:8000/rankings/volume

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
GET /api/rankings/change?window=24h&limit=50&direction=long
```

交易量排行榜：

```text
GET /api/rankings/volume?window=24h&limit=50&direction=short
```

合约列表：

```text
GET /api/instruments?query=BTC&limit=50
```

K 线数据：

```text
GET /api/candles?inst_id=BTC-USDT-SWAP&limit=100
```

参数：

- `window`：可选 `1h`、`2h`、`4h`、`12h`、`24h`，默认 `24h`。
- `limit`：返回条数，范围 `1` 到 `500`，默认 `50`。
- `direction`：多空方向，可选 `long`、`short`；不传则返回全部方向。
- `query`：合约搜索关键词，用于 `/api/instruments`。
- `inst_id`：OKX 合约 ID，用于 `/api/candles`，例如 `BTC-USDT-SWAP`。

返回示例：

```json
{
  "metric": "pct_change",
  "window": "24h",
  "direction": "long",
  "limit": 50,
  "collector_mode": "rest",
  "data": [
    {
      "rank": 1,
      "inst_id": "BTC-USDT-SWAP",
      "direction": "long",
      "pct_change": 2.31,
      "abs_pct_change": 2.31,
      "volume_quote": 123456789.12,
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
| `ws_subscribe_batch_size` | `50` | WebSocket 每批订阅数量 |
| `ws_reconnect_initial_seconds` | `5` | WebSocket 初始重连等待秒数 |
| `ws_reconnect_max_seconds` | `60` | WebSocket 最大重连等待秒数 |
