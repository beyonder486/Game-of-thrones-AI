"""Monte Carlo Tree Search (MCTS) for strategic diplomacy decisions.

Context A — own diplomatic decision:   ["propose_alliance", "betray", "solo"]
Context B — responding to a proposal:  ["accept", "reject"]

Fuzzy scores are used as UCT action biases — they never replace simulation:
    UCT = Q/N + UCT_C * sqrt(ln(N_parent) / N) + fuzzy_score[action]

KNOWN APPROXIMATION: rollouts use the Greedy opponent model for every house,
not a true recursive MCTS for each opponent — a computationally tractable
tradeoff.
"""

from __future__ import annotations

import math
import random

from algorithms.greedy import greedy_pick
from constants import (
    ARMY_COST,
    BASE_INCOME,
    MCTS_ITER,
    MCTS_ROLLOUT_DEPTH,
    REWARD_ALLIANCE_RISK,
    REWARD_MILITARY,
    REWARD_RESOURCE,
    REWARD_TERRITORY,
    REWARD_THRONE,
    UCT_C,
)
from diplomacy import Diplomacy
from house import House
from map import Map, Territory

# Rewards are divided by this before entering UCT so the exploration term and
# the fuzzy bias (both ~0-1) stay on a comparable scale with Q/N.
REWARD_SCALE = 100.0

# Context A action → fuzzy score key
CONTEXT_A_BIAS = {"propose_alliance": "alliance", "betray": "betrayal", "solo": "solo"}


class _MCTSNode:
    def __init__(self, action: str, bias: float) -> None:
        self.action = action
        self.bias = bias
        self.visits = 0
        self.total_reward = 0.0


