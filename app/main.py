import asyncio
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app import db
from app.collector import RestCollector, WebSocketCollector
from app.config import settings
from app.funding import funding_loop
from app.major_coins import MAJOR_COIN_DAILY_WINDOWS, MAJOR_COIN_WINDOWS, major_coin_daily_loop, major_coin_loop
from app.rankings import WINDOWS, ranking_loop

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Market Rankings")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


@app.on_event("startup")
async def startup() -> None:
    db.init_db()
    collector = WebSocketCollector() if settings.collector_mode == "websocket" else RestCollector()
    asyncio.create_task(collector.run_forever())
    asyncio.create_task(ranking_loop())
    if settings.funding_enabled:
        asyncio.create_task(funding_loop())
    asyncio.create_task(major_coin_loop())
    asyncio.create_task(major_coin_daily_loop())


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "ranking.html",
        {"request": request, "title": "Market Rankings"},
    )


@app.get("/rankings/change", response_class=HTMLResponse)
async def change_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "ranking.html",
        {"request": request, "title": "Market Rankings"},
    )


@app.get("/rankings/major-coins", response_class=HTMLResponse)
async def major_coin_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "major_coin_ranking.html",
        {"request": request, "title": "主流币涨跌幅"},
    )


@app.get("/api/rankings/change")
async def api_change(
    window: str = Query("24h"),
    limit: int = Query(50, ge=1, le=2000),
    direction: str | None = Query(None),
    sort_by_funding_rate: bool = Query(False),
    sort_by_funding_time: bool = Query(False),
) -> dict:
    return _ranking_response(
        window,
        limit,
        direction,
        sort_by_funding_rate,
        sort_by_funding_time,
    )


@app.get("/api/major-coins/rankings/change")
async def api_major_coin_change(
    window: str = Query("30m"),
    limit: int = Query(50, ge=1, le=500),
    direction: str | None = Query(None),
) -> dict:
    return _major_coin_ranking_response(window, limit, direction)


@app.get("/api/major-coins/daily-rankings/change")
async def api_major_coin_daily_change(
    window: str = Query("30d"),
    limit: int = Query(50, ge=1, le=500),
    direction: str | None = Query(None),
) -> dict:
    return _major_coin_daily_ranking_response(window, limit, direction)


@app.get("/api/major-coins/candles")
async def api_major_coin_candles(
    inst_id: str = Query(..., min_length=1),
    limit: int = Query(30, ge=1, le=1000),
) -> dict:
    inst_id = inst_id.upper()
    rows = db.query_major_coin_candles(inst_id, limit)
    return _candles_response(inst_id, "1m", limit, rows)


@app.get("/api/major-coins/daily-candles")
async def api_major_coin_daily_candles(
    inst_id: str = Query(..., min_length=1),
    limit: int = Query(30, ge=1, le=1000),
) -> dict:
    inst_id = inst_id.upper()
    rows = db.query_major_coin_daily_candles(inst_id, limit)
    return _candles_response(inst_id, "1D", limit, rows)


def _candles_response(inst_id: str, bar: str, limit: int, rows) -> dict:
    return {
        "inst_id": inst_id,
        "bar": bar,
        "limit": limit,
        "data": [
            {
                "ts": row["ts"],
                "open": row["open"],
                "high": row["high"],
                "low": row["low"],
                "close": row["close"],
                "volume_contract": row["volume_contract"],
                "volume_base": row["volume_base"],
                "volume_quote": row["volume_quote"],
                "confirmed": row["confirmed"],
                "fetched_at": row["fetched_at"],
            }
            for row in rows
        ],
    }


