#!/bin/sh
# shop-data service: make sure /data/shop_timeline.dump exists and is not corrupted.
# Downloads it on the first start (GitHub Release); later starts finish in a second.
DUMP=/data/shop_timeline.dump
cd /data || exit 1
check() { tr -d '\r' < shop_timeline.dump.sha256 | sha256sum -c - >/dev/null 2>&1; }

if [ -s "$DUMP" ] && check; then
    echo ">>> data file OK"
    exit 0
fi
echo ">>> downloading $DATA_URL ..."
curl -fL --retry 3 --progress-bar -o "$DUMP.part" "$DATA_URL" && mv "$DUMP.part" "$DUMP" || {
    echo "!!! download failed: download shop_timeline.dump yourself from the Releases page, put it in data/, then run docker compose up -d again"
    exit 1
}
check || { echo "!!! checksum mismatch: delete data/shop_timeline.dump and run docker compose up -d again"; exit 1; }
echo ">>> data file OK"
