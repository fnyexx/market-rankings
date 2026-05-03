import asyncio
import logging

from app import db
from app.config import settings

logger = logging.getLogger(__name__)

WINDOWS = {"1h": 1, "2h": 2, "4h": 4, "12h": 12, "24h": 24}


def calculate_rankings() -> int:
    rows = []
    inst_ids = db.list_instrument_ids()
    with db.connect() as conn:
        for inst_id in inst_ids:
            candles = conn.execute(
                """
                SELECT ts, open, close, volume_quote
                FROM candles_1h
                WHERE inst_id = ? AND confirmed = 1
                ORDER BY ts DESC
                LIMIT 24
                """,
                (inst_id,),
            ).fetchall()
            candles = list(reversed(candles))
            for window, size in WINDOWS.items():
                if len(candles) < size:
                    continue
                scoped = candles[-size:]
                open_price = scoped[0]["open"]
                close_price = scoped[-1]["close"]
                if open_price <= 0:
                    continue
                pct_change = (close_price - open_price) / open_price * 100
                direction = "long" if pct_change >= 0 else "short"
                common = (
                    window,
                    inst_id,
                    direction,
                    pct_change,
                    open_price,
                    close_price,
                    scoped[0]["ts"],
                    scoped[-1]["ts"],
                )
                rows.append(("pct_change", *common))
    db.replace_rankings(rows)
    return len(rows)


async def ranking_loop() -> None:
    while True:
        try:
            count = calculate_rankings()
            logger.info("calculated %s ranking rows", count)
        except Exception:
            logger.exception("ranking calculation failed")
        await asyncio.sleep(settings.ranking_interval_seconds)
