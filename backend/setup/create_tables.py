"""Create the three tables: musicians, bands, memberships.

Run once during setup, from the backend/ folder:
    python setup/create_tables.py
Safe to run again -- CREATE TABLE IF NOT EXISTS won't clobber existing data.
"""
import os
import sys

# This script lives in backend/setup/, but db.py is in backend/.
# Add the parent folder (backend/) to the import path so "from db" works.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db import get_connection

# mbid/qid stay NULL until the crawler backfills them: an entity may be in
# MusicBrainz, Wikidata, both, or (like every seed row) neither.
#
# Identity is the MBID, NOT the name. name is NOT UNIQUE -- two different people
# or bands genuinely share a name (Mick Jones of Foreigner vs The Clash; the US
# glam Skid Row vs early Nirvana). A PARTIAL unique index keeps only the mbid-LESS
# rows (unreconciled seeds) unique by name, so the seed loader can still dedup;
# once a row has an mbid, homonyms with the same name are allowed.
SCHEMA = """
CREATE TABLE IF NOT EXISTS musicians (
    id   SERIAL PRIMARY KEY,
    mbid TEXT UNIQUE,
    qid  TEXT UNIQUE,
    name TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS musicians_seed_name_uniq
    ON musicians (name) WHERE mbid IS NULL;

CREATE TABLE IF NOT EXISTS bands (
    id      SERIAL PRIMARY KEY,
    mbid    TEXT UNIQUE,
    qid     TEXT UNIQUE,
    name    TEXT NOT NULL,
    is_rock BOOLEAN,           -- NULL = not yet fetched; set true/false on crawl
    genres  TEXT               -- display-only, comma-joined MB genres; is_rock is derived from these
);
CREATE UNIQUE INDEX IF NOT EXISTS bands_seed_name_uniq
    ON bands (name) WHERE mbid IS NULL;

CREATE TABLE IF NOT EXISTS memberships (
    musician_id INT REFERENCES musicians(id),
    band_id     INT REFERENCES bands(id),
    instrument  TEXT,
    year_from   INT,
    year_to     INT,
    PRIMARY KEY (musician_id, band_id)
);
"""


def main():
    conn = get_connection()
    # "with conn" commits the transaction if no error is raised.
    with conn, conn.cursor() as cur:
        cur.execute(SCHEMA)
    conn.close()
    print("Tables ready (created, or already existed).")


if __name__ == "__main__":
    main()
