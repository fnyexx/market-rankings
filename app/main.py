import asyncio
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app import db
from app.collector import RestCollector, WebSocketCollector
from app.config import settings
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


@app.get("/rankings/volume", response_class=HTMLResponse)
async def volume_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "ranking.html",
        {"request": request, "title": "Market Rankings"},
    )


@app.get("/api/rankings/change")
async def api_change(
    window: str = Query("24h"),
    limit: int = Query(50, ge=1, le=500),
    direction: str | None = Query(None),
) -> dict:
    return _ranking_response("pct_change", window, limit, direction)


@app.get("/api/rankings/volume")
async def api_volume(
    window: str = Query("24h"),
    limit: int = Query(50, ge=1, le=500),
    direction: str | None = Query(None),
) -> dict:
    return _ranking_response("volume", window, limit, direction)


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


def _ranking_response(metric: str, window: str, limit: int, direction: str | None = None) -> dict:
    if window not in WINDOWS:
        raise HTTPException(status_code=400, detail=f"window must be one of {', '.join(WINDOWS)}")
    if direction not in (None, "long", "short"):
        raise HTTPException(status_code=400, detail="direction must be long or short")
    rows = db.query_rankings(metric, window, limit, direction)
    return {
        "metric": metric,
        "window": window,
        "direction": direction,
        "limit": limit,
        "collector_mode": settings.collector_mode,
        "data": [
            {
                "rank": index + 1,
                "inst_id": row["inst_id"],
                "direction": row["direction"],
                "pct_change": row["pct_change"],
                "abs_pct_change": abs(row["pct_change"] or 0),
                "volume_quote": row["volume_quote"],
                "open_price": row["open_price"],
                "close_price": row["close_price"],
                "start_ts": row["start_ts"],
                "end_ts": row["end_ts"],
                "calculated_at": row["calculated_at"],
            }
            for index, row in enumerate(rows)
        ],
    }
