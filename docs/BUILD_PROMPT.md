# Build brief: "Six Degrees of Rock"

*Paste this whole file to a capable coding agent (e.g. Claude) as the spec for building the project from scratch. It captures not just **what** to build but the **decisions and their rationale**, plus the traps discovered the hard way — follow them and you'll land close to the reference build. Exact data won't match (it depends on live MusicBrainz state and crawl order), but the architecture, schema, code shape, and behaviour will.*

---

## 0. What you're building

A learning project that maps rock musicians into a network and finds the **degrees of separation** between any two, through shared bands (the "Kevin Bacon game" for rock). It's a full pipeline: **gather → store → graph → API → UI**. Build each phase runnable before moving on; a working small thing beats a half-built big thing. Assume the human is at a "some coding" level — favour clarity and heavy comments over cleverness.

**Stack (and why — make these same choices):**
- **PostgreSQL** for storage — most in-demand DB; the SQL/schema skills transfer to a résumé. (Not SQLite/Neo4j; Neo4j is an optional Phase 6 port.)
- **Python + NetworkX** for the graph, rebuilt in memory from Postgres. BFS = shortest path = "degrees of separation."
- **FastAPI** backend exposing JSON. **React + Vite + Tailwind CSS** frontend, decoupled, run as two processes.
- **MusicBrainz API** as the data source (free, structured artist⇄band relationships). Wikidata is a secondary source.

Run Postgres in Docker: `docker run --name sixdb -e POSTGRES_PASSWORD=six -e POSTGRES_DB=sixdegrees -p 5432:5432 -d postgres`. Python in a repo-root venv; a shared `db.py` reads `PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE` env vars defaulting to that local setup.

