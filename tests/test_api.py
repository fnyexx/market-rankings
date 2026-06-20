import pytest
from fastapi.testclient import TestClient
from app.main import app
from app import db


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path):
    original_db_path = db.settings.db_path
    test_db = tmp_path / "test.db"

    # 强制修改 frozen dataclass 字段
    object.__setattr__(db.settings, "db_path", test_db)
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

    yield

    # 恢复原始路径
    object.__setattr__(db.settings, "db_path", original_db_path)


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
