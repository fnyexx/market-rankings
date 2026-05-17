import asyncio
import logging

from app import db
from app.config import settings
from app.okx_client import OkxClient

logger = logging.getLogger(__name__)

MAJOR_COIN_WINDOWS = {"1m": 1, "5m": 5, "15m": 15, "30m": 30}
MAJOR_COIN_DAILY_WINDOWS = {"1d": 1, "5d": 5, "15d": 15, "30d": 30}


async def major_coin_loop() -> None:
    client = OkxClient()
    try:
        while True:
            try:
                await refresh_major_coin_candles(client)
                count = calculate_major_coin_rankings()
                logger.info("calculated %s major coin ranking rows", count)
            except Exception:
                logger.exception("major coin refresh failed")
            await asyncio.sleep(settings.major_coin_poll_interval_seconds)
    finally:
        await client.close()


async def major_coin_daily_loop() -> None:
    client = OkxClient()
    try:
        while True:
            try:
                await refresh_major_coin_daily_candles(client)
                count = calculate_major_coin_daily_rankings()
                logger.info("calculated %s major coin daily ranking rows", count)
            except Exception:
                logger.exception("major coin daily refresh failed")
            await asyncio.sleep(settings.major_coin_daily_poll_interval_seconds)
    finally:
        await client.close()


async def refresh_major_coin_candles(client: OkxClient | None = None) -> int:
    owns_client = client is None
    client = client or OkxClient()
    updated = 0
    try:
        for inst_id in settings.major_coin_inst_ids:
            try:
                candles = await client.get_candles(
                    inst_id,
                    "1m",
                    settings.major_coin_candles_limit,
                )
                db.upsert_major_coin_candles(inst_id, candles)
                updated += 1
            except Exception:
                logger.exception("failed to refresh major coin candles for %s", inst_id)
        return updated
    finally:
        if owns_client:
            await client.close()


async def refresh_major_coin_daily_candles(client: OkxClient | None = None) -> int:
    owns_client = client is None
    client = client or OkxClient()
    updated = 0
    try:
        for inst_id in settings.major_coin_inst_ids:
            try:
                candles = await client.get_candles(
                    inst_id,
                    "1D",
                    settings.major_coin_daily_candles_limit,
                )
                db.upsert_major_coin_daily_candles(inst_id, candles)
                updated += 1
            except Exception:
                logger.exception("failed to refresh major coin daily candles for %s", inst_id)
        return updated
    finally:
        if owns_client:
            await client.close()


def calculate_major_coin_rankings() -> int:
    rows = []
    with db.connect() as conn:
        for inst_id in settings.major_coin_inst_ids:
            candles = conn.execute(
                """
                SELECT ts, open, close, volume_quote
                FROM major_coin_candles_1m
                WHERE inst_id = ?
                ORDER BY ts DESC
                LIMIT ?
                """,
                (inst_id, max(MAJOR_COIN_WINDOWS.values())),
            ).fetchall()
            candles = list(reversed(candles))
            for window, size in MAJOR_COIN_WINDOWS.items():
                if len(candles) < size:
                    continue
                scoped = candles[-size:]
                open_price = scoped[0]["open"]
                close_price = scoped[-1]["close"]
                if open_price <= 0:
                    continue
                volume_quote = sum(candle["volume_quote"] or 0 for candle in scoped)
                pct_change = (close_price - open_price) / open_price * 100
                direction = "long" if pct_change >= 0 else "short"
                rows.append(
                    (
                        "pct_change",
                        window,
                        inst_id,
                        direction,
                        pct_change,
                        volume_quote,
                        volume_quote / size,
                        open_price,
                        close_price,
                        scoped[0]["ts"],
                        scoped[-1]["ts"],
                    )
                )
    db.replace_major_coin_rankings(rows)
    return len(rows)


def calculate_major_coin_daily_rankings() -> int:
    rows = []
    with db.connect() as conn:
        for inst_id in settings.major_coin_inst_ids:
            candles = conn.execute(
                """
                SELECT ts, open, close, volume_quote
                FROM major_coin_candles_1d
                WHERE inst_id = ?
                ORDER BY ts DESC
                LIMIT ?
                """,
                (inst_id, max(MAJOR_COIN_DAILY_WINDOWS.values())),
            ).fetchall()
            candles = list(reversed(candles))
            for window, size in MAJOR_COIN_DAILY_WINDOWS.items():
                if len(candles) < size:
                    continue
                scoped = candles[-size:]
                open_price = scoped[0]["open"]
                close_price = scoped[-1]["close"]
                if open_price <= 0:
                    continue
                volume_quote = sum(candle["volume_quote"] or 0 for candle in scoped)
                pct_change = (close_price - open_price) / open_price * 100
                direction = "long" if pct_change >= 0 else "short"
                rows.append(
                    (
                        "pct_change",
                        window,
                        inst_id,
                        direction,
                        pct_change,
                        volume_quote,
                        volume_quote / size,
                        open_price,
                        close_price,
                        scoped[0]["ts"],
                        scoped[-1]["ts"],
                    )
                )
    db.replace_major_coin_daily_rankings(rows)
    return len(rows)