class _Sim:
    """Compact, index-based snapshot of the game for fast rollouts."""

    def __init__(self, all_houses: list[House], game_map: Map) -> None:
        self.territories: list[Territory] = game_map.get_all()
        index = {t.name: i for i, t in enumerate(self.territories)}
        self.adjacency = [[index[n.name] for n in t.neighbors] for t in self.territories]
        self.throne = index[game_map.iron_throne.name]
        self.order = [h.name for h in all_houses]
        self.owner = [t.owner for t in self.territories]
        self.garrison = [t.armies for t in self.territories]
        self.armies = {h.name: float(h.armies) for h in all_houses}
        self.gold = {h.name: float(h.gold) for h in all_houses}

    def clone(self) -> _Sim:
        other = object.__new__(_Sim)
        other.territories = self.territories
        other.adjacency = self.adjacency
        other.throne = self.throne
        other.order = self.order
        other.owner = list(self.owner)
        other.garrison = list(self.garrison)
        other.armies = dict(self.armies)
        other.gold = dict(self.gold)
        return other

    def alive(self, name: str) -> bool:
        return name in self.owner

    def candidates(self, name: str, protected: str | None, only: str | None = None) -> list[Territory]:
        seen: set[int] = set()
        for i, owner in enumerate(self.owner):
            if owner != name:
                continue
            for j in self.adjacency[i]:
                o = self.owner[j]
                if o == name or (protected is not None and o == protected):
                    continue
                if only is not None and o != only:
                    continue
                seen.add(j)
        return [self.territories[j] for j in seen]

    def attack(self, attacker: str, target: Territory) -> None:
        j = self.territories.index(target)
        defender = self.owner[j]
        d_armies = self.armies[defender] if defender else float(self.garrison[j])
        a_power = self.armies[attacker] * random.uniform(0.8, 1.2)
        d_power = d_armies * target.defense_bonus * random.uniform(0.8, 1.2)
        if a_power > d_power:
            self.armies[attacker] = max(0.0, self.armies[attacker] - int(d_armies * 0.5))
            if defender:
                self.armies[defender] = d_armies - int(d_armies * 0.8)
            else:
                self.garrison[j] = 0
            self.owner[j] = attacker
            if defender and defender not in self.owner:
                self.gold[attacker] += self.gold[defender]
                self.gold[defender] = 0.0
        else:
            self.armies[attacker] -= int(self.armies[attacker] * 0.6)
            if defender:
                self.armies[defender] = d_armies - int(d_armies * 0.2)
            else:
                self.garrison[j] = int(d_armies - int(d_armies * 0.2))

    def economy(self) -> None:
        for name in self.order:
            if not self.alive(name):
                continue
            self.gold[name] += BASE_INCOME + sum(
                t.resource_value for t, o in zip(self.territories, self.owner) if o == name
            )
            recruits = int(self.gold[name] // ARMY_COST) // 2
            self.armies[name] += recruits
            self.gold[name] -= recruits * ARMY_COST

    def reward(self, me: str, alliance_risk_penalty: float) -> float:
        mine = [t for t, o in zip(self.territories, self.owner) if o == me]
        territory_score = sum(t.resource_value + t.defense_bonus for t in mine)
        military_strength = self.armies[me] + sum(t.defense_bonus for t in mine)
        resource_score = sum(t.resource_value for t in mine)
        return (
            REWARD_TERRITORY * territory_score
            + REWARD_MILITARY * military_strength
            + REWARD_RESOURCE * resource_score
            + REWARD_ALLIANCE_RISK * alliance_risk_penalty  # weight is negative (-0.4)
        )


def _rollout(
    base: _Sim,
    me: str,
    partner: str | None,
    trust: float,
    alliance_active: bool,
    alliance_pending: bool,
    betray_first: str | None,
) -> float:
    """Play MCTS_ROLLOUT_DEPTH turns where every house moves greedily."""
    sim = base.clone()
    risk = 30.0 if betray_first else 0.0  # betrayal costs 30 trust points
    allied = alliance_active

    for step in range(MCTS_ROLLOUT_DEPTH):
        if alliance_pending and step == 1:
            allied = True
        if allied:
            # Alliance breakdown: p_break = 1 - trust/100 → solo play for the remainder.
            if random.random() < 1.0 - trust / 100.0:
                allied = False
                risk += 10.0
            else:
                risk += (1.0 - trust / 100.0) * 5.0

        for name in sim.order:
            if not sim.alive(name) or sim.armies[name] <= 0:
                continue
            protected = None
            if allied and partner is not None:
                if name == me:
                    protected = partner
                elif name == partner:
                    protected = me
            if step == 0 and name == me and betray_first:
                pool = sim.candidates(name, None, only=betray_first)
            else:
                pool = sim.candidates(name, protected)
            target = greedy_pick(pool)
            if target is not None:
                sim.attack(name, target)

        holder = sim.owner[sim.throne]
        if holder == me:
            return REWARD_THRONE / REWARD_SCALE
        if not sim.alive(me):
            return 0.0
        if holder is not None:
            # A rival took the throne: the game would end in defeat, so the
            # positional reward is halved rather than flattened to zero (keeps
            # actions distinguishable when rivals often win the race).
            return 0.5 * max(0.0, sim.reward(me, risk)) / REWARD_SCALE
        sim.economy()

    return max(0.0, sim.reward(me, risk)) / REWARD_SCALE


def _run_uct(
    actions: dict[str, float],
    simulate: dict[str, callable],
) -> str:
    children = [_MCTSNode(action, bias) for action, bias in actions.items()]
    parent_visits = 0
    for _ in range(MCTS_ITER):
        parent_visits += 1
        unvisited = [c for c in children if c.visits == 0]
        if unvisited:
            node = unvisited[0]
        else:
            node = max(
                children,
                key=lambda c: c.total_reward / c.visits
                + UCT_C * math.sqrt(math.log(parent_visits) / c.visits)
                + c.bias,
            )
        node.total_reward += simulate[node.action]()
        node.visits += 1
    return max(children, key=lambda c: (c.visits, c.total_reward)).action


def get_diplomacy_decision(
    house: House,
    all_houses: list[House],
    game_map: Map,
    fuzzy_scores: dict[str, float],
    diplomacy: Diplomacy,
) -> tuple[str, House | None]:
    """Context A → ("propose_alliance" | "betray" | "solo", target_house)."""
    others = [h for h in all_houses if h.name != house.name and not h.is_eliminated()]
    ally = next((h for h in others if diplomacy.are_allied(house, h)), None)
    base = _Sim(all_houses, game_map)

    actions: dict[str, float] = {"solo": fuzzy_scores.get("solo", 0.0)}
    simulate: dict[str, callable] = {}
    targets: dict[str, House | None] = {"solo": None}

    if ally is not None:
        trust = diplomacy.get_trust(house, ally)
        actions["betray"] = fuzzy_scores.get("betrayal", 0.0)
        targets["betray"] = ally
        simulate["solo"] = lambda: _rollout(base, house.name, ally.name, trust, True, False, None)
        simulate["betray"] = lambda: _rollout(base, house.name, ally.name, trust, False, False, ally.name)
    elif len(others) >= 2:
        # Court the most trusted house; on ties, the weaker one (ally against the strongest).
        partner = max(others, key=lambda h: (diplomacy.get_trust(house, h), -h.get_military_strength()))
        trust = diplomacy.get_trust(house, partner)
        actions["propose_alliance"] = fuzzy_scores.get("alliance", 0.0)
        targets["propose_alliance"] = partner
        # The partner answers next turn; model acceptance with probability trust/100.
        simulate["solo"] = lambda: _rollout(base, house.name, None, trust, False, False, None)
        simulate["propose_alliance"] = lambda: _rollout(
            base, house.name, partner.name, trust, False, random.random() < trust / 100.0, None
        )
    else:
        return "solo", None

    decision = _run_uct(actions, simulate)
    return decision, targets[decision]


def get_proposal_response(
    house: House,
    proposer: House,
    all_houses: list[House],
    game_map: Map,
    fuzzy_scores: dict[str, float],
    diplomacy: Diplomacy,
) -> str:
    """Context B → "accept" | "reject".

    Biases: accept ← alliance desirability, reject ← max(betrayal, solo).
    """
    if proposer.is_eliminated() or house.is_eliminated():
        return "reject"
    surviving = [h for h in all_houses if not h.is_eliminated()]
    if len(surviving) <= 2:
        return "reject"
    base = _Sim(all_houses, game_map)
    trust = diplomacy.get_trust(house, proposer)
    actions = {
        "accept": fuzzy_scores.get("alliance", 0.0),
        "reject": max(fuzzy_scores.get("betrayal", 0.0), fuzzy_scores.get("solo", 0.0)),
    }
    simulate = {
        "accept": lambda: _rollout(base, house.name, proposer.name, trust, True, False, None),
        "reject": lambda: _rollout(base, house.name, None, trust, False, False, None),
    }
    return _run_uct(actions, simulate)