Build order that worked: **Phase 0 setup → schema → Phase 3 graph on a seed CSV (do this early, it's the payoff and tells you what data you need) → Phase 1 crawler → identity fix → Phase 4 API → Phase 5 frontend.**

---

## 1. The data model — decisions that matter

Three domain tables + one operational table. **Identity is the MusicBrainz ID (MBID), NOT the name.** This is the single most important decision; getting it wrong corrupts answers (see the homonym trap below).

```sql
CREATE TABLE musicians (
    id   SERIAL PRIMARY KEY,
    mbid TEXT UNIQUE,        -- MusicBrainz artist id; NULL until crawled
    qid  TEXT UNIQUE,        -- Wikidata id; NULL unless a Wikidata path is added
    name TEXT NOT NULL       -- NOT unique: homonyms exist (see below)
);
CREATE UNIQUE INDEX musicians_seed_name_uniq ON musicians (name) WHERE mbid IS NULL;

CREATE TABLE bands (
    id      SERIAL PRIMARY KEY,
    mbid    TEXT UNIQUE,
    qid     TEXT UNIQUE,
    name    TEXT NOT NULL,   -- also NOT unique
    is_rock BOOLEAN,         -- NULL=not fetched, TRUE=rock, FALSE=non-rock (crawl boundary)
    genres  TEXT             -- display-only, comma-joined MB genres; is_rock is derived from these
);
CREATE UNIQUE INDEX bands_seed_name_uniq ON bands (name) WHERE mbid IS NULL;

CREATE TABLE memberships (
    musician_id INT REFERENCES musicians(id),
    band_id     INT REFERENCES bands(id),
    instrument  TEXT,        -- free-text display label only
    year_from   INT,
    year_to     INT,
    PRIMARY KEY (musician_id, band_id)   -- one row per pair; stops dup links on re-crawl
);
CREATE INDEX ON memberships (band_id);
```

**Why `name` is not unique but has a partial index:** two genuinely different entities share a name — Mick Jones (Foreigner vs The Clash), Roger Taylor (Queen vs Duran Duran), the US glam Skid Row vs early Nirvana (who briefly used that name), The Firm (Jimmy Page's band vs the Nas hip-hop group). If `name` is `UNIQUE` and your resolver falls back to name-matching, these **merge into one node**, inventing false edges. The partial unique index `WHERE mbid IS NULL` keeps only unreconciled seed rows deduped by name, while allowing homonyms (which have distinct MBIDs) to coexist. **Build this in from the start** — retrofitting it after crawling is painful (it was, in the reference build).

**Modeling decisions to encode (write them down — that IS the data-modeling exercise):**
- **Edge rule: two musicians are linked if they were EVER in the same band — dates ignored.** Same as the Bacon game ("same movie," not "same scene"). Considered and rejected temporal overlap: it drops real edges (Clapton left the Bluesbreakers the year before Mick Taylor joined) and would make stint-modeling load-bearing (collapsing two stints into one row invents a continuous tenure). Accepted looseness: the graph may link musicians who never actually met. Keep `year_from/year_to` anyway — they cost nothing and the UI will want them.
- **Scope: band MEMBERSHIP only, NOT album/session credits.** Use MusicBrainz "member of band" relations. Do NOT traverse recording/release performer credits. Sidemen, touring/session players, guest solos, and producers won't create edges — so some real-world links are absent by design (Brad Gillis toured with Ozzy but MB has it as a recording credit, not a membership; he won't bridge Night Ranger→Ozzy). This is a deliberate scope line: credits are ~50× the volume (one artist can have 260 recording credits vs 5 memberships), finding co-performers means fetching every recording (explosion), and they need heavy filtering (Various-Artists/compilation albums create false cliques; session players/producers become mega-hubs). MB credit coverage is also spotty. If a few marquee session links are wanted later, add them targeted/curated — not a full credit crawl.
- **`instrument` is a free-text display label** — not queried, not constrained, not used by the graph. Store what the source gives. MusicBrainz is granular/academic (`membranophone` = drums); don't canonicalize.
- **`genres` is display-only**; `is_rock` is derived from it. Store the raw comma-joined genres for auditability.

---

## 2. Phase 0–3: setup, schema, seed, graph

1. **Setup:** Docker Postgres, venv, `pip install networkx psycopg2-binary`. A `db.py` with `get_connection()`. `create_tables.py` (the schema above), `check_db.py` (connection smoke test).
2. **Seed:** hand-curate a CSV of ~170 memberships across ~46 real bands spanning the 1960s–2000s (blues/Cream/Fleetwood-Mac web; CSNY/Byrds folk-rock; Deep-Purple/Sabbath metal; Yes/Crimson/ELP prog; Soundgarden/Pearl-Jam grunge). **Deliberately add a few "bridge" supergroups** (e.g. The Dirty Mac, a Faces→Who lineup move, Mirror Ball, XYZ, ELP&Powell/GTR) so the seed is **one connected component** rather than disconnected islands — this teaches connected components early. Load it with an idempotent `load_seed.py` using `INSERT ... ON CONFLICT (name) WHERE mbid IS NULL DO NOTHING`.
   - CSV gotcha: quote names containing commas (`"Crosby, Stills, Nash & Young"`) or a comma-delimited file silently mangles them.
3. **Graph (`graph.py`), built early:** one SQL join pulls memberships as `(musician_id, musician, band_id, band, instrument)` filtered by `WHERE b.is_rock IS NOT FALSE`. Build an undirected NetworkX graph. **Key nodes on `id`, with `name` as a node attribute** (not on name — else homonyms re-merge in the graph even after you split them in the DB). Generalize the projection so you can build either axis:
   - **musician graph:** nodes = musicians, edge when they share a band (edge stores the set of band names).
   - **band graph (mirror):** nodes = bands, edge when they share a member (edge stores member names).
   Provide `ids_for_name()` (a name → possibly several ids) and a homonym-aware `shortest_path()` that tries all id pairs. Demo: Kurt Cobain → Jimmy Page should be 3 hops (Cobain→Nirvana→Dave Grohl→Them Crooked Vultures→John Paul Jones→Led Zeppelin→Page).

---

## 3. Phase 1: the MusicBrainz crawler (`crawl.py`)

A snowball BFS crawl that grows the network beyond the seed. Design it to be **bounded, resumable, and schedule-friendly** from the start.

**Core pieces:**
- **Persistent frontier:** a `crawl_queue` table `(entity_type, mbid, name, depth, status, retries)`, popped lowest-depth-first with `FOR UPDATE SKIP LOCKED`. This is the BFS from the seed, persisted so runs resume. `status`: pending/done/skipped/error.
- **Rate limit + cache:** ~1 req/sec (MusicBrainz limit is 1/sec/IP), a **mandatory real User-Agent** (`App/ver ( contact )` — anonymous agents get throttled/blocked), 503 → re-queue don't drop. Cache every response to `data/cache/<mbid>.json` so re-runs cost zero API calls. **Cache key is the mbid/name, NOT the query** — so if you change fetch logic, clear the cache or you'll re-read stale results.
- **Identity resolution (`resolve()`):** match by mbid → else match by normalized name **ONLY when the existing row's `mbid IS NULL`** (reconciling a seed row) → else INSERT a new row. **Never merge across differing MBIDs.** Normalize names (casefold + strip non-alphanumerics) for matching only.
- **Instrument aggregation:** a person's several instrument relations for one band must be collected into a single `guitar/vocals` value BEFORE insert — else the second hits `ON CONFLICT DO NOTHING` and vanishes.
- **Genre boundary (`rock_genres.py`):** on fetching a band, `rock = (depth == 0) or is_rock(genres)`; write it to `bands.is_rock`; non-rock bands are marked `skipped` and not expanded. Use an **explicit ~110-genre allowlist**, NOT a substring match on "rock" — substring both lets in reggae ("lovers rock") and excludes real rock (grunge, britpop, shoegaze, the metal family, post-punk). Include the metal family; exclude reggae. Add an `--ignore-genre` flag that expands non-rock bands anyway (for bridge-hunting) while still recording the verdict.
- **CLI:** `--seed` (resolve seed band MBIDs by name search, backfill onto seed rows, enqueue at depth 0), `--add-seeds` (enqueue extra bands from a text file; promote already-discovered bands to depth-0 so they expand), `--limit N`, `--max-depth D` (default 2), `--ignore-genre`.

**Three real-data bugs you WILL hit — pre-empt them:**
1. **Console encoding:** MusicBrainz names carry Unicode (U+2010 hyphen, curly apostrophes) that crash a Windows cp1252 console mid-`print`. Add `sys.stdout.reconfigure(encoding="utf-8", errors="replace")`. DB writes are UTF-8 regardless.
2. **Role routing:** decide musician-vs-band role by **which side you're crawling**, NOT the counterparty's MB `type` — that field is often null even for real people, which routes a band's own id into `musician_id` and trips the FK.
3. **Per-entity resilience:** wrap each entity in try/except, park failures as `status='error'` (skip those on pop), and continue — one bad record must not kill an unattended batch.

**Scale behaviour to expect:** depth-2 from a ~46-band seed → ~2–3k bands, ~5–6k musicians, ~10k memberships. ~60% of depth-2 bands come back non-rock (session/pop side projects) — the genre filter earns its keep. Back up (`pg_dump`) before large batches; once crawled, the DB is not cheaply rebuildable (though the cache makes re-crawls free).

**Completeness (know this):** because bands are the crawl target, ~100% of bands in the dataset get their *full* member roster from MB — all within-band edges are captured. But only ~15% of musicians get fetched; the other ~85% are frontier nodes showing only the bands that were themselves crawled and happened to list them. So a band reachable only through an un-fetched musician is absent entirely. The graph is complete *within* the crawled depth-2 region with a ragged, incomplete boundary. Crawling deeper fills it but the frontier multiplies — it's asymptotic (MB has ~2.5M artists), never "done".

**Expansion:** add an `extra_seed_bands.txt` and crawl outward to cover more scenes (new wave, 80s, thrash/glam metal, nu-metal, post-punk). Most scenes merge into one giant component via supergroups and members who move between bands; only stable-lineup acts (U2, Talking Heads, Depeche Mode's synth-pop family) resist — bridge them by crawling a member's **solo/side project** genre-blind (`--ignore-genre`), which pulls in collaborators whose other bands are legitimately rock.

---

## 4. Phase 4: FastAPI backend (`api.py`)

Wrap the graph behind HTTP. Build **both projections** at startup (people + bands) from one `load_rows()`. Six endpoints:

- People: `GET /musicians`, `GET /path?from=&to=`, `GET /neighbors?id=`
- Bands: `GET /bands`, `GET /band-path?from=&to=`, `GET /band-neighbors?id=`

Rules: `from`/`to` accept an **id or a name**; a homonym name returns `{"ambiguous": {from|to: [{id, name, hint}]}}` (the `hint` is a distinguishing band/member) so the caller re-queries with an id. Listings include a `hint` only for duplicated names. Enable permissive CORS for dev (the React app is on another port). Run `uvicorn api:app --reload`; verify at `/docs`. Sanity checks: Cobain→Page = 3 degrees; Led Zeppelin→Nirvana = 2 band-degrees; `/path?from=Mick Jones` returns two people.

---

## 5. Phase 5: React frontend (`frontend/`)

Scaffold with Vite (`npm create vite@latest frontend -- --template react`). **Use Tailwind CSS v4** (`npm i tailwindcss @tailwindcss/vite`, add the plugin to `vite.config.js`, put `@import "tailwindcss";` in the CSS entry). Build `src/App.jsx` with:
- A **People ↔ Bands** mode toggle (both projections from one UI).
- Two **filterable comboboxes** populated from `/musicians` or `/bands`. Show a `hint` next to duplicated names and **select by stable id** (this resolves "which Mick Jones?" up front, so `/path` rarely returns `ambiguous`).
- A "Find connection" button → `/path` or `/band-path`, and a result that renders the chain with the linking band/member at each hop.
- `useState` for selections, `useEffect` + `fetch` to load lists on mode change. Dark theme, accent colour, responsive.
- Later: a graph visualization with `react-force-graph` fed by `/neighbors` / `/band-neighbors`.

---

## 6. Gotchas & lessons (the stuff that cost time — heed to reproduce closely)

- **Identity = MBID, not name.** The homonym merge is the one bug that makes *answers* wrong. Fix it structurally (name not unique + resolve keys on mbid + graph keys on id + API disambiguates). Split any merges surgically from cache.
- **`is_rock([])` is False** — a band with NO MB genre tags defaults to non-rock and gets excluded. Occasionally a real rock band (esp. side projects) has no tags; those need a manual `is_rock=TRUE` override, and re-crawling them re-derives FALSE from empty genres and re-splits the graph. Know this fragility.
- **Person-as-band is mostly legitimate**, not noise: eponymous bands (Marilyn Manson) and solo projects (Les Claypool's) are real collaboration hubs — don't clean them away. Only single-member self-duplicates are noise; a `HAVING count(*)>=2` display filter handles them.
- **Large "collective" bands (Pigface, charity singles, festival supergroups)** form huge cliques that inflate apparent closeness. Measure before worrying: removing such a hub often leaves connectivity intact (it only props up members who have no other band). It's a modeling question about collectives, not a bug.
- **Not every seed "band" is a MusicBrainz Group** (Mirror Ball is a Neil Young album; Billy Idol is a solo Person). They stay name-only or resolve via their actual band (Generation X for Billy Idol). Seed-band name searches must be loose (filter results to `type=Group` with a score threshold, not a strict phrase query — the seed's "John Mayall's Bluesbreakers" is "John Mayall & the Bluesbreakers" in MB).
- **Windows/venv:** use the venv's interpreter explicitly (`.venv\Scripts\python.exe`) — a bare `python` may be a different install missing packages. The venv `python.exe` is a launcher stub, so one process shows as two — not two crawlers.
- **The seed is the only irreplaceable artifact** — it encodes hand-curated bridge supergroups and a connected component. The crawled DB is regenerable from cache; the seed CSV is not.

---

## 7. Verify as you go

Cobain→Page = 3 degrees at every stage. After the crawl: ~1 connected component (check `nx.connected_components`). After the identity fix: `Mick Jones` resolves to 2 people, the two Skid Rows are distinct band nodes with correct `is_rock` (glam=rock, and the hip-hop Firm split off as non-rock). Backend `/docs` exercisable; frontend loads the list and renders a chain in the browser.
