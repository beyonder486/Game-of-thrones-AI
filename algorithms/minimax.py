"""Minimax with Alpha-Beta Pruning (Decomposed & Paranoid modes) for combat/expansion.

The search runs over a lightweight snapshot of the game (ownership, armies, gold)
and resolves simulated attacks with the *expected* outcome of the combat model
(random factors averaged to 1.0), so it never mutates the real game state.

KNOWN APPROXIMATIONS
  1. Decomposed Minimax: opponent interactions are evaluated independently —
     may underestimate coordination between enemies.
  2. Paranoid Minimax: assumes full coalition cooperation — valid while the
     alliance holds, not after breakdown (MCTS accounts for breakdown).
"""

from __future__ import annotations

import random

from algorithms.astar import get_path
from combat import effective_defense
from constants import MIN_ATTACK_ARMIES, MINIMAX_DEPTH, THRONE_BONUS
from diplomacy import Diplomacy
from house import House
from map import Map, Territory


def _throne_path_costs(game_map: Map) -> dict[str, float]:
    """Compute (and cache on the map) A* defense-weighted path cost from every hold to King's Landing."""
    cached = getattr(game_map, "_astar_throne_costs", None)
    if isinstance(cached, dict):
        return cached
    throne = game_map.iron_throne
    costs: dict[str, float] = {}
    for t in game_map.get_all():
        if t == throne:
            costs[t.name] = 0.0
        else:
            path = get_path(game_map, t, throne)
            costs[t.name] = sum(float(step.defense_bonus) for step in path[1:]) if path else 20.0
    setattr(game_map, "_astar_throne_costs", costs)
    return costs


class _State:
    """Mutable-by-copy snapshot used inside the search tree."""

    __slots__ = ("owner", "garrison", "armies", "gold")

    def __init__(
        self,
        owner: dict[str, str | None],
        garrison: dict[str, int],
        armies: dict[str, int],
        gold: dict[str, int],
    ) -> None:
        self.owner = owner
        self.garrison = garrison
        self.armies = armies
        self.gold = gold

    def copy(self) -> _State:
        return _State(dict(self.owner), dict(self.garrison), dict(self.armies), dict(self.gold))


def _snapshot(all_houses: list[House], game_map: Map) -> _State:
    return _State(
        owner={t.name: t.owner for t in game_map.get_all()},
        garrison={t.name: t.armies for t in game_map.get_all()},
        armies={h.name: h.armies for h in all_houses},
        gold={h.name: h.gold for h in all_houses},
    )


def _evaluate_state(me: str, enemy_names: list[str], game_map: Map, state: _State) -> float:
    all_territories = game_map.get_all()
    own_territories = [t for t in all_territories if state.owner[t.name] == me]
    own_territory_score = sum(t.resource_value + t.defense_bonus for t in own_territories)
    throne_bonus = THRONE_BONUS if state.owner[game_map.iron_throne.name] == me else 0
    # A* throne-corridor proximity: reward advancing along the lowest-defense-cost route to King's Landing
    throne_costs = _throne_path_costs(game_map)
    min_throne_cost = min((throne_costs[t.name] for t in own_territories), default=20.0)
    throne_approach = max(0.0, 12.0 - min_throne_cost) * 1.5
    enemy_score = sum(
        sum(t.resource_value for t in all_territories if state.owner[t.name] == e)
        + state.armies[e] * 1.5
        for e in enemy_names
    )
    return (
        own_territory_score * 2
        + state.armies[me] * 1.5
        + state.gold[me] * 0.5
        + throne_bonus
        + throne_approach
        - enemy_score
    )


def evaluate(house: House, enemies: list[House], game_map: Map, state: _State | None = None) -> float:
    """Spec evaluation: territory value, armies, gold, Iron Throne bonus minus enemy score."""
    if state is None:
        state = _snapshot([house, *enemies], game_map)
    return _evaluate_state(house.name, [e.name for e in enemies], game_map, state)


