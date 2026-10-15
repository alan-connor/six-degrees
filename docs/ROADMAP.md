# Six Degrees of Rock — A Full-Pipeline Learning Project

Build a system that maps rock musicians into a network and finds the "degrees of separation" between any two of them. You'll learn the complete data workflow used in real projects: **gather → clean → model → analyze → visualize → ship**. Pitched for someone comfortable-ish with code but not yet confident.

The trick that makes this addictive: you already have a real starter dataset (`rock_memberships_seed.csv`), so you can build something working on day one and expand it as your scraping skills grow.

---

## The mental model

Two people are connected if they've been in the same band. So the data is a **graph**: musicians are *nodes*, and a shared band is an *edge* between them. "Degrees of separation" = the shortest path between two nodes. That shortest-path search is a famous algorithm called **breadth-first search (BFS)** — learning it is the intellectual core of the project.

| Stage | What you build | Skill you pick up |
|---|---|---|
| 1. Gather | Pull band/member data from the web | APIs, JSON, rate-limiting, caching |
| 2. Store + model | A Postgres database of musicians/bands | Relational modeling, SQL — the marketable skill |
| 3. Graph + paths | Build the network, find shortest paths | Graph theory, BFS, NetworkX |
| 4. Backend API | Wrap the graph logic in a FastAPI service | REST API design, JSON, FastAPI |
| 5. React frontend | A single-page app that calls the API | React, JS, interactive graph viz |
| 6. Port to Neo4j *(optional)* | Same graph in a graph-native DB | Neo4j, Cypher — specialist premium skill |

Do them in order, but keep each stage *runnable* — a working small thing beats a half-built big thing.

> **Storage decision: PostgreSQL from the start.** Postgres is the most in-demand database in the industry (most-used *and* most-desired in the 2025 Stack Overflow survey), so building on it means the SQL and schema-design skills you pick up here go straight onto a résumé. The CSV is now just the *seed you load in once* — Postgres is your real, durable store that the scraper appends to.

---

## Phase 0 — Setup (½ day)

