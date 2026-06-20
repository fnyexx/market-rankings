# 资金费率接口实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 `/api/funding/rankings` 资金费率数据接口，并在 web api 文档中注明入参和出参。

**Architecture:** 
1. 数据库层：在 `app/db.py` 中实现 `query_funding_rankings` 逻辑，支持 `limit`, `inst_id`, `funding_interval_hours`, `min_abs_funding_rate`, `window` 过滤，默认以 `ABS(funding_rate) DESC` 排序。
2. 接口层：在 `app/main.py` 中新增路由 `/api/funding/rankings`，接收并校验参数，然后渲染返回结果。
3. 文档：在 `README.md` 或相关接口文档中添加接口描述。
4. 测试：引入 `pytest` 和 `httpx`，对数据库层和 API 路由层分别进行单元测试。

**Tech Stack:** FastAPI, SQLite, Python 3, Pytest

---

### Task 1: 初始化测试环境与数据库测试编写

**Files:**
- Modify: `requirements.txt`
- Create: `tests/test_db.py`

- [ ] **Step 1: 往 requirements.txt 添加 pytest 依赖**

编辑 `requirements.txt`，添加：
```text
pytest==8.2.2
```

- [ ] **Step 2: 编写测试用例 `tests/test_db.py`**

创建 `tests/test_db.py`：
```python
import sqlite3
import pytest
from app import db

@pytest.fixture(autouse=True)
def setup_test_db(monkeypatch, tmp_path):
    # 使用临时内存数据库或临时文件数据库
    test_db = tmp_path / "test.db"
    monkeypatch.setattr(db.settings, "db_path", test_db)
    db.init_db()
    
    # 填充一些测试数据
    with db.connect() as conn:
        # 1. 插入 instruments 测试数据
        conn.executemany(
            """
            INSERT INTO instruments (
                inst_id, base_ccy, quote_ccy, settle_ccy, state, 
                funding_rate, funding_time, next_funding_time, 
                funding_interval_hours, funding_updated_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("BTC-USDT-SWAP", "BTC", "USDT", "USDT", "live", 0.00015, 1718870400000, 1718899200000, 8.0, 1718871234, 1718871234),
                ("ETH-USDT-SWAP", "ETH", "USDT", "USDT", "live", -0.00025, 1718870400000, 1718899200000, 8.0, 1718871234, 1718871234),
                ("SOL-USDT-SWAP", "SOL", "USDT", "USDT", "live", 0.00005, 1718870400000, 1718884800000, 4.0, 1718871234, 1718871234),
                ("SUSHI-USDT-SWAP", "SUSHI", "USDT", "USDT", "suspend", 0.00050, 1718870400000, 1718899200000, 8.0, 1718871234, 1718871234),
            ]
        )
        # 2. 插入 rankings 测试数据
        conn.executemany(
            """
            INSERT INTO rankings (
                metric, window, inst_id, direction, pct_change, 
                volume_quote, open_price, close_price, start_ts, end_ts, calculated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("pct_change", "24h", "BTC-USDT-SWAP", "long", 1.25, 1200000.0, 65000.0, 65812.5, 1718784000, 1718870400, 1718870400),
                ("pct_change", "24h", "ETH-USDT-SWAP", "short", -2.50, 800000.0, 3500.0, 3412.5, 1718784000, 1718870400, 1718870400),
            ]
        )

def test_query_funding_rankings_default():
    # 默认应当返回 live 且 funding_rate 不为 None 的数据，按 ABS(funding_rate) 降序
    rows = db.query_funding_rankings()
    # 预期的 live 数据有 ETH (-0.00025), BTC (0.00015), SOL (0.00005)
    # 按绝对值降序：ETH (0.00025) -> BTC (0.00015) -> SOL (0.00005)
    # SUSHI 因 state = suspend 不应该返回
    assert len(rows) == 3
    assert rows[0]["inst_id"] == "ETH-USDT-SWAP"
    assert rows[1]["inst_id"] == "BTC-USDT-SWAP"
    assert rows[2]["inst_id"] == "SOL-USDT-SWAP"

def test_query_funding_rankings_filters():
    # 1. 过滤 inst_id
    rows = db.query_funding_rankings(inst_id="BTC-USDT-SWAP")
    assert len(rows) == 1
    assert rows[0]["inst_id"] == "BTC-USDT-SWAP"
    assert rows[0]["pct_change"] == 1.25  # 检查是否正确 LEFT JOIN 了 rankings 表

    # 2. 过滤 funding_interval_hours
    rows = db.query_funding_rankings(funding_interval_hours=4.0)
    assert len(rows) == 1
    assert rows[0]["inst_id"] == "SOL-USDT-SWAP"
    assert rows[0]["pct_change"] is None  # SOL 无 ranking 数据，应该为 None

    # 3. 过滤 min_abs_funding_rate
    rows = db.query_funding_rankings(min_abs_funding_rate=0.00020)
    assert len(rows) == 1
    assert rows[0]["inst_id"] == "ETH-USDT-SWAP"
```

