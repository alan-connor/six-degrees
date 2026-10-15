"""Hand-written BFS shortest path over the rock network.

A learning/demo script (not part of the runtime app). Self-contained: builds
the connection map from the seed CSV, then finds the fewest-hops chain between
two musicians -- no Postgres or NetworkX needed.

Run from the backend/ folder:  python setup/bfs_demo.py
"""
import csv
import os
from collections import deque, defaultdict

# The CSV lives at repo_root/data/. This file is at repo_root/backend/setup/,
# so climb three levels up to the repo root, then into data/.
CSV_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "rock_memberships_seed.csv",
)


def build_adjacency(rows):
    """Return {musician: {neighbor: band_that_links_them}}.

    Two musicians are neighbors if they share a band. We remember one linking
    band per pair so we can name the connection when we print the chain.
    """
    # Group musicians by band first.
    band_members = defaultdict(list)
    for r in rows:
        band_members[r["band"]].append(r["musician"])

    adjacency = defaultdict(dict)
    for band, members in band_members.items():
        # Every pair of members in the same band becomes an edge.
        for a in members:
            for b in members:
                if a != b:
                    adjacency[a][b] = band
    return adjacency


def shortest_path(adjacency, start, target):
    """Fewest-hops path from start to target, or None if they aren't connected."""
    if start not in adjacency or target not in adjacency:
        return None

    queue = deque([start])
    visited = {start}
    came_from = {start: None}

    while queue:
        current = queue.popleft()
        if current == target:
            break
        for neighbor in adjacency[current]:
            if neighbor not in visited:
                visited.add(neighbor)
                came_from[neighbor] = current
                queue.append(neighbor)

    # If we never reached the target, there's no connection.
    if target not in came_from:
        return None

    # Walk came_from backwards from target to start, then reverse.
    path = []
    node = target
    while node is not None:
        path.append(node)
        node = came_from[node]
    path.reverse()
    return path


def describe(adjacency, path):
    """Print the chain with the linking band between each pair."""
    if path is None:
        print("No connection found.")
        return
    degrees = len(path) - 1
    print(f"{degrees} degrees of separation:\n")
    for i, name in enumerate(path):
        print(f"  {name}")
        if i < len(path) - 1:
            band = adjacency[name][path[i + 1]]
            print(f"      | ({band})")


if __name__ == "__main__":
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    adjacency = build_adjacency(rows)

    path = shortest_path(adjacency, "Kurt Cobain", "Jimmy Page")
    describe(adjacency, path)
