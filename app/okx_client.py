import asyncio
import json
from collections.abc import AsyncIterator

import httpx
import websockets

from app.config import settings


class OkxClient:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(base_url=settings.okx_base_url, timeout=20)

    async def close(self) -> None:
        await self._client.aclose()

    async def get_swap_instruments(self) -> list[dict]:
        response = await self._client.get("/api/v5/public/instruments", params={"instType": "SWAP"})
        response.raise_for_status()
        payload = response.json()
        _raise_for_okx_error(payload)
        quote = settings.quote_ccy.upper()
        return [
            item
            for item in payload["data"]
            if item.get("state") == "live"
            and (item.get("quoteCcy") == quote or item.get("settleCcy") == quote)
        ]

    async def get_candles(self, inst_id: str, bar: str, limit: int) -> list[list[str]]:
        response = await self._client.get(
            "/api/v5/market/candles",
            params={"instId": inst_id, "bar": bar, "limit": limit},
        )
        response.raise_for_status()
        payload = response.json()
        _raise_for_okx_error(payload)
        return payload["data"]

    async def get_1h_candles(self, inst_id: str, limit: int | None = None) -> list[list[str]]:
        return await self.get_candles(inst_id, "1H", limit or settings.candles_limit)

    async def get_funding_rate(self, inst_id: str) -> dict | None:
        response = await self._client.get("/api/v5/public/funding-rate", params={"instId": inst_id})
        response.raise_for_status()
        payload = response.json()
        _raise_for_okx_error(payload)
        if not payload["data"]:
            return None
        return payload["data"][0]


async def stream_1h_candles(inst_ids: list[str]) -> AsyncIterator[tuple[str, list[str]]]:
    async with websockets.connect(settings.okx_ws_url, ping_interval=20, ping_timeout=20) as ws:
        for offset in range(0, len(inst_ids), settings.ws_subscribe_batch_size):
            batch = inst_ids[offset : offset + settings.ws_subscribe_batch_size]
            await ws.send(
                json.dumps(
                    {
                        "op": "subscribe",
                        "args": [{"channel": "candle1H", "instId": inst_id} for inst_id in batch],
                    }
                )
            )
            await asyncio.sleep(0.2)

        async for message in ws:
            payload = json.loads(message)
            if payload.get("event"):
                continue
            arg = payload.get("arg") or {}
            data = payload.get("data") or []
            inst_id = arg.get("instId")
            if not inst_id:
                continue
            for candle in data:
                yield inst_id, candle


def _raise_for_okx_error(payload: dict) -> None:
    if payload.get("code") != "0":
        raise RuntimeError(f"OKX API error {payload.get('code')}: {payload.get('msg')}")
