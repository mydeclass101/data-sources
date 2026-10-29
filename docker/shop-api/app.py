"""Mock shop API: how much the shop paid for online ads each day, per campaign.

Behaves like a real third-party API on purpose:
  - needs an API key in the X-API-Key header           -> 401 without it
  - results are paginated (page, page_size, total_pages)
  - randomly rate-limits (429 + Retry-After) or fails (503) -> clients must retry
  - lives on real (Bangkok) time: a day's report is final only after REPORT_READY_HOUR (05:00) the next day
  - /v1/ad-spend/status?date= tells whether a day is final (never flaky: what a sensor should poll)
    -> 425 Too Early before that, 404 for future days
Numbers are deterministic per (date, campaign): pulling the same day twice returns the same data.
"""
import os
import random
from datetime import date, datetime, timedelta, timezone

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import JSONResponse

API_KEY = os.getenv("API_KEY", "class-demo-key")
FLAKY_RATE = float(os.getenv("FLAKY_RATE", "0.25"))          # share of data requests that fail on purpose
MIN_DATE = date.fromisoformat(os.getenv("MIN_DATE", "2025-01-01"))
REPORT_READY_HOUR = int(os.getenv("REPORT_READY_HOUR", "5"))        # yesterday's report is final at 05:00 Bangkok
BANGKOK = timezone(timedelta(hours=7))

# campaign_id, channel (= customers.acquisition_channel), name, typical daily spend (THB)
CAMPAIGNS = [
    ("GGL-SEARCH-BRAND", "google_ads", "Search - Brand keywords", 1800),
    ("GGL-SEARCH-GENERIC", "google_ads", "Search - Generic keywords", 2600),
    ("GGL-PMAX", "google_ads", "Performance Max", 2200),
    ("GGL-YOUTUBE", "google_ads", "YouTube awareness", 1500),
    ("FB-PROSPECT", "facebook_ads", "Prospecting - Lookalike", 2100),
    ("FB-RETARGET", "facebook_ads", "Retargeting - Cart abandoners", 900),
    ("FB-CATALOG", "facebook_ads", "Dynamic catalog ads", 1600),
    ("TT-SPARK", "tiktok", "Spark Ads - Creators", 3200),
    ("TT-LIVE", "tiktok", "Live shopping boost", 2500),
    ("TT-INFEED", "tiktok", "In-feed video", 1900),
    ("LINE-BROADCAST", "line_oa", "LINE OA broadcast", 700),
    ("LINE-LAP", "line_oa", "LINE Ads Platform", 1300),
]

app = FastAPI(title="Shop Ads API (mock)", version="1.0")


def check_key(x_api_key: str | None) -> None:
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="missing or invalid API key (header X-API-Key)")


def maybe_fail() -> JSONResponse | None:
    if random.random() >= FLAKY_RATE:
        return None
    if random.random() < 0.7:
        return JSONResponse({"error": "rate limit exceeded, slow down"}, status_code=429, headers={"Retry-After": "1"})
    return JSONResponse({"error": "service temporarily unavailable"}, status_code=503)


def report_ready_at(day: date) -> datetime:
    """The report of `day` is final at REPORT_READY_HOUR the next morning (Bangkok)."""
    return datetime.combine(day + timedelta(days=1), datetime.min.time(), BANGKOK) + timedelta(hours=REPORT_READY_HOUR)


def spend_row(day: date, campaign: tuple) -> dict:
    campaign_id, channel, name, base = campaign
    rng = random.Random(f"{day.isoformat()}|{campaign_id}")
    weekend = 1.25 if day.weekday() >= 5 else 1.0
    spend = round(base * weekend * rng.uniform(0.7, 1.3), 2)
    impressions = int(spend * rng.uniform(8, 15))
    clicks = int(impressions * rng.uniform(0.008, 0.03))
    return {"date": day.isoformat(), "campaign_id": campaign_id, "campaign_name": name, "channel": channel,
            "impressions": impressions, "clicks": clicks, "spend": spend}


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/v1/campaigns")
def campaigns(x_api_key: str | None = Header(default=None)) -> dict:
    check_key(x_api_key)
    return {"data": [{"campaign_id": c[0], "channel": c[1], "campaign_name": c[2]} for c in CAMPAIGNS]}


@app.get("/v1/ad-spend/status")
def ad_spend_status(
    date_: date = Query(alias="date", description="report date, YYYY-MM-DD"),
    x_api_key: str | None = Header(default=None),
):
    """Is the report of this day final? 200 = yes, 425 = not yet, 404 = future day. Never flaky (cheap endpoint)."""
    check_key(x_api_key)
    now = datetime.now(BANGKOK)
    ready_at = report_ready_at(date_)
    if date_ > now.date():
        raise HTTPException(status_code=404, detail=f"no report for a future day ({date_})")
    if now < ready_at:
        return JSONResponse({"date": date_.isoformat(), "ready": False, "ready_at": f"{ready_at:%Y-%m-%d %H:%M}"},
                            status_code=425, headers={"Retry-After": "600"})
    return {"date": date_.isoformat(), "ready": True}


@app.get("/v1/ad-spend")
def ad_spend(
    date_: date = Query(alias="date", description="report date, YYYY-MM-DD"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=5, ge=1, le=100),
    x_api_key: str | None = Header(default=None),
):
    check_key(x_api_key)
    if date_ < MIN_DATE:
        raise HTTPException(status_code=400, detail=f"date must be on or after {MIN_DATE}")
    now = datetime.now(BANGKOK)
    ready_at = report_ready_at(date_)
    if date_ > now.date():
        raise HTTPException(status_code=404, detail=f"no report for a future day ({date_})")
    if now < ready_at:
        message = f"report for {date_} is not final yet, try again after {ready_at:%Y-%m-%d %H:%M} (Bangkok)"
        return JSONResponse({"error": message}, status_code=425, headers={"Retry-After": "600"})
    failure = maybe_fail()
    if failure is not None:
        return failure

    rows = [spend_row(date_, c) for c in CAMPAIGNS]
    total_pages = (len(rows) + page_size - 1) // page_size
    start = (page - 1) * page_size
    return {"date": date_.isoformat(), "currency": "THB", "page": page, "page_size": page_size,
            "total_pages": total_pages, "total_records": len(rows), "data": rows[start:start + page_size]}