@app.get("/api/instruments")
async def api_instruments(
    query: str = Query(""),
    limit: int = Query(500, ge=1, le=2000),
) -> dict:
    rows = db.list_instruments(query, limit)
    return {
        "query": query,
        "limit": limit,
        "data": [
            {
                "inst_id": row["inst_id"],
                "base_ccy": row["base_ccy"],
                "quote_ccy": row["quote_ccy"],
                "settle_ccy": row["settle_ccy"],
                "state": row["state"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ],
    }


@app.get("/api/candles")
async def api_candles(
    inst_id: str = Query(..., min_length=1),
    limit: int = Query(100, ge=1, le=1000),
) -> dict:
    inst_id = inst_id.upper()
    rows = db.query_candles(inst_id, limit)
    return {
        "inst_id": inst_id,
        "bar": "1H",
        "limit": limit,
        "data": [
            {
                "ts": row["ts"],
                "open": row["open"],
                "high": row["high"],
                "low": row["low"],
                "close": row["close"],
                "volume_contract": row["volume_contract"],
                "volume_base": row["volume_base"],
                "volume_quote": row["volume_quote"],
                "confirmed": row["confirmed"],
                "fetched_at": row["fetched_at"],
            }
            for row in rows
        ],
    }


def _major_coin_ranking_response(
    window: str,
    limit: int,
    direction: str | None = None,
) -> dict:
    if window not in MAJOR_COIN_WINDOWS:
        raise HTTPException(status_code=400, detail=f"window must be one of {', '.join(MAJOR_COIN_WINDOWS)}")
    if direction not in (None, "long", "short"):
        raise HTTPException(status_code=400, detail="direction must be long or short")
    rows = db.query_major_coin_rankings(window, limit, direction)
    direction_counts = db.count_major_coin_ranking_directions(window)
    return {
        "metric": "pct_change",
        "window": window,
        "direction": direction,
        "direction_counts": direction_counts,
        "limit": limit,
        "configured_inst_ids": settings.major_coin_inst_ids,
        "poll_interval_seconds": settings.major_coin_daily_poll_interval_seconds,
        "data": [
            {
                "rank": index + 1,
                "inst_id": row["inst_id"],
                "direction": row["direction"],
                "pct_change": row["pct_change"],
                "abs_pct_change": abs(row["pct_change"] or 0),
                "volume_quote": row["volume_quote"],
                "avg_minute_volume_quote": row["avg_minute_volume_quote"],
                "open_price": row["open_price"],
                "close_price": row["close_price"],
                "start_ts": row["start_ts"],
                "end_ts": row["end_ts"],
                "calculated_at": row["calculated_at"],
            }
            for index, row in enumerate(rows)
        ],
    }


def _major_coin_daily_ranking_response(
    window: str,
    limit: int,
    direction: str | None = None,
) -> dict:
    if window not in MAJOR_COIN_DAILY_WINDOWS:
        raise HTTPException(status_code=400, detail=f"window must be one of {', '.join(MAJOR_COIN_DAILY_WINDOWS)}")
    if direction not in (None, "long", "short"):
        raise HTTPException(status_code=400, detail="direction must be long or short")
    rows = db.query_major_coin_daily_rankings(window, limit, direction)
    direction_counts = db.count_major_coin_daily_ranking_directions(window)
    return {
        "metric": "pct_change",
        "window": window,
        "direction": direction,
        "direction_counts": direction_counts,
        "limit": limit,
        "configured_inst_ids": settings.major_coin_inst_ids,
        "poll_interval_seconds": settings.major_coin_poll_interval_seconds,
        "data": [
            {
                "rank": index + 1,
                "inst_id": row["inst_id"],
                "direction": row["direction"],
                "pct_change": row["pct_change"],
                "abs_pct_change": abs(row["pct_change"] or 0),
                "volume_quote": row["volume_quote"],
                "avg_daily_volume_quote": row["avg_daily_volume_quote"],
                "open_price": row["open_price"],
                "close_price": row["close_price"],
                "start_ts": row["start_ts"],
                "end_ts": row["end_ts"],
                "calculated_at": row["calculated_at"],
            }
            for index, row in enumerate(rows)
        ],
    }


def _ranking_response(
    window: str,
    limit: int,
    direction: str | None = None,
    sort_by_funding_rate: bool = False,
    sort_by_funding_time: bool = False,
) -> dict:
    if window not in WINDOWS:
        raise HTTPException(status_code=400, detail=f"window must be one of {', '.join(WINDOWS)}")
    if direction not in (None, "long", "short"):
        raise HTTPException(status_code=400, detail="direction must be long or short")
    rows = db.query_rankings(window, limit, direction, sort_by_funding_rate, sort_by_funding_time)
    direction_counts = db.count_ranking_directions(window)
    window_hours = WINDOWS[window]
    return {
        "metric": "pct_change",
        "window": window,
        "direction": direction,
        "direction_counts": direction_counts,
        "sort_by_funding_rate": sort_by_funding_rate,
        "sort_by_funding_time": sort_by_funding_time,
        "limit": limit,
        "collector_mode": settings.collector_mode,
        "funding_enabled": settings.funding_enabled,
        "data": [
            {
                "rank": index + 1,
                "inst_id": row["inst_id"],
                "direction": row["direction"],
                "pct_change": row["pct_change"],
                "abs_pct_change": abs(row["pct_change"] or 0),
                "volume_quote": row["volume_quote"],
                "avg_hourly_volume_quote": (row["volume_quote"] or 0) / window_hours,
                "open_price": row["open_price"],
                "close_price": row["close_price"],
                "funding_rate": row["funding_rate"],
                "abs_funding_rate": abs(row["funding_rate"]) if row["funding_rate"] is not None else None,
                "funding_interval_hours": row["funding_interval_hours"],
                "funding_time": row["funding_time"],
                "next_funding_time": row["next_funding_time"],
                "funding_updated_at": row["funding_updated_at"],
                "start_ts": row["start_ts"],
                "end_ts": row["end_ts"],
                "calculated_at": row["calculated_at"],
            }
            for index, row in enumerate(rows)
        ],
    }
