"""Phase 1: snowball crawler that grows the network from MusicBrainz.

Runs in bounded batches so it's friendly to a 1 req/sec API and can be put on a
schedule (Task Scheduler on Windows). Each run pops up to --limit entities off a
persistent queue, fetches them, writes results to Postgres, and enqueues their
rock-genre neighbours for a future run. Ctrl-C safe: unfinished rows stay
'pending' and the next run resumes.

Typical use, turning the knob up as you trust it:
    python crawl.py --seed              # bootstrap the queue from seed bands (once)
    python crawl.py --limit 1           # watch ONE fetch end to end
    python crawl.py --limit 10          # confidence
    python crawl.py --limit 500         # ~15 min; hand this to the scheduler

The queue IS the BFS frontier from bfs_demo/graph.py -- persisted to a table and
spread over time instead of living in an in-memory deque.

BEFORE trusting the numbers: run --limit 1 and eyeball the parsed output against
the raw cached JSON in data/cache/. The MusicBrainz relationship shape is fiddly
and the parse functions below are marked where they need your verification.
"""
import argparse
import json
import os
import re
import sys
import time

import requests

from db import get_connection
from rock_genres import is_rock

# --- Config ---------------------------------------------------------------

# A real, contactable User-Agent is MANDATORY. Anonymous agents get throttled
# into a shared bucket and can be blocked by identifier. Format: app/ver (contact).
# Set MB_CONTACT to your own email or URL when running your own crawl.
MB_CONTACT = os.environ.get("MB_CONTACT", "https://github.com/alan-connor/six-degrees")
HEADERS = {"User-Agent": f"SixDegreesOfRock/0.1 ( {MB_CONTACT} )"}

MB_BASE = "https://musicbrainz.org/ws/2"
MIN_INTERVAL = 1.1          # seconds between live requests (stay under 1/sec/IP)
MAX_503_RETRIES = 3

# Disk cache keyed by MBID. Makes re-runs during development cost zero requests.
# Add data/cache/ to .gitignore.
CACHE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cache"
)

_last_request_at = 0.0      # module-global rate-limit clock


# --- HTTP + cache ---------------------------------------------------------

def _rate_limit():
    """Sleep just enough to keep live requests >= MIN_INTERVAL apart."""
    global _last_request_at
    wait = MIN_INTERVAL - (time.monotonic() - _last_request_at)
    if wait > 0:
        time.sleep(wait)
    _last_request_at = time.monotonic()


def mb_get(path, params, cache_key):
    """GET from MusicBrainz with on-disk caching, rate limiting, and 503 retry.

    Returns parsed JSON, or None if the fetch ultimately failed (caller requeues).
    cache_key is usually the MBID; cached responses skip the network entirely.
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(CACHE_DIR, f"{cache_key}.json")
    if os.path.exists(cache_path):
        with open(cache_path, encoding="utf-8") as f:
            return json.load(f)

    params = {**params, "fmt": "json"}
    for attempt in range(MAX_503_RETRIES):
        _rate_limit()
        r = requests.get(f"{MB_BASE}/{path}", headers=HEADERS, params=params, timeout=30)
        if r.status_code == 503:            # rate limited -- back off and retry
            time.sleep(2 * (attempt + 1))
            continue
        r.raise_for_status()
        r.encoding = "utf-8"                 # MB is UTF-8; don't let requests guess
        data = r.json()
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        return data
    return None                             # exhausted retries


# --- Name normalization (for reconciling against seed rows) ---------------

def normalize_name(name):
    """Casefold and strip non-alphanumerics so 'John Mayall's Bluesbreakers'
    can match MusicBrainz's 'John Mayall & the Bluesbreakers'. Used ONLY for
    matching; the display name stored in the DB is left untouched."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


# --- Entity resolution: mbid -> qid -> normalized name -> insert ----------
# qid is skipped here because MusicBrainz never supplies it; it becomes relevant
# only if/when a Wikidata source path is added (pull P434 there to bridge them).

