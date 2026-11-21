"""Standalone Presentation Visualizer for Game of Thrones: AI Conquest.

Runs the real Python AI engines (Minimax with Alpha-Beta Pruning, MCTS with UCT,
A* Pathfinding, and Mamdani Fuzzy Logic) on authentic Westeros board states,
records step-by-step execution traces, and generates a single self-contained,
offline-ready interactive HTML/SVG presentation app (`tree_visualizer.html`).

Usage:
    python visualize_trees.py
    python visualize_trees.py --seed 42 --open
"""

from __future__ import annotations

import argparse
import heapq
import json
import math
import os
import random
import webbrowser
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from algorithms.astar import _heuristic, get_path
from algorithms.fuzzy_diplomacy import evaluate_diplomacy
from algorithms.greedy import greedy_pick
from algorithms.mcts import REWARD_SCALE, _Sim
from algorithms.minimax import (
    _apply,
    _evaluate_state,
    _moves,
    _snapshot,
    _throne_path_costs,
)
from combat import effective_defense
from constants import (
    MCTS_ITER,
    MCTS_ROLLOUT_DEPTH,
    MINIMAX_DEPTH,
    REWARD_THRONE,
    THRONE_BONUS,
    UCT_C,
)
from diplomacy import Diplomacy
from house import House, create_initial_houses
from map import Map, Territory, hex_distance


# ---------------------------------------------------------------------------
# Helpers: build real Westeros board snapshots
# ---------------------------------------------------------------------------


def _set_trust(diplomacy: Diplomacy, h1: House, h2: House, value: float) -> None:
    diplomacy.trust_scores[(h1.name, h2.name)] = float(value)
    diplomacy.trust_scores[(h2.name, h1.name)] = float(value)
    diplomacy._sync_house(h1.name)
    diplomacy._sync_house(h2.name)


def _grant_holds(game_map: Map, house: House, names: tuple[str, ...]) -> None:
    for name in names:
        t = game_map.by_name[name]
        t.armies = 0
        house.gain_territory(t)


def _make_initial_world() -> tuple[Map, list[House], Diplomacy]:
    """Create the exact Turn-1 starting state of the game."""
    game_map = Map()
    houses = create_initial_houses(game_map)
    diplomacy = Diplomacy(houses)
    return game_map, houses, diplomacy


def _make_midgame_world() -> tuple[Map, list[House], Diplomacy]:
    """Create an authentic Turn-5 mid-game Westeros state for Paranoid/MCTS demos."""
    game_map, houses, diplomacy = _make_initial_world()
    by_name = {h.name: h for h in houses}

    _grant_holds(game_map, by_name["STARK"], ("THE WALL", "MOAT CAILIN", "PYKE"))
    by_name["STARK"].armies = 15
    by_name["STARK"].gold = 72

    _grant_holds(game_map, by_name["LANNISTER"], ("LANNISPORT", "OLDTOWN", "HIGHGARDEN", "RIVERRUN"))
    by_name["LANNISTER"].armies = 24
    by_name["LANNISTER"].gold = 95

    _grant_holds(game_map, by_name["TARGARYEN"], ("STORM'S END", "THE EYRIE"))
    by_name["TARGARYEN"].armies = 16
    by_name["TARGARYEN"].gold = 68

    _set_trust(diplomacy, by_name["STARK"], by_name["TARGARYEN"], 68)
    _set_trust(diplomacy, by_name["STARK"], by_name["LANNISTER"], 30)
    _set_trust(diplomacy, by_name["LANNISTER"], by_name["TARGARYEN"], 42)
    return game_map, houses, diplomacy


def _make_betrayal_world() -> tuple[Map, list[House], Diplomacy]:
    """Create a late-mid-game state where Stark & Targaryen are allied, Stark is strong & trust is low."""
    game_map, houses, diplomacy = _make_initial_world()
    by_name = {h.name: h for h in houses}

    _grant_holds(game_map, by_name["STARK"], ("THE WALL", "CASTLE BLACK", "MOAT CAILIN", "THE TWINS", "RIVERRUN"))
    by_name["STARK"].armies = 28
    by_name["STARK"].gold = 110

    _grant_holds(game_map, by_name["LANNISTER"], ("LANNISPORT", "OLDTOWN"))
    by_name["LANNISTER"].armies = 11
    by_name["LANNISTER"].gold = 45

    _grant_holds(game_map, by_name["TARGARYEN"], ("STORM'S END", "HARRENHAL", "WHITE HARBOR"))
    by_name["TARGARYEN"].armies = 14
    by_name["TARGARYEN"].gold = 60

    diplomacy.form_alliance(by_name["STARK"], by_name["TARGARYEN"])
    _set_trust(diplomacy, by_name["STARK"], by_name["TARGARYEN"], 22)
    _set_trust(diplomacy, by_name["STARK"], by_name["LANNISTER"], 35)
    _set_trust(diplomacy, by_name["LANNISTER"], by_name["TARGARYEN"], 40)
    return game_map, houses, diplomacy


# ---------------------------------------------------------------------------
# 1. Minimax + Alpha-Beta Pruning Trace Recorder
# ---------------------------------------------------------------------------


def _eval_breakdown(me: str, enemy_names: list[str], game_map: Map, state) -> dict[str, object]:
    """Compute exact _evaluate_state() and return every arithmetic component."""
    all_territories = game_map.get_all()
    own_territories = [t for t in all_territories if state.owner[t.name] == me]
    own_terr_raw = sum(t.resource_value + t.defense_bonus for t in own_territories)
    own_terr_term = round(own_terr_raw * 2.0, 2)
    armies_val = state.armies[me]
    armies_term = round(armies_val * 1.5, 2)
    gold_val = state.gold[me]
    gold_term = round(gold_val * 0.5, 2)
    throne_owner = state.owner[game_map.iron_throne.name]
    throne_term = float(THRONE_BONUS) if throne_owner == me else 0.0

    throne_costs = _throne_path_costs(game_map)
    if own_territories:
        closest_hold = min(own_territories, key=lambda t: throne_costs[t.name])
        min_cost = throne_costs[closest_hold.name]
        closest_name = closest_hold.name
    else:
        min_cost = 20.0
        closest_name = "NONE"
    astar_term = round(max(0.0, 12.0 - min_cost) * 1.5, 2)

    enemy_res_total = 0
    enemy_armies_total = 0
    for e in enemy_names:
        enemy_res_total += sum(t.resource_value for t in all_territories if state.owner[t.name] == e)
        enemy_armies_total += state.armies[e]
    enemy_term = round(enemy_res_total + enemy_armies_total * 1.5, 2)

    total = round(_evaluate_state(me, enemy_names, game_map, state), 2)
    return {
        "own_holds": [t.name for t in own_territories],
        "own_terr_raw": own_terr_raw,
        "own_terr_term": own_terr_term,
        "armies": armies_val,
        "armies_term": armies_term,
        "gold": gold_val,
        "gold_term": gold_term,
        "throne_term": throne_term,
        "closest_hold": closest_name,
        "min_throne_cost": round(min_cost, 1),
        "astar_term": astar_term,
        "enemy_res": enemy_res_total,
        "enemy_armies": enemy_armies_total,
        "enemy_term": enemy_term,
        "total": total,
    }


def _fmt_bound(v: float) -> str:
    if v == float("-inf"):
        return "-∞"
    if v == float("inf"):
        return "+∞"
    return f"{v:+.1f}"


def record_minimax_scenario(
    scenario_id: str,
    title: str,
    subtitle: str,
    mode: str,
    me: str,
    opponents: list[str],
    game_map: Map,
    houses: list[House],
    my_forbidden: set[str],
    depth: int = MINIMAX_DEPTH,
    max_branch: int | None = None,
    global_root_alpha: bool = False,
) -> dict[str, object]:
    """Run real Depth-3 Alpha-Beta Minimax and record every tree node + step event."""
    state0 = _snapshot(houses, game_map)
    nodes: list[dict[str, object]] = []
    events: list[dict[str, object]] = []

    def add_node(
        parent_id: int | None,
        ply: int,
        kind: str,
        actor: str,
        move_label: str,
        pruned: bool = False,
    ) -> int:
        nid = len(nodes)
        nodes.append(
            {
                "id": nid,
                "parent": parent_id,
                "children": [],
                "ply": ply,
                "kind": kind,  # "MAX" | "MIN" | "LEAF"
                "actor": actor,
                "move": move_label,
                "pruned": pruned,
                "value": None,
                "alpha": "-∞",
                "beta": "+∞",
                "breakdown": None,
                "combat_note": "",
            }
        )
        if parent_id is not None:
            nodes[parent_id]["children"].append(nid)
        return nid

    root_id = add_node(None, 0, "MAX", me, f"ROOT ({me})")
    root_breakdown = _eval_breakdown(me, opponents, game_map, state0)
    nodes[root_id]["breakdown"] = root_breakdown

    def combat_summary(before, after, attacker: str, target: Territory | None) -> str:
        if target is None:
            if attacker in before.armies:
                return f"{attacker} holds fortifications (armies stay {before.armies[attacker]})."
            return f"Coalition ({attacker}) holds fortifications."
        defender = before.owner[target.name]
        d_arm = before.armies[defender] if defender else before.garrison[target.name]
        eff = effective_defense(d_arm, target.defense_bonus, is_house=bool(defender))
        a_before = before.armies[attacker]
        a_after = after.armies[attacker]
        won = after.owner[target.name] == attacker
        verdict = "CAPTURED" if won else "REPELLED"
        def_label = defender if defender else "Neutral"
        return (
            f"{attacker} ({a_before} arm) → {target.name} ({def_label} {d_arm}×def{target.defense_bonus} "
            f"→ eff {eff:.1f}): {verdict} (attacker → {a_after} arm)."
        )

    def _ab(
        state,
        parent_id: int,
        ply: int,
        rem_depth: int,
        alpha: float,
        beta: float,
        maximizing: bool,
    ) -> float:
        throne_owner = state.owner[game_map.iron_throne.name]
        if rem_depth == 0 or throne_owner is not None:
            bd = _eval_breakdown(me, opponents, game_map, state)
            val = float(bd["total"])
            bonus_note = ""
            if throne_owner == me and rem_depth > 0:
                val += rem_depth * 50.0
                bonus_note = f" + {rem_depth * 50.0:.0f} early-throne bonus"
            elif throne_owner is not None and rem_depth > 0:
                val -= rem_depth * 50.0
                bonus_note = f" − {rem_depth * 50.0:.0f} rival-throne penalty"
            val = round(val, 2)
            nodes[parent_id]["kind"] = "LEAF"
            nodes[parent_id]["value"] = val
            nodes[parent_id]["breakdown"] = bd
            nodes[parent_id]["alpha"] = _fmt_bound(alpha)
            nodes[parent_id]["beta"] = _fmt_bound(beta)
            events.append(
                {
                    "type": "leaf",
                    "node": parent_id,
                    "value": val,
                    "alpha": _fmt_bound(alpha),
                    "beta": _fmt_bound(beta),
                    "msg": (
                        f"Evaluate leaf [{nodes[parent_id]['move']}]: "
                        f"2×Terr({bd['own_terr_term']:+.1f}) + 1.5×Arm({bd['armies_term']:+.1f}) "
                        f"+ 0.5×Gold({bd['gold_term']:+.1f}) + A*({bd['astar_term']:+.1f}) "
                        f"− Enemy({bd['enemy_term']:.1f}){bonus_note} = {val:+.1f}."
                    ),
                }
            )
            return val

        if maximizing:
            value = float("-inf")
            cand_targets: list[Territory | None] = [None, *_moves(state, game_map, me, my_forbidden)]
            if max_branch is not None and len(cand_targets) > max_branch:
                cand_targets = cand_targets[:max_branch]
            for idx, target in enumerate(cand_targets):
                move_lbl = "HOLD" if target is None else target.name
                child_state = state if target is None else _apply(state, me, target)
                child_kind = "LEAF" if (rem_depth - 1 == 0 or child_state.owner[game_map.iron_throne.name] is not None) else "MIN"
                cid = add_node(parent_id, ply + 1, child_kind, me, move_lbl)
                nodes[cid]["combat_note"] = combat_summary(state, child_state, me, target)
                events.append(
                    {
                        "type": "enter",
                        "node": cid,
                        "alpha": _fmt_bound(alpha),
                        "beta": _fmt_bound(beta),
                        "msg": (
                            f"MAX ({me}) explores {move_lbl} with window "
                            f"(α={_fmt_bound(alpha)}, β={_fmt_bound(beta)}). {nodes[cid]['combat_note']}"
                        ),
                    }
                )
                child_val = _ab(child_state, cid, ply + 1, rem_depth - 1, alpha, beta, False)
                if child_val > value:
                    value = child_val
                if value > alpha:
                    alpha = value
                nodes[parent_id]["value"] = round(value, 2)
                nodes[parent_id]["alpha"] = _fmt_bound(alpha)
                nodes[parent_id]["beta"] = _fmt_bound(beta)
                events.append(
                    {
                        "type": "backup",
                        "node": parent_id,
                        "from": cid,
                        "value": round(value, 2),
                        "alpha": _fmt_bound(alpha),
                        "beta": _fmt_bound(beta),
                        "msg": (
                            f"MAX node [{nodes[parent_id]['move']}] backs up {child_val:+.1f} from {move_lbl} "
                            f"→ best={value:+.1f}, α={_fmt_bound(alpha)}, β={_fmt_bound(beta)}."
                        ),
                    }
                )
                if alpha >= beta:
                    skipped = cand_targets[idx + 1 :]
                    pruned_ids = []
                    for sk in skipped:
                        sk_lbl = "HOLD" if sk is None else sk.name
                        pid = add_node(parent_id, ply + 1, "LEAF", me, sk_lbl, pruned=True)
                        pruned_ids.append(pid)
                    if pruned_ids:
                        sk_names = ", ".join("HOLD" if s is None else s.name for s in skipped)
                        events.append(
                            {
                                "type": "prune",
                                "node": parent_id,
                                "pruned_ids": pruned_ids,
                                "alpha": _fmt_bound(alpha),
                                "beta": _fmt_bound(beta),
                                "msg": (
                                    f"β-CUTOFF! α ({_fmt_bound(alpha)}) ≥ β ({_fmt_bound(beta)}): "
                                    f"parent MIN already has a better option ≤ {_fmt_bound(beta)}. "
                                    f"Pruned {len(pruned_ids)} sibling(s): {sk_names}."
                                ),
                            }
                        )
                    break
            return value

        # Minimizing ply
        value = float("inf")
        coalition = set(opponents)
        replies: list[tuple[str | None, Territory | None]] = [(None, None)]
        for opp in opponents:
            replies.extend((opp, t) for t in _moves(state, game_map, opp, coalition))
        if max_branch is not None and len(replies) > max_branch:
            replies = replies[:max_branch]

        opp_label = "+".join(opponents)
        for idx, (opp, target) in enumerate(replies):
            move_lbl = "HOLD" if target is None else (f"{opp[:3]}:{target.name}" if len(opponents) > 1 else target.name)
            actor_name = opp if opp else opp_label
            child_state = state if target is None else _apply(state, opp, target)
            child_kind = "LEAF" if (rem_depth - 1 == 0 or child_state.owner[game_map.iron_throne.name] is not None) else "MAX"
            cid = add_node(parent_id, ply + 1, child_kind, actor_name, move_lbl)
            nodes[cid]["combat_note"] = combat_summary(state, child_state, actor_name, target)
            events.append(
                {
                    "type": "enter",
                    "node": cid,
                    "alpha": _fmt_bound(alpha),
                    "beta": _fmt_bound(beta),
                    "msg": (
                        f"MIN ({actor_name}) tests counter-move {move_lbl} with window "
                        f"(α={_fmt_bound(alpha)}, β={_fmt_bound(beta)}). {nodes[cid]['combat_note']}"
                    ),
                }
            )
            child_val = _ab(child_state, cid, ply + 1, rem_depth - 1, alpha, beta, True)
            if child_val < value:
                value = child_val
            if value < beta:
                beta = value
            nodes[parent_id]["value"] = round(value, 2)
            nodes[parent_id]["alpha"] = _fmt_bound(alpha)
            nodes[parent_id]["beta"] = _fmt_bound(beta)
            events.append(
                {
                    "type": "backup",
                    "node": parent_id,
                    "from": cid,
                    "value": round(value, 2),
                    "alpha": _fmt_bound(alpha),
                    "beta": _fmt_bound(beta),
                    "msg": (
                        f"MIN node [{nodes[parent_id]['move']}] backs up {child_val:+.1f} from {move_lbl} "
                        f"→ worst-case={value:+.1f}, α={_fmt_bound(alpha)}, β={_fmt_bound(beta)}."
                    ),
                }
            )
            if alpha >= beta:
                skipped = replies[idx + 1 :]
                pruned_ids = []
                for sk_opp, sk_t in skipped:
                    sk_lbl = "HOLD" if sk_t is None else (f"{sk_opp[:3]}:{sk_t.name}" if len(opponents) > 1 else sk_t.name)
                    pid = add_node(parent_id, ply + 1, "MAX", sk_opp or opp_label, sk_lbl, pruned=True)
                    pruned_ids.append(pid)
                if pruned_ids:
                    sk_names = ", ".join("HOLD" if s[1] is None else s[1].name for s in skipped)
                    events.append(
                        {
                            "type": "prune",
                            "node": parent_id,
                            "pruned_ids": pruned_ids,
                            "alpha": _fmt_bound(alpha),
                            "beta": _fmt_bound(beta),
                            "msg": (
                                f"α-CUTOFF! α ({_fmt_bound(alpha)}) ≥ β ({_fmt_bound(beta)}): "
                                f"MAX already guaranteed ≥ {_fmt_bound(alpha)} elsewhere. "
                                f"Pruned {len(pruned_ids)} reply branch(es): {sk_names}."
                            ),
                        }
                    )
                break
        return value

    # Root loop
    root_moves: list[Territory | None] = [None, *_moves(state0, game_map, me, my_forbidden)]
    if max_branch is not None and len(root_moves) > max_branch:
        root_moves = root_moves[:max_branch]

    events.append(
        {
            "type": "enter",
            "node": root_id,
            "alpha": "-∞",
            "beta": "+∞",
            "msg": (
                f"Start {mode} Minimax (Depth {depth}) for House {me} vs {' & '.join(opponents)}. "
                f"Evaluating {len(root_moves)} root actions: "
                f"{', '.join('HOLD' if m is None else m.name for m in root_moves)}."
            ),
        }
    )

    root_alpha = float("-inf")
    root_best_val = float("-inf")
    root_best_cid = None
    root_scores: dict[str, float] = {}

    for target in root_moves:
        move_lbl = "HOLD" if target is None else target.name
        child_state = state0 if target is None else _apply(state0, me, target)
        cid = add_node(root_id, 1, "MIN", me, move_lbl)
        nodes[cid]["combat_note"] = combat_summary(state0, child_state, me, target)
        search_alpha = root_alpha if global_root_alpha else float("-inf")
        events.append(
            {
                "type": "enter",
                "node": cid,
                "alpha": _fmt_bound(search_alpha),
                "beta": "+∞",
                "msg": (
                    f"Root MAX tests action {move_lbl} "
                    f"(window α={_fmt_bound(search_alpha)}, β=+∞). {nodes[cid]['combat_note']}"
                ),
            }
        )
        score = _ab(child_state, cid, 1, depth - 1, search_alpha, float("inf"), False)
        score = round(score, 2)
        root_scores[move_lbl] = score
        if score > root_best_val:
            root_best_val = score
            root_best_cid = cid
        if global_root_alpha and score > root_alpha:
            root_alpha = score
        nodes[root_id]["value"] = round(root_best_val, 2)
        nodes[root_id]["alpha"] = _fmt_bound(root_best_val)
        events.append(
            {
                "type": "backup",
                "node": root_id,
                "from": cid,
                "value": round(root_best_val, 2),
                "alpha": _fmt_bound(root_best_val),
                "beta": "+∞",
                "msg": (
                    f"Root MAX finishes subtree [{move_lbl}] = {score:+.1f}. "
                    f"Current best action: {nodes[root_best_cid]['move']} ({root_best_val:+.1f})."
                ),
            }
        )

    # Trace winning principal variation path from root down to optimal leaf
    pv_path: list[int] = [root_id]
    cur = root_id
    while nodes[cur]["children"]:
        valid_kids = [c for c in nodes[cur]["children"] if not nodes[c]["pruned"] and nodes[c]["value"] is not None]
        if not valid_kids:
            break
        if nodes[cur]["kind"] == "MAX":
            nxt = max(valid_kids, key=lambda c: nodes[c]["value"])
        else:
            nxt = min(valid_kids, key=lambda c: nodes[c]["value"])
        pv_path.append(nxt)
        cur = nxt

    events.append(
        {
            "type": "finish",
            "node": root_best_cid if root_best_cid is not None else root_id,
            "pv_path": pv_path,
            "best_move": nodes[root_best_cid]["move"] if root_best_cid is not None else "HOLD",
            "best_value": round(root_best_val, 2),
            "msg": (
                f"Search complete! Optimal move for {me}: {nodes[root_best_cid]['move']} "
                f"(Minimax value {root_best_val:+.1f}). Principal variation highlighted in emerald."
            ),
        }
    )

    pruned_count = sum(1 for n in nodes if n["pruned"])
    leaf_count = sum(1 for n in nodes if n["kind"] == "LEAF" and not n["pruned"])

    return {
        "id": scenario_id,
        "title": title,
        "subtitle": subtitle,
        "mode": mode,
        "me": me,
        "opponents": opponents,
        "depth": depth,
        "nodes": nodes,
        "events": events,
        "pv_path": pv_path,
        "root_scores": root_scores,
        "stats": {
            "total_nodes": len(nodes),
            "evaluated_nodes": len(nodes) - pruned_count,
            "leaves_evaluated": leaf_count,
            "pruned_nodes": pruned_count,
        },
    }


