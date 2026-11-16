"""Depth-First Search (DFS) for deep expansion path scouting."""

from __future__ import annotations

from map import Map, Territory


def get_expansion_paths(
    game_map: Map,
    start: Territory,
    depth_limit: int,
) -> list[list[Territory]]:
    """Return paths up to `depth_limit` into neutral or weakly defended (defense_bonus < 2) zones."""
    paths: list[list[Territory]] = []

    def _dfs(current: Territory, path: list[Territory], depth: int) -> None:
        if depth > 0 and (current.owner is None or current.defense_bonus < 2):
            paths.append(list(path))
        if depth >= depth_limit:
            return
        for neighbor in game_map.get_neighbors(current):
            if neighbor not in path:
                path.append(neighbor)
                _dfs(neighbor, path, depth + 1)
                path.pop()

    _dfs(start, [start], 0)
    return paths