def resolve(cur, table, mbid, name):
    """Return the row id for this entity, creating or backfilling as needed.

    1. match by mbid -> return id
    2. match by name ONLY when the existing row has no mbid yet (an unreconciled
       seed row) -> backfill its mbid, return id
    3. insert a new row -> return id

    Identity is the MBID. The name fallback exists ONLY to reconcile seed rows
    (which start mbid-less) with their first crawl. It must NOT match a row that
    already carries a *different* mbid -- that's a homonym (two "Mick Jones", two
    "Skid Row"), a distinct entity that gets its own row.
    """
    if mbid:
        cur.execute(f"SELECT id FROM {table} WHERE mbid = %s", (mbid,))
        hit = cur.fetchone()
        if hit:
            return hit[0]

    cur.execute(
        f"SELECT id FROM {table} "
        f"WHERE regexp_replace(lower(name), '[^a-z0-9]', '', 'g') = %s AND mbid IS NULL",
        (normalize_name(name),),
    )
    hit = cur.fetchone()
    if hit:
        row_id = hit[0]
        if mbid:                            # backfill the seed row's missing id
            cur.execute(f"UPDATE {table} SET mbid = %s WHERE id = %s", (mbid, row_id))
        return row_id

    cur.execute(
        f"INSERT INTO {table} (mbid, name) VALUES (%s, %s) RETURNING id", (mbid, name)
    )
    return cur.fetchone()[0]


# --- MusicBrainz JSON parsing --------------------------------------------
# VERIFY THESE on your first --limit 1 run against the raw JSON in data/cache/.
# Both a band and a person are "artists"; the link is a "member of band"
# relation. For a Group the counterparties are its members (persons); for a
# Person they are the bands. So one fetch shape, branch on counterparty type.

def fetch_artist(mbid):
    """Fetch an artist with its band-membership relations and genre tags."""
    return mb_get(f"artist/{mbid}", {"inc": "artist-rels+genres"}, mbid)


def _year(date_str):
    """'1975-03-01' or '1975' -> 1975; '' / None -> None."""
    if not date_str:
        return None
    m = re.match(r"(\d{4})", date_str)
    return int(m.group(1)) if m else None


def parse_memberships(artist):
    """Yield one dict per (person, band) link from a fetched artist.

    Aggregates instruments per counterparty so a person listed under several
    instrument relations becomes ONE membership row -- otherwise the second row
    hits ON CONFLICT (musician_id, band_id) DO NOTHING and vanishes silently.

    Returns dicts: {counterparty_mbid, counterparty_name, counterparty_kind
    ('group'|'person'), instrument, year_from, year_to}.
    """
    agg = {}
    for rel in artist.get("relations", []):
        if rel.get("type") != "member of band":
            continue
        other = rel.get("artist", {})
        mbid = other.get("id")
        if not mbid:
            continue
        entry = agg.setdefault(mbid, {
            "counterparty_mbid": mbid,
            "counterparty_name": other.get("name", ""),
            "counterparty_kind": (other.get("type") or "").lower(),  # 'group'/'person'
            "instruments": [],
            "year_from": _year(rel.get("begin")),
            "year_to": _year(rel.get("end")),
        })
        entry["instruments"].extend(rel.get("attributes", []))

    for e in agg.values():
        instruments = "/".join(dict.fromkeys(e.pop("instruments"))) or None  # dedupe, keep order
        yield {**e, "instrument": instruments}


def genre_names(artist):
    """Lowercase genre tag names from a fetched artist (may be empty)."""
    return [g["name"] for g in artist.get("genres", [])]


# --- Crawl queue (persistent BFS frontier) --------------------------------
# Kept here rather than in create_tables.py because it's operational state, not
# domain data. Move it there if you'd rather keep all schema in one place.

QUEUE_SCHEMA = """
CREATE TABLE IF NOT EXISTS crawl_queue (
    entity_type TEXT NOT NULL,               -- 'band' | 'musician'
    mbid        TEXT NOT NULL,
    name        TEXT,
    depth       INT  NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',  -- pending | done | skipped | error
    retries     INT  NOT NULL DEFAULT 0,
    PRIMARY KEY (entity_type, mbid)          -- dedupe overlapping discoveries
);
"""


def ensure_queue(conn):
    with conn, conn.cursor() as cur:
        cur.execute(QUEUE_SCHEMA)


def enqueue(cur, entity_type, mbid, name, depth):
    """Add a neighbour to the frontier. ON CONFLICT DO NOTHING means an entity
    already seen (at any status) is never re-queued."""
    cur.execute(
        "INSERT INTO crawl_queue (entity_type, mbid, name, depth) "
        "VALUES (%s, %s, %s, %s) ON CONFLICT (entity_type, mbid) DO NOTHING",
        (entity_type, mbid, name, depth),
    )


def pop_batch(cur, limit):
    """Claim up to `limit` pending rows, lowest depth first (true BFS order).
    FOR UPDATE SKIP LOCKED is the canonical job-queue pattern -- lets a second
    process run without handing out the same rows."""
    cur.execute(
        "SELECT entity_type, mbid, name, depth FROM crawl_queue "
        "WHERE status = 'pending' ORDER BY depth, mbid LIMIT %s "
        "FOR UPDATE SKIP LOCKED",
        (limit,),
    )
    return cur.fetchall()


