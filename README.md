# Data sources · ระบบต้นทางของร้านค้าออนไลน์

repo นี้คือระบบที่ **ทีม SWE และ partner** เป็นเจ้าของ ทีม DE (เรา) มีหน้าที่แค่เปิดใช้งานแล้วดึงข้อมูลออกไป
ไม่ต้องแก้โค้ดในนี้ เหมือนในงานจริงที่เราไม่ได้เป็นคนเขียนระบบต้นทาง

| แหล่งข้อมูล | คืออะไร | ต่อจากเครื่องเรา | ต่อจาก container อื่น (network `data-sources`) |
|---|---|---|---|
| `shop-db` | PostgreSQL ของร้าน | `localhost:5432` | `shop-db:5432` |
| `partner-drop` | partner วางไฟล์ CSV ยอดขายบน marketplace ทุกคืน | โฟลเดอร์ `inbox/marketplace/` | mount โฟลเดอร์นี้เข้าไป |
| `shop-api` | API ค่าโฆษณารายวัน | http://localhost:8000/docs | `http://shop-api:8000` |

รายละเอียดทุกตาราง คอลัมน์ และ ER diagram ดูใน [docs/data_dictionary.md](docs/data_dictionary.md)

**ร้านนี้มีชีวิต:** ข้อมูลเดินตามนาฬิกาจริง (เวลาไทย) ทุกนาทีจะมี order ใหม่ ลูกค้าใหม่ และ order เก่าเปลี่ยนสถานะ
ไปจนถึง **31 ม.ค. 2027** เปิดทิ้งไว้แล้วทุกวันจะมีข้อมูลของเมื่อวานเพิ่มเข้ามา

## 1. เปิดใช้งาน

ต้องมี Docker Desktop และ port 5432 กับ 8000 ต้องว่าง (ถ้าชน ดูข้อ 5)

```bash
git clone <url ของ repo นี้> data_sources
cd data_sources
docker compose up -d --build
docker compose ps
```

- ครั้งแรก ระบบจะดาวน์โหลดไฟล์ข้อมูลร้าน (154 MB) แล้ว restore เข้า database ใช้เวลาประมาณ 5 นาที
- พร้อมใช้เมื่อ `shop-db` ขึ้นสถานะ `healthy` และ `partner-drop` กับ `shop-api` ขึ้น `running`
- `shop-data` ขึ้น `exited (0)` คือปกติ (ตัวนี้ทำหน้าที่ดาวน์โหลดไฟล์ข้อมูลเสร็จแล้วก็จบไป)
- ดาวน์โหลดไม่ผ่าน: ไปโหลด `shop_timeline.dump` จากหน้า **Releases** ของ repo นี้ วางไว้ใน `data/` แล้วรัน `docker compose up -d` อีกครั้ง

## 2. `shop-db` · database ของร้าน

| | |
|---|---|
| host / port | `localhost:5432` (จากเครื่องเรา) · `shop-db:5432` (จาก container ใน network `data-sources`) |
| database | `shop` |
| user / password | `student` / `student123` (**อ่านอย่างเดียว**) |
| schema | `public` |

- เวลาในตาราง (`created_at`, `updated_at`, ...) เป็น **เวลาไทยแบบไม่มี timezone** (`timestamp without time zone`)
- เปิดด้วย DBeaver แล้วลองรันคำสั่งนี้สองครั้ง ห่างกันสัก 5 นาที จะเห็นว่าตัวเลขขยับเอง
  ```sql
  SELECT count(*), max(created_at), max(updated_at) FROM orders;
  ```

## 3. `partner-drop` · ไฟล์ยอดขายจาก marketplace partner

partner (Shopee / Lazada / TikTok Shop) วางไฟล์ไว้ในโฟลเดอร์ `inbox/marketplace/` ของ repo นี้

| | |
|---|---|
| ชื่อไฟล์ | `marketplace_orders_<YYYY-MM-DD>.csv` = order ของวันนั้นทั้งวัน |
| ส่งเมื่อไร | **01:00 น. (เวลาไทย) ของวันถัดไป** เช่น ไฟล์ของวันที่ 20 จะมาตอน 01:00 ของวันที่ 21 |
| ย้อนหลัง | ส่งให้ทุกวันตั้งแต่ 2026-09-25 ถ้าปิดเครื่องไปหลายวัน พอเปิดกลับมาจะส่งของวันที่ขาดไปให้ครบ |
| ส่งแก้ | ถ้า partner ต้องส่งไฟล์ของวันเดิมใหม่ จะตั้งชื่อเป็น `marketplace_orders_<YYYY-MM-DD>_v2.csv` |
| คอลัมน์ | `marketplace, order_ref, order_datetime, sku, qty, unit_price, platform_fee, status` |

