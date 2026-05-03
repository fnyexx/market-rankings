import asyncio
import logging

from app import db
from app.config import settings
from app.okx_client import OkxClient

logger = logging.getLogger(__name__)


async def funding_loop() -> None:
    client = OkxClient()
    try:
        while True:
            await refresh_funding_rates(client)
            await asyncio.sleep(settings.funding_refresh_seconds)
    finally:
        await client.close()


async def refresh_funding_rates(client: OkxClient | None = None) -> int:
    owns_client = client is None
    client = client or OkxClient()
    updated = 0
    delay = 1 / max(settings.funding_requests_per_second, 0.1)
    try:
        for inst_id in db.list_instrument_ids():
            try:
                item = await client.get_funding_rate(inst_id)
                if not item:
                    continue
                db.update_instrument_funding(
                    inst_id=inst_id,
                    funding_rate=_optional_float(item.get("fundingRate")),
                    funding_time=_optional_int(item.get("fundingTime")),
                    next_funding_time=_optional_int(item.get("nextFundingTime")),
                )
                updated += 1
            except Exception:
                logger.exception("failed to refresh funding rate for %s", inst_id)
            await asyncio.sleep(delay)
        logger.info("refreshed funding rates for %s instruments", updated)
        return updated
    finally:
        if owns_client:
            await client.close()


def _optional_float(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _optional_int(value: str | None) -> int | None:
    if value in (None, ""):
        return None
    return int(value)
