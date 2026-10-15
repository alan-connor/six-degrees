"""Phase 3: build the NetworkX graph from Postgres and find shortest paths.

This is the library version of the hand-written BFS in bfs_demo.py -- same
result, but NetworkX does the traversal. It reads from Postgres (source of truth).

Nodes are musician *ids*, not names. Two different people can share a name
(Mick Jones of Foreigner vs The Clash), so keying on the stable id keeps them
distinct; each node carries a 'name' attribute for display. Names are resolved
to ids at query time, and a name may map to several people.

Run:  python graph.py
"""
import networkx as nx

from db import get_connection

# Pull every membership with the stable ids AND display names.
# is_rock IS NOT FALSE keeps confirmed-rock (true) and not-yet-fetched (NULL)
# bands, dropping only the ones the crawler confirmed are non-rock.
QUERY = """
SELECT m.id AS musician_id, m.name AS musician,
       b.id AS band_id,     b.name AS band,
       mem.instrument AS instrument
FROM memberships mem
JOIN musicians m ON m.id = mem.musician_id
JOIN bands     b ON b.id = mem.band_id
WHERE b.is_rock IS NOT FALSE
"""


def load_rows():
    """Fetch membership rows from Postgres as a list of dicts."""
    conn = get_connection()
    with conn, conn.cursor() as cur:
        cur.execute(QUERY)
        rows = [
            {"musician_id": mid, "musician": musician,
             "band_id": bid, "band": band, "instrument": instrument}
            for mid, musician, bid, band, instrument in cur.fetchall()
        ]
    conn.close()
    return rows


def _project(rows, node_id, node_name, group_id, group_name, edge_label):
    """Project the bipartite membership rows onto one axis.

    Nodes are `node_id` values (carrying `node_name` as a 'name' attribute);
    two nodes are linked when they share a `group_id`, and the edge stores the
    set of group display names under `edge_label`. This is the single shape
    behind both the musician graph and its mirror, the band graph.
    """
    G = nx.Graph()
    groups = {}        # group_id -> [node_id, ...]
    group_disp = {}    # group_id -> display name (for edge labels)
    for r in rows:
        G.add_node(r[node_id], name=r[node_name])
        groups.setdefault(r[group_id], []).append(r[node_id])
        group_disp[r[group_id]] = r[group_name]

    for gid, members in groups.items():
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                a, b = members[i], members[j]
                if a == b:
                    continue
                if G.has_edge(a, b):
                    G[a][b][edge_label].add(group_disp[gid])
                else:
                    G.add_edge(a, b, **{edge_label: {group_disp[gid]}})
    return G


def build_graph(rows):
    """Musician graph: nodes are musicians (by id), edges are shared bands.
    Each edge stores the set of band names linking the two musicians (attr
    'bands'), so we can name the connection later."""
    return _project(rows, "musician_id", "musician", "band_id", "band", "bands")


def build_band_graph(rows):
    """Band graph (mirror projection): nodes are bands (by id), edges are shared
    members. Each edge stores the set of member names linking the two bands
    (attr 'members'). Same rows, opposite axis."""
    return _project(rows, "band_id", "band", "musician_id", "musician", "members")


def ids_for_name(G, name):
    """All musician ids whose display name matches. Homonyms -> several ids."""
    return [n for n, d in G.nodes(data=True) if d.get("name") == name]


def shortest_path(G, start, target):
    """Fewest-hops path between two musicians, given as ids or names.

    A name may resolve to several people; we try every start/target id pair and
    return the shortest chain. Returns a list of node ids, or None.
    """
    starts = [start] if start in G else ids_for_name(G, start)
    targets = [target] if target in G else ids_for_name(G, target)
    best = None
    for s in starts:
        for t in targets:
            try:
                p = nx.shortest_path(G, s, t)
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                continue
            if best is None or len(p) < len(best):
                best = p
    return best


def describe(G, path):
    """Print the chain with a linking band between each pair."""
    if not path:
        print("No connection found.")
        return
    print(f"{len(path) - 1} degrees of separation:\n")
    for i, nid in enumerate(path):
        print(f"  {G.nodes[nid]['name']}")
        if i < len(path) - 1:
            band = sorted(G[nid][path[i + 1]]["bands"])[0]
            print(f"      | ({band})")


if __name__ == "__main__":
    rows = load_rows()
    G = build_graph(rows)
    print(f"Graph: {G.number_of_nodes()} musicians, {G.number_of_edges()} links\n")
    describe(G, shortest_path(G, "Kurt Cobain", "Jimmy Page"))