- [ ] **Step 3: 运行测试以验证失败**

安装依赖：
```bash
pip install -r requirements.txt
```
运行测试：
```bash
pytest tests/test_db.py -v
```
预期：失败（`AttributeError: module 'app.db' has no attribute 'query_funding_rankings'`）

- [ ] **Step 4: 提交包含测试的代码**

```bash
git add requirements.txt tests/test_db.py
git commit -m "test: add db tests for query_funding_rankings"
```

---

### Task 2: 实现数据库层的查询方法

**Files:**
- Modify: `app/db.py`

- [ ] **Step 1: 在 `app/db.py` 中实现 `query_funding_rankings` 方法**

修改 `app/db.py`，在合适位置（例如 `query_major_coin_daily_rankings` 后面）添加该方法：
```python
def query_funding_rankings(
    limit: int = 100,
    inst_id: str | None = None,
    funding_interval_hours: float | None = None,
    min_abs_funding_rate: float | None = None,
    window: str = "24h",
) -> list[sqlite3.Row]:
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

- [ ] **Step 2: 运行测试以验证通过**

运行命令：
```bash
pytest tests/test_db.py -v
```
预期：PASS

- [ ] **Step 3: 提交更改**

```bash
git add app/db.py
git commit -m "feat: implement query_funding_rankings in db.py"
```

---

### Task 3: 编写 API 路由测试

**Files:**
- Create: `tests/test_api.py`

- [ ] **Step 1: 编写 `/api/funding/rankings` API 测试**

创建 `tests/test_api.py`：
```python
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app import db

@pytest.fixture(autouse=True)
def setup_test_db(monkeypatch, tmp_path):
    test_db = tmp_path / "test.db"
    monkeypatch.setattr(db.settings, "db_path", test_db)
    db.init_db()
    with db.connect() as conn:
        conn.executemany(
            """
            INSERT INTO instruments (
                inst_id, base_ccy, quote_ccy, settle_ccy, state, 
                funding_rate, funding_time, next_funding_time, 
                funding_interval_hours, funding_updated_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("BTC-USDT-SWAP", "BTC", "USDT", "USDT", "live", 0.00015, 1718870400000, 1718899200000, 8.0, 1718871234, 1718871234),
                ("ETH-USDT-SWAP", "ETH", "USDT", "USDT", "live", -0.00025, 1718870400000, 1718899200000, 8.0, 1718871234, 1718871234),
            ]
        )
        conn.executemany(
            """
            INSERT INTO rankings (
                metric, window, inst_id, direction, pct_change, 
                volume_quote, open_price, close_price, start_ts, end_ts, calculated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("pct_change", "24h", "BTC-USDT-SWAP", "long", 1.25, 1200000.0, 65000.0, 65812.5, 1718784000, 1718870400, 1718870400),
            ]
        )