# ---------------------------------------------------------------------------
# 2. MCTS (UCT + 10-Turn Greedy Rollouts) Trace Recorder
# ---------------------------------------------------------------------------


def _logged_rollout(
    base: _Sim,
    me: str,
    partner: str | None,
    trust: float,
    alliance_active: bool,
    alliance_pending: bool,
    betray_first: str | None,
    capture_log: bool,
) -> tuple[float, dict[str, object]]:
    """Run one exact MCTS rollout and optionally return turn-by-turn Greedy action log."""
    sim = base.clone()
    risk = 30.0 if betray_first else 0.0
    allied = alliance_active
    broke_alliance = False
    turns_log: list[dict[str, object]] = []
    outcome = "horizon_10"

    for step in range(MCTS_ROLLOUT_DEPTH):
        turn_events: list[str] = []
        if alliance_pending and step == 1:
            allied = True
            if capture_log:
                turn_events.append(f"Pact activated with {partner}")
        if allied:
            if step > 0 and random.random() < (1.0 - trust / 100.0) * 0.25:
                allied = False
                broke_alliance = True
                risk += 10.0
                if capture_log:
                    turn_events.append(f"Alliance broke! (risk +10)")

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
                j = sim.territories.index(target)
                sim.attack(name, target)
                if capture_log:
                    won = sim.owner[j] == name
                    turn_events.append(f"{name[:3]}→{target.name} ({'WIN' if won else 'REPEL'})")

        holder = sim.owner[sim.throne]
        if capture_log:
            my_holds = sum(1 for o in sim.owner if o == me)
            turns_log.append(
                {
                    "turn": step + 1,
                    "actions": turn_events if turn_events else ["All houses held"],
                    "my_holds": my_holds,
                    "my_armies": int(sim.armies[me]),
                }
            )

        if holder == me:
            reward = REWARD_THRONE / REWARD_SCALE
            outcome = "throne_win"
            return reward, {
                "outcome": outcome,
                "broke": broke_alliance,
                "holds": sum(1 for o in sim.owner if o == me),
                "armies": int(sim.armies[me]),
                "turns_played": step + 1,
                "log": turns_log,
            }
        if not sim.alive(me):
            outcome = "eliminated"
            return 0.0, {
                "outcome": outcome,
                "broke": broke_alliance,
                "holds": 0,
                "armies": 0,
                "turns_played": step + 1,
                "log": turns_log,
            }
        if holder is not None:
            reward = 0.5 * max(0.0, sim.reward(me, risk)) / REWARD_SCALE
            outcome = f"rival_throne ({holder})"
            return reward, {
                "outcome": outcome,
                "broke": broke_alliance,
                "holds": sum(1 for o in sim.owner if o == me),
                "armies": int(sim.armies[me]),
                "turns_played": step + 1,
                "log": turns_log,
            }
        sim.economy()

    reward = max(0.0, sim.reward(me, risk)) / REWARD_SCALE
    return reward, {
        "outcome": outcome,
        "broke": broke_alliance,
        "holds": sum(1 for o in sim.owner if o == me),
        "armies": int(sim.armies[me]),
        "turns_played": MCTS_ROLLOUT_DEPTH,
        "log": turns_log,
    }


def record_mcts_scenario(
    scenario_id: str,
    title: str,
    context: str,
    house_name: str,
    partner_name: str,
    game_map: Map,
    houses: list[House],
    diplomacy: Diplomacy,
    fuzzy_inputs: dict[str, float],
    actions_spec: list[dict[str, object]],
) -> dict[str, object]:
    """Run all 500 real UCT rollouts and capture iteration-by-iteration traces."""
    fuzzy_scores = evaluate_diplomacy(
        fuzzy_inputs["enemy_strength"],
        fuzzy_inputs["own_weakness"],
        fuzzy_inputs["trust_history"],
    )
    base = _Sim(houses, game_map)
    by_name = {h.name: h for h in houses}
    trust = diplomacy.get_trust(by_name[house_name], by_name[partner_name])

    branches = []
    for spec in actions_spec:
        bias_key = spec["bias_key"]
        if bias_key == "reject_max":
            bias = max(fuzzy_scores["betrayal"], fuzzy_scores["solo"])
        else:
            bias = fuzzy_scores[bias_key]
        branches.append(
            {
                "action": spec["action"],
                "label": spec["label"],
                "bias": round(float(bias), 2),
                "visits": 0,
                "total_reward": 0.0,
                "spec": spec,
            }
        )

    detailed_iters = set(range(1, 21)) | {25, 40, 60, 80, 100, 150, 200, 300, 400, 500}
    history: list[dict[str, object]] = []

    for it in range(1, MCTS_ITER + 1):
        # Record pre-selection UCT breakdown for every branch
        uct_snap = []
        unvisited = [b for b in branches if b["visits"] == 0]
        for b in branches:
            if b["visits"] == 0:
                uct_snap.append(
                    {
                        "action": b["action"],
                        "q": 0.0,
                        "explore": None,
                        "bias": b["bias"],
                        "uct": None,
                        "visits": 0,
                    }
                )
            else:
                q_mean = b["total_reward"] / b["visits"]
                explore = UCT_C * math.sqrt(math.log(it) / b["visits"])
                uct_val = q_mean + explore + b["bias"]
                uct_snap.append(
                    {
                        "action": b["action"],
                        "q": round(q_mean, 3),
                        "explore": round(explore, 3),
                        "bias": b["bias"],
                        "uct": round(uct_val, 3),
                        "visits": b["visits"],
                    }
                )

        if unvisited:
            chosen = unvisited[0]
            select_reason = f"Unvisited node → forced initial exploration of {chosen['label']}."
        else:
            chosen = max(
                branches,
                key=lambda b: b["total_reward"] / b["visits"]
                + UCT_C * math.sqrt(math.log(it) / b["visits"])
                + b["bias"],
            )
            c_snap = next(u for u in uct_snap if u["action"] == chosen["action"])
            select_reason = (
                f"Highest UCT ({c_snap['uct']:.3f} = Q {c_snap['q']:.3f} + "
                f"Exp {c_snap['explore']:.3f} + Bias {c_snap['bias']:.2f}) → selects {chosen['label']}."
            )

        spec = chosen["spec"]
        mode = spec["sim_mode"]
        capture_log = it in detailed_iters

        if mode == "solo":
            rew, meta = _logged_rollout(base, house_name, None, trust, False, False, None, capture_log)
        elif mode == "keep_ally":
            rew, meta = _logged_rollout(base, house_name, partner_name, trust, True, False, None, capture_log)
        elif mode == "propose":
            accepted = random.random() < trust / 100.0
            rew, meta = _logged_rollout(base, house_name, partner_name, trust, False, accepted, None, capture_log)
            meta["accepted_in_rollout"] = accepted
        elif mode == "accept":
            rew, meta = _logged_rollout(base, house_name, partner_name, trust, True, False, None, capture_log)
        elif mode == "betray":
            rew, meta = _logged_rollout(base, house_name, partner_name, trust, False, False, partner_name, capture_log)
        else:
            rew, meta = _logged_rollout(base, house_name, None, trust, False, False, None, capture_log)

        chosen["total_reward"] += rew
        chosen["visits"] += 1

        post = [
            {
                "action": b["action"],
                "visits": b["visits"],
                "avg_q": round(b["total_reward"] / max(1, b["visits"]), 3),
            }
            for b in branches
        ]

        entry: dict[str, object] = {
            "iter": it,
            "chosen": chosen["action"],
            "reward": round(rew, 3),
            "outcome": meta["outcome"],
            "broke": meta["broke"],
            "holds": meta["holds"],
            "armies": meta["armies"],
            "turns_played": meta["turns_played"],
            "uct": uct_snap,
            "post": post,
            "reason": select_reason,
        }
        if capture_log:
            entry["log"] = meta["log"]
        if "accepted_in_rollout" in meta:
            entry["accepted_in_rollout"] = meta["accepted_in_rollout"]
        history.append(entry)

    winner = max(branches, key=lambda b: (b["visits"], b["total_reward"]))
    return {
        "id": scenario_id,
        "title": title,
        "context": context,
        "house": house_name,
        "partner": partner_name,
        "trust": trust,
        "fuzzy_inputs": fuzzy_inputs,
        "fuzzy_scores": fuzzy_scores,
        "iterations": MCTS_ITER,
        "uct_c": UCT_C,
        "branches": [
            {
                "action": b["action"],
                "label": b["label"],
                "bias": b["bias"],
                "final_visits": b["visits"],
                "final_q": round(b["total_reward"] / max(1, b["visits"]), 3),
            }
            for b in branches
        ],
        "winner": winner["action"],
        "winner_label": winner["label"],
        "history": history,
    }


# ---------------------------------------------------------------------------
# 3. A* Pathfinding Trace Recorder
# ---------------------------------------------------------------------------


def record_astar_data() -> dict[str, object]:
    """Record exact A* expansions from all 3 capitals to King's Landing on Map()."""
    game_map = Map()
    goal = game_map.iron_throne

    territories = [
        {
            "name": t.name,
            "col": t.col,
            "row": t.row,
            "res": t.resource_value,
            "def": t.defense_bonus,
            "owner": t.owner,
            "is_throne": t.is_iron_throne,
            "h_throne": int(hex_distance((t.col, t.row), (goal.col, goal.row))),
        }
        for t in game_map.get_all()
    ]

    edge_set: set[tuple[str, str]] = set()
    for t in game_map.get_all():
        for nb in t.neighbors:
            a, b = sorted((t.name, nb.name))
            edge_set.add((a, b))
    edges = [[a, b] for a, b in sorted(edge_set)]

    routes = []
    for start_name, house_tag in (
        ("WINTERFELL", "STARK"),
        ("CASTERLY ROCK", "LANNISTER"),
        ("DRAGONSTONE", "TARGARYEN"),
    ):
        start = game_map.by_name[start_name]
        counter = 0
        h0 = _heuristic(start, goal)
        open_heap: list[tuple[float, int, Territory]] = [(h0, counter, start)]
        came_from: dict[str, str] = {}
        g_score: dict[str, float] = {start.name: 0.0}
        f_score_map: dict[str, float] = {start.name: h0}
        closed: list[str] = []
        steps: list[dict[str, object]] = []

        steps.append(
            {
                "type": "init",
                "current": start.name,
                "open": [
                    {
                        "name": start.name,
                        "g": 0.0,
                        "h": round(h0, 1),
                        "f": round(h0, 1),
                    }
                ],
                "closed": [],
                "relaxed": [],
                "came_from": {},
                "msg": (
                    f"Initialize A* from {start.name} → {goal.name}. "
                    f"Push {start.name} with g=0, h=hex_dist={h0:.0f}, f={h0:.0f}."
                ),
            }
        )

        final_path: list[str] = []
        while open_heap:
            popped_f, _, current = heapq.heappop(open_heap)
            if current.name in closed:
                continue
            closed.append(current.name)
            cur_g = g_score[current.name]
            cur_h = _heuristic(current, goal)

            if current == goal:
                path: list[str] = [current.name]
                cur = current.name
                while cur in came_from:
                    cur = came_from[cur]
                    path.append(cur)
                path.reverse()
                final_path = path
                corridor_bonus = round(max(0.0, 12.0 - cur_g) * 1.5, 2)
                steps.append(
                    {
                        "type": "goal",
                        "current": current.name,
                        "open": _format_open(open_heap, g_score, goal, closed),
                        "closed": list(closed),
                        "relaxed": [],
                        "came_from": dict(came_from),
                        "path": final_path,
                        "total_cost": round(cur_g, 1),
                        "corridor_bonus": corridor_bonus,
                        "msg": (
                            f"Popped goal {goal.name}! Optimal corridor found: "
                            f"{' → '.join(final_path)} (Total Defense Cost g={cur_g:.0f}, "
                            f"Minimax Corridor Bonus = max(0, 12−{cur_g:.0f})×1.5 = +{corridor_bonus:.1f})."
                        ),
                    }
                )
                break

            relaxed = []
            for nb in game_map.get_neighbors(current):
                tentative_g = cur_g + float(nb.defense_bonus)
                old_g = g_score.get(nb.name, float("inf"))
                nb_h = _heuristic(nb, goal)
                if tentative_g < old_g:
                    came_from[nb.name] = current.name
                    g_score[nb.name] = tentative_g
                    new_f = tentative_g + nb_h
                    f_score_map[nb.name] = new_f
                    counter += 1
                    heapq.heappush(open_heap, (new_f, counter, nb))
                    relaxed.append(
                        {
                            "to": nb.name,
                            "edge_cost": nb.defense_bonus,
                            "g": round(tentative_g, 1),
                            "h": round(nb_h, 1),
                            "f": round(new_f, 1),
                            "improved": True,
                        }
                    )
                else:
                    relaxed.append(
                        {
                            "to": nb.name,
                            "edge_cost": nb.defense_bonus,
                            "g": round(tentative_g, 1),
                            "h": round(nb_h, 1),
                            "f": round(tentative_g + nb_h, 1),
                            "improved": False,
                        }
                    )

            imp_names = [f"{r['to']} (f={r['f']:.0f})" for r in relaxed if r["improved"]]
            imp_text = ", ".join(imp_names) if imp_names else "no better routes found"
            steps.append(
                {
                    "type": "expand",
                    "current": current.name,
                    "current_g": round(cur_g, 1),
                    "current_h": round(cur_h, 1),
                    "current_f": round(cur_g + cur_h, 1),
                    "open": _format_open(open_heap, g_score, goal, closed),
                    "closed": list(closed),
                    "relaxed": relaxed,
                    "came_from": dict(came_from),
                    "msg": (
                        f"Pop lowest-f node {current.name} (g={cur_g:.0f} + h={cur_h:.0f} = f={cur_g + cur_h:.0f}). "
                        f"Updated Open Set: {imp_text}."
                    ),
                }
            )

        # Cross-check against real algorithms/astar.py get_path
        real_path = [t.name for t in get_path(game_map, start, goal)]
        assert final_path == real_path, f"A* mismatch: {final_path} vs {real_path}"

        total_cost = sum(float(game_map.by_name[n].defense_bonus) for n in final_path[1:])
        routes.append(
            {
                "id": house_tag.lower(),
                "house": house_tag,
                "start": start.name,
                "goal": goal.name,
                "path": final_path,
                "total_cost": round(total_cost, 1),
                "corridor_bonus": round(max(0.0, 12.0 - total_cost) * 1.5, 2),
                "steps": steps,
            }
        )

    return {
        "territories": territories,
        "edges": edges,
        "routes": routes,
    }


