"""Phase 4: FastAPI backend exposing the six-degrees graph as JSON.

Two projections of the same bipartite membership data, each with three endpoints:

  people view (nodes = musicians, edges = shared bands)
    GET /musicians          -> [{id, name, hint?}] for the UI dropdowns
    GET /path?from=&to=     -> shortest-path chain (from/to are ids OR names)
    GET /neighbors?id=      -> a musician's bandmates, for the graph view

  band view (nodes = bands, edges = shared members)
    GET /bands              -> [{id, name, hint?}]
    GET /band-path?from=&to=-> shortest path between two bands
    GET /band-neighbors?id= -> bands sharing a member

Both graphs are built once from Postgres at startup. Nodes are ids, so homonyms
(Mick Jones of Foreigner vs The Clash; the two Skid Rows) stay distinct; a name
lookup can resolve to several entities, returned for disambiguation.

Run (from backend/):  uvicorn api:app --reload      Docs: http://127.0.0.1:8000/docs
"""
from collections import Counter
from contextlib import asynccontextmanager

import networkx as nx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from graph import load_rows, build_graph, build_band_graph, ids_for_name

_state = {}   # holds the two in-memory graphs, built at startup


@asynccontextmanager
async def lifespan(app: FastAPI):
    rows = load_rows()
    _state["people"] = build_graph(rows)        # nodes = musicians, edges 'bands'
    _state["bands"] = build_band_graph(rows)    # nodes = bands, edges 'members'
    yield
    _state.clear()


app = FastAPI(title="Six Degrees of Rock", lifespan=lifespan)

# Dev CORS: the React (Vite) app runs on a different port and calls this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # dev only -- tighten to the frontend origin for deploy
    allow_methods=["GET"],
    allow_headers=["*"],
)


# --- shared helpers, parametrized by graph + the edge-set attribute name ------

def hint_for(g, node_id, label):
    """A representative linked name to tell homonyms apart -- a band for a
    musician node, a member for a band node."""
    for nbr in g[node_id]:
        names = g[node_id][nbr][label]
        if names:
            return sorted(names)[0]
    return None


def resolve_endpoint(g, value, label):
    """Turn a from|to value (an id or a name) into a node id on graph `g`.
    Returns (id, None), or (None, options) when a name is shared by several
    entities, or raises 404 if unknown."""
    if value.isdigit() and int(value) in g:
        return int(value), None
    ids = ids_for_name(g, value)
    if not ids:
        raise HTTPException(404, f"Unknown: {value!r}")
    if len(ids) > 1:
        return None, [{"id": i, "name": g.nodes[i]["name"], "hint": hint_for(g, i, label)}
                      for i in ids]
    return ids[0], None


def listing(g, label):
    """All nodes as {id, name, degree}, with a `hint` added for duplicated names.
    `degree` (how many others it links to) lets the UI seed on a well-connected one."""
    counts = Counter(d["name"] for _, d in g.nodes(data=True))
    out = []
    for n, d in g.nodes(data=True):
        item = {"id": n, "name": d["name"], "degree": g.degree(n)}
        if counts[d["name"]] > 1:
            item["hint"] = hint_for(g, n, label)
        out.append(item)
    out.sort(key=lambda m: m["name"].lower())
    return out


def shortest(g, from_, to, label, link_key):
    """Shortest-path result between two nodes given as ids or names."""
    src, src_opts = resolve_endpoint(g, from_, label)
    dst, dst_opts = resolve_endpoint(g, to, label)
    if src_opts or dst_opts:
        return {"ambiguous": {"from": src_opts, "to": dst_opts}}
    try:
        p = nx.shortest_path(g, src, dst)
    except nx.NetworkXNoPath:
        return {"connected": False, "degrees": None, "chain": []}
    chain = []
    for i, nid in enumerate(p):
        link = {"id": nid, "name": g.nodes[nid]["name"], link_key: None}
        if i < len(p) - 1:
            link[link_key] = ", ".join(sorted(g[nid][p[i + 1]][label]))
        chain.append(link)
    return {"connected": True, "degrees": len(p) - 1, "chain": chain}


def local(g, node_id, label, link_key):
    """A node's local subgraph (itself + direct neighbours) for the viz."""
    if node_id not in g:
        raise HTTPException(404, f"No node with id {node_id}")
    nodes = [{"id": node_id, "name": g.nodes[node_id]["name"]}]
    links = []
    for nbr in g[node_id]:
        nodes.append({"id": nbr, "name": g.nodes[nbr]["name"]})
        links.append({"source": node_id, "target": nbr,
                      link_key: ", ".join(sorted(g[node_id][nbr][label]))})
    return {"nodes": nodes, "links": links}


# --- endpoints ----------------------------------------------------------------

@app.get("/")
def root():
    p, b = _state["people"], _state["bands"]
    return {"service": "Six Degrees of Rock", "docs": "/docs",
            "people": {"nodes": p.number_of_nodes(), "edges": p.number_of_edges()},
            "bands": {"nodes": b.number_of_nodes(), "edges": b.number_of_edges()}}


# people view -- nodes are musicians, linked by shared bands
@app.get("/musicians")
def musicians():
    return listing(_state["people"], "bands")


@app.get("/path")
def path(from_: str = Query(alias="from"), to: str = Query(...)):
    return shortest(_state["people"], from_, to, "bands", "band_to_next")


@app.get("/neighbors")
def neighbors(id: int = Query(...)):
    return local(_state["people"], id, "bands", "band")


# band view -- nodes are bands, linked by shared members
@app.get("/bands")
def bands():
    return listing(_state["bands"], "members")


@app.get("/band-path")
def band_path(from_: str = Query(alias="from"), to: str = Query(...)):
    return shortest(_state["bands"], from_, to, "members", "member_to_next")


@app.get("/band-neighbors")
def band_neighbors(id: int = Query(...)):
    return local(_state["bands"], id, "members", "member")
