# 资金费率数据接口设计文档

## 1. 背景与目标

为了支持前端以及其他外部系统获取市场的资金费率数据排行，我们需要在 Web API 服务中新增一个资金费率数据查询接口。该接口支持按资金费率绝对值倒序排列，支持根据币种（交易对 ID）、结算周期、以及费率阈值等条件过滤，并需要集成涨跌幅和成交量等行情数据。

## 2. 接口设计

### 2.1 请求定义

- **接口路径**: `/api/funding/rankings`
- **请求方法**: `GET`
- **内容类型**: `application/json`

### 2.2 请求参数 (Query Parameters)

| 参数名 | 类型 | 必填 | 默认值 | 描述 |
| :--- | :--- | :--- | :--- | :--- |
| `limit` | Integer | 否 | `100` | 返回的数据条数限制，取值范围 `1` ~ `2000` |
| `inst_id` | String | 否 | - | 交易对 ID（如 `BTC-USDT-SWAP`），精确匹配，自动转为大写 |
| `funding_interval_hours` | Float | 否 | - | 结算周期（小时），例如 `8.0`（代表 8 小时结算一次） |
| `min_abs_funding_rate` | Float | 否 | - | 过滤资金费率绝对值大于等于此数值的记录，例如 `0.0001` (0.01%) |
| `window` | String | 否 | `"24h"` | 关联行情排行数据时的窗口期，取值必须是 `WINDOWS` 中的值（如 `1h`, `4h`, `24h` 等） |

### 2.3 响应结果 (Response Body)

#### 响应结构 (成功 - 200 OK)

```json
{
  "metric": "funding_rate",
  "window": "24h",
  "limit": 100,
  "data": [
    {
      "rank": 1,
      "inst_id": "BTC-USDT-SWAP",
      "base_ccy": "BTC",
      "quote_ccy": "USDT",
      "settle_ccy": "USDT",
      "funding_rate": 0.00015,
      "abs_funding_rate": 0.00015,
      "funding_interval_hours": 8.0,
      "funding_time": 1718870400000,
      "next_funding_time": 1718899200000,
      "funding_updated_at": 1718871234,
      "pct_change": 1.25,
      "abs_pct_change": 1.25,
      "volume_quote": 1200500.5,
      "direction": "long",
      "open_price": 65000.0,
      "close_price": 65812.5,
      "calculated_at": 1718871200
    }
  ]
}
```

#### 响应字段说明

| 字段名 | 类型 | 说明 |
| :--- | :--- | :--- |
| `metric` | String | 排行指标，固定为 `"funding_rate"` |
| `window` | String | 关联行情排行数据的窗口期 |
| `limit` | Integer | 本次查询实际限制的条数 |
| `data` | Array | 资金费率排行数据列表 |
| `data[].rank` | Integer | 排行序号，按 `abs_funding_rate` 从大到小排列 (1-based) |
| `data[].inst_id` | String | 交易对 ID |
| `data[].base_ccy` | String | 交易币种 (如 `"BTC"`) |
| `data[].quote_ccy` | String | 计价币种 (如 `"USDT"`) |
| `data[].settle_ccy` | String | 结算币种 (如 `"USDT"`) |
| `data[].funding_rate` | Float | 资金费率（如 `0.00015` 代表 0.015%） |
| `data[].abs_funding_rate` | Float | 资金费率绝对值 |
| `data[].funding_interval_hours`| Float | 结算周期（小时） |
| `data[].funding_time` | Integer | 最新资金费率结算时间戳（毫秒） |
| `data[].next_funding_time` | Integer | 下次资金费率结算时间戳（毫秒） |
| `data[].funding_updated_at` | Integer | 本地数据库中资金费率更新时间（秒级时间戳） |
| `data[].pct_change` | Float | 对应窗口期内的涨跌幅（如 `1.25` 代表 1.25%，无对应行情时为 null） |
| `data[].abs_pct_change` | Float | 涨跌幅绝对值 |
| `data[].volume_quote` | Float | 对应窗口期内的计价币成交量 |
| `data[].direction` | String | 价格变化方向 (`"long"` - 上涨, `"short"` - 下跌, 无行情时为 null) |
| `data[].open_price` | Float | 窗口开盘价 |
| `data[].close_price` | Float | 窗口收盘价 |
| `data[].calculated_at` | Integer | 排行行情计算时间（秒级时间戳） |