- Install Python 3, set up a virtual environment (`python -m venv venv`), activate it.
- `pip install pandas networkx pyvis requests psycopg2-binary`
- **Install PostgreSQL.** Easiest paths: [Postgres.app](https://postgresapp.com/) (Mac), the official installer (Windows), or — cleanest and most job-relevant — run it in **Docker**: `docker run --name rockdb -e POSTGRES_PASSWORD=rock -p 5432:5432 -d postgres`. Learning Docker alongside Postgres is a bonus marketable skill.
- Grab a GUI to look at your data: **DBeaver** or **pgAdmin** (both free). Being able to browse tables makes learning SQL far less abstract.
- Create a database: `createdb sixdegrees` (or via the GUI).

**Checkpoint:** connect to the database from Python with `psycopg2` and run `SELECT version();`. If that prints, you're ready.

---

## Data storage — the schema

Your data is naturally relational: people, bands, and the many-to-many links between them. Three tables:

```sql
CREATE TABLE musicians (
    id   SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE bands (
    id   SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE memberships (
    musician_id INT REFERENCES musicians(id),
    band_id     INT REFERENCES bands(id),
    instrument  TEXT,            -- e.g. "guitar", "bass/keyboards"
    year_from   INT,            -- optional, fill in when you have it
    year_to     INT,            -- optional
    PRIMARY KEY (musician_id, band_id)   -- stops duplicate links on re-scrapes
);
```

Why this shape:

- The `memberships` join table is the classic way to model many-to-many (a musician is in many bands; a band has many musicians). This *is* relational data modeling — the single most transferable database skill.
- `UNIQUE` on names and the composite `PRIMARY KEY` on memberships mean re-running your scraper can't create duplicates (use `INSERT ... ON CONFLICT DO NOTHING`).
- **`instrument` lives here, on the membership — not on `musicians` — because the same person plays different instruments in different bands** (Dave Grohl: `drums` in Nirvana, `guitar/vocals` in Foo Fighters). This maps one-to-one to the `instrument` column in the seed CSV.
- `year_from`/`year_to` are optional now but let you later ask fun questions like "were they in the band at the *same time*?"

**Load the seed CSV once** to populate these tables (pandas can read the CSV, then insert names into `musicians`/`bands` and the pairs into `memberships`). After that, the scraper in Phase 1 writes here directly and the CSV is retired.

---

## Phase 3 first? Yes — build the graph before you scrape

Counterintuitive, but once the seed data is loaded into Postgres, do the **graph + pathfinding** next. It's the most fun, it teaches the payoff, and it tells you exactly what data you'll need to gather later.

1. **Query the data out of Postgres** with a single SQL join, into Python: `SELECT m.name, b.name FROM memberships mem JOIN musicians m ON m.id = mem.musician_id JOIN bands b ON b.id = mem.band_id;`. This is where you start actually *using* SQL.
2. **Build the graph.** Group by band; every pair of musicians in the same band becomes an edge. NetworkX makes this a few lines:
   - Create an empty `nx.Graph()`.
   - For each band, for each pair of its members, `G.add_edge(a, b, band=bandname)`.
3. **Find degrees of separation.** `nx.shortest_path(G, "Kurt Cobain", "Jimmy Page")` returns the chain. `nx.shortest_path_length(...)` gives the number.
4. Try it on the star chain: **Kurt Cobain → Dave Grohl (Nirvana) → John Paul Jones (Them Crooked Vultures) → Jimmy Page (Led Zeppelin)**. Three hops across three rock eras. That "aha" is why this project is worth building.

**Learn here:** how a graph represents relationships, and how BFS finds the shortest chain. Optional deep-dive: write BFS yourself (a queue + a "visited" set) before letting NetworkX do it — it's ~15 lines and it's the single best thing you'll learn from this project.

**Resources:** NetworkX tutorial (official docs); any "BFS explained" video; the Wikipedia "Six degrees of separation" and "breadth-first search" pages.

---

## Phase 1 — Gather real data (the part that scales it up)

The seed CSV is ~40 bands. Now learn to grow it automatically.

- **Use an API, not raw scraping.** [MusicBrainz](https://musicbrainz.org/doc/MusicBrainz_API) is a free, open music database with structured artist⇄band relationships — far cleaner than scraping Wikipedia HTML. Wikipedia's API is a good second source.
- Learn: making requests with `requests`, parsing JSON, respecting rate limits (MusicBrainz wants ~1 request/sec — add a `time.sleep`), and **caching** responses to disk so you never re-fetch.
- Write a function: given a band name, return its members. Then given a musician, return their other bands. Loop outward from a seed band to grow your network — this "crawl the neighborhood" pattern is itself a core skill.
- **Insert results straight into Postgres** with `INSERT ... ON CONFLICT DO NOTHING`, so duplicates from overlapping crawls are handled by the database, not by you. The graph in Phase 3 just re-runs its query and picks up the new data.

**Learn here:** working with real, messy external data — the most transferable skill in the whole project. Watch for the classic traps: name variations ("Mick Taylor" vs "Michael Taylor"), duplicate entries, and knowing when to stop crawling.

**Resources:** MusicBrainz API docs; the `requests` library quickstart; search "API pagination and rate limiting."

---

## Phase 2 — Clean and model (woven into Phases 1 and the schema)

Real data is dirty. Clean it *before* it lands in Postgres: strip whitespace and standardize names in Python, and let the database's `UNIQUE`/`ON CONFLICT` rules catch the rest. Decide your modeling rules — do touring members count? Do one-off supergroups count? — and encode them as you insert. Writing down those decisions *is* data modeling.

**Learn here:** the split between app-side cleaning (pandas/Python) and database-enforced integrity (constraints) — exactly how real systems keep data sane.

---

## Architecture — decoupled backend + frontend

We're building this the industry-standard way from the start: a **Python API backend** and a **React frontend** that talk over HTTP/JSON. The backend owns the data and the graph; the frontend owns what the user sees. They're separate codebases you run as two processes in dev.

```
[ React SPA ]  ──HTTP/JSON──▶  [ FastAPI ]  ──▶  NetworkX (BFS)
 dropdowns, graph viz              /path         Postgres (data)
                                                 LLM (narration)
```

The key idea: the API is **UI-agnostic**. Once `/path?from=X&to=Y` returns clean JSON, the React app is just one client consuming it — the graph logic never needs to know a UI exists.

> **Heads-up (you're at "some coding"):** React out of the box is the ambitious path — you're learning JavaScript, React, *and* API design at once. Totally doable, but expect the frontend to be the steepest part. Keep the backend working and testable on its own (via the browser or `curl`) before you wire the UI to it, so you're never debugging both halves at the same time. Optionally use `pyvis` for a throwaway 5-line graph picture while building Phase 3, just to eyeball the data — it's a dev sanity-check, not the real UI.

---

## Phase 4 — Backend API (FastAPI)

Wrap the graph logic from Phase 3 in a web API. This is where your Python becomes a service.

- **Use FastAPI** (`pip install fastapi uvicorn`). It's the modern, in-demand Python API framework and gives you automatic interactive docs at `/docs` for free — you can test every endpoint in the browser without a frontend.
- **Design the endpoints** — a few clean ones:
  - `GET /musicians` → list of names to populate the dropdowns.
  - `GET /path?from=Kurt+Cobain&to=Jimmy+Page` → the shortest-path result as JSON: `{"degrees": 3, "chain": [{"name": "...", "instrument": "...", "band_to_next": "..."}, ...]}`.
  - `GET /neighbors?name=Dave+Grohl` → a musician's local subgraph, for the graph view.
- **Inside each endpoint:** query Postgres, build/hold the NetworkX graph, run the BFS, and (for the AI feature) call the LLM to narrate — then return JSON. This is your Phase 3 code, now behind a URL.
- **Enable CORS** so the React app (on a different port) is allowed to call it.
- Run it with `uvicorn main:app --reload` and hit `/docs` to confirm it works *before* touching React.

**Learn here:** REST API design, request/response modeling, and the discipline of a backend that's testable on its own.

**Resources:** the FastAPI tutorial (excellent and beginner-friendly); "what is CORS"; "REST API design basics."

---

## Phase 5 — React frontend

The single-page app that consumes your API.

- **Scaffold with Vite** (`npm create vite@latest` → React). Vite gives you a fast dev server (`npm run dev`) and is the current standard for spinning up a React app.
- **Build the UI:** two dropdowns/search boxes (populated from `GET /musicians`), a "Find connection" button that calls `GET /path` with `fetch`, and a results area that renders the returned chain (name + instrument + linking band, exactly like the mockup).
- **Render the graph** with a ready-made React graph library rather than hand-writing D3: **react-force-graph** (easiest), **vis-network**, or **cytoscape.js**. Feed it the nodes/edges from `/neighbors` or `/path`; get dragging, zoom, and click-to-highlight for free.
- **Core React concepts you'll pick up:** components, `useState` for the selected musicians, `useEffect` + `fetch` to load data, and passing props down to the graph component.

**Learn here:** React fundamentals and how a frontend talks to a backend — the exact shape of most real web apps, and a strong résumé combo with the Python side.

**Resources:** the official React docs ("Learn React"); the Vite guide; the react-force-graph examples.

---

## Phase 5.5 — Ship it

- Put both codebases on GitHub (one repo with `/backend` and `/frontend` folders is fine) with a README covering the architecture. "Designed a normalized PostgreSQL schema, built an ETL scraper, and shipped a FastAPI + React app" is a strong full-stack résumé line.
- To deploy: the React build is static files (host on Netlify/Vercel/GitHub Pages); the FastAPI backend runs on a small host (Render, Railway, Fly.io) with the Postgres database alongside.

**Learn here:** packaging and deploying a two-part app — the difference between "I did a tutorial" and "I built and shipped a thing."

---

## Phase 6 — Port to Neo4j (optional, do this once the rest works)

This is the "specialist skill on top of a mainstream base" move. You already have the graph in Postgres and NetworkX; now express the same data in a graph-*native* database. Neo4j is a smaller job market than Postgres but pays a premium and sits right next to the hot AI / knowledge-graph work — so it's a strong differentiator, not a starting point. Only start this after Phases 0–5 are working.

- **Install Neo4j.** Easiest is a free **Neo4j AuraDB** cloud instance, or run it locally in Docker: `docker run --name rock-neo4j -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/rockrock -d neo4j`. The built-in **Neo4j Browser** (at `localhost:7474`) lets you see the graph visually as you go.
- **Model as nodes + relationships.** Instead of a join table, you create `(:Musician)` and `(:Band)` nodes and a `[:PLAYED_IN]` relationship between them. Notice the shift: in Postgres the connection was a *row*; in Neo4j it's a first-class *relationship* you traverse directly.
- **Load your data.** Pull the same rows out of Postgres and write them into Neo4j with the `neo4j` Python driver, using Cypher `MERGE` (Neo4j's dedupe-on-insert, like `ON CONFLICT`):
  ```cypher
  MERGE (m:Musician {name: $musician})
  MERGE (b:Band {name: $band})
  MERGE (m)-[:PLAYED_IN]->(b)
  ```
- **The payoff — shortest path is one line of Cypher:**
  ```cypher
  MATCH p = shortestPath(
    (a:Musician {name: 'Kurt Cobain'})-[*]-(b:Musician {name: 'Jimmy Page'})
  )
  RETURN p
  ```
  Neo4j Browser draws the resulting chain as a graph automatically — no pyvis needed. Compare this to the NetworkX version you wrote earlier; seeing the *same problem* solved two ways is where the graph-database concepts really click.
- **Stretch goal (the marketable part):** layer on the AI angle that's driving Neo4j demand — use the graph as a knowledge graph feeding an LLM ("who connects these two artists, and summarize how"). That combination, graph DB + GenAI/RAG, is exactly what a lot of current Neo4j postings ask for.

**Learn here:** graph-native data modeling and the Cypher query language, plus the ability to speak to *both* a mainstream relational DB and a specialist graph DB — a combination that stands out.

**Resources:** the free [Neo4j GraphAcademy](https://graphacademy.neo4j.com/) courses; the Cypher manual; "Neo4j Python driver" quickstart.

---

## AI touchpoints — where a runtime AI call earns its place

Most of this pipeline should be plain deterministic code (rules, lookups, stable IDs). Add AI only at the genuinely fuzzy steps below. **The guardrail: AI is for interpreting, structuring, and phrasing data you already fetched from a real source — never as your primary source of facts, because it will confidently invent bandmates that never existed.** Get memberships from MusicBrainz/Wikidata; point AI at the interpreting jobs.

Listed best-and-safest first:

1. **Prose → structured membership (Phase 1 — highest value).** When a band isn't in MusicBrainz/Wikidata's structured fields, fetch its Wikipedia article text and have an LLM extract members as JSON (`name / instrument / years`). Low risk because it's reading a real document; it fills the gaps your structured APIs miss.
2. **Natural-language query + chain narration (Phase 5/6 — the headline feature).** Two touches: (a) *interpret* a plain-English question ("the nirvana drummer and the zeppelin bassist" → Dave Grohl, John Paul Jones) so the graph can pathfind it; (b) *narrate* the path the graph returns into readable prose. Safe because the facts come from your graph — the AI only supplies phrasing.
3. **Genre / era tagging (Phase 1–2).** When a source lacks a genre tag, have the AI classify the band (grunge / prog / metal / folk-rock) and its rough decade. This powers the crawl boundary ("only enqueue rock-adjacent bands") and the era filters in your visualization.
4. **Entity resolution when IDs run out (Phase 2 — use sparingly).** For the leftover ambiguous cases stable IDs can't settle (which "Mick Taylor" is this?), let an LLM judge from context. Only where ID-matching fails.
5. **Data-quality flagging (Phase 2 — nice-to-have).** Run new rows past an AI reviewer to catch junk rules miss ("this 'band' is an album title"; "this 'member' is a producer, not a musician").

**Do NOT use AI to *source* memberships** (e.g., "who was in Cream?") — that's inventing facts. Lookups and IDs for what you can specify; AI for the fuzzy steps.

If you build only two: **#1 (prose extraction)** and **#2 (the "how are these two connected" feature)** — together they solve the messy-input problem and give the project an impressive front end.

---

## Suggested first three actions

1. Phase 0: get PostgreSQL running (Docker is the cleanest), create the `sixdegrees` database, and create the three tables from the schema above.
2. Load `rock_memberships_seed.csv` into those tables once, then query it back out with the join SQL to confirm the data's in there.
3. Build the NetworkX graph from that query and run one `shortest_path` — get the Cobain→Page chain to print. *Then* start Phase 1 (pull one band from the MusicBrainz API and `INSERT` it).

Nail those and you've already touched Postgres setup, schema design, SQL, and graph building — the spine of the whole pipeline. Everything after is expansion.

---

## Starter data + a lesson on connected components

`data/rock_memberships_seed.csv` contains ~46 real, verified bands spanning the 1960s–2000s (170 memberships, 103 musicians), organized as several dense genre webs: the Bluesbreakers/Cream/Fleetwood Mac blues web, the CSNY/Byrds/Buffalo Springfield folk-rock web, the Deep Purple/Sabbath/Rainbow metal web, the Yes/King Crimson/ELP/Asia prog web, and the Soundgarden/Pearl Jam/Alice in Chains grunge web.

Those webs are stitched into **one fully connected network** by six real bridge collaborations — worth knowing, because *this is a concept you'll hit constantly in graph work*: a graph made of separate islands has multiple **connected components**, and BFS can only find a path *within* a component. When two musicians are in different components, "no connection found" is the correct answer, not a bug. Run `nx.connected_components(G)` (or `nx.number_connected_components(G)`) to check — a healthy six-degrees graph is a single component.

The bridges that unify this one (each a genuine, documented supergroup or lineup move):

- **The Dirty Mac** (1968): Lennon + Clapton + Keith Richards → Beatles world ↔ Clapton/Stones web
- **Kenney Jones**: Faces drummer who joined The Who → The Who ↔ main web
- **Screaming Trees** + Mark Lanegan in Queens of the Stone Age → Seattle grunge ↔ main web
- **Mirror Ball** (1995): Neil Young backed by Pearl Jam → folk-rock ↔ grunge
- **XYZ** (1981): ex-Yes/Zeppelin, Jimmy Page + Chris Squire → prog ↔ main web
- **Emerson, Lake & Powell** (Cozy Powell) and **GTR** (Steve Howe + Steve Hackett) → metal and Genesis ↔ prog

Takeaway for when you start crawling in Phase 1: real data begins as many disconnected islands, and it's the *bridge bands* — supergroups, side projects, replacement members — that merge them. Finding those bridges is what makes a six-degrees graph interesting.