def set_status(cur, entity_type, mbid, status, bump_retry=False):
    cur.execute(
        f"UPDATE crawl_queue SET status = %s"
        f"{', retries = retries + 1' if bump_retry else ''} "
        f"WHERE entity_type = %s AND mbid = %s",
        (status, entity_type, mbid),
    )


# --- Seeding --------------------------------------------------------------

def search_band_mbid(name, min_score=90):
    """One-time bootstrap: resolve a seed band name to its MBID via search.

    Query loosely and filter in Python. A strict phrase query (artist:"...")
    fails on name variants -- the seed's "John Mayall's Bluesbreakers" is
    "John Mayall & the Bluesbreakers" in MusicBrainz. Returns None when nothing
    scores as a Group, which is correct for seed entries that aren't really
    bands ("Mirror Ball" is a Neil Young album, not a group).
    """
    data = mb_get("artist", {"query": name, "limit": 5},
                  cache_key=f"search_{normalize_name(name)}")
    groups = [a for a in (data or {}).get("artists", [])
              if a.get("type") == "Group" and a.get("score", 0) >= min_score]
    return groups[0]["id"] if groups else None


def seed_queue(conn):
    """Enqueue every seed band (depth 0) after resolving its MBID by name.

    Also backfills that MBID onto the seed row. This is the one moment we hold
    both the seed's name and the resolved MBID together, so it's where we pin
    identity -- otherwise a later fetch under MusicBrainz's canonical name
    ("John Mayall & the Bluesbreakers") wouldn't reconcile with the seed row
    ("John Mayall's Bluesbreakers") and would insert a duplicate band.

    Idempotent: re-running skips bands already queued and already-pinned rows.
    """
    with conn, conn.cursor() as cur:
        cur.execute("SELECT id, name FROM bands ORDER BY name")
        rows = cur.fetchall()
    added = 0
    for band_id, name in rows:
        mbid = search_band_mbid(name)
        if not mbid:
            print(f"  no MBID found for seed band: {name}")
            continue
        with conn, conn.cursor() as cur:
            cur.execute("UPDATE bands SET mbid = %s WHERE id = %s AND mbid IS NULL",
                        (mbid, band_id))
            enqueue(cur, "band", mbid, name, 0)
            added += cur.rowcount
    print(f"Seeded {added} bands into the queue.")


EXTRA_SEEDS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "extra_seed_bands.txt",
)


def add_seeds(conn, path=EXTRA_SEEDS_PATH):
    """Enqueue extra seed bands listed in a text file (one name per line).

    Unlike seed_queue there's no row to backfill -- these bands aren't in the
    table yet, so the crawl inserts them fresh (as depth-0, hence trusted rock)
    when it reaches them. Just resolve each name to an MBID and enqueue at 0.
    """
    with open(path, encoding="utf-8") as f:
        names = [ln.strip() for ln in f
                 if ln.strip() and not ln.startswith("#")]
    added = 0
    for name in names:
        mbid = search_band_mbid(name)
        if not mbid:
            print(f"  no MBID found for: {name}")
            continue
        with conn, conn.cursor() as cur:
            # New band -> enqueue at depth 0. A band already discovered deeper
            # (depth > 0) was fetched but never expanded, so promote it to a
            # depth-0 seed. Existing depth-0 seeds are left as-is. Re-fetch of a
            # promoted band is free (cached), and it now expands its members.
            cur.execute(
                "INSERT INTO crawl_queue (entity_type, mbid, name, depth, status) "
                "VALUES ('band', %s, %s, 0, 'pending') "
                "ON CONFLICT (entity_type, mbid) DO UPDATE "
                "SET depth = 0, status = 'pending' WHERE crawl_queue.depth > 0",
                (mbid, name),
            )
            added += cur.rowcount
    print(f"Seeded {added} bands (new or promoted) of {len(names)} listed.")


# --- Main crawl loop ------------------------------------------------------