def test_api_funding_rankings():
    client = TestClient(app)
    response = client.get("/api/funding/rankings?window=24h&limit=5")
    assert response.status_code == 200
    data = response.json()
    assert data["metric"] == "funding_rate"
    assert data["window"] == "24h"
    assert len(data["data"]) == 2
    
    # 检验排序：绝对值倒序，ETH 绝对值为 0.00025，排第一
    assert data["data"][0]["inst_id"] == "ETH-USDT-SWAP"
    assert data["data"][0]["abs_funding_rate"] == 0.00025
    assert data["data"][0]["pct_change"] is None  # 无排行行情数据
    
    assert data["data"][1]["inst_id"] == "BTC-USDT-SWAP"
    assert data["data"][1]["abs_funding_rate"] == 0.00015
    assert data["data"][1]["pct_change"] == 1.25

def test_api_funding_rankings_invalid_window():
    client = TestClient(app)
    response = client.get("/api/funding/rankings?window=invalid_window")
    assert response.status_code == 400
    assert "window must be one of" in response.json()["detail"]
```

- [ ] **Step 2: 运行测试验证失败**

运行：
```bash
pytest tests/test_api.py -v
```
预期：FAIL (404 Not Found)

- [ ] **Step 3: 提交 API 测试**

```bash
git add tests/test_api.py
git commit -m "test: add api tests for /api/funding/rankings"
```

---

### Task 4: 实现 API 路由

**Files:**
- Modify: `app/main.py`

- [ ] **Step 1: 在 `app/main.py` 中添加对应的请求路由**

在 `app/main.py` 中添加路由和辅助函数。把路由放在 `api_candles` 之后，`_candles_response` 之前：
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

- [ ] **Step 2: 运行测试验证通过**

运行所有测试：
```bash
pytest -v
```
预期：`tests/test_db.py` 和 `tests/test_api.py` 均全部 PASS。

- [ ] **Step 3: 提交路由实现**

```bash
git add app/main.py
git commit -m "feat: add api endpoint for /api/funding/rankings"
```

---

### Task 5: 编写接口文档

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 在 `README.md` 中添加接口入参和出参说明**

在文档的 API 章节中追加对新接口的描述。

在 `README.md` 底部或现有接口文档部分添加：
```markdown
### 资金费率排行榜数据接口

**接口地址**: `/api/funding/rankings`
**请求方式**: `GET`

#### 请求参数 (Query Parameters)
- `limit`: 返回数量限制，默认 100，可选范围 1 ~ 2000。
- `inst_id`: 指定币种/交易对 ID 过滤（如 `BTC-USDT-SWAP`），精确匹配，大小写不敏感。
- `funding_interval_hours`: 指定结算周期过滤（如 `8` 表示 8 小时）。
- `min_abs_funding_rate`: 过滤资金费率绝对值大于等于此值的记录（如 `0.0001`）。
- `window`: 关联的行情排行窗口，默认 `24h`。

#### 响应参数说明 (成功 200 OK)
返回 JSON 对象，格式如下：
```json
{
  "metric": "funding_rate",
  "window": "24h",
  "limit": 100,
  "data": [
    {
      "rank": 1,
      "inst_id": "ETH-USDT-SWAP",
      "base_ccy": "ETH",
      "quote_ccy": "USDT",
      "settle_ccy": "USDT",
      "funding_rate": -0.00025,
      "abs_funding_rate": 0.00025,
      "funding_interval_hours": 8.0,
      "funding_time": 1718870400000,
      "next_funding_time": 1718899200000,
      "funding_updated_at": 1718871234,
      "pct_change": -2.5,
      "abs_pct_change": 2.5,
      "volume_quote": 800000.0,
      "direction": "short",
      "open_price": 3500.0,
      "close_price": 3412.5,
      "calculated_at": 1718870400
    }
  ]
}
```
```

- [ ] **Step 2: 提交文档修改**

```bash
git add README.md
git commit -m "docs: add api documentation for /api/funding/rankings"
```
