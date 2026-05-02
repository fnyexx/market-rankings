import sqlite3
import time
from pathlib import Path
from typing import Iterable, Sequence

from app.config import settings


def connect() -> sqlite3.Connection:
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS instruments (
              inst_id TEXT PRIMARY KEY,
              base_ccy TEXT,
              quote_ccy TEXT,
              settle_ccy TEXT,
              state TEXT,
              updated_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS candles_1h (
              inst_id TEXT NOT NULL,
              ts INTEGER NOT NULL,
              open REAL NOT NULL,
              high REAL NOT NULL,
              low REAL NOT NULL,
              close REAL NOT NULL,
              volume_contract REAL,
              volume_base REAL,
              volume_quote REAL,
              confirmed INTEGER NOT NULL DEFAULT 0,
              fetched_at INTEGER NOT NULL,
              PRIMARY KEY (inst_id, ts)
            );

            CREATE INDEX IF NOT EXISTS idx_candles_1h_inst_ts
            ON candles_1h(inst_id, ts DESC);

            CREATE TABLE IF NOT EXISTS rankings (
              metric TEXT NOT NULL,
              window TEXT NOT NULL,
              inst_id TEXT NOT NULL,
              direction TEXT NOT NULL DEFAULT 'long',
              pct_change REAL,
              volume_quote REAL,
              open_price REAL,
              close_price REAL,
              start_ts INTEGER,
              end_ts INTEGER,
              calculated_at INTEGER NOT NULL,
              PRIMARY KEY (metric, window, inst_id)
            );

            CREATE INDEX IF NOT EXISTS idx_rankings_change
            ON rankings(metric, window, pct_change DESC);

            CREATE INDEX IF NOT EXISTS idx_rankings_volume
            ON rankings(metric, window, volume_quote DESC);
            """
        )
        _ensure_column(conn, "rankings", "direction", "TEXT NOT NULL DEFAULT 'long'")
        _backfill_ranking_directions(conn)


def upsert_instruments(instruments: Iterable[dict]) -> None:
    now = int(time.time())
    rows = [
        (
            item["instId"],
            item.get("baseCcy"),
            item.get("quoteCcy"),
            item.get("settleCcy"),
            item.get("state"),
            now,
        )
        for item in instruments
    ]
    with connect() as conn:
        conn.executemany(
            """
            INSERT INTO instruments (inst_id, base_ccy, quote_ccy, settle_ccy, state, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(inst_id) DO UPDATE SET
              base_ccy = excluded.base_ccy,
              quote_ccy = excluded.quote_ccy,
              settle_ccy = excluded.settle_ccy,
              state = excluded.state,
              updated_at = excluded.updated_at
            """,
            rows,
        )


def list_instrument_ids() -> list[str]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT inst_id
            FROM instruments
            WHERE state = 'live'
            ORDER BY inst_id
            """
        ).fetchall()
    return [row["inst_id"] for row in rows]


def upsert_candles(inst_id: str, candles: Iterable[Sequence[str]]) -> None:
    now = int(time.time())
    rows = []
    for candle in candles:
        rows.append(
            (
                inst_id,
                int(candle[0]),
                float(candle[1]),
                float(candle[2]),
                float(candle[3]),
                float(candle[4]),
                _optional_float(candle, 5),
                _optional_float(candle, 6),
                _optional_float(candle, 7),
                int(candle[8]) if len(candle) > 8 and candle[8] != "" else 0,
                now,
            )
        )
    if not rows:
        return
    with connect() as conn:
        conn.executemany(
            """
            INSERT INTO candles_1h (
              inst_id, ts, open, high, low, close,
              volume_contract, volume_base, volume_quote, confirmed, fetched_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(inst_id, ts) DO UPDATE SET
              open = excluded.open,
              high = excluded.high,
              low = excluded.low,
              close = excluded.close,
              volume_contract = excluded.volume_contract,
              volume_base = excluded.volume_base,
              volume_quote = excluded.volume_quote,
              confirmed = excluded.confirmed,
              fetched_at = excluded.fetched_at
            """,
            rows,
        )


def replace_rankings(rows: Iterable[tuple]) -> None:
    rows = list(rows)
    calculated_at = int(time.time())
    with connect() as conn:
        conn.execute("DELETE FROM rankings")
        conn.executemany(
            """
            INSERT INTO rankings (
              metric, window, inst_id, direction, pct_change, volume_quote,
              open_price, close_price, start_ts, end_ts, calculated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [(*row, calculated_at) for row in rows],
        )


def query_rankings(metric: str, window: str, limit: int, direction: str | None = None) -> list[sqlite3.Row]:
    order_expression = "volume_quote DESC" if metric == "volume" else "ABS(pct_change) DESC"
    direction_clause = "AND direction = ?" if direction else ""
    params: tuple = (metric, window, direction, limit) if direction else (metric, window, limit)
    with connect() as conn:
        return conn.execute(
            f"""
            SELECT *
            FROM rankings
            WHERE metric = ? AND window = ?
            {direction_clause}
            ORDER BY {order_expression}
            LIMIT ?
            """,
            params,
        ).fetchall()


def _optional_float(values: Sequence[str], index: int) -> float | None:
    if len(values) <= index or values[index] == "":
        return None
    return float(values[index])


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = conn.execute(f"PRAGMA table_info({table})").fetchall()
    if any(row["name"] == column for row in columns):
        return
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _backfill_ranking_directions(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        UPDATE rankings
        SET direction = CASE
            WHEN pct_change < 0 THEN 'short'
            ELSE 'long'
        END
        """
    )
