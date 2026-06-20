import sqlite3
import pytest
from app import db

@pytest.fixture(autouse=True)
def setup_test_db(tmp_path):
    # 记录原始路径
    original_db_path = db.settings.db_path
    test_db = tmp_path / "test.db"

    # 强制修改 frozen dataclass 的字段
    object.__setattr__(db.settings, "db_path", test_db)
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

    yield

    # 恢复原始路径
    object.__setattr__(db.settings, "db_path", original_db_path)

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
