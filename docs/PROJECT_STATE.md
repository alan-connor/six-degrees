# Project state & handoff

A living note on where "Six Degrees of Rock" stands, so any tool (or person) can pick up cleanly. Full plan lives in `ROADMAP.md`.

## What this is

A learning project that maps rock musicians into a network and finds the "degrees of separation" between any two, through shared bands. It's a full-pipeline exercise: **gather → store → graph → API → UI**. Learner is at a "some coding" level.

## Architecture (decided)

- **Data store:** PostgreSQL. Three domain tables — `musicians`, `bands`, and a `memberships` join table carrying `instrument`, `year_from`, `year_to` — plus one operational table, `crawl_queue` (the crawler's persistent frontier; see Phase 1).
- **Stable IDs / identity:** `musicians` and `bands` each carry nullable `mbid` (MusicBrainz artist ID) and `qid` (Wikidata item ID), both `UNIQUE`. Nullable permanently — an entity may exist in MusicBrainz, Wikidata, both, or neither. Every seed row starts with both NULL; the crawler backfills them. **`name` is NOT unique** — identity is the MBID. Two different entities genuinely share a name (Mick Jones of Foreigner vs The Clash), so homonyms get separate rows. A *partial* unique index keeps only mbid-less rows (unreconciled seeds) name-unique, so the seed loader can still dedup. `graph.py` keys nodes on `id`, not name.
- **Genre flag:** `bands.is_rock` is a nullable boolean — three states: `NULL` = not yet fetched, `TRUE` = confirmed rock, `FALSE` = confirmed non-rock. The crawler sets it on fetch; `graph.py` keeps `is_rock IS NOT FALSE` (rock + unknown, dropping only confirmed non-rock). See "Genre boundary" below. **Caveat:** `is_rock([])` is `False`, so a band with *no* MB genre tags defaults to non-rock — ~1,370 untagged bands are excluded this way, occasionally a real rock band (this is why the bridge overrides were needed).
- **Genres (display):** `bands.genres` is a nullable, comma-joined display string of the raw MB genre tags (e.g. `"hard rock, heavy metal, thrash metal"`). Display-only, like `instrument` — not queried, not logic. `is_rock` is *derived* from these, so storing them makes the flag auditable. NULL for unfetched or MB-untagged bands.
- **Graph/logic:** Python + NetworkX, in memory, rebuilt from Postgres. BFS = shortest path = "degrees of separation."
- **Edge rule:** two musicians are linked if they were *ever* in the same band — dates are **not** considered. Same rule the Kevin Bacon game uses ("same movie", not "same scene"). Temporal overlap was considered and rejected: measured on the seed it drops 16 of 260 edges (e.g. Clapton left the Bluesbreakers the year before Mick Taylor joined) but adds real cost — it would make stint modeling load-bearing, since collapsing two stints into one row invents a continuous tenure and fabricates overlaps. Accepted looseness: the graph will link musicians who never actually met.
- **Scope: band MEMBERSHIP only, NOT album/session credits (deliberate).** Edges come from MusicBrainz "member of band" relations. Sidemen, touring/session players, guest solos, and producers who never became formal band members do NOT create edges — so genuine real-world links are missing by design (e.g. Brad Gillis toured with Ozzy in 1982 but MB models it as a recording credit, not a membership, so he doesn't bridge Night Ranger→Ozzy). Why not add credits: an artist has ~50× more recording credits than memberships (Brad Gillis: 260 vs 5), finding co-performers means fetching every recording (volume explosion), and it needs a heavy filtering layer — Various-Artists/compilation albums create false cliques, session players/producers become mega-hubs. Coverage is also spotty (MB doesn't even have Gillis's Ozzy credits). Verdict: a legitimate but large "v2"; if a few marquee session links are wanted, add them *targeted/curated*, not via a full credit crawl.
- **Instrument:** a free-text display label, nothing more. Not queried, not constrained, not used by the graph. Stored as the source gave it, no canonicalization — the seed's hand-curated ordering is primary-instrument-first (Chris Cornell is `vocals/guitar`, Tom Petty is `guitar/vocals`), which alphabetizing would destroy. Reversible: if instrument ever needs querying, add a normalized table alongside rather than reworking this column.
- **Backend (planned):** FastAPI exposing JSON endpoints (`/musicians`, `/path`, `/neighbors`).
- **Frontend (planned):** React (Vite) SPA calling the API, graph drawn with a JS lib (react-force-graph).
- Decoupled backend + frontend, run as two processes.

## Repo layout

```
six-degrees/
├── backend/
│   ├── db.py            # shared Postgres connection (env vars, defaults to local Docker)
│   ├── graph.py         # load from Postgres, build NetworkX graph, shortest_path
│   ├── crawl.py         # Phase 1 crawler: MusicBrainz -> Postgres (see Phase 1)
│   ├── api.py           # Phase 4 FastAPI backend (/musicians, /path, /neighbors)
│   ├── rock_genres.py   # rock-genre allowlist (113 genres) + is_rock() for the crawl boundary
│   └── setup/           # one-time / learning scripts
│       ├── check_db.py       # connection checkpoint
│       ├── create_tables.py  # build schema (musicians, bands, memberships)
│       ├── load_seed.py      # CSV -> Postgres (idempotent)
│       └── bfs_demo.py       # completed learning exercise: hand-written BFS. NOT a pipeline step.
├── data/
│   ├── rock_memberships_seed.csv   # original seed: 170 memberships, 103 musicians, 46 bands
│   ├── extra_seed_bands.txt        # expansion seeds (new wave/80s/90s/metal), one name/line, for --add-seeds
│   └── cache/                      # crawler's on-disk response cache (gitignored, regenerable)
├── frontend/                       # Phase 5: Vite + React 19 + Tailwind CSS v4 (src/App.jsx). node_modules gitignored.
├── requirements.txt                # pinned deps (networkx, psycopg2-binary, requests, fastapi, uvicorn)
├── .gitignore                      # .venv/, __pycache__/, data/cache/, .env
├── docs/                           # ROADMAP.md (the full plan), BUILD_PROMPT.md, this file
```

## Local environment

- Postgres runs in Docker. The live container is named **`sixdb`** (an equivalent recreate command):
  `docker run --name sixdb -e POSTGRES_PASSWORD=six -e POSTGRES_DB=sixdegrees -p 5432:5432 -d postgres`
- Connection: host `localhost`, port `5432`, user `postgres`, password `six`, db `sixdegrees`. Live version is Postgres 18.4.
  `db.py` reads these from env vars (`PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `PGDATABASE`) with those as defaults.
- Python: virtual env at the repo root (`.venv/`). Install: `pip install -r requirements.txt`.
  **Gotcha 1:** use the venv's interpreter explicitly (`.venv\Scripts\python.exe`) or activate it. A bare `python` on this machine resolves to a *different* install (pythoncore-3.14) that lacks these packages — `ModuleNotFoundError: requests` means you hit that.
  **Gotcha 2:** the venv's `python.exe` is a launcher stub that re-execs the real interpreter, so one crawl shows up as *two* `python.exe` processes (a parent + worker with the same command line). That is one logical crawler at 1 req/sec, NOT two — don't mistake it for a rate-limit problem.
- Run backend scripts **from the `backend/` folder**: `python graph.py`, `python crawl.py ...`; setup scripts with the `setup/` prefix, e.g. `python setup/create_tables.py`.
- **Backup before destructive changes or big crawl batches:**
  `docker exec sixdb pg_dump -U postgres sixdegrees > backup.sql`  (restore: `docker exec -i sixdb psql -U postgres sixdegrees < backup.sql`)

## Done

- **Phase 0–2:** schema (`create_tables.py`), idempotent seed loader (`load_seed.py`), connection check (`check_db.py`). Verified against live Postgres: the full drop → create → load → graph cycle runs end to end.
- **Phase 3 (done first, per plan):** `graph.py` builds the graph and finds shortest paths; `bfs_demo.py` is the completed hand-written counterpart. Cobain→Page returns the expected 3-hop chain.
- **Seed is one connected network:** originally 8 disconnected clusters; six real bridge supergroups were added (The Dirty Mac, Kenney Jones' Faces→Who move, Screaming Trees, Mirror Ball, XYZ, Emerson Lake & Powell / GTR). See the roadmap's "connected components" section.
- **Phase 1 crawler — BUILT and running.** `crawl.py` snowball-crawls MusicBrainz into Postgres. See below.

## Phase 1 — the crawler (built; depth-2 crawl done for all seeds)

`crawl.py` is written, hardened, and has crawled the full seed set to depth 2. It grows the network beyond the seed.

**Commands** (from `backend/`, with the venv Python):
- `python crawl.py --seed` — one-time: resolve each original (CSV) seed band's MBID by name search, backfill it onto the seed row, enqueue at depth 0.
- `python crawl.py --add-seeds` — enqueue extra seeds from `data/extra_seed_bands.txt`. New bands enqueue at depth 0; bands already discovered *deeper* are promoted to depth-0 seeds so they get expanded (a depth-2 band was fetched but never expanded). Solo artists (a Person, not a Group) won't resolve — seed their band instead (e.g. Generation X for Billy Idol).
- `python crawl.py --limit N` — process up to N queued entities this run (default 1). Bounded and resumable, so it's schedule-friendly.
- `--max-depth D` — hops from a seed band (default 2). Note: raising it later does NOT re-expand already-`done` depth-2 bands; reset them to `pending` first (cached, so free on API calls).
- `--ignore-genre` — expand non-rock bands too (bridge-hunting). Still records each band's real `is_rock`; just doesn't stop at non-rock. See "Connectivity & bridges".

**How it works:**
- **Persistent frontier:** `crawl_queue` (`entity_type, mbid, name, depth, status, retries`), popped lowest-depth-first with `FOR UPDATE SKIP LOCKED`. This is the BFS from `bfs_demo`/`graph.py`, persisted and spread over time.
- **Rate limit / caching:** ~1 req/sec, real User-Agent (mandatory), 503 → re-queue not drop. Responses cached to `data/cache/<mbid>.json`, so re-runs cost zero API calls. NOTE: cache key is the mbid/name, *not* the query — clear `data/cache/` when you change fetch logic or a stale result is re-read.
- **Identity resolution** (`resolve()`): match on `mbid` → else normalized name → else insert; backfill a missing mbid on a name match. `qid` unused until a Wikidata path is added (pull P434 there to bridge the ID spaces). Names normalized (casefold + strip non-alphanumerics) for matching only.
- **Instrument aggregation:** a person's instrument relations for one band are collected into a single `guitar/vocals` value before insert — else the second relation hits `ON CONFLICT DO NOTHING` and vanishes.
- **Genre boundary:** on fetching a band, `rock = (depth == 0) or is_rock(genres)`. Written to `bands.is_rock`; non-rock bands are `skipped` (not expanded) unless `--ignore-genre`. `rock_genres.py` holds the 113-genre allowlist (an explicit set, because substring "rock" both lets in reggae and excludes grunge/britpop/metal).

**Hardening (three real-data bugs found and fixed while crawling at scale):**
- *Console encoding:* MusicBrainz names carry Unicode (U+2010 hyphen, curly apostrophes) that crash a cp1252 Windows console mid-`print`. Fixed with `sys.stdout.reconfigure(encoding="utf-8", errors="replace")`. DB writes were always UTF-8.
- *FK routing:* role (musician vs band) is decided by which side we're crawling, NOT the counterparty's MB `type` — that field is often null even for real people, which used to route a band's own id into `musician_id` and trip the foreign key.
- *Per-entity resilience:* `crawl()` wraps each entity in try/except, parks a failure as `status='error'` (pop_batch skips those), and continues — one bad record can't kill an unattended batch.

**Live state (snapshot; moves as the crawl runs):** ~6,062 musicians, ~2,589 bands, ~10,790 memberships; queue drained (0 pending). Rock graph: ~5,452 musicians, ~60k edges, 1 connected component (after bridge crawls + homonym fix). Cobain→Page still 3 degrees.

**Completeness — bands complete, musician frontier partial.** Bands were the primary crawl target, so ~100% of bands in the dataset (886/888 in the rock graph) were *fetched* with their full MusicBrainz roster — every edge among a band's members is captured. Musicians are the ragged edge: only ~15% (930/6,062) were fetched, so the other ~85% show only the bands that were themselves crawled and happened to list them. Any band reachable *only* through an un-fetched frontier musician is missing entirely (Brad Gillis was never fetched; his bands Rubicon/Skills/Vicious Rumors aren't in the data). So the graph is complete *within* the crawled depth-2 region but has an incomplete boundary. Filling it means crawling deeper — a multiplying frontier that never truly finishes (MB has ~2.5M artists); it's asymptotic, not completable.

**Known data behaviours (by design):**
- *Non-rock leaf bands:* a band is inserted the moment a crawled musician lists it, before its genre is known (`is_rock` NULL). The filter prevents *expansion*, not insertion, so `bands` accumulates off-genre leaves. They contribute ~0 edges and drop from the graph once confirmed FALSE.
- *Instrument granularity:* MusicBrainz is finer/academic than the seed (`membranophone` = drums). Seed bands keep their cleaner labels via `ON CONFLICT DO NOTHING`; crawled bands carry MB's terms. Display-only.
- *Stints / year gaps:* one row per (musician, band). A non-contiguous rejoin collapses to a single row keeping the *first-listed* stint's dates and merging instruments. Invisible to the graph by design.
- *Non-band seeds:* a few seed "bands" aren't MusicBrainz groups (Mirror Ball is a Neil Young album; Billy Idol is a solo Person). They stay name-only — correct.

## Connectivity & bridges

The graph is currently **one connected component** (~5,452 musicians). It got there in stages: the seed crawl left a giant component plus a few islands (U2, Depeche Mode, B-52's, Talking Heads, `Late!`); genre-blind solo-project bridge crawls then merged them all. Lesson learned live: rock is a densely interconnected web — thrash, glam, nu-metal, grunge, prog, post-punk all merge via supergroups and members who move between bands. Only acts with *stable, insular lineups* resist, and even those fall to a deep enough solo-project crawl.

- **Connectivity is robust (an earlier "soft" worry was measured and mostly dismissed).** The homonym-merge fix (below) is DONE — the false Skid Row / Mick Jones / Roger Taylor edges are gone, and the graph *stayed* 1 component, so it wasn't relying on those. The remaining worry was **Pigface** (a 120-member industrial collective) acting as a false mega-hub — but measuring it: removing Pigface leaves the core **still 1 component**, and Bono / Dave Gahan / Cobain reach Jimmy Page at the *same* hop counts without it. Only **87 musicians** (for whom Pigface is their *only* rock band) depend on it — ~470k of ~14.9M pairs (3.17%), all of them involving those 87. The core has zero dependency, and the notable bridges (U2, Depeche Mode) do NOT route through Pigface out of necessity.
- **Open modeling question (general, not a bug):** should a large "collective" band (Pigface's 120 members; also charity singles, festival supergroups) imply all members are one degree apart — a full clique? That inflates apparent closeness for those members. It's a modeling choice about collectives, not a defect; revisit if degrees start looking implausibly short.
- **How islands were bridged.** `--ignore-genre` expands non-rock bands to find cross-genre links. Two mechanisms seen: (1) a real non-rock band + real shared musician, merged by manually flipping `is_rock` to TRUE; (2) crawling a member's solo/side project genre-blind, which pulls in collaborators whose *other* bands are legitimately rock — no override needed (this is how Depeche Mode & U2 connected). The manual overrides:
  - `Tom Tom Club` → Adrian Belew → King Crimson (merged Talking Heads)
  - `Fred Schneider & The Shake Society` → Bernie Worrell (merged the B-52's)
  - `Tone Dogs` → Matt Cameron (merged the lone `Late!` node)
- These four `is_rock=TRUE` overrides (incl. Tom Tom Club) are the only bands whose flag disagrees with `rock_genres.is_rock()`. Notably, several have **no MB genre tags at all** (`bands.genres` is NULL) — so they weren't judged non-rock, they defaulted to it for lack of data. The override corrects a missing-data verdict, not a wrong-genre one.
- **Fragility:** these overrides live only in the `is_rock` column. Re-crawling such a band (e.g. resetting it to `pending`) re-derives `is_rock` from its (empty) genres and overwrites TRUE back to FALSE, re-splitting the graph. They're currently `done`, so a normal crawl won't touch them.

## Next

- Phase 1 is at a stopping point (queue drained; genre-blind bridge crawls merged Depeche Mode and U2, so the rock graph is currently **1 robustly-connected component** — homonym merges fixed, and the Pigface "mega-hub" worry was measured and dismissed; see Connectivity). Optional: seed more scenes via `data/extra_seed_bands.txt` + `--add-seeds`, or hunt bridges with `--ignore-genre`.
- **Identity fix (the `UNIQUE(name)` / homonym problem) — DONE.** See below.
- **Phase 4 backend — BUILT (`backend/api.py`).** FastAPI over **two graph projections** of the same data, six endpoints. People view (nodes = musicians): `GET /musicians`, `GET /path?from=&to=`, `GET /neighbors?id=`. Band view (nodes = bands, edges = shared members): `GET /bands`, `GET /band-path?from=&to=`, `GET /band-neighbors?id=`. from/to accept id OR name; a homonym name returns `{"ambiguous": {...}}` with options (id + a `hint` band/member). `graph.py:_project` builds either axis; both graphs built once at startup; CORS open for dev. Run from `backend/`: `uvicorn api:app --reload`; docs at `/docs`. Verified: Cobain→Page = 3 degrees; Led Zeppelin→Nirvana = 2 band-degrees; Mick Jones / Skid Row correctly disambiguate. Remaining polish: tests, tighten CORS for deploy. Note: band-degrees skew short (a prolific session musician cliques many bands).
- **Phase 5 frontend — STARTED (`frontend/`).** Vite + React 19 + **Tailwind CSS v4** (`@tailwindcss/vite` plugin). `src/App.jsx`: People/Bands mode toggle, two filterable comboboxes (from `/musicians` or `/bands`; homonyms shown with a `hint` and selected by id), "Find connection" → `/path` or `/band-path`, and a chain-rendering result. Verified in-browser: renders with Tailwind styling, list loads (5,452), Cobain→Page = 3 degrees via the real fetch flow. Run: `cd frontend && npm install && npm run dev` (needs the backend on :8000). Own `.gitignore` covers `node_modules`/`dist`. Remaining: the react-force-graph visualization (`/neighbors` / `/band-neighbors`), and homonym `ambiguous`-response handling in the UI (comboboxes pick ids up front, so it rarely triggers).
- **Phase 5.5** (ship) → **Phase 6** (optional Neo4j port). AI touchpoints (prose extraction, natural-language "how are these two connected" + narrated chains) plug into Phases 1 and 4/5.
- Housekeeping backlog: person-named entities occasionally land in `bands` (role-inversion on messy MB solo-project data) — but note most person-as-band nodes are *legitimate* collaboration hubs (Les Claypool's projects, Marilyn Manson); only the ~10 single-member self-duplicates are noise, and a `HAVING count(*)>=2` display filter handles them. And the repo still has **zero git commits**.

### Identity fix (the `UNIQUE(name)` / homonym-merge problem) — DONE

**Problem (was):** `resolve()` matched by MBID then fell back to normalized *name*, and `name` was `UNIQUE`. A second, genuinely different entity with the same name (its own MBID) got **merged** into the existing row, its MBID discarded — the "name as identity" trap. Blast radius: 10 bands + 5 musicians, incl. **Mick Jones** (Foreigner vs The Clash), **Roger Taylor** (Queen vs Duran Duran), **Skid Row** (US glam metal vs early Nirvana), **The Firm** (Jimmy Page's rock band vs the Nas hip-hop group).

**What was done:**
1. `resolve()` (crawl.py) — name-match now only reconciles rows where `mbid IS NULL` (seeds); a differing MBID means a homonym → new row. Prevents all future merges.
2. Schema — dropped `UNIQUE(name)` on both tables; added a **partial** unique index `(name) WHERE mbid IS NULL` so seeds still dedup. `load_seed.py` updated to `ON CONFLICT (name) WHERE mbid IS NULL`.
3. `graph.py` — nodes keyed on `id` with `name` as an attribute; `ids_for_name()` + a homonym-aware `shortest_path()` (tries all id pairs).
4. Migration — **surgical split** (not a rebuild): for each of the 15, created a row for the lost MBID from its cache and moved its exclusive members/bands off the kept row. Preserved seed data and the 3 manual overrides; 0 orphan memberships.

**Result:** homonyms are now distinct rows (e.g. early-Nirvana Skid Row `id=472` vs glam Skid Row `id=2586`, and each got the correct `is_rock` — glam=rock, hip-hop Firm=non-rock/excluded). Graph stayed 1 component. Cobain→Page still 3 degrees.