def _moves(state: _State, game_map: Map, name: str, forbidden: set[str]) -> list[Territory]:
    """Adjacent territories `name` may attack (never its own, never a protected owner)."""
    a_armies = state.armies.get(name, 0)
    if a_armies <= 0:
        return []
    seen: set[str] = set()
    result: list[Territory] = []
    for t in game_map.get_all():
        if state.owner[t.name] != name:
            continue
        for nb in t.neighbors:
            owner = state.owner[nb.name]
            if owner == name or owner in forbidden or nb.name in seen:
                continue
            # Army sufficiency restraint: if below MIN_ATTACK_ARMIES, only expand into neutral zones
            if a_armies < MIN_ATTACK_ARMIES and owner is not None:
                continue
            # Do not rush the Iron Throne unless military strength can plausibly overcome its defense
            if nb.is_iron_throne:
                d_armies = state.armies[owner] if owner else state.garrison[nb.name]
                if a_armies < effective_defense(d_armies, nb.defense_bonus, is_house=bool(owner)):
                    continue
            seen.add(nb.name)
            result.append(nb)
    return result


def _apply(state: _State, attacker: str, target: Territory) -> _State:
    """Expected outcome of the combat casualty model."""
    s = state.copy()
    defender = s.owner[target.name]
    d_armies = s.armies[defender] if defender else s.garrison[target.name]
    a_armies = s.armies[attacker]
    if a_armies > effective_defense(d_armies, target.defense_bonus, is_house=bool(defender)):
        s.armies[attacker] = max(1, a_armies - int(d_armies * 0.5))
        if defender:
            s.armies[defender] = max(1, d_armies - int(d_armies * 0.8))
        else:
            s.garrison[target.name] = 0
        s.owner[target.name] = attacker
        if defender and defender not in s.owner.values():
            s.gold[attacker] += s.gold[defender]
            s.gold[defender] = 0
    else:
        s.armies[attacker] = max(1, a_armies - int(a_armies * 0.6))
        if defender:
            s.armies[defender] = max(1, d_armies - int(d_armies * 0.2))
        else:
            s.garrison[target.name] = max(1, d_armies - int(d_armies * 0.2))
    return s


def _alphabeta(
    state: _State,
    game_map: Map,
    me: str,
    my_forbidden: set[str],
    opponents: list[str],
    eval_enemies: list[str],
    depth: int,
    alpha: float,
    beta: float,
    maximizing: bool,
) -> float:
    if depth == 0:
        return _evaluate_state(me, eval_enemies, game_map, state)

    if maximizing:
        value = float("-inf")
        for target in [None, *_moves(state, game_map, me, my_forbidden)]:
            child = state if target is None else _apply(state, me, target)
            value = max(
                value,
                _alphabeta(child, game_map, me, my_forbidden, opponents, eval_enemies, depth - 1, alpha, beta, False),
            )
            alpha = max(alpha, value)
            if alpha >= beta:
                break
        return value

    # Minimizing ply: the opponent side (one house, or a merged coalition) picks
    # the move that hurts us most. Coalition members never attack each other.
    value = float("inf")
    coalition = set(opponents)
    replies: list[tuple[str | None, Territory | None]] = [(None, None)]
    for opp in opponents:
        replies.extend((opp, t) for t in _moves(state, game_map, opp, coalition))
    for opp, target in replies:
        child = state if target is None else _apply(state, opp, target)
        value = min(
            value,
            _alphabeta(child, game_map, me, my_forbidden, opponents, eval_enemies, depth - 1, alpha, beta, True),
        )
        beta = min(beta, value)
        if alpha >= beta:
            break
    return value


def _search_root(
    state: _State,
    game_map: Map,
    me: str,
    root_moves: list[Territory | None],
    my_forbidden: set[str],
    opponents: list[str],
    eval_enemies: list[str],
    depth: int,
) -> dict[str | None, float]:
    """Score every root move with alpha-beta below it."""
    scores: dict[str | None, float] = {}
    alpha = float("-inf")
    for target in root_moves:
        child = state if target is None else _apply(state, me, target)
        score = _alphabeta(
            child, game_map, me, my_forbidden, opponents, eval_enemies, depth - 1, alpha, float("inf"), False
        )
        scores[target.name if target else None] = score
        alpha = max(alpha, score)
    return scores


