#!/bin/bash
# Runs once, on the first start (empty volume): restore the shop and create the class user.
# Sourced by the postgres entrypoint, so avoid `set -e` / top-level `exit 0`.
#
# What is inside: schema shop_history keeps every version of every row (until 2027-01-31, hidden from students).
# Each table in public is a view that shows the version valid "now" (Bangkok time), so the shop moves on with
# the real clock: new orders appear, old orders change status - no simulator process needed.

restore_shop() {
    echo ">>> restoring the shop from /data/shop_timeline.dump (a few minutes, please wait) ..."
    # the dump creates schema public itself: drop the empty one of the new database first
    psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d shop -c "DROP SCHEMA public CASCADE" || return 1
    pg_restore -U "$POSTGRES_USER" -d shop --no-owner --no-acl --exit-on-error -j 2 /data/shop_timeline.dump || return 1
    psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d shop <<'SQL' || return 1
-- student: read the shop tables (a real source system is read-only for us)
CREATE ROLE student LOGIN PASSWORD 'student123';
GRANT CONNECT ON DATABASE shop TO student;
GRANT USAGE ON SCHEMA public TO student;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO student;
ANALYZE;
SQL
    echo ">>> shop restored"
}

if ! restore_shop; then
    # postgres will not re-run init scripts on this volume: keep the container unhealthy (see healthcheck)
    touch /var/lib/postgresql/data/COURSE_DATA_MISSING
    echo "!!! Could not load the course data. Fix data/shop_timeline.dump, then run:"
    echo "!!!     docker compose down -v"
    echo "!!!     docker compose up -d"
fi
