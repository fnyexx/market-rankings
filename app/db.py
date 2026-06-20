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
              funding_rate REAL,
              funding_time INTEGER,
              next_funding_time INTEGER,
              funding_interval_hours REAL,
              funding_updated_at INTEGER,
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

            CREATE TABLE IF NOT EXISTS major_coin_candles_1m (
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

            CREATE INDEX IF NOT EXISTS idx_major_coin_candles_1m_inst_ts
            ON major_coin_candles_1m(inst_id, ts DESC);

            CREATE TABLE IF NOT EXISTS major_coin_candles_1d (
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

            CREATE INDEX IF NOT EXISTS idx_major_coin_candles_1d_inst_ts
            ON major_coin_candles_1d(inst_id, ts DESC);

            CREATE TABLE IF NOT EXISTS major_coin_daily_rankings (
              metric TEXT NOT NULL,
              window TEXT NOT NULL,
              inst_id TEXT NOT NULL,
              direction TEXT NOT NULL,
              pct_change REAL,
              volume_quote REAL,
              avg_daily_volume_quote REAL,
              open_price REAL,
              close_price REAL,
              start_ts INTEGER,
              end_ts INTEGER,
              calculated_at INTEGER NOT NULL,
              PRIMARY KEY (metric, window, inst_id)
            );

            CREATE INDEX IF NOT EXISTS idx_major_coin_daily_rankings_change
            ON major_coin_daily_rankings(metric, window, pct_change DESC);

            CREATE TABLE IF NOT EXISTS major_coin_rankings (
              metric TEXT NOT NULL,
              window TEXT NOT NULL,
              inst_id TEXT NOT NULL,
              direction TEXT NOT NULL,
              pct_change REAL,
              volume_quote REAL,
              avg_minute_volume_quote REAL,
              open_price REAL,
              close_price REAL,
              start_ts INTEGER,
              end_ts INTEGER,
              calculated_at INTEGER NOT NULL,
              PRIMARY KEY (metric, window, inst_id)
            );

            CREATE INDEX IF NOT EXISTS idx_major_coin_rankings_change
            ON major_coin_rankings(metric, window, pct_change DESC);

            """
        )
        _ensure_column(conn, "rankings", "direction", "TEXT NOT NULL DEFAULT 'long'")
        _ensure_column(conn, "rankings", "volume_quote", "REAL")
        _ensure_column(conn, "instruments", "funding_rate", "REAL")
        _ensure_column(conn, "instruments", "funding_time", "INTEGER")
        _ensure_column(conn, "instruments", "next_funding_time", "INTEGER")
        _ensure_column(conn, "instruments", "funding_interval_hours", "REAL")
        _ensure_column(conn, "instruments", "funding_updated_at", "INTEGER")
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


def list_instruments(query: str = "", limit: int = 500) -> list[sqlite3.Row]:
    keyword = f"%{query.upper()}%"
    with connect() as conn:
        if query:
            return conn.execute(
                """
                SELECT
                  inst_id, base_ccy, quote_ccy, settle_ccy, state,
                  funding_rate, funding_time, next_funding_time,
                  funding_interval_hours, funding_updated_at, updated_at
                FROM instruments
                WHERE state = 'live' AND UPPER(inst_id) LIKE ?
                ORDER BY inst_id
                LIMIT ?
                """,
                (keyword, limit),
            ).fetchall()
        return conn.execute(
            """
            SELECT
              inst_id, base_ccy, quote_ccy, settle_ccy, state,
              funding_rate, funding_time, next_funding_time,
              funding_interval_hours, funding_updated_at, updated_at
            FROM instruments
            WHERE state = 'live'
            ORDER BY inst_id
            LIMIT ?
            """,
            (limit,),
        ).fetchall()


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


def upsert_major_coin_candles(inst_id: str, candles: Iterable[Sequence[str]]) -> None:
    now = int(time.time())
    rows = _build_candle_rows(inst_id, candles, now)
    if not rows:
        return
    with connect() as conn:
        conn.executemany(
            """
            INSERT INTO major_coin_candles_1m (
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


def upsert_major_coin_daily_candles(inst_id: str, candles: Iterable[Sequence[str]]) -> None:
    now = int(time.time())
    rows = _build_candle_rows(inst_id, candles, now)
    if not rows:
        return
    with connect() as conn:
        conn.executemany(
            """
            INSERT INTO major_coin_candles_1d (
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
              metric, window, inst_id, direction, pct_change,
              volume_quote, open_price, close_price, start_ts, end_ts, calculated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [(*row, calculated_at) for row in rows],
        )


def replace_major_coin_rankings(rows: Iterable[tuple]) -> None:
    rows = list(rows)
    calculated_at = int(time.time())
    with connect() as conn:
        conn.execute("DELETE FROM major_coin_rankings")
        conn.executemany(
            """
            INSERT INTO major_coin_rankings (
              metric, window, inst_id, direction, pct_change,
              volume_quote, avg_minute_volume_quote,
              open_price, close_price, start_ts, end_ts, calculated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [(*row, calculated_at) for row in rows],
        )


def replace_major_coin_daily_rankings(rows: Iterable[tuple]) -> None:
    rows = list(rows)
    calculated_at = int(time.time())
    with connect() as conn:
        conn.execute("DELETE FROM major_coin_daily_rankings")
        conn.executemany(
            """
            INSERT INTO major_coin_daily_rankings (
              metric, window, inst_id, direction, pct_change,
              volume_quote, avg_daily_volume_quote,
              open_price, close_price, start_ts, end_ts, calculated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [(*row, calculated_at) for row in rows],
        )


def query_rankings(
    window: str,
    limit: int,
    direction: str | None = None,
    sort_by_funding_rate: bool = False,
    sort_by_funding_time: bool = False,
) -> list[sqlite3.Row]:
    direction_clause = "AND direction = ?" if direction else ""
    params: tuple = (window, direction, limit) if direction else (window, limit)
    order_expression = _ranking_order_expression(sort_by_funding_rate, sort_by_funding_time)
    with connect() as conn:
        return conn.execute(
            f"""
            SELECT *
            FROM rankings
            LEFT JOIN instruments USING (inst_id)
            WHERE metric = 'pct_change' AND window = ?
            {direction_clause}
            ORDER BY {order_expression}
            LIMIT ?
            """,
            params,
        ).fetchall()


def query_major_coin_rankings(
    window: str,
    limit: int,
    direction: str | None = None,
) -> list[sqlite3.Row]:
    direction_clause = "AND direction = ?" if direction else ""
    params: tuple = (window, direction, limit) if direction else (window, limit)
    with connect() as conn:
        return conn.execute(
            f"""
            SELECT *
            FROM major_coin_rankings
            WHERE metric = 'pct_change' AND window = ?
            {direction_clause}
            ORDER BY ABS(pct_change) DESC
            LIMIT ?
            """,
            params,
        ).fetchall()


def query_major_coin_daily_rankings(
    window: str,
    limit: int,
    direction: str | None = None,
) -> list[sqlite3.Row]:
    direction_clause = "AND direction = ?" if direction else ""
    params: tuple = (window, direction, limit) if direction else (window, limit)
    with connect() as conn:
        return conn.execute(
            f"""
            SELECT *
            FROM major_coin_daily_rankings
            WHERE metric = 'pct_change' AND window = ?
            {direction_clause}
            ORDER BY ABS(pct_change) DESC
            LIMIT ?
            """,
            params,
        ).fetchall()


def count_ranking_directions(window: str) -> dict[str, int]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT direction, COUNT(*) AS count
            FROM rankings
            WHERE metric = 'pct_change' AND window = ?
            GROUP BY direction
            """,
            (window,),
        ).fetchall()
    counts = {"long": 0, "short": 0}
    for row in rows:
        if row["direction"] in counts:
            counts[row["direction"]] = row["count"]
    counts["total"] = counts["long"] + counts["short"]
    return counts


def count_major_coin_ranking_directions(window: str) -> dict[str, int]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT direction, COUNT(*) AS count
            FROM major_coin_rankings
            WHERE metric = 'pct_change' AND window = ?
            GROUP BY direction
            """,
            (window,),
        ).fetchall()
    counts = {"long": 0, "short": 0}
    for row in rows:
        if row["direction"] in counts:
            counts[row["direction"]] = row["count"]
    counts["total"] = counts["long"] + counts["short"]
    return counts


def count_major_coin_daily_ranking_directions(window: str) -> dict[str, int]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT direction, COUNT(*) AS count
            FROM major_coin_daily_rankings
            WHERE metric = 'pct_change' AND window = ?
            GROUP BY direction
            """,
            (window,),
        ).fetchall()
    counts = {"long": 0, "short": 0}
    for row in rows:
        if row["direction"] in counts:
            counts[row["direction"]] = row["count"]
    counts["total"] = counts["long"] + counts["short"]
    return counts


def _ranking_order_expression(sort_by_funding_rate: bool, sort_by_funding_time: bool) -> str:
    if sort_by_funding_time and sort_by_funding_rate:
        return "funding_time IS NULL, funding_time ASC, funding_rate IS NULL, ABS(funding_rate) DESC, ABS(pct_change) DESC"
    if sort_by_funding_time:
        return "funding_time IS NULL, funding_time ASC, ABS(pct_change) DESC"
    if sort_by_funding_rate:
        return "funding_rate IS NULL, ABS(funding_rate) DESC, ABS(pct_change) DESC"
    return "ABS(pct_change) DESC"


def update_instrument_funding(
    inst_id: str,
    funding_rate: float | None,
    funding_time: int | None,
    next_funding_time: int | None,
) -> None:
    interval_hours = None
    if funding_time is not None and next_funding_time is not None and next_funding_time > funding_time:
        interval_hours = (next_funding_time - funding_time) / 3_600_000
    with connect() as conn:
        conn.execute(
            """
            UPDATE instruments
            SET
              funding_rate = ?,
              funding_time = ?,
              next_funding_time = ?,
              funding_interval_hours = ?,
              funding_updated_at = ?
            WHERE inst_id = ?
            """,
            (
                funding_rate,
                funding_time,
                next_funding_time,
                interval_hours,
                int(time.time()),
                inst_id,
            ),
        )


def query_candles(inst_id: str, limit: int) -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(
            """
            SELECT
              inst_id, ts, open, high, low, close,
              volume_contract, volume_base, volume_quote,
              confirmed, fetched_at
            FROM candles_1h
            WHERE inst_id = ?
            ORDER BY ts DESC
            LIMIT ?
            """,
            (inst_id, limit),
        ).fetchall()


def query_major_coin_candles(inst_id: str, limit: int) -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(
            """
            SELECT
              inst_id, ts, open, high, low, close,
              volume_contract, volume_base, volume_quote,
              confirmed, fetched_at
            FROM major_coin_candles_1m
            WHERE inst_id = ?
            ORDER BY ts DESC
            LIMIT ?
            """,
            (inst_id, limit),
        ).fetchall()


def query_major_coin_daily_candles(inst_id: str, limit: int) -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(
            """
            SELECT
              inst_id, ts, open, high, low, close,
              volume_contract, volume_base, volume_quote,
              confirmed, fetched_at
            FROM major_coin_candles_1d
            WHERE inst_id = ?
            ORDER BY ts DESC
            LIMIT ?
            """,
            (inst_id, limit),
        ).fetchall()


def _build_candle_rows(
    inst_id: str,
    candles: Iterable[Sequence[str]],
    fetched_at: int,
) -> list[tuple]:
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
                fetched_at,
            )
        )
    return rows


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


def query_funding_rankings(
    limit: int = 100,
    inst_id: str | None = None,
    funding_interval_hours: float | None = None,
    min_abs_funding_rate: float | None = None,
    window: str = "24h",
) -> list[sqlite3.Row]:
    clauses = ["i.state = 'live'", "i.funding_rate IS NOT NULL"]
    params = []

    if inst_id:
        clauses.append("i.inst_id = ?")
        params.append(inst_id.upper())

    if funding_interval_hours is not None:
        clauses.append("i.funding_interval_hours = ?")
        params.append(funding_interval_hours)

    if min_abs_funding_rate is not None:
        clauses.append("ABS(i.funding_rate) >= ?")
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
