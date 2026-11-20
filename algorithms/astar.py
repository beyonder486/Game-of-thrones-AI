"""A* pathfinding for optimal troop movement routing."""

from __future__ import annotations

import heapq

from map import Map, Territory, hex_distance


def _heuristic(a: Territory, b: Territory) -> float:
    return float(hex_distance((a.col, a.row), (b.col, b.row)))


def get_path(game_map: Map, start: Territory, goal: Territory) -> list[Territory]:
    """Return the lowest-risk ordered path of territories from `start` to `goal`."""
    if start == goal:
        return [start]

    counter = 0
    open_heap: list[tuple[float, int, Territory]] = [(0.0, counter, start)]
    came_from: dict[Territory, Territory] = {}
    g_score: dict[Territory, float] = {start: 0.0}

    while open_heap:
        _, _, current = heapq.heappop(open_heap)
        if current == goal:
            path: list[Territory] = [current]
            while current in came_from:
                current = came_from[current]
                path.append(current)
            path.reverse()
            return path

        for neighbor in game_map.get_neighbors(current):
            tentative_g = g_score[current] + float(neighbor.defense_bonus)
            if tentative_g < g_score.get(neighbor, float("inf")):
                came_from[neighbor] = current
                g_score[neighbor] = tentative_g
                f_score = tentative_g + _heuristic(neighbor, goal)
                counter += 1
                heapq.heappush(open_heap, (f_score, counter, neighbor))

    return [start, goal]
