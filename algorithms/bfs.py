"""Breadth-First Search (BFS) for territory reachability checks."""

from __future__ import annotations

from collections import deque

from map import Map, Territory


def get_reachable(game_map: Map, start: Territory, n_steps: int) -> set[Territory]:
    """Return the set of territories reachable from `start` within `n_steps` edges."""
    visited: set[Territory] = {start}
    queue: deque[tuple[Territory, int]] = deque([(start, 0)])

    while queue:
        current, dist = queue.popleft()
        if dist >= n_steps:
            continue
        for neighbor in game_map.get_neighbors(current):
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, dist + 1))

    return visited