def _format_open(
    open_heap: list[tuple[float, int, Territory]],
    g_score: dict[str, float],
    goal: Territory,
    closed: list[str],
) -> list[dict[str, object]]:
    """Return deduplicated, sorted Open Set entries for display."""
    best: dict[str, dict[str, object]] = {}
    closed_set = set(closed)
    for f_val, _, terr in open_heap:
        if terr.name in closed_set:
            continue
        g_val = g_score[terr.name]
        h_val = _heuristic(terr, goal)
        true_f = g_val + h_val
        if terr.name not in best or true_f < best[terr.name]["f"]:
            best[terr.name] = {
                "name": terr.name,
                "g": round(g_val, 1),
                "h": round(h_val, 1),
                "f": round(true_f, 1),
            }
    return sorted(best.values(), key=lambda x: (x["f"], x["h"], x["name"]))


# ---------------------------------------------------------------------------
# 4. Fuzzy Logic Presets (cross-checked directly against evaluate_diplomacy)
# ---------------------------------------------------------------------------


def record_fuzzy_presets() -> list[dict[str, object]]:
    presets = [
        {
            "id": "underdog",
            "name": "Underdog vs Giant (Ctx A)",
            "desc": "Stark faces a dominant Lannister threat while weakened, with warm trust toward Targaryen.",
            "e": 82,
            "w": 74,
            "t": 68,
        },
        {
            "id": "dominant_betray",
            "name": "Strong & Low Trust (Betrayal)",
            "desc": "Stark is strong (low weakness) against a weak rival while trust in its ally collapsed to 20.",
            "e": 24,
            "w": 18,
            "t": 20,
        },
        {
            "id": "solo_confident",
            "name": "Confident Solo Leader",
            "desc": "House is strong (low weakness) and diplomacy is stable (high trust) — solo conquest dominates.",
            "e": 35,
            "w": 15,
            "t": 78,
        },
        {
            "id": "ctx_b_coalition",
            "name": "Incoming Proposal (Ctx B)",
            "desc": "Targaryen offers a pact to Lannister while Stark is strong (threat=78, weakness=62, trust=60).",
            "e": 78,
            "w": 62,
            "t": 60,
        },
    ]
    for p in presets:
        p["python_scores"] = evaluate_diplomacy(p["e"], p["w"], p["t"])
    return presets


# ---------------------------------------------------------------------------
# Assemble complete real dataset
# ---------------------------------------------------------------------------


def build_trace_bundle(seed: int) -> dict[str, object]:
    random.seed(seed)

    # Tab 1: Minimax scenarios
    map1, houses1, _ = _make_initial_world()
    mm_opening = record_minimax_scenario(
        scenario_id="opening_decomposed",
        title="Turn 1 — Stark vs Lannister (Decomposed, Depth 3)",
        subtitle="Real opening Westeros board. Exact root evaluation with Alpha-Beta cutoffs inside Ply 2.",
        mode="DECOMPOSED",
        me="STARK",
        opponents=["LANNISTER"],
        game_map=map1,
        houses=houses1,
        my_forbidden=set(),
        depth=MINIMAX_DEPTH,
        max_branch=None,
        global_root_alpha=False,
    )

    map2, houses2, _ = _make_initial_world()
    mm_global_ab = record_minimax_scenario(
        scenario_id="opening_global_ab",
        title="Turn 1 — Full Global α-β Pruning (Depth 3)",
        subtitle="Same Turn-1 board carrying α across root moves to demonstrate BOTH α-cutoffs (Ply 1) and β-cutoffs (Ply 2).",
        mode="ALPHA-BETA",
        me="STARK",
        opponents=["LANNISTER"],
        game_map=map2,
        houses=houses2,
        my_forbidden=set(),
        depth=MINIMAX_DEPTH,
        max_branch=None,
        global_root_alpha=True,
    )

    map3, houses3, dip3 = _make_midgame_world()
    by3 = {h.name: h for h in houses3}
    dip3.form_alliance(by3["LANNISTER"], by3["TARGARYEN"])
    mm_paranoid = record_minimax_scenario(
        scenario_id="midgame_paranoid",
        title="Turn 5 — Stark vs Allied Coalition (Paranoid, Depth 3)",
        subtitle="Lannister & Targaryen merged into a single MIN coalition (top 4 moves/ply shown for crisp projection).",
        mode="PARANOID",
        me="STARK",
        opponents=["LANNISTER", "TARGARYEN"],
        game_map=map3,
        houses=houses3,
        my_forbidden=set(),
        depth=MINIMAX_DEPTH,
        max_branch=4,
        global_root_alpha=True,
    )

    # Tab 2: MCTS scenarios (500 real rollouts each)
    map_m1, houses_m1, dip_m1 = _make_midgame_world()
    mcts_ctx_a = record_mcts_scenario(
        scenario_id="ctx_a_propose",
        title="Context A — Stark: Propose Alliance to Targaryen vs Go Solo",
        context="Context A (Own Turn)",
        house_name="STARK",
        partner_name="TARGARYEN",
        game_map=map_m1,
        houses=houses_m1,
        diplomacy=dip_m1,
        fuzzy_inputs={"enemy_strength": 82.0, "own_weakness": 74.0, "trust_history": 68.0},
        actions_spec=[
            {"action": "propose_alliance", "label": "PROPOSE TARGARYEN", "bias_key": "alliance", "sim_mode": "propose"},
            {"action": "solo", "label": "GO SOLO", "bias_key": "solo", "sim_mode": "solo"},
        ],
    )

    map_m2, houses_m2, dip_m2 = _make_midgame_world()
    mcts_ctx_b = record_mcts_scenario(
        scenario_id="ctx_b_respond",
        title="Context B — Targaryen Responds to Stark's Alliance Proposal",
        context="Context B (Incoming Proposal)",
        house_name="TARGARYEN",
        partner_name="STARK",
        game_map=map_m2,
        houses=houses_m2,
        diplomacy=dip_m2,
        fuzzy_inputs={"enemy_strength": 80.0, "own_weakness": 68.0, "trust_history": 68.0},
        actions_spec=[
            {"action": "accept", "label": "ACCEPT PACT", "bias_key": "alliance", "sim_mode": "accept"},
            {"action": "reject", "label": "REJECT PACT", "bias_key": "reject_max", "sim_mode": "solo"},
        ],
    )

    map_m3, houses_m3, dip_m3 = _make_betrayal_world()
    mcts_betray = record_mcts_scenario(
        scenario_id="ctx_a_betray",
        title="Context A — Stark Evaluates Keeping Pact vs Betraying Targaryen",
        context="Context A (Allied Betrayal Check)",
        house_name="STARK",
        partner_name="TARGARYEN",
        game_map=map_m3,
        houses=houses_m3,
        diplomacy=dip_m3,
        fuzzy_inputs={"enemy_strength": 26.0, "own_weakness": 18.0, "trust_history": 22.0},
        actions_spec=[
            {"action": "solo", "label": "KEEP ALLIANCE", "bias_key": "solo", "sim_mode": "keep_ally"},
            {"action": "betray", "label": "BETRAY TARGARYEN", "bias_key": "betrayal", "sim_mode": "betray"},
        ],
    )

    # Tab 3: A*
    astar_data = record_astar_data()

    # Tab 4: Fuzzy presets
    fuzzy_presets = record_fuzzy_presets()

    return {
        "seed": seed,
        "minimax": [mm_opening, mm_global_ab, mm_paranoid],
        "mcts": [mcts_ctx_a, mcts_ctx_b, mcts_betray],
        "astar": astar_data,
        "fuzzy_presets": fuzzy_presets,
    }


