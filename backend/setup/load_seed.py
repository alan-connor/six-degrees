"""Load the seed CSV into Postgres.

Run once after create_tables.py, from the backend/ folder:
    python setup/load_seed.py

Idempotent: ON CONFLICT DO NOTHING means running it twice won't create
duplicates, so it's safe to re-run.
"""
import csv
import os
import sys

# db.py is in backend/, one level up from this setup/ folder.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db import get_connection

# The CSV lives at repo_root/data/. This file is at repo_root/backend/setup/,
# so climb three levels up to the repo root, then into data/.
CSV_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "rock_memberships_seed.csv",
)


def load():
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    conn = get_connection()
    with conn, conn.cursor() as cur:
        # 1. Insert every unique musician and band (duplicates ignored).
        musicians = {r["musician"] for r in rows}
        bands = {r["band"] for r in rows}
        # Seed rows have no mbid, so dedup against the partial unique index on
        # (name) WHERE mbid IS NULL (name alone is no longer unique -- homonyms).
        for name in musicians:
            cur.execute(
                "INSERT INTO musicians (name) VALUES (%s) "
                "ON CONFLICT (name) WHERE mbid IS NULL DO NOTHING",
                (name,),
            )
        for name in bands:
            cur.execute(
                "INSERT INTO bands (name) VALUES (%s) "
                "ON CONFLICT (name) WHERE mbid IS NULL DO NOTHING",
                (name,),
            )

        # 2. Build name -> id lookups so we can link the join table.
        cur.execute("SELECT id, name FROM musicians")
        musician_id = {name: mid for mid, name in cur.fetchall()}
        cur.execute("SELECT id, name FROM bands")
        band_id = {name: bid for bid, name in cur.fetchall()}

        # 3. Insert one membership per CSV row (duplicate links ignored).
        for r in rows:
            cur.execute(
                "INSERT INTO memberships "
                "(musician_id, band_id, instrument, year_from, year_to) "
                "VALUES (%s, %s, %s, %s, %s) "
                "ON CONFLICT (musician_id, band_id) DO NOTHING",
                (
                    musician_id[r["musician"]],
                    band_id[r["band"]],
                    r["instrument"] or None,
                    int(r["year_from"]) if r["year_from"] else None,
                    int(r["year_to"]) if r["year_to"] else None,
                ),
            )

    conn.close()
    print(
        f"Loaded {len(rows)} memberships "
        f"({len(musicians)} musicians, {len(bands)} bands)."
    )


if __name__ == "__main__":
    load()
