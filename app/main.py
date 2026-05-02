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
) -> dict:
    return _ranking_response("pct_change", window, limit)


@app.get("/api/rankings/volume")
async def api_volume(
    window: str = Query("24h"),
    limit: int = Query(50, ge=1, le=500),
) -> dict:
    return _ranking_response("volume", window, limit)


def _ranking_response(metric: str, window: str, limit: int) -> dict:
    if window not in WINDOWS:
        raise HTTPException(status_code=400, detail=f"window must be one of {', '.join(WINDOWS)}")
    rows = db.query_rankings(metric, window, limit)
    return {
        "metric": metric,
        "window": window,
        "limit": limit,
        "collector_mode": settings.collector_mode,
        "data": [
            {
                "rank": index + 1,
                "inst_id": row["inst_id"],
                "pct_change": row["pct_change"],
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
