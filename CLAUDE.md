# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A mock of the "upstream" systems of an online shop, made for a data-engineering class. Students (the DE team) only start the stack and pull data out of it, usually from their own Airflow stack in a sibling folder (`../airflow`). They never edit this repo. `README.md` is the student-facing guide (in Thai). Keep it in sync with any behaviour change, and keep its tone: it describes the systems as if they were real third-party systems.

**The flaws are on purpose.** Flaky API responses, bad CSV rows, renamed columns and late reports exist so students have to handle them in their pipelines. Don't "fix" them unless you're asked to.

There is no build, lint or test tooling. Everything runs through Docker Compose.

## Commands

```bash
docker compose up -d --build                 # start everything (first run: downloads 154 MB dump, restores ~5 min)
docker compose up -d --build shop-api        # rebuild one service after editing its code
docker compose ps                            # shop-db healthy, partner-drop/shop-api running, shop-data exited (0)
docker compose logs -f partner-drop
docker compose down -v                       # wipe the DB volume; the next `up` restores the shop from scratch

# try the API (FLAKY_RATE=0 in .env turns off the random 429/503)
curl -H "X-API-Key: class-demo-key" "http://localhost:8000/v1/ad-spend?date=2026-10-01&page_size=100"
# DB as students see it
psql postgresql://student:student123@localhost:5432/shop
```

Ports and a few knobs come from `.env`, with defaults in `docker-compose.yaml`: `SHOP_DB_PORT`, `SHOP_API_PORT`, `DATA_URL`, `FLAKY_RATE`, `PARTNER_BROKEN_DATES`.

## Architecture

All services share the Docker network `data-sources`, which has a fixed name so other compose projects can join it as `external`. Everything runs on Bangkok time (`Asia/Bangkok`, UTC+7). All three sources follow the real clock, so there's no simulator process.

**`shop-data` → `shop-db`: the dump pipeline.**
- `shop-data` (curl image, `docker/shop-db/download.sh`) makes sure `data/shop_timeline.dump` exists and matches `data/shop_timeline.dump.sha256`, and downloads it from a GitHub Release in this repo (`mydeclass101/data-sources`, tag `timeline-v1`) if needed. The dump is git-ignored. If you publish a new dump, update the `.sha256` file too.
- `shop-db` runs `docker/shop-db/init/01_restore.sh` **only on an empty volume**. The script restores the dump and creates the read-only `student` role. Postgres sources the script (it doesn't run it as a separate process), so don't use `set -e` or a top-level `exit`.
- If the restore fails, the script touches `COURSE_DATA_MISSING` in the data dir and the healthcheck stays unhealthy. The only way to recover is `down -v` then `up`.
- Inside the dump, schema `shop_history` (hidden from students) holds every version of every row up to 2027-01-31. Each table in `public` is a view that shows the version valid at `now()`. That is why orders appear and change status over time.

**`partner-drop` (`docker/partner-drop/drop.py`)** checks every 60 s. At 01:00 on day D+1 it writes `inbox/marketplace/marketplace_orders_<D>.csv` for each day since `START_DATE` that hasn't been delivered yet.
- It reads SKUs and the price valid that day from `shop-db` (`products` joined to `product_price_history`, an SCD2 table). So it needs the DB to be healthy.
- It writes each file as `.part` and then renames it, so a visible file is always complete. It logs delivered days in `inbox/marketplace/.delivered`. Delete a line there (or the file) to deliver that day again.
- Output is seeded per day, so it's the same on every run. On days of the month divisible by 3 it adds 2 bad rows (unknown SKU, qty 0).
- For days listed in `BROKEN_DATES` it writes the file with renamed columns, then sends a correct `_v2.csv` at 10:00.

**`shop-api` (`docker/shop-api/app.py`, FastAPI)** serves daily ad spend per campaign. The campaign `channel` matches `customers.acquisition_channel` in the DB.
- Every endpoint needs the `X-API-Key` header.
- Responses are paginated and seeded per (date, campaign), so the same day always returns the same numbers.
- The report for day D is final at 05:00 on D+1. Before that the API returns `425`, and `404` for future days.
- `/v1/ad-spend` fails at random for a `FLAKY_RATE` share of requests (429 with `Retry-After`, or 503). `/v1/ad-spend/status` never fails at random; it's the endpoint a sensor should poll.

## Conventions

- `.gitattributes` forces LF line endings for `*.sh` and `*.sha256`, because they run in Linux containers and the repo is developed on Windows. Keep new shell scripts under that rule.
- Code comments are in English. Comments in `docker-compose.yaml` and `.env.example`, and the README, are in Thai because students read them.
- Container names start with `de7-`, and host ports bind to `127.0.0.1` only.