def process_one(conn, entity_type, mbid, name, depth, max_depth, ignore_genre=False):
    """Fetch one entity, write its memberships, enqueue rock neighbours.
    Each entity is its own transaction so a mid-batch crash loses at most one.

    ignore_genre: still record each band's real is_rock verdict, but DON'T stop
    at non-rock bands -- expand them anyway. Used for bridge-hunting: a link
    between an island and the main graph may run through a non-rock band that
    the normal boundary would skip (and so never explore).
    """
    artist = fetch_artist(mbid)
    if artist is None:                       # 503-exhausted -> let it retry later
        with conn, conn.cursor() as cur:
            set_status(cur, entity_type, mbid, "pending", bump_retry=True)
        return "requeued"

    # Genre boundary applies to bands. Seed bands (depth 0) are trusted rock even
    # if MusicBrainz tags them sparsely; deeper bands are judged by their tags.
    genres = genre_names(artist)
    rock = (depth == 0) or is_rock(genres)

    with conn, conn.cursor() as cur:
        this_table = "bands" if entity_type == "band" else "musicians"
        this_id = resolve(cur, this_table, mbid, artist.get("name", name))

        if entity_type == "band":
            # Record the genre verdict AND the raw genres (display-only) on the
            # band (three-state: both stay NULL for bands only ever seen as a leaf).
            cur.execute("UPDATE bands SET is_rock = %s, genres = %s WHERE id = %s",
                        (rock, ", ".join(genres) or None, this_id))
            if not rock and not ignore_genre:
                set_status(cur, "band", mbid, "skipped")
                return "skipped (non-rock)"

        for m in parse_memberships(artist):
            # Role is fixed by which side we're crawling, NOT by the counterparty's
            # MusicBrainz "type" -- that field is often null even for real people,
            # which previously routed a band's own id into musician_id and tripped
            # the foreign key. Fetching a band -> counterparties are its members;
            # fetching a musician -> counterparties are their bands.
            if entity_type == "band":
                musician_id = resolve(cur, "musicians", m["counterparty_mbid"], m["counterparty_name"])
                band_id = this_id
                neighbour = ("musician", m["counterparty_mbid"], m["counterparty_name"])
            else:
                musician_id = this_id
                band_id = resolve(cur, "bands", m["counterparty_mbid"], m["counterparty_name"])
                neighbour = ("band", m["counterparty_mbid"], m["counterparty_name"])

            cur.execute(
                "INSERT INTO memberships "
                "(musician_id, band_id, instrument, year_from, year_to) "
                "VALUES (%s, %s, %s, %s, %s) "
                "ON CONFLICT (musician_id, band_id) DO NOTHING",
                (musician_id, band_id, m["instrument"], m["year_from"], m["year_to"]),
            )

            if depth < max_depth:
                enqueue(cur, *neighbour, depth + 1)

        set_status(cur, entity_type, mbid, "done")
    return "done"


def crawl(limit, max_depth, ignore_genre=False):
    conn = get_connection()
    ensure_queue(conn)
    processed = 0
    while processed < limit:
        with conn, conn.cursor() as cur:
            batch = pop_batch(cur, min(50, limit - processed))
        if not batch:
            print("Queue empty -- nothing left to crawl.")
            break
        for entity_type, mbid, name, depth in batch:
            try:
                result = process_one(conn, entity_type, mbid, name, depth, max_depth, ignore_genre)
            except Exception as exc:
                # One bad entity must not kill an unattended batch. Clear the
                # aborted transaction, park the row as 'error' (pop_batch skips
                # those), and carry on. Review error rows later, don't loop them.
                conn.rollback()
                with conn, conn.cursor() as cur:
                    set_status(cur, entity_type, mbid, "error", bump_retry=True)
                result = f"ERROR {type(exc).__name__}: {exc}"
            processed += 1
            print(f"  [{processed:>4}] d{depth} {entity_type:8} {name or mbid} -> {result}")
            if processed >= limit:
                break
    conn.close()
    print(f"\nDone: {processed} entities this run.")


def main():
    # MusicBrainz names carry Unicode (accents, U+2010 hyphen, etc.) but a
    # Windows console defaults to cp1252 and will crash mid-print on them. The
    # DB writes are UTF-8 regardless; this just keeps our progress prints safe.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    p = argparse.ArgumentParser(description="Snowball-crawl MusicBrainz into Postgres.")
    p.add_argument("--seed", action="store_true",
                   help="bootstrap the queue from seed bands, then exit")
    p.add_argument("--add-seeds", action="store_true",
                   help="enqueue extra seeds from data/extra_seed_bands.txt, then exit")
    p.add_argument("--limit", type=int, default=1,
                   help="max entities to process this run (default 1)")
    p.add_argument("--max-depth", type=int, default=2,
                   help="how many hops from a seed band to crawl (default 2)")
    p.add_argument("--ignore-genre", action="store_true",
                   help="expand non-rock bands too (bridge-hunting); still records is_rock")
    args = p.parse_args()

    if args.seed or args.add_seeds:
        conn = get_connection()
        ensure_queue(conn)
        (add_seeds if args.add_seeds else seed_queue)(conn)
        conn.close()
        return
    crawl(args.limit, args.max_depth, args.ignore_genre)


if __name__ == "__main__":
    main()
