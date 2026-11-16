"""Greedy target selection.

Role 1: standalone attack target selection — get_greedy_move().
Role 2: MCTS rollout opponent model — mcts.py imports greedy_pick() so that every
        house in a simulated rollout picks moves greedily (never randomly).
"""

from __future__ import annotations

from collections.abc import Iterable

from house import House
from map import Map, Territory


def greedy_pick(candidates: Iterable[Territory]) -> Territory | None:
    """argmax(resource_value - defense_bonus); ties favour the Iron Throne."""
    pool = list(candidates)
    if not pool:
        return None
    return max(pool, key=lambda t: (t.resource_value - t.defense_bonus, t.is_iron_throne))


def get_greedy_move(
    house: House,
    game_map: Map,
    enemies: list[House] | None = None,
) -> Territory | None:
    """Select the adjacent enemy or neutral territory maximizing (resource_value - defense_bonus)."""
    enemy_names = {e.name.upper() for e in enemies} if enemies is not None else None
    candidates: set[Territory] = set()

    for territory in game_map.get_owned_by(house):
        for neighbor in game_map.get_neighbors(territory):
            if neighbor.owner == house.name:
                continue
            if neighbor.owner is None or enemy_names is None or neighbor.owner.upper() in enemy_names:
                candidates.add(neighbor)

    return greedy_pick(candidates)