- ไฟล์ที่มองเห็นในโฟลเดอร์คือไฟล์ที่เขียนเสร็จแล้วเสมอ (partner เขียนเป็นไฟล์ `.part` ก่อน เสร็จแล้วค่อยเปลี่ยนชื่อ)
- `order_datetime` เป็นเวลาไทย · `sku` ตรงกับ `products.sku` ใน `shop-db`
- **ห้ามแก้ ย้าย หรือลบไฟล์ในโฟลเดอร์นี้** เพราะเป็นของ partner (ไฟล์ `.delivered` คือบันทึกการส่งของ partner เอง)
- ดูว่า partner ส่งอะไรไปบ้าง: `docker compose logs partner-drop`

## 4. `shop-api` · API ค่าโฆษณา

ค่าโฆษณาที่ร้านจ่ายในแต่ละวัน แยกตาม campaign · คู่มือแบบลองยิงได้อยู่ที่ http://localhost:8000/docs (กดปุ่ม Authorize)

| | |
|---|---|
| base URL | `http://localhost:8000` (จากเครื่องเรา) · `http://shop-api:8000` (จาก container ใน network `data-sources`) |
| auth | header `X-API-Key: class-demo-key` (ไม่ส่ง = 401) |

| endpoint | ใช้ทำอะไร |
|---|---|
| `GET /v1/ad-spend/status?date=YYYY-MM-DD` | รายงานของวันนั้นพร้อมหรือยัง: `200` พร้อม · `425` ยังไม่พร้อม · `404` เป็นวันในอนาคต |
| `GET /v1/ad-spend?date=YYYY-MM-DD&page=1&page_size=5` | ค่าโฆษณาของวันนั้น แบ่งหน้า (`page_size` สูงสุด 100) ข้อมูลอยู่ใน `data` |
| `GET /v1/campaigns` | รายชื่อ campaign |

- รายงานของวัน D จะพร้อม (เป็นตัวเลขสุดท้าย) หลัง **05:00 น. ของวัน D+1** เวลาไทย
- เป็น API ของบริษัทภายนอก บางครั้งจะตอบ **429** (ยิงถี่เกินไป มี header `Retry-After` บอกเวลาที่ควรรอ) หรือ **503** (ระบบล่มชั่วคราว)
  ฝั่งที่ดึงข้อมูลต้องรองรับการ retry เอง · `/v1/ad-spend/status` ไม่เคยตอบ 429 หรือ 503
- ดึงวันเดิมซ้ำกี่ครั้งก็ได้ตัวเลขเหมือนเดิม

## 5. ต่อจาก Airflow หรือ container อื่น

stack นี้สร้าง docker network ชื่อ `data-sources` ไว้ให้ ถ้า container ของเราอยู่ใน network นี้ จะเรียก `shop-db` และ
`shop-api` ด้วยชื่อ service ได้เลย (ใช้ `localhost` ไม่ได้ เพราะใน container `localhost` หมายถึงตัว container เอง)

```yaml
# ใน docker-compose ของเรา
services:
  <service ที่ต้องต่อ>:
    networks: [default, data-sources]   # ต้องมี default ด้วย ไม่อย่างนั้นจะต่อ service อื่นใน compose ของเราเองไม่ได้

networks:
  data-sources:
    external: true                      # network นี้ stack data_sources เป็นคนสร้าง: ต้องเปิด data_sources ก่อน
```

ถ้าต้องอ่านไฟล์ของ partner ให้ mount โฟลเดอร์ `inbox/` ของ repo นี้เข้าไปใน container ของเรา
(ควร clone repo นี้ไว้ข้าง ๆ โปรเจกต์ของเรา เช่น `data-platform/data_sources` คู่กับ `data-platform/airflow`
แล้วอ้างถึงด้วย path แบบ `../data_sources/inbox`)

## 6. คำสั่งที่ใช้บ่อย

```bash
docker compose ps                       # สถานะ
docker compose logs -f partner-drop     # ดู log (ใช้กับ shop-db / shop-api ได้เหมือนกัน)
docker compose stop   /   docker compose start   # พัก / ใช้ต่อ (ข้อมูลยังอยู่)
docker compose down -v                  # ลบทุกอย่าง แล้ว restore ร้านใหม่ตั้งแต่ต้นตอนรัน up ครั้งหน้า
```

**port ชน** (เช่น มี Postgres ตัวอื่นใช้ 5432 อยู่): คัดลอก `.env.example` เป็น `.env` แล้วแก้ `SHOP_DB_PORT=5433`
จากนั้นรัน `docker compose up -d` อีกครั้ง (port นี้ใช้เฉพาะตอนต่อจากเครื่องเรา ถ้าต่อจาก container ใน network ยังเป็น `shop-db:5432` เหมือนเดิม)
# data-sources
