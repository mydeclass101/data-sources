"""The marketplace partner: every night it drops yesterday's orders as a CSV into our SFTP-style inbox.

At DROP_HOUR (01:00 Bangkok) on day D+1 it writes inbox/marketplace/marketplace_orders_<D>.csv for every finished
day D since START_DATE that was not delivered yet (real SKUs + the price valid that day, from the shop database).
The file appears atomically (written as .part, then renamed), so a file you can see is always complete.
If the machine was off for a few days, the next start delivers every missing day at once.

Like a real partner, the files are not always perfect (deterministic per day, so the instructor knows in advance):
  - day of month divisible by 3: 2 bad rows (unknown SKU, qty 0) -> silver labels them in column `problem`
  - BROKEN_DATES (env, comma separated): the partner renamed the columns -> the pipeline must reject the file.
    They notice and send a fixed file marketplace_orders_<D>_v2.csv at FIX_HOUR (10:00) the same morning.
"""
from __future__ import annotations

import csv
import os
import random
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import psycopg

BANGKOK = timezone(timedelta(hours=7))
INBOX = Path(os.getenv("INBOX", "/inbox/marketplace"))
STATE = INBOX / ".delivered"                      # days already delivered (the partner's own log)
START_DATE = date.fromisoformat(os.getenv("START_DATE", "2026-09-25"))
DROP_HOUR = int(os.getenv("DROP_HOUR", "1"))
FIX_HOUR = int(os.getenv("FIX_HOUR", "10"))
BROKEN_DATES = {d.strip() for d in os.getenv("BROKEN_DATES", "").split(",") if d.strip()}
DSN = os.getenv("SHOP_DSN", "postgresql://student:student123@shop-db:5432/shop")
MARKETPLACES = [("shopee", 0.5, 0.12), ("lazada", 0.3, 0.10), ("tiktok_shop", 0.2, 0.08)]   # name, share, fee rate
COLUMNS = ["marketplace", "order_ref", "order_datetime", "sku", "qty", "unit_price", "platform_fee", "status"]


def log(msg: str) -> None:
    print(f"{datetime.now(BANGKOK):%Y-%m-%d %H:%M:%S} {msg}", flush=True)


def due(now: datetime) -> list[tuple[date, bool]]:
    """(day, is_fix) still to deliver: the normal file at 01:00 on D+1, the fixed _v2 of a broken day at 10:00."""
    delivered = set(STATE.read_text().split()) if STATE.exists() else set()
    now = now.replace(tzinfo=None)
    out, day = [], START_DATE
    while datetime.combine(day + timedelta(days=1), datetime.min.time()) + timedelta(hours=DROP_HOUR) <= now:
        if day.isoformat() not in delivered:
            out.append((day, False))
        fix_at = datetime.combine(day + timedelta(days=1), datetime.min.time()) + timedelta(hours=FIX_HOUR)
        if day.isoformat() in BROKEN_DATES and fix_at <= now and f"{day}:v2" not in delivered:
            out.append((day, True))
        day += timedelta(days=1)
    return out


def products_on(day: date) -> list[tuple[str, float]]:
    """Active SKUs and the price that was valid that day (product_price_history = SCD2)."""
    with psycopg.connect(DSN) as conn:
        return conn.execute("""
            SELECT p.sku, h.unit_price FROM products p
            JOIN product_price_history h ON h.product_id = p.product_id
             AND h.valid_from <= %(t)s AND (h.valid_to IS NULL OR h.valid_to > %(t)s)
            WHERE p.status = 'active' AND p.launched_at <= %(t)s
            ORDER BY p.product_id""", {"t": datetime.combine(day, datetime.min.time())}).fetchall()


def make_rows(day: date) -> list[list]:
    rng = random.Random(f"marketplace|{day}")
    catalogue = products_on(day)
    popular = random.Random(20260927).sample(catalogue, min(300, len(catalogue)))
    rows = []
    for n in range(rng.randint(40, 70)):
        name, _, fee = rng.choices(MARKETPLACES, weights=[m[1] for m in MARKETPLACES])[0]
        ts = datetime.combine(day, datetime.min.time()) + timedelta(seconds=rng.randint(0, 86399))
        ref = f"{name[:2].upper()}{day:%y%m%d}{n:04d}"
        status = rng.choices(["completed", "shipped", "cancelled"], weights=[70, 22, 8])[0]
        for sku, price in rng.sample(popular, rng.choice([1, 1, 1, 2])):
            qty = rng.choice([1, 1, 1, 2, 3])
            unit = round(float(price) * rng.uniform(0.95, 1.05), 2)
            rows.append([name, ref, ts.strftime("%Y-%m-%d %H:%M:%S"), sku, qty, f"{unit:.2f}",
                         f"{unit * qty * fee:.2f}", status])
    if day.day % 3 == 0:                                     # the partner's own data-quality problems
        rows.append(["shopee", f"SH{day:%y%m%d}9998", f"{day} 12:00:00", "XXX-NOSKU-00000", 1, "199.00", "23.88",
                     "completed"])
        sku, price = popular[0]
        rows.append(["lazada", f"LA{day:%y%m%d}9999", f"{day} 13:30:00", sku, 0, f"{float(price):.2f}", "0.00",
                     "completed"])
    rows.sort(key=lambda r: r[2])
    return rows


def deliver(day: date, is_fix: bool) -> None:
    rows = make_rows(day)
    header = COLUMNS
    if day.isoformat() in BROKEN_DATES and not is_fix:       # partner changed their export: wrong column names
        header = ["shop", "order_ref", "order_time", "sku", "quantity", "price", "fee", "state"]
    path = INBOX / f"marketplace_orders_{day}{'_v2' if is_fix else ''}.csv"
    tmp = path.with_suffix(".part")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)
    tmp.rename(path)                                         # appear atomically: never a half-written file
    with STATE.open("a") as f:
        f.write(f"{day}{':v2' if is_fix else ''}\n")
    log(f"dropped {path.name} ({len(rows)} rows{', BROKEN columns' if header != COLUMNS else ''})")


def main() -> None:
    INBOX.mkdir(parents=True, exist_ok=True)
    log(f"partner started: files from {START_DATE}, every day at {DROP_HOUR:02d}:00 into {INBOX}"
        f" (broken files on {', '.join(sorted(BROKEN_DATES)) or '-'}, fixed at {FIX_HOUR:02d}:00)")
    while True:
        try:
            for day, is_fix in due(datetime.now(BANGKOK)):
                deliver(day, is_fix)
        except Exception as exc:                             # e.g. the shop database is restarting
            log(f"delivery failed, retrying in a minute: {exc!r}")
        time.sleep(60)


if __name__ == "__main__":
    main()
