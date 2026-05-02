import asyncio
import logging
import time

from app import db
from app.config import settings
from app.okx_client import OkxClient, stream_1h_candles

logger = logging.getLogger(__name__)


class RestCollector:
    def __init__(self) -> None:
        self.client = OkxClient()
        self._last_instrument_refresh = 0.0

    async def run_forever(self) -> None:
        try:
            while True:
                await self.refresh_instruments_if_needed(force=not db.list_instrument_ids())
                inst_ids = db.list_instrument_ids()
                delay = 1 / max(settings.rest_requests_per_second, 0.1)
                for inst_id in inst_ids:
                    try:
                        candles = await self.client.get_1h_candles(inst_id)
                        db.upsert_candles(inst_id, candles)
                    except Exception:
                        logger.exception("failed to fetch candles for %s", inst_id)
                    await asyncio.sleep(delay)
        finally:
            await self.client.close()

    async def refresh_instruments_if_needed(self, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_instrument_refresh < settings.instruments_refresh_seconds:
            return
        instruments = await self.client.get_swap_instruments()
        db.upsert_instruments(instruments)
        self._last_instrument_refresh = now
        logger.info("refreshed %s instruments", len(instruments))


class WebSocketCollector:
    def __init__(self) -> None:
        self.client = OkxClient()

    async def run_forever(self) -> None:
        reconnect_delay = settings.ws_reconnect_initial_seconds
        try:
            while True:
                try:
                    instruments = await self.client.get_swap_instruments()
                    db.upsert_instruments(instruments)
                    inst_ids = db.list_instrument_ids()
                    if not inst_ids:
                        logger.warning("no websocket instruments found; retrying in %s seconds", reconnect_delay)
                        await asyncio.sleep(reconnect_delay)
                        reconnect_delay = self._next_reconnect_delay(reconnect_delay)
                        continue

                    logger.info("connecting websocket collector for %s instruments", len(inst_ids))
                    reconnect_delay = settings.ws_reconnect_initial_seconds
                    async for inst_id, candle in stream_1h_candles(inst_ids):
                        db.upsert_candles(inst_id, [candle])
                except Exception:
                    logger.exception(
                        "websocket collector disconnected; reconnecting in %s seconds",
                        reconnect_delay,
                    )
                    await asyncio.sleep(reconnect_delay)
                    reconnect_delay = self._next_reconnect_delay(reconnect_delay)
        finally:
            await self.client.close()

    def _next_reconnect_delay(self, current_delay: int) -> int:
        return min(current_delay * 2, settings.ws_reconnect_max_seconds)