def _decomposed_scores(
    house: House,
    enemies: list[House],
    game_map: Map,
    root_moves: list[Territory | None],
    state: _State,
    my_forbidden: set[str],
    depth: int = MINIMAX_DEPTH,
) -> dict[str | None, float]:
    total = sum(e.get_military_strength() for e in enemies) or 1.0
    combined: dict[str | None, float] = {}
    for enemy in enemies:
        weight = enemy.get_military_strength() / total
        scores = _search_root(
            state, game_map, house.name, root_moves, my_forbidden, [enemy.name], [enemy.name], depth
        )
        for key, value in scores.items():
            combined[key] = combined.get(key, 0.0) + weight * value
    return combined


def decomposed_minimax(
    house: House,
    enemies: list[House],
    game_map: Map,
    root_moves: list[Territory | None],
    state: _State,
    my_forbidden: set[str],
    depth: int = MINIMAX_DEPTH,
) -> Territory | None:
    # Heuristic approximation — opponent interactions evaluated independently:
    #   score = w2 * minimax(H1 vs H2) + w3 * minimax(H1 vs H3)
    #   w_i   = military_strength(H_i) / total_enemy_strength
    # May underestimate coordination effects between enemies.
    return _pick(_decomposed_scores(house, enemies, game_map, root_moves, state, my_forbidden, depth), game_map)


def paranoid_minimax(
    house: House,
    enemies: list[House],
    game_map: Map,
    root_moves: list[Territory | None],
    state: _State,
    my_forbidden: set[str],
    depth: int = MINIMAX_DEPTH,
) -> Territory | None:
    # Allied enemies are merged into a single virtual opponent (combined armies and
    # territories). Assumption is literally valid while the alliance holds;
    # MCTS accounts for breakdown.
    names = [e.name for e in enemies]
    scores = _search_root(state, game_map, house.name, root_moves, my_forbidden, names, names, depth)
    return _pick(scores, game_map)


def _pick(scores: dict[str | None, float], game_map: Map) -> Territory | None:
    if not scores:
        return None
    best_val = max(scores.values())
    # Allow slight opening variety among near-tied top moves (within 2.0 pts of optimal)
    top_attacks = [k for k, v in scores.items() if k is not None and v >= best_val - 2.0]
    if top_attacks:
        chosen = random.choice(top_attacks)
        return game_map.by_name[chosen]
    best = max(scores, key=lambda k: (scores[k], k is not None))
    return game_map.by_name[best] if best is not None else None


def get_move_scores(
    house: House,
    all_houses: list[House],
    game_map: Map,
    diplomacy: Diplomacy,
    betray_target: House | None = None,
) -> dict[str | None, float]:
    """Return Minimax scores for every candidate adjacent territory plus None (Hold)."""
    others = [h for h in all_houses if h.name != house.name and not h.is_eliminated()]
    if not others or house.armies <= 0:
        return {}
    state = _snapshot(all_houses, game_map)

    ally = next((h for h in others if diplomacy.are_allied(house, h)), None)
    if betray_target is not None:
        my_forbidden: set[str] = set()
        root_moves: list[Territory | None] = [
            t for t in _moves(state, game_map, house.name, set()) if t.owner == betray_target.name
        ]
        enemies = others
        if not root_moves:  # ally not adjacent — fall back to a normal move
            betray_target = None
    if betray_target is None:
        my_forbidden = {ally.name} if ally else set()
        root_moves = [None, *_moves(state, game_map, house.name, my_forbidden)]
        enemies = [h for h in others if h is not ally] or others

    if ally is not None and betray_target is None:
        house.mode = "PARANOID"
        names = [e.name for e in enemies]
        return _search_root(state, game_map, house.name, root_moves, my_forbidden, names, names, MINIMAX_DEPTH)
    if len(enemies) >= 2 and diplomacy.are_allied(enemies[0], enemies[1]):
        house.mode = "PARANOID"
        names = [e.name for e in enemies]
        return _search_root(state, game_map, house.name, root_moves, my_forbidden, names, names, MINIMAX_DEPTH)

    house.mode = "DECOMPOSED"
    return _decomposed_scores(house, enemies, game_map, root_moves, state, my_forbidden)


def get_best_move(
    house: House,
    all_houses: list[House],
    game_map: Map,
    diplomacy: Diplomacy,
    betray_target: House | None = None,
) -> Territory | None:
    """Select the combat/expansion target (None = hold this turn)."""
    scores = get_move_scores(house, all_houses, game_map, diplomacy, betray_target=betray_target)
    return _pick(scores, game_map)