---

## 3. 系统实现设计

### 3.1 数据库层设计 (`app/db.py`)

在 `app/db.py` 中新增 `query_funding_rankings` 方法：

```python
def query_funding_rankings(
    limit: int = 100,
    inst_id: str | None = None,
    funding_interval_hours: float | None = None,
    min_abs_funding_rate: float | None = None,
    window: str = "24h",
) -> list[sqlite3.Row]:
    """
    按资金费率绝对值降序查询资金费率排行，并关联行情数据。
    """
    clauses = ["state = 'live'", "funding_rate IS NOT NULL"]
    params = []

    if inst_id:
        clauses.append("inst_id = ?")
        params.append(inst_id.upper())

    if funding_interval_hours is not None:
        clauses.append("funding_interval_hours = ?")
        params.append(funding_interval_hours)

    if min_abs_funding_rate is not None:
        clauses.append("ABS(funding_rate) >= ?")
        params.append(min_abs_funding_rate)

    where_clause = " AND ".join(clauses)
    
    # 关联指定 window 的 rankings 表
    sql = f"""
        SELECT 
            i.inst_id, i.base_ccy, i.quote_ccy, i.settle_ccy,
            i.funding_rate, i.funding_time, i.next_funding_time,
            i.funding_interval_hours, i.funding_updated_at,
            r.pct_change, r.volume_quote, r.direction,
            r.open_price, r.close_price, r.calculated_at
        FROM instruments i
        LEFT JOIN rankings r ON i.inst_id = r.inst_id AND r.metric = 'pct_change' AND r.window = ?
        WHERE {where_clause}
        ORDER BY ABS(i.funding_rate) DESC
        LIMIT ?
    """
    
    query_params = [window] + params + [limit]
    
    with connect() as conn:
        return conn.execute(sql, query_params).fetchall()
```

### 3.2 控制层设计 (`app/main.py`)

1. 新增 API 路由 `/api/funding/rankings`：

```python
@app.get("/api/funding/rankings")
async def api_funding_rankings(
    limit: int = Query(100, ge=1, le=2000),
    inst_id: str | None = Query(None),
    funding_interval_hours: float | None = Query(None),
    min_abs_funding_rate: float | None = Query(None),
    window: str = Query("24h"),
) -> dict:
    if window not in WINDOWS:
        raise HTTPException(status_code=400, detail=f"window must be one of {', '.join(WINDOWS)}")
        
    rows = db.query_funding_rankings(
        limit=limit,
        inst_id=inst_id,
        funding_interval_hours=funding_interval_hours,
        min_abs_funding_rate=min_abs_funding_rate,
        window=window,
    )
    
    return {
        "metric": "funding_rate",
        "window": window,
        "limit": limit,
        "data": [
            {
                "rank": index + 1,
                "inst_id": row["inst_id"],
                "base_ccy": row["base_ccy"],
                "quote_ccy": row["quote_ccy"],
                "settle_ccy": row["settle_ccy"],
                "funding_rate": row["funding_rate"],
                "abs_funding_rate": abs(row["funding_rate"]) if row["funding_rate"] is not None else None,
                "funding_interval_hours": row["funding_interval_hours"],
                "funding_time": row["funding_time"],
                "next_funding_time": row["next_funding_time"],
                "funding_updated_at": row["funding_updated_at"],
                "pct_change": row["pct_change"],
                "abs_pct_change": abs(row["pct_change"]) if row["pct_change"] is not None else None,
                "volume_quote": row["volume_quote"],
                "direction": row["direction"],
                "open_price": row["open_price"],
                "close_price": row["close_price"],
                "calculated_at": row["calculated_at"],
            }
            for index, row in enumerate(rows)
        ]
    }
```

### 3.3 文档编写

在现有的 API 接口文档中添加本接口的说明，包括：
1. 请求参数定义
2. 响应格式及各字段含义
3. 示例请求与响应