# ---------------------------------------------------------------------------
# Self-Contained Interactive HTML / CSS / SVG / JS Template
# ---------------------------------------------------------------------------

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>Game of Thrones: AI Conquest — Live Algorithm &amp; Search Tree Visualizer</title>
<style>
  :root {
    --bg: #0b1318;
    --panel: #111c23;
    --panel-alt: #16242d;
    --border: #283c48;
    --gold: #ecb95e;
    --gold-dim: #b6893a;
    --text: #e6eef2;
    --muted: #8ea6b5;
    --stark: #49a7bf;
    --lannister: #e88335;
    --targaryen: #a374e6;
    --green: #5ee39b;
    --red: #f06a5a;
    --cyan: #57d6e6;
  }
  * { box-sizing: border-box; }
  html, body {
    margin: 0; padding: 0;
    background: var(--bg);
    color: var(--text);
    font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
    height: 100%;
    overflow: hidden;
  }
  .app {
    display: flex;
    flex-direction: column;
    height: 100vh;
  }
  /* Header & Tabs */
  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 6px 14px;
    background: linear-gradient(180deg, #15232c, #0e181f);
    border-bottom: 1px solid var(--border);
    gap: 10px;
    flex-shrink: 0;
  }
  .brand {
    display: flex;
    align-items: center;
    gap: 9px;
  }
  .brand-crest {
    width: 28px; height: 28px;
    border-radius: 6px;
    background: linear-gradient(135deg, #3c2c12, #182731);
    border: 1px solid var(--gold);
    display: grid; place-items: center;
    color: var(--gold); font-weight: 800; font-size: 13px;
    font-family: Georgia, serif;
    flex-shrink: 0;
  }
  .brand h1 {
    margin: 0; font-size: 14px; letter-spacing: 0.7px;
    font-family: Georgia, "Palatino Linotype", serif;
    color: var(--gold);
    text-transform: uppercase;
    line-height: 1.15;
  }
  .brand span {
    display: block; font-size: 10.5px; color: var(--muted);
    letter-spacing: 0.3px;
  }
  .tabs {
    display: flex;
    gap: 5px;
    flex-wrap: wrap;
  }
  .tab-btn {
    background: #132028;
    border: 1px solid var(--border);
    color: var(--muted);
    padding: 5px 11px;
    border-radius: 6px;
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.15s ease;
  }
  .tab-btn:hover { color: var(--text); border-color: var(--gold-dim); }
  .tab-btn.active {
    background: linear-gradient(180deg, #2b2416, #1b1a16);
    border-color: var(--gold);
    color: var(--gold);
    box-shadow: 0 0 10px rgba(236, 185, 94, 0.18);
  }
  .kbd-hint {
    font-size: 10.5px;
    color: var(--muted);
    white-space: nowrap;
  }
  .kbd {
    display: inline-block;
    padding: 1px 4px;
    border: 1px solid #354e5d;
    border-radius: 4px;
    background: #0d161c;
    color: var(--text);
    font-family: Consolas, monospace;
    font-size: 9.5px;
  }
  /* Toolbar */
  .toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 6px 14px;
    background: #0f1920;
    border-bottom: 1px solid var(--border);
    gap: 10px;
    flex-wrap: wrap;
    flex-shrink: 0;
  }
  .controls {
    display: flex;
    align-items: center;
    gap: 5px;
    flex-wrap: wrap;
  }
  .btn {
    background: var(--panel-alt);
    border: 1px solid var(--border);
    color: var(--text);
    padding: 5px 9px;
    border-radius: 6px;
    font-size: 11.5px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.12s;
  }
  .btn:hover { border-color: var(--gold); color: var(--gold); }
  .btn.primary {
    background: linear-gradient(180deg, #c7943b, #966b22);
    border-color: #f3c978;
    color: #0b1115;
  }
  .btn.primary:hover { filter: brightness(1.08); color: #080d10; }
  .btn.toggled {
    border-color: var(--cyan);
    color: var(--cyan);
    background: #122a34;
  }
  select {
    background: var(--panel-alt);
    border: 1px solid var(--border);
    color: var(--text);
    padding: 5px 8px;
    border-radius: 6px;
    font-size: 11.5px;
    font-weight: 600;
    cursor: pointer;
  }
  select:focus { outline: none; border-color: var(--gold); }
  .scrubber-wrap {
    display: flex;
    align-items: center;
    gap: 8px;
    flex: 1;
    min-width: 140px;
    max-width: 310px;
  }
  .scrubber-wrap input[type=range] {
    flex: 1;
    accent-color: var(--gold);
    cursor: pointer;
  }
  .step-counter {
    font-family: Consolas, monospace;
    font-size: 11.5px;
    color: var(--gold);
    min-width: 86px;
    text-align: right;
    white-space: nowrap;
  }
  /* Main workspace */
  .tab-pane {
    display: none;
    flex: 1;
    min-height: 0;
    flex-direction: column;
  }
  .tab-pane.active { display: flex; }
  .split {
    display: flex;
    flex: 1;
    min-height: 0;
  }
  .stage {
    flex: 1;
    position: relative;
    overflow: hidden;
    background: radial-gradient(circle at 50% 30%, #13222c 0%, #0b1318 75%);
  }
  .sidebar {
    width: 356px;
    background: var(--panel);
    border-left: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    overflow-y: auto;
    padding: 10px 11px;
    gap: 8px;
    flex-shrink: 0;
  }
  .card {
    background: var(--panel-alt);
    border: 1px solid var(--border);
    border-radius: 7px;
    padding: 8px 10px;
    flex-shrink: 0;
  }
  .card h3 {
    margin: 0 0 5px 0;
    font-size: 10.5px;
    text-transform: uppercase;
    letter-spacing: 0.85px;
    color: var(--gold);
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .narrative {
    font-size: 12px;
    line-height: 1.4;
    color: #eef5f8;
    min-height: 40px;
  }
  .badge {
    display: inline-block;
    padding: 1px 6px;
    border-radius: 4px;
    font-size: 9.5px;
    font-weight: 700;
    letter-spacing: 0.4px;
    text-transform: uppercase;
  }
  .badge.gold { background: rgba(236,185,94,0.18); color: var(--gold); border: 1px solid rgba(236,185,94,0.45); }
  .badge.green { background: rgba(94,227,155,0.16); color: var(--green); border: 1px solid rgba(94,227,155,0.45); }
  .badge.red { background: rgba(240,106,90,0.18); color: var(--red); border: 1px solid rgba(240,106,90,0.45); }
  .badge.blue { background: rgba(73,167,191,0.18); color: var(--stark); border: 1px solid rgba(73,167,191,0.45); }
  .stat-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 5px;
  }
  .stat-box {
    background: #0e181f;
    border: 1px solid #223540;
    border-radius: 5px;
    padding: 5px 8px;
  }
  .stat-label { font-size: 9.5px; color: var(--muted); text-transform: uppercase; }
  .stat-val { font-size: 14px; font-weight: 700; font-family: Consolas, monospace; margin-top: 1px; }
  table.math-tbl {
    width: 100%;
    border-collapse: collapse;
    font-size: 11.5px;
  }
  table.math-tbl td {
    padding: 2.5px 2px;
    border-bottom: 1px solid rgba(255,255,255,0.06);
  }
  table.math-tbl td:last-child {
    text-align: right;
    font-family: Consolas, monospace;
    font-weight: 600;
  }
  table.math-tbl tr.total-row td {
    border-top: 1px solid var(--gold-dim);
    border-bottom: none;
    padding-top: 5px;
    color: var(--gold);
    font-weight: 700;
    font-size: 12px;
  }
  .legend {
    position: absolute;
    left: 14px;
    bottom: 14px;
    background: rgba(11, 19, 24, 0.88);
    border: 1px solid var(--border);
    border-radius: 7px;
    padding: 7px 11px;
    display: flex;
    gap: 12px;
    font-size: 11px;
    color: var(--muted);
    pointer-events: none;
    flex-wrap: wrap;
  }
  .leg-item { display: flex; align-items: center; gap: 5px; }
  .dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
  .stage-hud {
    position: absolute;
    top: 12px;
    left: 14px;
    background: rgba(11, 19, 24, 0.88);
    border: 1px solid var(--border);
    border-radius: 7px;
    padding: 8px 12px;
    pointer-events: none;
    max-width: 560px;
  }
  .stage-hud .title { font-size: 13px; font-weight: 700; color: var(--gold); }
  .stage-hud .sub { font-size: 11px; color: var(--muted); margin-top: 2px; }
  .stage-zoom {
    position: absolute;
    top: 12px;
    right: 14px;
    display: flex;
    gap: 5px;
  }
  /* MCTS layout */
  .mcts-stage {
    padding: 16px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 14px;
  }
  .mcts-svg-box {
    background: #0d171e;
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 10px;
  }
  .rollout-log {
    max-height: 210px;
    overflow-y: auto;
    font-family: Consolas, monospace;
    font-size: 11px;
    line-height: 1.5;
    background: #0b1318;
    border: 1px solid #20323d;
    border-radius: 6px;
    padding: 8px 10px;
  }
  .rollout-row {
    padding: 2px 0;
    border-bottom: 1px solid rgba(255,255,255,0.04);
  }
  /* Priority queue rows */
  .pq-list {
    display: flex;
    flex-direction: column;
    gap: 5px;
    max-height: 240px;
    overflow-y: auto;
  }
  .pq-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    background: #0d171e;
    border: 1px solid #243844;
    border-radius: 5px;
    padding: 5px 9px;
    font-size: 12px;
    font-family: Consolas, monospace;
  }
  .pq-item.top {
    border-color: var(--gold);
    background: rgba(236,185,94,0.12);
    color: var(--gold);
  }
  /* Fuzzy layout */
  .fuzzy-stage {
    padding: 14px 16px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .fuzzy-grid-3 {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 10px;
  }
  .fuzzy-box {
    background: #0e181f;
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 8px 10px;
    transition: border-color 0.2s, box-shadow 0.2s;
  }
  .fuzzy-box.hl {
    border-color: var(--gold);
    box-shadow: 0 0 14px rgba(236,185,94,0.18);
  }
  .fuzzy-box h4 {
    margin: 0 0 6px 0;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.7px;
    color: var(--muted);
    display: flex;
    justify-content: space-between;
  }
  .slider-row {
    display: flex;
    flex-direction: column;
    gap: 3px;
    margin-bottom: 8px;
  }
  .slider-row label {
    display: flex;
    justify-content: space-between;
    font-size: 12px;
  }
  .slider-row input[type=range] {
    width: 100%;
    accent-color: var(--gold);
  }
  .rule-row {
    display: flex;
    flex-direction: column;
    gap: 3px;
    padding: 5px 7px;
    border-radius: 5px;
    background: #0c151b;
    border: 1px solid #1e2f3a;
    margin-bottom: 5px;
    font-size: 11px;
  }
  .rule-row.active-rule {
    border-color: var(--gold-dim);
    background: rgba(236,185,94,0.08);
  }
  .rule-bar-bg {
    height: 5px;
    background: #1b2c36;
    border-radius: 3px;
    overflow: hidden;
  }
  .rule-bar-fill {
    height: 100%;
    background: linear-gradient(90deg, var(--stark), var(--gold));
    transition: width 0.2s;
  }
  .formula-box {
    font-family: Consolas, monospace;
    font-size: 11.5px;
    color: #cde3ee;
    background: #0b1318;
    border: 1px solid #223540;
    border-radius: 6px;
    padding: 7px 9px;
    line-height: 1.45;
  }
  .root-score-bar {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 5px;
    font-size: 11.5px;
  }
  .root-score-name { width: 112px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .root-score-track { flex: 1; height: 8px; background: #0c151b; border-radius: 4px; overflow: hidden; border: 1px solid #20323d; }
  .root-score-fill { height: 100%; background: var(--stark); transition: width 0.2s; }
  .root-score-fill.best { background: var(--green); }
  .root-score-num { width: 52px; text-align: right; font-family: Consolas, monospace; }
</style>
</head>
<body>
<div class="app">
  <header>
    <div class="brand">
      <div class="brand-crest">GoT</div>
      <div>
        <h1>Game of Thrones: AI Conquest</h1>
        <span>Live Search Tree, Heuristic &amp; Decision Visualizer &bull; Real Engine Traces</span>
      </div>
    </div>
    <div class="tabs">
      <button class="tab-btn active" data-tab="minimax">1. Minimax (&alpha;-&beta;)</button>
      <button class="tab-btn" data-tab="mcts">2. MCTS (UCT)</button>
      <button class="tab-btn" data-tab="astar">3. A* Pathfinding</button>
      <button class="tab-btn" data-tab="fuzzy">4. Mamdani Fuzzy</button>
    </div>
    <div class="kbd-hint">
      <span class="kbd">Space</span> Play &nbsp;
      <span class="kbd">&larr;</span><span class="kbd">&rarr;</span> Step &nbsp;
      <span class="kbd">1-4</span> Tabs
    </div>
  </header>

  <!-- ==================== TAB 1: MINIMAX ==================== -->
  <section class="tab-pane active" id="pane-minimax">
    <div class="toolbar">
      <div class="controls">
        <select id="mm-scenario"></select>
        <button class="btn primary" id="mm-play">&#9654; Play</button>
        <button class="btn" id="mm-prev">&#9664; Back</button>
        <button class="btn" id="mm-next">Step &#9654;</button>
        <button class="btn" id="mm-reset">&#9198; Reset</button>
        <button class="btn" id="mm-end">&#9197; End</button>
        <select id="mm-speed">
          <option value="900">0.5&times; Slow</option>
          <option value="420" selected>1&times; Normal</option>
          <option value="160">2.5&times; Fast</option>
          <option value="55">6&times; Rapid</option>
        </select>
        <button class="btn toggled" id="mm-subtree">View: Active Subtree</button>
        <button class="btn toggled" id="mm-follow">Auto-Follow: ON</button>
      </div>
      <div class="scrubber-wrap">
        <input type="range" id="mm-scrub" min="0" max="0" value="0" />
        <span class="step-counter" id="mm-counter">Step 0 / 0</span>
      </div>
    </div>
    <div class="split">
      <div class="stage" id="mm-stage">
        <svg id="mm-svg" width="100%" height="100%" style="cursor: grab;"></svg>
        <div class="stage-hud">
          <div class="title" id="mm-hud-title"></div>
          <div class="sub" id="mm-hud-sub"></div>
        </div>
        <div class="stage-zoom">
          <button class="btn" id="mm-zoom-in">+</button>
          <button class="btn" id="mm-zoom-out">&minus;</button>
          <button class="btn" id="mm-fit">Fit Tree</button>
        </div>
        <div class="legend">
          <span class="leg-item"><span class="dot" style="background:var(--stark)"></span>MAX Node</span>
          <span class="leg-item"><span class="dot" style="background:var(--lannister)"></span>MIN Node</span>
          <span class="leg-item"><span class="dot" style="background:var(--gold)"></span>Active Step</span>
          <span class="leg-item"><span class="dot" style="background:var(--red)"></span>Pruned (&alpha;&ge;&beta;)</span>
          <span class="leg-item"><span class="dot" style="background:var(--green)"></span>Optimal Path</span>
        </div>
      </div>
      <aside class="sidebar">
        <div class="card">
          <h3>Live Decision Explanation <span class="badge gold" id="mm-event-badge">READY</span></h3>
          <div class="narrative" id="mm-narrative">Press Play or Step to watch Alpha-Beta DFS explore the Westeros game tree.</div>
        </div>
        <div class="card">
          <h3>Search Metrics</h3>
          <div class="stat-grid">
            <div class="stat-box"><div class="stat-label">Nodes Visited</div><div class="stat-val" id="mm-stat-vis">0</div></div>
            <div class="stat-box"><div class="stat-label">Leaves Evaluated</div><div class="stat-val" id="mm-stat-leaf">0</div></div>
            <div class="stat-box"><div class="stat-label">Branches Pruned</div><div class="stat-val" style="color:var(--red)" id="mm-stat-prune">0</div></div>
            <div class="stat-box"><div class="stat-label">Best Root Score</div><div class="stat-val" style="color:var(--green)" id="mm-stat-best">&mdash;</div></div>
          </div>
        </div>
        <div class="card">
          <h3>Heuristic Breakdown <span class="badge blue" id="mm-insp-label">CLICK ANY NODE</span></h3>
          <div id="mm-combat-note" style="font-size:11.5px;color:var(--muted);margin-bottom:7px;"></div>
          <table class="math-tbl" id="mm-breakdown-tbl"></table>
        </div>
        <div class="card">
          <h3>Root Action Scores</h3>
          <div id="mm-root-bars"></div>
        </div>
      </aside>
    </div>
  </section>

  <!-- ==================== TAB 2: MCTS ==================== -->
  <section class="tab-pane" id="pane-mcts">
    <div class="toolbar">
      <div class="controls">
        <select id="mcts-scenario"></select>
        <button class="btn primary" id="mcts-play">&#9654; Play</button>
        <button class="btn" id="mcts-prev">&#9664; -1</button>
        <button class="btn" id="mcts-next">+1 Rollout &#9654;</button>
        <button class="btn" id="mcts-plus25">+25</button>
        <button class="btn" id="mcts-reset">&#9198; Reset</button>
        <button class="btn" id="mcts-end">&#9197; 500</button>
        <select id="mcts-speed">
          <option value="slow">Presentation (1-by-1 then smooth)</option>
          <option value="step">Always 1-by-1</option>
          <option value="fast">Fast to 500</option>
        </select>
      </div>
      <div class="scrubber-wrap">
        <input type="range" id="mcts-scrub" min="0" max="500" value="0" />
        <span class="step-counter" id="mcts-counter">Rollout 0 / 500</span>
      </div>
    </div>
    <div class="split">
      <div class="stage mcts-stage">
        <div class="mcts-svg-box">
          <svg id="mcts-tree-svg" width="100%" viewBox="0 0 860 320"></svg>
        </div>
        <div class="mcts-svg-box">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
            <span style="font-size:11px;text-transform:uppercase;letter-spacing:0.8px;color:var(--gold);font-weight:700;">Live Q/N Convergence &amp; Visit Share (Rollouts 1 &rarr; 500)</span>
            <span style="font-size:11px;color:var(--muted);">UCT = Q/N + 1.414&middot;&radic;(ln N<sub>p</sub> / N) + FuzzyBias</span>
          </div>
          <svg id="mcts-chart-svg" width="100%" viewBox="0 0 860 220"></svg>
        </div>
      </div>
      <aside class="sidebar">
        <div class="card">
          <h3>UCT Selection &amp; Backprop <span class="badge gold" id="mcts-badge">READY</span></h3>
          <div class="narrative" id="mcts-narrative">Press Play or +1 Rollout to watch UCT balance exploration, exploitation, and Fuzzy Logic bias across 500 simulations.</div>
        </div>
        <div class="card">
          <h3>Fuzzy Bias Seed (From Tab 4)</h3>
          <div class="formula-box" id="mcts-fuzzy-box"></div>
        </div>
        <div class="card">
          <h3>10-Turn Greedy Rollout Trace <span class="badge blue" id="mcts-outcome-badge">&mdash;</span></h3>
          <div class="rollout-log" id="mcts-rollout-log">Step to rollout #1 to inspect the simulated 10-turn Westeros future.</div>
        </div>
        <div class="card">
          <h3>Final Decision Rule</h3>
          <div class="formula-box" id="mcts-decision-box">Most-visited child wins (tie-break: highest total Q).</div>
        </div>
      </aside>
    </div>
  </section>

  <!-- ==================== TAB 3: A* PATHFINDING ==================== -->
  <section class="tab-pane" id="pane-astar">
    <div class="toolbar">
      <div class="controls">
        <select id="astar-route"></select>
        <button class="btn primary" id="astar-play">&#9654; Play</button>
        <button class="btn" id="astar-prev">&#9664; Back</button>
        <button class="btn" id="astar-next">Step &#9654;</button>
        <button class="btn" id="astar-reset">&#9198; Reset</button>
        <button class="btn" id="astar-end">&#9197; Optimal Path</button>
        <select id="astar-speed">
          <option value="1100">0.5&times; Slow</option>
          <option value="650" selected>1&times; Normal</option>
          <option value="300">2&times; Fast</option>
        </select>
      </div>
      <div class="scrubber-wrap">
        <input type="range" id="astar-scrub" min="0" max="0" value="0" />
        <span class="step-counter" id="astar-counter">Step 0 / 0</span>
      </div>
    </div>
    <div class="split">
      <div class="stage">
        <svg id="astar-svg" width="100%" height="100%" viewBox="0 0 960 540" preserveAspectRatio="xMidYMid meet"></svg>
        <div class="legend">
          <span class="leg-item"><span class="dot" style="background:var(--gold)"></span>Current Popped Node</span>
          <span class="leg-item"><span class="dot" style="background:var(--cyan)"></span>Open Set (Frontier)</span>
          <span class="leg-item"><span class="dot" style="background:#50738a"></span>Closed Set (Explored)</span>
          <span class="leg-item"><span class="dot" style="background:var(--green)"></span>Optimal Corridor</span>
        </div>
      </div>
      <aside class="sidebar">
        <div class="card">
          <h3>A* Step Explanation <span class="badge gold" id="astar-badge">INIT</span></h3>
          <div class="narrative" id="astar-narrative"></div>
        </div>
        <div class="card">
          <h3>Cost &amp; Heuristic Formula</h3>
          <div class="formula-box">
            f(n) = g(n) + h(n)<br/>
            g(n) = &Sigma; defense_bonus along path<br/>
            h(n) = hex_distance(n, KING'S LANDING)<br/>
            <span style="color:var(--green)">Minimax Bonus = max(0, 12 &minus; g*) &times; 1.5</span>
          </div>
        </div>
        <div class="card">
          <h3>Priority Queue (Open Set &mdash; Sorted by f)</h3>
          <div class="pq-list" id="astar-pq"></div>
        </div>
        <div class="card">
          <h3>Edge Relaxations This Step</h3>
          <div class="pq-list" id="astar-relax"></div>
        </div>
      </aside>
    </div>
  </section>

  <!-- ==================== TAB 4: MAMDANI FUZZY LOGIC ==================== -->
  <section class="tab-pane" id="pane-fuzzy">
    <div class="toolbar">
      <div class="controls">
        <select id="fuzzy-preset"></select>
        <button class="btn primary" id="fuzzy-play">&#9654; Animate 4 Stages</button>
        <button class="btn" id="fuzzy-prev">&#9664; Prev Stage</button>
        <button class="btn" id="fuzzy-next">Next Stage &#9654;</button>
      </div>
      <div style="font-size:12px;color:var(--gold);font-weight:600;" id="fuzzy-stage-label">Stage 4 / 4: Centroid Defuzzification</div>
    </div>
    <div class="split">
      <div class="stage fuzzy-stage">
        <div class="fuzzy-grid-3" id="fuzzy-inputs-grid">
          <div class="fuzzy-box" id="fbox-e"><h4>Enemy Threat (e) <span id="fval-e">82</span></h4><svg id="fsvg-e" width="100%" viewBox="0 0 280 120"></svg></div>
          <div class="fuzzy-box" id="fbox-w"><h4>Own Weakness (w) <span id="fval-w">74</span></h4><svg id="fsvg-w" width="100%" viewBox="0 0 280 120"></svg></div>
          <div class="fuzzy-box" id="fbox-t"><h4>Trust History (t) <span id="fval-t">68</span></h4><svg id="fsvg-t" width="100%" viewBox="0 0 280 120"></svg></div>
        </div>
        <div class="fuzzy-grid-3" id="fuzzy-outputs-grid">
          <div class="fuzzy-box" id="fbox-ally"><h4>Alliance Output <span style="color:var(--green)" id="fout-ally">0.00</span></h4><svg id="fsvg-ally" width="100%" viewBox="0 0 280 145"></svg></div>
          <div class="fuzzy-box" id="fbox-betray"><h4>Betrayal Output <span style="color:var(--red)" id="fout-betray">0.00</span></h4><svg id="fsvg-betray" width="100%" viewBox="0 0 280 145"></svg></div>
          <div class="fuzzy-box" id="fbox-solo"><h4>Solo Output <span style="color:var(--stark)" id="fout-solo">0.00</span></h4><svg id="fsvg-solo" width="100%" viewBox="0 0 280 145"></svg></div>
        </div>
        <div class="card" style="background:#0e181f;">
          <h3>Pipeline Stage Explanation <span class="badge gold" id="fuzzy-stage-badge">STAGE 4</span></h3>
          <div class="narrative" id="fuzzy-narrative" style="min-height:36px;"></div>
        </div>
      </div>
      <aside class="sidebar">
        <div class="card">
          <h3>Interactive Crisp Inputs (Drag Live!)</h3>
          <div class="slider-row">
            <label><span>Enemy Military Threat</span><strong id="sl-e-lbl" style="color:var(--lannister)">82</strong></label>
            <input type="range" id="sl-e" min="0" max="100" value="82" />
          </div>
          <div class="slider-row">
            <label><span>Own Weakness</span><strong id="sl-w-lbl" style="color:var(--stark)">74</strong></label>
            <input type="range" id="sl-w" min="0" max="100" value="74" />
          </div>
          <div class="slider-row">
            <label><span>Trust History</span><strong id="sl-t-lbl" style="color:var(--green)">68</strong></label>
            <input type="range" id="sl-t" min="0" max="100" value="68" />
          </div>
          <div id="fuzzy-preset-desc" style="font-size:11.5px;color:var(--muted);margin-top:4px;"></div>
        </div>
        <div class="card">
          <h3>6 Mamdani Inference Rules (min-AND)</h3>
          <div id="fuzzy-rules-list"></div>
        </div>
        <div class="card">
          <h3>Defuzzified UCT Biases &rarr; MCTS</h3>
          <div class="formula-box" id="fuzzy-summary-box"></div>
        </div>
      </aside>
    </div>
  </section>
</div>

<script>
const DATA = __TRACE_JSON__;

// =========================================================================
// Shared utilities & tab management
// =========================================================================
const SVG_NS = "http://www.w3.org/2000/svg";
function el(tag, attrs = {}, text = null) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  if (text !== null) node.textContent = text;
  return node;
}

let activeTab = "minimax";
const tabBtns = document.querySelectorAll(".tab-btn");
function switchTab(tab) {
  stopAllTimers();
  activeTab = tab;
  tabBtns.forEach(b => b.classList.toggle("active", b.dataset.tab === tab));
  document.querySelectorAll(".tab-pane").forEach(p => p.classList.toggle("active", p.id === "pane-" + tab));
  if (tab === "minimax") mmRender();
  if (tab === "mcts") mctsRender();
  if (tab === "astar") astarRender();
  if (tab === "fuzzy") fuzzyRender();
}
tabBtns.forEach(b => b.addEventListener("click", () => switchTab(b.dataset.tab)));

function stopAllTimers() {
  mmStop(); mctsStop(); astarStop(); fuzzyStop();
}

document.addEventListener("keydown", (e) => {
  if (e.target.tagName === "INPUT" || e.target.tagName === "SELECT") return;
  if (e.key === "1") switchTab("minimax");
  else if (e.key === "2") switchTab("mcts");
  else if (e.key === "3") switchTab("astar");
  else if (e.key === "4") switchTab("fuzzy");
  else if (e.code === "Space") {
    e.preventDefault();
    if (activeTab === "minimax") mmTogglePlay();
    else if (activeTab === "mcts") mctsTogglePlay();
    else if (activeTab === "astar") astarTogglePlay();
    else if (activeTab === "fuzzy") fuzzyStartAnim();
  } else if (e.key === "ArrowRight") {
    if (activeTab === "minimax") mmStep(1);
    else if (activeTab === "mcts") mctsStep(1);
    else if (activeTab === "astar") astarStep(1);
    else if (activeTab === "fuzzy") { fuzzyStage = Math.min(4, fuzzyStage + 1); fuzzyRender(); }
  } else if (e.key === "ArrowLeft") {
    if (activeTab === "minimax") mmStep(-1);
    else if (activeTab === "mcts") mctsStep(-1);
    else if (activeTab === "astar") astarStep(-1);
    else if (activeTab === "fuzzy") { fuzzyStage = Math.max(1, fuzzyStage - 1); fuzzyRender(); }
  }
});

// =========================================================================
// TAB 1: MINIMAX + ALPHA-BETA PRUNING
// =========================================================================
let mmIdx = 0;
let mmStepIdx = 0;
let mmTimer = null;
let mmFollow = true;
let mmSubtreeMode = true;
let mmExpandedRootChild = null;
let mmSelectedNode = 0;
let mmLayout = null;
let mmView = { x: 0, y: 0, w: 1200, h: 680 };

const mmScenarioSel = document.getElementById("mm-scenario");
DATA.minimax.forEach((sc, i) => {
  const opt = document.createElement("option");
  opt.value = i;
  opt.textContent = sc.title;
  mmScenarioSel.appendChild(opt);
});

function mmRootChildOf(sc, nid) {
  let cur = nid;
  while (cur !== null && cur !== 0 && sc.nodes[cur].parent !== 0) {
    cur = sc.nodes[cur].parent;
  }
  return cur === 0 ? null : cur;
}

function computeTreeLayout(sc, expandOnlyRootChild) {
  const nodes = sc.nodes;
  const xGap = 116;
  const yGap = 148;
  let leafX = 0;
  const pos = new Array(nodes.length).fill(null);
  const visible = new Set();

  function dfs(id) {
    visible.add(id);
    const n = nodes[id];
    const shouldExpand =
      n.children.length > 0 &&
      (expandOnlyRootChild === null || n.ply === 0 || id === expandOnlyRootChild || n.ply >= 2);
    if (!shouldExpand) {
      pos[id] = { x: leafX * xGap + 85, y: n.ply * yGap + 88 };
      leafX++;
    } else {
      n.children.forEach(dfs);
      const first = pos[n.children[0]].x;
      const last = pos[n.children[n.children.length - 1]].x;
      pos[id] = { x: (first + last) / 2, y: n.ply * yGap + 88 };
    }
  }
  dfs(0);
  const visPos = [...visible].map(id => pos[id]);
  const maxX = Math.max(...visPos.map(p => p.x)) + 100;
  const maxY = Math.max(...visPos.map(p => p.y)) + 90;
  return { pos, visible, maxX, maxY };
}

function mmLoadScenario(idx) {
  mmStop();
  mmIdx = idx;
  mmStepIdx = 0;
  mmSelectedNode = 0;
  mmExpandedRootChild = null;
  const sc = DATA.minimax[mmIdx];
  const firstChild = sc.nodes[0].children.length ? sc.nodes[0].children[0] : null;
  mmLayout = computeTreeLayout(sc, mmSubtreeMode ? firstChild : null);
  document.getElementById("mm-hud-title").textContent = sc.title;
  document.getElementById("mm-hud-sub").textContent = sc.subtitle;
  const scrub = document.getElementById("mm-scrub");
  scrub.max = sc.events.length - 1;
  scrub.value = 0;
  mmFitView();
  mmRender();
}

function mmFitView() {
  if (!mmLayout) return;
  const svg = document.getElementById("mm-svg");
  const rect = svg.getBoundingClientRect();
  const aspect = (rect.width && rect.height) ? rect.width / rect.height : 1.75;
  const padTop = 68;
  const contentH = mmLayout.maxY + padTop;
  const w = Math.max(mmLayout.maxX, contentH * aspect);
  const h = w / aspect;
  mmView = { x: -(w - mmLayout.maxX) / 2, y: -padTop, w, h };
  mmApplyViewBox();
}

window.addEventListener("resize", () => {
  if (activeTab === "minimax") mmFitView();
});

function mmFocusNode(nid) {
  if (!mmLayout || !mmLayout.pos[nid]) return;
  const p = mmLayout.pos[nid];
  const svg = document.getElementById("mm-svg");
  const rect = svg.getBoundingClientRect();
  const aspect = (rect.width && rect.height) ? rect.width / rect.height : 1.75;
  const targetH = Math.min(mmLayout.maxY + 40, 620);
  const targetW = targetH * aspect;
  mmView = { x: p.x - targetW / 2, y: Math.max(-36, p.y - targetH * 0.52), w: targetW, h: targetH };
  mmApplyViewBox();
}

function mmApplyViewBox() {
  const svg = document.getElementById("mm-svg");
  svg.setAttribute("viewBox", `${mmView.x.toFixed(1)} ${mmView.y.toFixed(1)} ${mmView.w.toFixed(1)} ${mmView.h.toFixed(1)}`);
}

// Pan & Zoom on Minimax SVG
(() => {
  const svg = document.getElementById("mm-svg");
  let dragging = false, sx = 0, sy = 0, vx = 0, vy = 0;
  svg.addEventListener("mousedown", (e) => {
    if (e.target.closest(".mm-node")) return;
    dragging = true; sx = e.clientX; sy = e.clientY; vx = mmView.x; vy = mmView.y;
    svg.style.cursor = "grabbing";
  });
  window.addEventListener("mousemove", (e) => {
    if (!dragging) return;
    const rect = svg.getBoundingClientRect();
    const dx = (e.clientX - sx) * (mmView.w / rect.width);
    const dy = (e.clientY - sy) * (mmView.h / rect.height);
    mmView.x = vx - dx;
    mmView.y = vy - dy;
    mmApplyViewBox();
  });
  window.addEventListener("mouseup", () => { dragging = false; svg.style.cursor = "grab"; });
  svg.addEventListener("wheel", (e) => {
    e.preventDefault();
    const factor = e.deltaY > 0 ? 1.14 : 0.88;
    const rect = svg.getBoundingClientRect();
    const mx = (e.clientX - rect.left) / rect.width;
    const my = (e.clientY - rect.top) / rect.height;
    const nw = mmView.w * factor;
    const nh = mmView.h * factor;
    mmView.x += (mmView.w - nw) * mx;
    mmView.y += (mmView.h - nh) * my;
    mmView.w = nw; mmView.h = nh;
    mmApplyViewBox();
  }, { passive: false });
})();

function mmBuildStateAt(sc, stepIdx) {
  const state = sc.nodes.map(() => ({
    seen: false,
    pruned: false,
    value: null,
    alpha: "-∞",
    beta: "+∞",
    leafDone: false,
  }));
  let visitedCount = 0;
  let leafCount = 0;
  let prunedCount = 0;
  const rootVals = {};
  let activeNode = 0;
  let finished = false;

  for (let i = 0; i <= stepIdx; i++) {
    const ev = sc.events[i];
    if (ev.type === "enter") {
      if (!state[ev.node].seen) visitedCount++;
      state[ev.node].seen = true;
      state[ev.node].alpha = ev.alpha;
      state[ev.node].beta = ev.beta;
      activeNode = ev.node;
    } else if (ev.type === "leaf") {
      state[ev.node].seen = true;
      state[ev.node].leafDone = true;
      state[ev.node].value = ev.value;
      state[ev.node].alpha = ev.alpha;
      state[ev.node].beta = ev.beta;
      leafCount++;
      activeNode = ev.node;
    } else if (ev.type === "backup") {
      state[ev.node].value = ev.value;
      state[ev.node].alpha = ev.alpha;
      state[ev.node].beta = ev.beta;
      activeNode = ev.node;
      if (ev.node === 0 && ev.from !== undefined) {
        const kid = sc.nodes[ev.from];
        rootVals[kid.move] = state[ev.from].value;
      }
    } else if (ev.type === "prune") {
      ev.pruned_ids.forEach(pid => {
        if (!state[pid].pruned) prunedCount++;
        state[pid].seen = true;
        state[pid].pruned = true;
      });
      activeNode = ev.node;
    } else if (ev.type === "finish") {
      finished = true;
      activeNode = ev.node;
    }
  }
  return { state, visitedCount, leafCount, prunedCount, rootVals, activeNode, finished };
}

function mmRenderBreakdown(sc, nid) {
  const node = sc.nodes[nid];
  const lbl = document.getElementById("mm-insp-label");
  const note = document.getElementById("mm-combat-note");
  const tbl = document.getElementById("mm-breakdown-tbl");
  lbl.textContent = node ? `${node.move} (Ply ${node.ply})` : "NONE";
  note.textContent = node && node.combat_note ? node.combat_note : (node && node.pruned ? "Pruned branch — never evaluated!" : "Root starting state before move selection.");
  tbl.innerHTML = "";
  if (!node || !node.breakdown) {
    tbl.innerHTML = `<tr><td colspan="2" style="color:var(--muted);padding:8px 0;">Select any evaluated LEAF (or root) node to inspect exact heuristic arithmetic.</td></tr>`;
    return;
  }
  const b = node.breakdown;
  const rows = [
    [`Own Territory (&Sigma;(res+def)=${b.own_terr_raw}) &times; 2`, `+${b.own_terr_term.toFixed(1)}`],
    [`Own Armies (${b.armies}) &times; 1.5`, `+${b.armies_term.toFixed(1)}`],
    [`Own Gold (${b.gold}G) &times; 0.5`, `+${b.gold_term.toFixed(1)}`],
    [`Iron Throne Bonus`, `+${b.throne_term.toFixed(1)}`],
    [`A* Corridor (${b.closest_hold}, cost=${b.min_throne_cost})`, `+${b.astar_term.toFixed(1)}`],
    [`&minus; Enemy (res=${b.enemy_res}, arm=${b.enemy_armies})`, `&minus;${b.enemy_term.toFixed(1)}`],
  ];
  rows.forEach(([k, v]) => {
    tbl.innerHTML += `<tr><td>${k}</td><td>${v}</td></tr>`;
  });
  tbl.innerHTML += `<tr class="total-row"><td>State Evaluation V(s)</td><td>${b.total >= 0 ? "+" : ""}${b.total.toFixed(1)}</td></tr>`;
}

function mmRender() {
  const sc = DATA.minimax[mmIdx];
  const ev = sc.events[mmStepIdx];
  const snap = mmBuildStateAt(sc, mmStepIdx);
  const svg = document.getElementById("mm-svg");
  svg.innerHTML = "";

  // Determine which Ply-1 root child to expand in Active Subtree mode
  let activeRootChild = mmRootChildOf(sc, snap.activeNode);
  if (activeRootChild === null) {
    activeRootChild = snap.finished && sc.pv_path.length > 1
      ? sc.pv_path[1]
      : (sc.nodes[0].children.length ? sc.nodes[0].children[0] : null);
  }
  const expandTarget = mmSubtreeMode ? (mmExpandedRootChild !== null ? mmExpandedRootChild : activeRootChild) : null;
  mmLayout = computeTreeLayout(sc, expandTarget);

  if (mmSubtreeMode) {
    mmFitView();
  } else if (mmFollow && !snap.finished) {
    mmFocusNode(snap.activeNode);
  } else if (mmFollow && snap.finished) {
    mmFitView();
  }

  const pvSet = new Set(snap.finished ? sc.pv_path : []);
  const pvEdges = new Set();
  if (snap.finished) {
    for (let i = 0; i < sc.pv_path.length - 1; i++) pvEdges.add(`${sc.pv_path[i]}-${sc.pv_path[i+1]}`);
  }

  const boxW = 104, boxH = 62;

  // Draw edges first (only visible nodes)
  const edgeGroup = el("g");
  sc.nodes.forEach((n) => {
    if (n.parent === null || !mmLayout.visible.has(n.id) || !mmLayout.visible.has(n.parent)) return;
    const ns = snap.state[n.id];
    const p1 = mmLayout.pos[n.parent];
    const p2 = mmLayout.pos[n.id];
    const isPv = pvEdges.has(`${n.parent}-${n.id}`);
    const isActiveEdge = (ev.type === "backup" && ev.from === n.id) || (ev.type === "enter" && ev.node === n.id);
    const midY = (p1.y + p2.y) / 2;
    const d = `M ${p1.x} ${p1.y + boxH / 2} C ${p1.x} ${midY}, ${p2.x} ${midY}, ${p2.x} ${p2.y - boxH / 2}`;
    let stroke = "#223642";
    let sw = 1.4;
    let dash = "";
    let op = ns.seen ? 0.95 : 0.24;
    if (ns.pruned) { stroke = "#f06a5a"; sw = 2; dash = "6 4"; op = 0.88; }
    else if (isPv) { stroke = "#5ee39b"; sw = 3.5; op = 1; }
    else if (isActiveEdge) { stroke = "#ecb95e"; sw = 3; op = 1; }
    else if (ns.seen) { stroke = "#4a6c7f"; sw = 1.8; }

    edgeGroup.appendChild(el("path", {
      d, fill: "none", stroke, "stroke-width": sw, "stroke-dasharray": dash, opacity: op
    }));

    if (ns.pruned) {
      const mx = (p1.x + p2.x) / 2;
      const my = (p1.y + p2.y) / 2;
      edgeGroup.appendChild(el("line", { x1: mx - 9, y1: my - 9, x2: mx + 9, y2: my + 9, stroke: "#f06a5a", "stroke-width": 2.6 }));
      edgeGroup.appendChild(el("line", { x1: mx + 9, y1: my - 9, x2: mx - 9, y2: my + 9, stroke: "#f06a5a", "stroke-width": 2.6 }));
    }
  });
  svg.appendChild(edgeGroup);

  // Draw nodes
  const nodeGroup = el("g");
  sc.nodes.forEach((n) => {
    if (!mmLayout.visible.has(n.id)) return;
    const ns = snap.state[n.id];
    const p = mmLayout.pos[n.id];
    const isActive = snap.activeNode === n.id;
    const isPv = pvSet.has(n.id);
    const isCollapsedPly1 = mmSubtreeMode && n.ply === 1 && n.children.length > 0 && n.id !== expandTarget;
    const g = el("g", { class: "mm-node", transform: `translate(${p.x}, ${p.y})`, style: "cursor:pointer;" });
    g.addEventListener("click", () => {
      if (mmSubtreeMode && n.ply === 1) {
        mmExpandedRootChild = n.id;
        mmRender();
      }
      mmSelectedNode = n.id;
      mmRenderBreakdown(sc, n.id);
    });

    let fill = "#121f27";
    let stroke = "#2b4250";
    let sw = 1.5;
    let op = ns.seen ? 1 : 0.30;
    if (ns.pruned) { fill = "#2b1416"; stroke = "#f06a5a"; sw = 2; }
    else if (isActive) { fill = "#2c2414"; stroke = "#ecb95e"; sw = 3; }
    else if (isPv) { fill = "#112b22"; stroke = "#5ee39b"; sw = 2.6; }
    else if (ns.seen) {
      stroke = n.kind === "MAX" ? "#49a7bf" : (n.kind === "MIN" ? "#e88335" : "#4db89c");
      fill = n.kind === "LEAF" ? "#102424" : "#152530";
    }

    g.appendChild(el("rect", {
      x: -boxW / 2, y: -boxH / 2, width: boxW, height: boxH, rx: 8,
      fill, stroke, "stroke-width": sw, opacity: op
    }));

    // Row 1: Kind pill
    const kindTxt = ns.pruned ? "PRUNED" : (n.kind === "MAX" ? "MAX ▲" : (n.kind === "MIN" ? "MIN ▼" : "LEAF"));
    const kindCol = ns.pruned ? "#f06a5a" : (n.kind === "MAX" ? "#49a7bf" : (n.kind === "MIN" ? "#e88335" : "#5ee39b"));
    g.appendChild(el("text", {
      x: 0, y: -17, "text-anchor": "middle", fill: kindCol, "font-size": 9, "font-weight": 700, opacity: op
    }, kindTxt));

    // Row 2: Move name
    const shortMove = n.move.length > 13 ? n.move.slice(0, 12) + "…" : n.move;
    g.appendChild(el("text", {
      x: 0, y: -3, "text-anchor": "middle", fill: "#edf4f8", "font-size": 10.5, "font-weight": 700, opacity: op
    }, shortMove));

    // Row 3: Value
    const valTxt = ns.pruned
      ? "α ≥ β cut"
      : (ns.value !== null ? `V = ${ns.value >= 0 ? "+" : ""}${ns.value.toFixed(1)}` : "evaluating…");
    g.appendChild(el("text", {
      x: 0, y: 11, "text-anchor": "middle",
      fill: ns.pruned ? "#f06a5a" : (ns.value !== null ? "#ecb95e" : "#8ea6b5"),
      "font-size": 9.8, "font-family": "Consolas, monospace", "font-weight": 700, opacity: op
    }, valTxt));

    // Row 4 (inside box!): [α, β] or collapsed hint — zero edge overlap!
    let footTxt = "";
    let footCol = "#8ea6b5";
    if (isCollapsedPly1) {
      footTxt = "▸ click subtree";
      footCol = "#57d6e6";
    } else if (ns.seen && !ns.pruned) {
      footTxt = `α:${ns.alpha} β:${ns.beta}`;
    }
    if (footTxt) {
      g.appendChild(el("text", {
        x: 0, y: 24, "text-anchor": "middle", fill: footCol,
        "font-size": 8.4, "font-family": "Consolas, monospace", opacity: op
      }, footTxt));
    }

    nodeGroup.appendChild(g);
  });
  svg.appendChild(nodeGroup);

  // Update sidebar
  document.getElementById("mm-counter").textContent = `Step ${mmStepIdx + 1} / ${sc.events.length}`;
  document.getElementById("mm-scrub").value = mmStepIdx;
  document.getElementById("mm-narrative").textContent = ev.msg;
  const badge = document.getElementById("mm-event-badge");
  badge.textContent = ev.type.toUpperCase();
  badge.className = "badge " + (ev.type === "prune" ? "red" : (ev.type === "finish" || ev.type === "leaf" ? "green" : "gold"));

  document.getElementById("mm-stat-vis").textContent = snap.visitedCount;
  document.getElementById("mm-stat-leaf").textContent = snap.leafCount;
  document.getElementById("mm-stat-prune").textContent = snap.prunedCount;
  const rVal = snap.state[0].value;
  document.getElementById("mm-stat-best").textContent = rVal !== null ? `${rVal >= 0 ? "+" : ""}${rVal.toFixed(1)}` : "—";

  // Auto-inspect evaluated leaf, or root if no leaf evaluated yet
  if (ev.type === "leaf") {
    mmSelectedNode = ev.node;
  } else if (mmStepIdx === 0) {
    mmSelectedNode = 0;
  }
  mmRenderBreakdown(sc, mmSelectedNode);

  // Root bars
  const barsEl = document.getElementById("mm-root-bars");
  barsEl.innerHTML = "";
  const rootChildren = sc.nodes[0].children.map(cid => sc.nodes[cid]);
  const vals = rootChildren.map(c => snap.state[c.id].value).filter(v => v !== null);
  const maxV = vals.length ? Math.max(...vals) : 1;
  const minV = vals.length ? Math.min(...vals) : 0;
  const span = Math.max(1, maxV - minV);
  rootChildren.forEach(c => {
    const v = snap.state[c.id].value;
    const pct = v === null ? 0 : (15 + 85 * ((v - minV) / span));
    const isBest = v !== null && v === maxV;
    barsEl.innerHTML += `
      <div class="root-score-bar">
        <span class="root-score-name" title="${c.move}">${c.move}</span>
        <div class="root-score-track"><div class="root-score-fill ${isBest ? "best" : ""}" style="width:${pct.toFixed(0)}%"></div></div>
        <span class="root-score-num" style="color:${isBest ? "var(--green)" : "var(--text)"}">${v === null ? "…" : (v >= 0 ? "+" : "") + v.toFixed(1)}</span>
      </div>`;
  });
}

function mmStep(delta) {
  const sc = DATA.minimax[mmIdx];
  mmExpandedRootChild = null;
  mmStepIdx = Math.max(0, Math.min(sc.events.length - 1, mmStepIdx + delta));
  mmRender();
}
function mmStop() {
  if (mmTimer) { clearInterval(mmTimer); mmTimer = null; }
  document.getElementById("mm-play").innerHTML = "&#9654; Play";
}
function mmTogglePlay() {
  if (mmTimer) { mmStop(); return; }
  const sc = DATA.minimax[mmIdx];
  mmExpandedRootChild = null;
  if (mmStepIdx >= sc.events.length - 1) mmStepIdx = 0;
  document.getElementById("mm-play").innerHTML = "&#9208; Pause";
  const speed = Number(document.getElementById("mm-speed").value);
  mmTimer = setInterval(() => {
    if (mmStepIdx >= sc.events.length - 1) { mmStop(); return; }
    mmStepIdx++;
    mmRender();
  }, speed);
}

mmScenarioSel.addEventListener("change", () => mmLoadScenario(Number(mmScenarioSel.value)));
document.getElementById("mm-play").addEventListener("click", mmTogglePlay);
document.getElementById("mm-prev").addEventListener("click", () => { mmStop(); mmStep(-1); });
document.getElementById("mm-next").addEventListener("click", () => { mmStop(); mmStep(1); });
document.getElementById("mm-reset").addEventListener("click", () => { mmStop(); mmExpandedRootChild = null; mmStepIdx = 0; mmRender(); });
document.getElementById("mm-end").addEventListener("click", () => { mmStop(); mmExpandedRootChild = null; mmStepIdx = DATA.minimax[mmIdx].events.length - 1; mmRender(); });
document.getElementById("mm-scrub").addEventListener("input", (e) => { mmStop(); mmExpandedRootChild = null; mmStepIdx = Number(e.target.value); mmRender(); });
document.getElementById("mm-speed").addEventListener("change", () => { if (mmTimer) { mmStop(); mmTogglePlay(); } });
document.getElementById("mm-subtree").addEventListener("click", (e) => {
  mmSubtreeMode = !mmSubtreeMode;
  mmExpandedRootChild = null;
  e.target.classList.toggle("toggled", mmSubtreeMode);
  e.target.textContent = mmSubtreeMode ? "View: Active Subtree" : "View: Full Tree";
  mmRender();
});
document.getElementById("mm-follow").addEventListener("click", (e) => {
  mmFollow = !mmFollow;
  e.target.classList.toggle("toggled", mmFollow);
  e.target.textContent = `Auto-Follow: ${mmFollow ? "ON" : "OFF"}`;
});
document.getElementById("mm-fit").addEventListener("click", mmFitView);
document.getElementById("mm-zoom-in").addEventListener("click", () => { mmView.x += mmView.w * 0.1; mmView.y += mmView.h * 0.1; mmView.w *= 0.8; mmView.h *= 0.8; mmApplyViewBox(); });
document.getElementById("mm-zoom-out").addEventListener("click", () => { mmView.x -= mmView.w * 0.12; mmView.y -= mmView.h * 0.12; mmView.w *= 1.24; mmView.h *= 1.24; mmApplyViewBox(); });

// =========================================================================
// TAB 2: MCTS (UCT) LIVE ROLLOUT SIMULATOR
// =========================================================================
let mctsIdx = 0;
let mctsIter = 0; // 0 = initial, 1..500
let mctsTimer = null;

const mctsScenarioSel = document.getElementById("mcts-scenario");
DATA.mcts.forEach((sc, i) => {
  const opt = document.createElement("option");
  opt.value = i;
  opt.textContent = sc.title;
  mctsScenarioSel.appendChild(opt);
});

function mctsLoadScenario(idx) {
  mctsStop();
  mctsIdx = idx;
  mctsIter = 0;
  document.getElementById("mcts-scrub").value = 0;
  mctsRender();
}

function mctsRender() {
  const sc = DATA.mcts[mctsIdx];
  const cur = mctsIter > 0 ? sc.history[mctsIter - 1] : null;
  document.getElementById("mcts-counter").textContent = `Rollout ${mctsIter} / ${sc.iterations}`;
  document.getElementById("mcts-scrub").value = mctsIter;

  // Fuzzy seed box
  const fi = sc.fuzzy_inputs, fs = sc.fuzzy_scores;
  document.getElementById("mcts-fuzzy-box").innerHTML =
    `<strong>${sc.context}</strong> &bull; House ${sc.house} (Partner: ${sc.partner}, Trust ${sc.trust})<br/>` +
    `Inputs: Threat=${fi.enemy_strength}, Weakness=${fi.own_weakness}, Trust=${fi.trust_history}<br/>` +
    `Fuzzy Bias: <span style="color:var(--green)">Ally ${fs.alliance.toFixed(2)}</span> &bull; ` +
    `<span style="color:var(--red)">Betray ${fs.betrayal.toFixed(2)}</span> &bull; ` +
    `<span style="color:var(--stark)">Solo ${fs.solo.toFixed(2)}</span>`;

  // Narrative & Rollout log
  const badge = document.getElementById("mcts-badge");
  const nar = document.getElementById("mcts-narrative");
  const logEl = document.getElementById("mcts-rollout-log");
  const outBadge = document.getElementById("mcts-outcome-badge");

  if (!cur) {
    badge.textContent = "READY";
    badge.className = "badge gold";
    nar.textContent = `Ready to run ${sc.iterations} real UCT rollouts for House ${sc.house}. Press Play to watch Selection → 10-Turn Greedy Rollout → Backpropagation live.`;
    outBadge.textContent = "—";
    logEl.innerHTML = `<span style="color:var(--muted)">Step to Rollout #1 to inspect the simulated 10-turn Westeros future.</span>`;
  } else {
    badge.textContent = `ITER #${cur.iter}`;
    badge.className = cur.iter === sc.iterations ? "badge green" : "badge gold";
    const chosenBranch = sc.branches.find(b => b.action === cur.chosen);
    nar.textContent = `${cur.reason} 10-turn Greedy rollout finished (${cur.outcome}) → backpropagates reward +${cur.reward.toFixed(3)} to ${chosenBranch.label}.`;
    outBadge.textContent = `${cur.outcome} (+${cur.reward.toFixed(2)})`;
    outBadge.className = "badge " + (cur.outcome === "throne_win" ? "green" : (cur.outcome === "eliminated" ? "red" : "blue"));

    if (cur.log && cur.log.length) {
      logEl.innerHTML = cur.log.map(row =>
        `<div class="rollout-row"><span style="color:var(--gold)">T${row.turn}:</span> ${row.actions.join(" | ")} ` +
        `<span style="color:var(--muted)">[holds:${row.my_holds}, arm:${row.my_armies}]</span></div>`
      ).join("");
    } else {
      logEl.innerHTML =
        `<div style="color:var(--muted)">Summary for Rollout #${cur.iter} (detailed turn-by-turn logs stored for Rollouts 1–20 &amp; milestones 25, 40, 60, 80, 100, 150, 200, 300, 400, 500):</div>` +
        `<div style="margin-top:6px;">Outcome: <strong style="color:var(--gold)">${cur.outcome}</strong> in ${cur.turns_played} turns<br/>` +
        `Final Holds: <strong>${cur.holds}</strong> &bull; Armies: <strong>${cur.armies}</strong> &bull; ` +
        `Alliance Broke: <strong>${cur.broke ? "YES" : "NO"}</strong><br/>` +
        `Scaled Reward: <strong style="color:var(--green)">+${cur.reward.toFixed(3)}</strong></div>`;
    }
  }

  // Draw MCTS Tree SVG
  const svg = document.getElementById("mcts-tree-svg");
  svg.innerHTML = "";
  const rootX = 430, rootY = 44;

  // Root node
  svg.appendChild(el("rect", { x: rootX - 135, y: rootY - 26, width: 270, height: 52, rx: 10, fill: "#182732", stroke: "#ecb95e", "stroke-width": 2 }));
  svg.appendChild(el("text", { x: rootX, y: rootY - 6, "text-anchor": "middle", fill: "#ecb95e", "font-size": 12, "font-weight": 700 }, `ROOT: HOUSE ${sc.house} (${sc.context})`));
  svg.appendChild(el("text", { x: rootX, y: rootY + 13, "text-anchor": "middle", fill: "#cde2ee", "font-size": 11, "font-family": "Consolas, monospace" }, `Parent Visits Np = ${mctsIter} / ${sc.iterations}`));

  const bColors = ["#5ee39b", "#49a7bf", "#f06a5a"];
  const xs = sc.branches.length === 2 ? [240, 620] : [160, 430, 700];

  sc.branches.forEach((b, idx) => {
    const cx = xs[idx], cy = 188;
    const isChosen = cur && cur.chosen === b.action;
    const isFinalWin = mctsIter === sc.iterations && sc.winner === b.action;
    const post = cur ? cur.post.find(p => p.action === b.action) : { visits: 0, avg_q: 0 };
    const uctObj = cur ? cur.uct.find(u => u.action === b.action) : null;
    const share = mctsIter > 0 ? (post.visits / mctsIter) * 100 : 0;

    // Edge from root
    svg.appendChild(el("path", {
      d: `M ${rootX} ${rootY + 26} C ${rootX} 105, ${cx} 100, ${cx} ${cy - 54}`,
      fill: "none",
      stroke: isFinalWin ? "#5ee39b" : (isChosen ? "#ecb95e" : "#2f4756"),
      "stroke-width": isChosen || isFinalWin ? 3.5 : 2
    }));

    // Edge backprop label
    if (isChosen) {
      const mx = (rootX + cx) / 2, my = 102;
      svg.appendChild(el("rect", { x: mx - 46, y: my - 12, width: 92, height: 22, rx: 11, fill: "#282012", stroke: "#ecb95e", "stroke-width": 1.4 }));
      svg.appendChild(el("text", { x: mx, y: my + 3, "text-anchor": "middle", fill: "#ecb95e", "font-size": 10.5, "font-family": "Consolas, monospace", "font-weight": 700 }, `r = +${cur.reward.toFixed(2)} ↑`));
    }

    // Child Card
    const cardW = 290, cardH = 112;
    svg.appendChild(el("rect", {
      x: cx - cardW / 2, y: cy - 54, width: cardW, height: cardH, rx: 10,
      fill: isFinalWin ? "#102a21" : (isChosen ? "#222117" : "#122029"),
      stroke: isFinalWin ? "#5ee39b" : (isChosen ? "#ecb95e" : bColors[idx]),
      "stroke-width": isChosen || isFinalWin ? 2.6 : 1.6
    }));

    svg.appendChild(el("text", { x: cx - cardW / 2 + 14, y: cy - 32, fill: bColors[idx], "font-size": 13, "font-weight": 700 }, b.label));
    svg.appendChild(el("text", { x: cx + cardW / 2 - 14, y: cy - 32, "text-anchor": "end", fill: "#ecb95e", "font-size": 12, "font-family": "Consolas, monospace", "font-weight": 700 }, `N = ${post.visits} (${share.toFixed(0)}%)`));

    // Visit share bar
    svg.appendChild(el("rect", { x: cx - cardW / 2 + 14, y: cy - 22, width: cardW - 28, height: 8, rx: 4, fill: "#0a1218" }));
    svg.appendChild(el("rect", { x: cx - cardW / 2 + 14, y: cy - 22, width: Math.max(0, (cardW - 28) * share / 100), height: 8, rx: 4, fill: bColors[idx] }));

    const uctStr = uctObj
      ? (uctObj.uct === null ? "UCT = +∞ (unvisited)" : `UCT = ${uctObj.q.toFixed(2)} + ${uctObj.explore.toFixed(2)} + ${uctObj.bias.toFixed(2)} = ${uctObj.uct.toFixed(2)}`)
      : `Fuzzy Bias = +${b.bias.toFixed(2)}`;
    svg.appendChild(el("text", { x: cx - cardW / 2 + 14, y: cy + 5, fill: "#cde2ee", "font-size": 11, "font-family": "Consolas, monospace" }, `Avg Q/N = ${post.avg_q.toFixed(3)}   |   Bias = +${b.bias.toFixed(2)}`));
    svg.appendChild(el("text", { x: cx - cardW / 2 + 14, y: cy + 25, fill: "#8ea6b5", "font-size": 10.5, "font-family": "Consolas, monospace" }, uctStr));
    svg.appendChild(el("text", { x: cx - cardW / 2 + 14, y: cy + 44, fill: isFinalWin ? "#5ee39b" : (isChosen ? "#ecb95e" : "#5e7989"), "font-size": 10.5, "font-weight": 700 },
      isFinalWin ? "★ SELECTED WINNER (MOST VISITED)" : (isChosen ? "● SELECTED & SIMULATED THIS STEP" : "Idle this iteration")
    ));
  });

  // Rollout pipeline box at bottom
  svg.appendChild(el("rect", { x: 165, y: 264, width: 530, height: 40, rx: 8, fill: "#0e1a22", stroke: "#283f4d", "stroke-width": 1.3 }));
  svg.appendChild(el("text", { x: 430, y: 288, "text-anchor": "middle", fill: "#b9d3e0", "font-size": 11.5, "font-family": "Consolas, monospace" },
    cur
      ? `10-Turn Greedy Rollout #${cur.iter} → ${cur.outcome.toUpperCase()} | Reward = +${cur.reward.toFixed(3)} (scaled /100)`
      : `Rollout Engine: 10 Turns × Greedy Opponent Model + Uniform(0.8, 1.2) Combat + Trust Breakdown`
  ));

  // Convergence Chart SVG
  const csvg = document.getElementById("mcts-chart-svg");
  csvg.innerHTML = "";
  const padL = 52, padR = 24, padT = 16, padB = 28;
  const cw = 860 - padL - padR, ch = 220 - padT - padB;
  // Grid
  for (let i = 0; i <= 4; i++) {
    const y = padT + (ch * i) / 4;
    csvg.appendChild(el("line", { x1: padL, y1: y, x2: padL + cw, y2: y, stroke: "#1c2e38", "stroke-width": 1 }));
    csvg.appendChild(el("text", { x: padL - 8, y: y + 4, "text-anchor": "end", fill: "#7e97a6", "font-size": 10, "font-family": "Consolas, monospace" }, `${100 - i * 25}%`));
  }
  csvg.appendChild(el("text", { x: padL + cw / 2, y: 214, "text-anchor": "middle", fill: "#7e97a6", "font-size": 10 }, "Visit Share % Across MCTS Iterations (1 → 500)"));

  if (mctsIter > 0) {
    sc.branches.forEach((b, bi) => {
      const pts = [];
      const stride = mctsIter > 120 ? 2 : 1;
      for (let k = 1; k <= mctsIter; k += stride) {
        const h = sc.history[k - 1];
        const p = h.post.find(x => x.action === b.action);
        const pct = p.visits / k;
        const x = padL + (k / sc.iterations) * cw;
        const y = padT + ch * (1 - pct);
        pts.push(`${x.toFixed(1)},${y.toFixed(1)}`);
      }
      // ensure exact current point
      const hLast = sc.history[mctsIter - 1];
      const pLast = hLast.post.find(x => x.action === b.action);
      const lx = padL + (mctsIter / sc.iterations) * cw;
      const ly = padT + ch * (1 - pLast.visits / mctsIter);
      pts.push(`${lx.toFixed(1)},${ly.toFixed(1)}`);

      csvg.appendChild(el("polyline", { points: pts.join(" "), fill: "none", stroke: bColors[bi], "stroke-width": 2.4 }));
      csvg.appendChild(el("circle", { cx: lx, cy: ly, r: 4, fill: bColors[bi] }));
    });
  }
  // Legend on chart
  sc.branches.forEach((b, bi) => {
    const lx = padL + 12 + bi * 210;
    csvg.appendChild(el("rect", { x: lx, y: 4, width: 10, height: 10, rx: 2, fill: bColors[bi] }));
    csvg.appendChild(el("text", { x: lx + 15, y: 13, fill: "#d7e7f0", "font-size": 10.5, "font-weight": 600 }, b.label));
  });

  // Decision box
  const decBox = document.getElementById("mcts-decision-box");
  if (mctsIter === sc.iterations) {
    decBox.innerHTML = `<span style="color:var(--green);font-weight:700;">FINAL DECISION: ${sc.winner_label}</span><br/>` +
      sc.branches.map(b => `${b.label}: ${b.final_visits} visits, avg Q = ${b.final_q.toFixed(3)}`).join("<br/>");
  } else {
    decBox.innerHTML = `At 500 rollouts, the most-visited child wins.<br/>Current progress: ${mctsIter} / ${sc.iterations} simulations completed.`;
  }
}

function mctsStep(delta) {
  const sc = DATA.mcts[mctsIdx];
  mctsIter = Math.max(0, Math.min(sc.iterations, mctsIter + delta));
  mctsRender();
}
function mctsStop() {
  if (mctsTimer) { clearTimeout(mctsTimer); mctsTimer = null; }
  document.getElementById("mcts-play").innerHTML = "&#9654; Play";
}
function mctsTick() {
  const sc = DATA.mcts[mctsIdx];
  if (mctsIter >= sc.iterations) { mctsStop(); return; }
  const mode = document.getElementById("mcts-speed").value;
  let inc = 1, delay = 450;
  if (mode === "step") { inc = 1; delay = 420; }
  else if (mode === "fast") { inc = mctsIter < 10 ? 1 : 10; delay = 45; }
  else {
    // Presentation mode: 1-by-1 for first 12 rollouts so UCT is readable, then smoothly accelerates to 500
    if (mctsIter < 12) { inc = 1; delay = 520; }
    else if (mctsIter < 40) { inc = 2; delay = 140; }
    else if (mctsIter < 150) { inc = 5; delay = 65; }
    else { inc = 12; delay = 45; }
  }
  mctsIter = Math.min(sc.iterations, mctsIter + inc);
  mctsRender();
  mctsTimer = setTimeout(mctsTick, delay);
}
function mctsTogglePlay() {
  if (mctsTimer) { mctsStop(); return; }
  if (mctsIter >= DATA.mcts[mctsIdx].iterations) mctsIter = 0;
  document.getElementById("mcts-play").innerHTML = "&#9208; Pause";
  mctsTick();
}

mctsScenarioSel.addEventListener("change", () => mctsLoadScenario(Number(mctsScenarioSel.value)));
document.getElementById("mcts-play").addEventListener("click", mctsTogglePlay);
document.getElementById("mcts-prev").addEventListener("click", () => { mctsStop(); mctsStep(-1); });
document.getElementById("mcts-next").addEventListener("click", () => { mctsStop(); mctsStep(1); });
document.getElementById("mcts-plus25").addEventListener("click", () => { mctsStop(); mctsStep(25); });
document.getElementById("mcts-reset").addEventListener("click", () => { mctsStop(); mctsIter = 0; mctsRender(); });
document.getElementById("mcts-end").addEventListener("click", () => { mctsStop(); mctsIter = DATA.mcts[mctsIdx].iterations; mctsRender(); });
document.getElementById("mcts-scrub").addEventListener("input", (e) => { mctsStop(); mctsIter = Number(e.target.value); mctsRender(); });

// =========================================================================
// TAB 3: A* PATHFINDING ON REAL WESTEROS GRAPH
// =========================================================================
let astarIdx = 0;
let astarStepIdx = 0;
let astarTimer = null;

const astarRouteSel = document.getElementById("astar-route");
DATA.astar.routes.forEach((r, i) => {
  const opt = document.createElement("option");
  opt.value = i;
  opt.textContent = `${r.house}: ${r.start} → ${r.goal} (cost ${r.total_cost})`;
  astarRouteSel.appendChild(opt);
});

const TERR_POS = {};
DATA.astar.territories.forEach(t => {
  // Odd-q hex projection onto 960x540 canvas
  const x = 62 + (t.col - 1) * 48.5;
  const y = 66 + (t.row - 1) * 68 + ((t.col & 1) ? 24 : 0);
  TERR_POS[t.name] = { x, y, ...t };
});

function astarLoadRoute(idx) {
  astarStop();
  astarIdx = idx;
  astarStepIdx = 0;
  const r = DATA.astar.routes[astarIdx];
  const sc = document.getElementById("astar-scrub");
  sc.max = r.steps.length - 1;
  sc.value = 0;
  astarRender();
}

function astarRender() {
  const route = DATA.astar.routes[astarIdx];
  const step = route.steps[astarStepIdx];
  const svg = document.getElementById("astar-svg");
  svg.innerHTML = "";

  const closedSet = new Set(step.closed);
  const openMap = {};
  step.open.forEach(o => openMap[o.name] = o);
  const pathEdges = new Set();
  const pathNodes = new Set(step.path || []);
  if (step.path) {
    for (let i = 0; i < step.path.length - 1; i++) {
      pathEdges.add(`${step.path[i]}|${step.path[i+1]}`);
      pathEdges.add(`${step.path[i+1]}|${step.path[i]}`);
    }
  }
  const relaxMap = {};
  (step.relaxed || []).forEach(r => relaxMap[r.to] = r);

  // Draw edges
  DATA.astar.edges.forEach(([a, b]) => {
    const pa = TERR_POS[a], pb = TERR_POS[b];
    const isOpt = pathEdges.has(`${a}|${b}`);
    const isRelax = (step.current === a && relaxMap[b]) || (step.current === b && relaxMap[a]);
    const isTree = step.came_from[a] === b || step.came_from[b] === a;
    let stroke = "#223642", sw = 1.6, op = 0.65;
    if (isOpt) { stroke = "#5ee39b"; sw = 5; op = 1; }
    else if (isRelax) {
      const rel = step.current === a ? relaxMap[b] : relaxMap[a];
      stroke = rel.improved ? "#ecb95e" : "#5e717c";
      sw = rel.improved ? 3.2 : 1.8;
      op = 1;
    } else if (isTree) { stroke = "#49a7bf"; sw = 2.4; op = 0.9; }
    svg.appendChild(el("line", { x1: pa.x, y1: pa.y, x2: pb.x, y2: pb.y, stroke, "stroke-width": sw, opacity: op }));
  });

  // Draw territories
  DATA.astar.territories.forEach(t => {
    const p = TERR_POS[t.name];
    const isCur = step.current === t.name;
    const isOpt = pathNodes.has(t.name);
    const isOpen = !!openMap[t.name];
    const isClosed = closedSet.has(t.name);

    let fill = "#13212a", stroke = "#324c5b", sw = 1.8, r = t.is_throne ? 24 : 18;
    if (isOpt) { fill = "#133528"; stroke = "#5ee39b"; sw = 3.5; }
    else if (isCur) { fill = "#332814"; stroke = "#ecb95e"; sw = 3.5; }
    else if (isOpen) { fill = "#132c36"; stroke = "#57d6e6"; sw = 2.5; }
    else if (isClosed) { fill = "#1b2e3a"; stroke = "#56798f"; sw = 2; }
    else if (t.is_throne) { fill = "#2b1d14"; stroke = "#c98b32"; sw = 2.4; }

    svg.appendChild(el("circle", { cx: p.x, cy: p.y, r, fill, stroke, "stroke-width": sw }));
    svg.appendChild(el("text", { x: p.x, y: p.y + 4, "text-anchor": "middle", fill: t.is_throne ? "#ecb95e" : "#e6f0f5", "font-size": 10.5, "font-weight": 700, "font-family": "Consolas, monospace" },
      t.is_throne ? "★" + t.def : "d" + t.def
    ));
    svg.appendChild(el("text", { x: p.x, y: p.y + r + 13, "text-anchor": "middle", fill: isOpt ? "#5ee39b" : (isCur ? "#ecb95e" : "#b8ceda"), "font-size": 9.8, "font-weight": 700 }, t.name));

    if (isOpen) {
      const o = openMap[t.name];
      svg.appendChild(el("text", { x: p.x, y: p.y - r - 6, "text-anchor": "middle", fill: "#57d6e6", "font-size": 9.5, "font-family": "Consolas, monospace", "font-weight": 700 }, `f=${o.f} (${o.g}+${o.h})`));
    } else if (isCur && step.current_f !== undefined) {
      svg.appendChild(el("text", { x: p.x, y: p.y - r - 6, "text-anchor": "middle", fill: "#ecb95e", "font-size": 10, "font-family": "Consolas, monospace", "font-weight": 700 }, `f=${step.current_f} (${step.current_g}+${step.current_h})`));
    }
  });

  // Update sidebar
  document.getElementById("astar-counter").textContent = `Step ${astarStepIdx + 1} / ${route.steps.length}`;
  document.getElementById("astar-scrub").value = astarStepIdx;
  document.getElementById("astar-narrative").textContent = step.msg;
  const badge = document.getElementById("astar-badge");
  badge.textContent = step.type.toUpperCase();
  badge.className = "badge " + (step.type === "goal" ? "green" : "gold");

  const pqEl = document.getElementById("astar-pq");
  pqEl.innerHTML = step.open.length
    ? step.open.map((o, i) => `<div class="pq-item ${i === 0 ? "top" : ""}"><span>${i === 0 ? "▶ " : ""}${o.name}</span><span>g=${o.g} + h=${o.h} = <strong>f=${o.f}</strong></span></div>`).join("")
    : `<div style="color:var(--muted);font-size:12px;">Open Set empty / Goal reached.</div>`;

  const relEl = document.getElementById("astar-relax");
  relEl.innerHTML = (step.relaxed && step.relaxed.length)
    ? step.relaxed.map(r =>
        `<div class="pq-item" style="border-color:${r.improved ? "var(--green)" : "#23343f"}">` +
        `<span>→ ${r.to} (+def ${r.edge_cost})</span>` +
        `<span style="color:${r.improved ? "var(--green)" : "var(--muted)"}">${r.improved ? "PUSH f=" + r.f : "skip (worse)"}</span></div>`
      ).join("")
    : `<div style="color:var(--muted);font-size:12px;">${step.type === "goal" ? "Goal reached — corridor locked in!" : "Initial start node pushed to heap."}</div>`;
}

function astarStep(delta) {
  const r = DATA.astar.routes[astarIdx];
  astarStepIdx = Math.max(0, Math.min(r.steps.length - 1, astarStepIdx + delta));
  astarRender();
}
function astarStop() {
  if (astarTimer) { clearInterval(astarTimer); astarTimer = null; }
  document.getElementById("astar-play").innerHTML = "&#9654; Play";
}
function astarTogglePlay() {
  if (astarTimer) { astarStop(); return; }
  const r = DATA.astar.routes[astarIdx];
  if (astarStepIdx >= r.steps.length - 1) astarStepIdx = 0;
  document.getElementById("astar-play").innerHTML = "&#9208; Pause";
  const speed = Number(document.getElementById("astar-speed").value);
  astarTimer = setInterval(() => {
    if (astarStepIdx >= r.steps.length - 1) { astarStop(); return; }
    astarStepIdx++;
    astarRender();
  }, speed);
}

astarRouteSel.addEventListener("change", () => astarLoadRoute(Number(astarRouteSel.value)));
document.getElementById("astar-play").addEventListener("click", astarTogglePlay);
document.getElementById("astar-prev").addEventListener("click", () => { astarStop(); astarStep(-1); });
document.getElementById("astar-next").addEventListener("click", () => { astarStop(); astarStep(1); });
document.getElementById("astar-reset").addEventListener("click", () => { astarStop(); astarStepIdx = 0; astarRender(); });
document.getElementById("astar-end").addEventListener("click", () => { astarStop(); astarStepIdx = DATA.astar.routes[astarIdx].steps.length - 1; astarRender(); });
document.getElementById("astar-scrub").addEventListener("input", (e) => { astarStop(); astarStepIdx = Number(e.target.value); astarRender(); });
document.getElementById("astar-speed").addEventListener("change", () => { if (astarTimer) { astarStop(); astarTogglePlay(); } });

// =========================================================================
// TAB 4: MAMDANI FUZZY LOGIC (EXACT MATCH TO algorithms/fuzzy_diplomacy.py)
// =========================================================================
let fuzzyStage = 4; // 1=Fuzzify, 2=Rules, 3=Aggregate, 4=Centroid
let fuzzyTimer = null;

const fuzzyPresetSel = document.getElementById("fuzzy-preset");
DATA.fuzzy_presets.forEach((p, i) => {
  const opt = document.createElement("option");
  opt.value = i;
  opt.textContent = p.name;
  fuzzyPresetSel.appendChild(opt);
});

function trimf(x, a, b, c) {
  if (a === b && x <= a) return 1;
  if (b === c && x >= c) return 1;
  if (x === b) return 1;
  if (x > a && x < b && a !== b) return (x - a) / (b - a);
  if (x > b && x < c && b !== c) return (c - x) / (c - b);
  return 0;
}

function evalFuzzyJS(eVal, wVal, tVal) {
  const mu = (v) => ({
    low: trimf(v, 0, 0, 60),
    med: trimf(v, 20, 50, 80),
    high: trimf(v, 40, 100, 100),
  });
  const E = mu(eVal), W = mu(wVal), T = mu(tVal);
  const rules = [
    { id: "R1", text: "IF Threat HIGH AND Weakness HIGH → Alliance HIGH", fire: Math.min(E.high, W.high), out: "alliance", set: "high" },
    { id: "R2", text: "IF Trust LOW AND Threat MED → Alliance LOW", fire: Math.min(T.low, E.med), out: "alliance", set: "low" },
    { id: "R3", text: "IF Weakness LOW AND Threat LOW → Betrayal HIGH", fire: Math.min(W.low, E.low), out: "betrayal", set: "high" },
    { id: "R4", text: "IF Weakness LOW AND Trust HIGH → Solo HIGH", fire: Math.min(W.low, T.high), out: "solo", set: "high" },
    { id: "R5", text: "IF Threat HIGH AND Trust HIGH → Alliance MED", fire: Math.min(E.high, T.high), out: "alliance", set: "med" },
    { id: "R6", text: "IF Trust LOW → Betrayal MED", fire: T.low, out: "betrayal", set: "med" },
  ];

  const agg = { alliance: [], betrayal: [], solo: [] };
  for (let x = 0; x <= 100; x++) {
    const low = trimf(x, 0, 0, 60), med = trimf(x, 20, 50, 80), high = trimf(x, 40, 100, 100);
    agg.alliance.push(Math.max(Math.min(rules[1].fire, low), Math.min(rules[4].fire, med), Math.min(rules[0].fire, high)));
    agg.betrayal.push(Math.max(Math.min(rules[5].fire, med), Math.min(rules[2].fire, high)));
    agg.solo.push(Math.min(rules[3].fire, high));
  }
  const centroid = (arr) => {
    let num = 0, den = 0;
    for (let x = 0; x <= 100; x++) { num += x * arr[x]; den += arr[x]; }
    return den <= 1e-9 ? 0 : num / den;
  };
  const cAlly = centroid(agg.alliance);
  const cBetray = centroid(agg.betrayal);
  const cSolo = centroid(agg.solo);
  return {
    E, W, T, rules, agg,
    centroids: { alliance: cAlly, betrayal: cBetray, solo: cSolo },
    scores: { alliance: cAlly / 100, betrayal: cBetray / 100, solo: cSolo / 100 },
  };
}

function drawInputMF(svgId, val, mObj, showDrop) {
  const svg = document.getElementById(svgId);
  svg.innerHTML = "";
  const x0 = 24, y0 = 96, w = 236, h = 76;
  const px = (x) => x0 + (x / 100) * w;
  const py = (y) => y0 - y * h;

  svg.appendChild(el("line", { x1: x0, y1: y0, x2: x0 + w, y2: y0, stroke: "#314957", "stroke-width": 1.2 }));
  svg.appendChild(el("line", { x1: x0, y1: y0 - h, x2: x0, y2: y0, stroke: "#314957", "stroke-width": 1.2 }));
  [0, 50, 100].forEach(t => svg.appendChild(el("text", { x: px(t), y: y0 + 13, "text-anchor": "middle", fill: "#7d96a6", "font-size": 9 }, String(t))));

  const curves = [
    { pts: [[0,1],[60,0]], col: "#49a7bf", lbl: "LOW", lx: 14 },
    { pts: [[20,0],[50,1],[80,0]], col: "#ecb95e", lbl: "MED", lx: 50 },
    { pts: [[40,0],[100,1]], col: "#f06a5a", lbl: "HIGH", lx: 86 },
  ];
  curves.forEach(c => {
    const s = c.pts.map(([x,y]) => `${px(x)},${py(y)}`).join(" ");
    svg.appendChild(el("polyline", { points: s, fill: "none", stroke: c.col, "stroke-width": 2, opacity: 0.85 }));
    svg.appendChild(el("text", { x: px(c.lx), y: 14, "text-anchor": "middle", fill: c.col, "font-size": 8.5, "font-weight": 700 }, c.lbl));
  });

  if (showDrop) {
    const vx = px(val);
    svg.appendChild(el("line", { x1: vx, y1: y0 - h, x2: vx, y2: y0, stroke: "#ffffff", "stroke-width": 1.5, "stroke-dasharray": "4 3" }));
    [["low","#49a7bf"], ["med","#ecb95e"], ["high","#f06a5a"]].forEach(([k, col]) => {
      if (mObj[k] > 0.01) {
        svg.appendChild(el("circle", { cx: vx, cy: py(mObj[k]), r: 4, fill: col, stroke: "#0b1318", "stroke-width": 1.2 }));
      }
    });
    svg.appendChild(el("text", { x: x0 + w, y: y0 + 14, "text-anchor": "end", fill: "#cde3ee", "font-size": 8.5, "font-family": "Consolas, monospace" },
      `L:${mObj.low.toFixed(2)} M:${mObj.med.toFixed(2)} H:${mObj.high.toFixed(2)}`
    ));
  }
}

function drawOutputMF(svgId, arr, centVal, fillCol, showAgg, showCentroid) {
  const svg = document.getElementById(svgId);
  svg.innerHTML = "";
  const x0 = 24, y0 = 114, w = 236, h = 88;
  const px = (x) => x0 + (x / 100) * w;
  const py = (y) => y0 - y * h;

  svg.appendChild(el("line", { x1: x0, y1: y0, x2: x0 + w, y2: y0, stroke: "#314957", "stroke-width": 1.2 }));
  svg.appendChild(el("line", { x1: x0, y1: y0 - h, x2: x0, y2: y0, stroke: "#314957", "stroke-width": 1.2 }));
  [0, 50, 100].forEach(t => svg.appendChild(el("text", { x: px(t), y: y0 + 14, "text-anchor": "middle", fill: "#7d96a6", "font-size": 9 }, String(t))));

  // Faint base triangles
  [[[0,1],[60,0]], [[20,0],[50,1],[80,0]], [[40,0],[100,1]]].forEach(pts => {
    svg.appendChild(el("polyline", { points: pts.map(([x,y]) => `${px(x)},${py(y)}`).join(" "), fill: "none", stroke: "#2d4350", "stroke-width": 1.2, "stroke-dasharray": "3 3" }));
  });

  if (showAgg) {
    const polyPts = [`${px(0)},${py(0)}`];
    for (let x = 0; x <= 100; x++) polyPts.push(`${px(x).toFixed(1)},${py(arr[x]).toFixed(1)}`);
    polyPts.push(`${px(100)},${py(0)}`);
    svg.appendChild(el("polygon", { points: polyPts.join(" "), fill: fillCol, opacity: 0.34 }));
    svg.appendChild(el("polyline", { points: polyPts.slice(1, -1).join(" "), fill: "none", stroke: fillCol, "stroke-width": 2.2 }));
  }

  if (showCentroid && centVal > 0) {
    const cx = px(centVal);
    svg.appendChild(el("line", { x1: cx, y1: y0 - h - 4, x2: cx, y2: y0, stroke: "#ecb95e", "stroke-width": 2.4 }));
    svg.appendChild(el("polygon", { points: `${cx-5},${y0-h-4} ${cx+5},${y0-h-4} ${cx},${y0-h+4}`, fill: "#ecb95e" }));
    svg.appendChild(el("text", { x: Math.min(248, Math.max(40, cx)), y: 14, "text-anchor": "middle", fill: "#ecb95e", "font-size": 10, "font-weight": 700, "font-family": "Consolas, monospace" }, `CoG = ${centVal.toFixed(1)}`));
  }
}

function fuzzyRender() {
  const eVal = Number(document.getElementById("sl-e").value);
  const wVal = Number(document.getElementById("sl-w").value);
  const tVal = Number(document.getElementById("sl-t").value);
  document.getElementById("sl-e-lbl").textContent = eVal;
  document.getElementById("sl-w-lbl").textContent = wVal;
  document.getElementById("sl-t-lbl").textContent = tVal;
  document.getElementById("fval-e").textContent = eVal;
  document.getElementById("fval-w").textContent = wVal;
  document.getElementById("fval-t").textContent = tVal;

  const res = evalFuzzyJS(eVal, wVal, tVal);
  drawInputMF("fsvg-e", eVal, res.E, fuzzyStage >= 1);
  drawInputMF("fsvg-w", wVal, res.W, fuzzyStage >= 1);
  drawInputMF("fsvg-t", tVal, res.T, fuzzyStage >= 1);

  drawOutputMF("fsvg-ally", res.agg.alliance, res.centroids.alliance, "#5ee39b", fuzzyStage >= 3, fuzzyStage >= 4);
  drawOutputMF("fsvg-betray", res.agg.betrayal, res.centroids.betrayal, "#f06a5a", fuzzyStage >= 3, fuzzyStage >= 4);
  drawOutputMF("fsvg-solo", res.agg.solo, res.centroids.solo, "#49a7bf", fuzzyStage >= 3, fuzzyStage >= 4);

  document.getElementById("fout-ally").textContent = fuzzyStage >= 4 ? res.scores.alliance.toFixed(2) : "—";
  document.getElementById("fout-betray").textContent = fuzzyStage >= 4 ? res.scores.betrayal.toFixed(2) : "—";
  document.getElementById("fout-solo").textContent = fuzzyStage >= 4 ? res.scores.solo.toFixed(2) : "—";

  // Highlight active boxes
  ["fbox-e","fbox-w","fbox-t"].forEach(id => document.getElementById(id).classList.toggle("hl", fuzzyStage === 1));
  ["fbox-ally","fbox-betray","fbox-solo"].forEach(id => document.getElementById(id).classList.toggle("hl", fuzzyStage >= 3));

  // Rules list
  const rulesEl = document.getElementById("fuzzy-rules-list");
  rulesEl.innerHTML = res.rules.map(r => {
    const fired = fuzzyStage >= 2 && r.fire > 0.005;
    const pct = fuzzyStage >= 2 ? (r.fire * 100).toFixed(0) : 0;
    return `<div class="rule-row ${fired ? "active-rule" : ""}">
      <div style="display:flex;justify-content:space-between;gap:6px;">
        <span><strong style="color:var(--gold)">${r.id}:</strong> ${r.text}</span>
        <strong style="font-family:Consolas,monospace;color:${fired ? "var(--green)" : "var(--muted)"}">${fuzzyStage >= 2 ? r.fire.toFixed(2) : "—"}</strong>
      </div>
      <div class="rule-bar-bg"><div class="rule-bar-fill" style="width:${pct}%"></div></div>
    </div>`;
  }).join("");

  const stageNames = [
    "",
    "Stage 1 / 4: Fuzzification — Crisp inputs (e, w, t) are mapped onto overlapping LOW / MEDIUM / HIGH triangular curves.",
    "Stage 2 / 4: Rule Firing — Each of the 6 Mamdani rules evaluates min(μ₁, μ₂) to compute its firing strength.",
    "Stage 3 / 4: Implication & Max-Aggregation — Fired rules clip their output triangles and combine via max() into shaded polygons.",
    "Stage 4 / 4: Centroid Defuzzification — Center of gravity Σ(x·μ)/Σμ ÷ 100 outputs continuous UCT biases for MCTS.",
  ];
  document.getElementById("fuzzy-stage-label").textContent = stageNames[fuzzyStage].split(" — ")[0];
  document.getElementById("fuzzy-stage-badge").textContent = `STAGE ${fuzzyStage} / 4`;
  document.getElementById("fuzzy-narrative").textContent = stageNames[fuzzyStage];

  document.getElementById("fuzzy-summary-box").innerHTML =
    `ALLIANCE bias = <strong style="color:var(--green)">${res.scores.alliance.toFixed(2)}</strong> &nbsp;|&nbsp; ` +
    `BETRAYAL bias = <strong style="color:var(--red)">${res.scores.betrayal.toFixed(2)}</strong> &nbsp;|&nbsp; ` +
    `SOLO bias = <strong style="color:var(--stark)">${res.scores.solo.toFixed(2)}</strong><br/>` +
    `<span style="color:var(--muted)">Injected into MCTS: UCT = Q/N + 1.414&middot;&radic;(ln Np / N) + bias</span>`;
}

function fuzzyLoadPreset(idx) {
  const p = DATA.fuzzy_presets[idx];
  document.getElementById("sl-e").value = p.e;
  document.getElementById("sl-w").value = p.w;
  document.getElementById("sl-t").value = p.t;
  document.getElementById("fuzzy-preset-desc").textContent = p.desc;
  fuzzyStage = 4;
  fuzzyRender();
}
function fuzzyStop() {
  if (fuzzyTimer) { clearInterval(fuzzyTimer); fuzzyTimer = null; }
}
function fuzzyStartAnim() {
  fuzzyStop();
  fuzzyStage = 1;
  fuzzyRender();
  fuzzyTimer = setInterval(() => {
    if (fuzzyStage >= 4) { fuzzyStop(); return; }
    fuzzyStage++;
    fuzzyRender();
  }, 1350);
}

fuzzyPresetSel.addEventListener("change", () => fuzzyLoadPreset(Number(fuzzyPresetSel.value)));
["sl-e","sl-w","sl-t"].forEach(id => document.getElementById(id).addEventListener("input", () => { fuzzyStage = 4; fuzzyRender(); }));
document.getElementById("fuzzy-play").addEventListener("click", fuzzyStartAnim);
document.getElementById("fuzzy-prev").addEventListener("click", () => { fuzzyStop(); fuzzyStage = Math.max(1, fuzzyStage - 1); fuzzyRender(); });
document.getElementById("fuzzy-next").addEventListener("click", () => { fuzzyStop(); fuzzyStage = Math.min(4, fuzzyStage + 1); fuzzyRender(); });

// =========================================================================
// Boot all 4 tabs
// =========================================================================
mmLoadScenario(0);
mctsLoadScenario(0);
astarLoadRoute(0);
fuzzyLoadPreset(0);
</script>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate live interactive AI search tree visualizer.")
    parser.add_argument("--seed", type=int, default=42, help="Deterministic RNG seed for MCTS rollouts (default: 42).")
    parser.add_argument("--out", type=str, default="tree_visualizer.html", help="Output HTML file path.")
    parser.add_argument("--open", action="store_true", help="Open generated HTML in the default web browser.")
    args = parser.parse_args()

    bundle = build_trace_bundle(seed=args.seed)
    safe_json = json.dumps(bundle, separators=(",", ":")).replace("</", "<\\/")
    html = HTML_TEMPLATE.replace("__TRACE_JSON__", safe_json)

    out_path = Path(args.out).resolve()
    out_path.write_text(html, encoding="utf-8")

    print(f"Generated interactive visualizer: {out_path}")
    print(f"  Bundle size: {len(html) / 1024:.1f} KB (100% self-contained offline HTML)")
    print("  1. Minimax Scenarios:")
    for sc in bundle["minimax"]:
        st = sc["stats"]
        print(
            f"     - {sc['title']}: {st['evaluated_nodes']} visited, "
            f"{st['leaves_evaluated']} leaves, {st['pruned_nodes']} pruned, {len(sc['events'])} steps"
        )
    print("  2. MCTS Scenarios (500 rollouts each):")
    for sc in bundle["mcts"]:
        opts = ", ".join(f"{b['label']}={b['final_visits']}v (Q={b['final_q']:.2f})" for b in sc["branches"])
        print(f"     - {sc['title']}: winner={sc['winner_label']} [{opts}]")
    print("  3. A* Routes:")
    for r in bundle["astar"]["routes"]:
        print(
            f"     - {r['start']} -> {r['goal']}: {' -> '.join(r['path'])} "
            f"(cost={r['total_cost']}, bonus=+{r['corridor_bonus']}, {len(r['steps'])} steps)"
        )
    print("  4. Fuzzy Logic Presets:")
    for p in bundle["fuzzy_presets"]:
        s = p["python_scores"]
        print(f"     - {p['name']}: Ally={s['alliance']:.2f}, Betray={s['betrayal']:.2f}, Solo={s['solo']:.2f}")

    if args.open:
        webbrowser.open(out_path.as_uri())


if __name__ == "__main__":
    main()
