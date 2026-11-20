"""Verification & demo suite for all 7 AI algorithms and game-logic invariants.

Run with:
    python test_algorithms.py
"""

from __future__ import annotations

import os
import random

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from algorithms.astar import get_path
from algorithms.bfs import get_reachable
from algorithms.dfs import get_expansion_paths
from algorithms.fuzzy_diplomacy import evaluate_diplomacy
from algorithms.greedy import get_greedy_move
from algorithms.mcts import _Sim, get_diplomacy_decision, get_proposal_response
from algorithms.minimax import get_best_move
from combat import Combat, effective_defense
from diplomacy import Diplomacy
from main import GameController
from map import Map, hex_distance


def _fresh_controller(mode: str = "AI vs AI", human_house: str = "STARK") -> GameController:
    return GameController(mode=mode, human_house=human_house)


def test_bfs() -> None:
    game_map = Map()
    winterfell = game_map.by_name["WINTERFELL"]
    r1 = get_reachable(game_map, winterfell, 1)
    r2 = get_reachable(game_map, winterfell, 2)
    assert winterfell in r1
    assert set(winterfell.neighbors).issubset(r1)
    assert len(r2) > len(r1)
    assert game_map.iron_throne in r2
    print(f"[PASS] 1. BFS: Winterfell depth=1 -> {len(r1)} holds, depth=2 -> {len(r2)} holds (includes KING'S LANDING)")


def test_dfs() -> None:
    game_map = Map()
    winterfell = game_map.by_name["WINTERFELL"]
    paths = get_expansion_paths(game_map, winterfell, 3)
    assert len(paths) > 0
    for path in paths:
        assert path[0] == winterfell
        assert len(path) == len(set(path)), "DFS path must be simple (no repeated holds)"
        for a, b in zip(path, path[1:]):
            assert b in a.neighbors, "DFS steps must follow map adjacency"
    print(f"[PASS] 2. DFS: Winterfell depth=3 -> {len(paths)} valid simple expansion corridors")


def test_greedy() -> None:
    ctrl = _fresh_controller()
    stark = ctrl.by_name["STARK"]
    choice = get_greedy_move(stark, ctrl.map)
    assert choice is not None
    expected = max(
        (nb for nb in stark.territories[0].neighbors if nb.owner != stark.name),
        key=lambda t: (t.resource_value - t.defense_bonus, t.is_iron_throne),
    )
    assert choice == expected
    print(f"[PASS] 3. Greedy: Stark picked {choice.name} (res={choice.resource_value}, def={choice.defense_bonus})")


def test_astar() -> None:
    game_map = Map()
    winterfell = game_map.by_name["WINTERFELL"]
    kl = game_map.iron_throne
    path = get_path(game_map, winterfell, kl)
    assert path and path[0] == winterfell and path[-1] == kl
    for a, b in zip(path, path[1:]):
        assert b in a.neighbors
    hd = hex_distance((winterfell.col, winterfell.row), (kl.col, kl.row))
    cost = sum(t.defense_bonus for t in path[1:])
    route = " -> ".join(t.name for t in path)
    print(f"[PASS] 4. A*: {route} (defense cost={cost}, hex_distance={hd})")


def test_fuzzy() -> None:
    # High threat (90) + weak self (85) + moderate trust (65) -> alliance desired, betrayal near 0
    weak_scores = evaluate_diplomacy(90.0, 85.0, 65.0)
    assert weak_scores["alliance"] > 0.5 and weak_scores["betrayal"] < 0.2

    # Low threat (20) + strong self (weakness=10) + low trust (10) -> betrayal high, alliance low
    strong_scores = evaluate_diplomacy(20.0, 10.0, 10.0)
    assert strong_scores["betrayal"] > 0.5 and strong_scores["alliance"] < 0.2

    # Incoming proposal when threatened (85) and weak (75) with high trust (80) -> high alliance
    ctx_b = evaluate_diplomacy(85.0, 75.0, 80.0)
    assert ctx_b["alliance"] > 0.5
    print(
        "[PASS] 5. Fuzzy Logic: "
        f"weak+threat -> alliance={weak_scores['alliance']:.2f}, betrayal={weak_scores['betrayal']:.2f}; "
        f"strong+low_trust -> betrayal={strong_scores['betrayal']:.2f}, alliance={strong_scores['alliance']:.2f}"
    )


def test_minimax_and_alliance_modes() -> None:
    ctrl = _fresh_controller()
    stark = ctrl.by_name["STARK"]
    lannister = ctrl.by_name["LANNISTER"]
    targaryen = ctrl.by_name["TARGARYEN"]

    move_solo = get_best_move(stark, ctrl.houses, ctrl.map, ctrl.diplomacy)
    assert move_solo is not None
    assert stark.mode == "DECOMPOSED"

    # Forming an alliance must immediately flip ALL 3 houses (including the lone target) to PARANOID
    ctrl.diplomacy.form_alliance(lannister, targaryen)
    assert lannister.mode == "PARANOID"
    assert targaryen.mode == "PARANOID"
    assert stark.mode == "PARANOID", "Lone third house must immediately enter PARANOID mode"

    move_paranoid = get_best_move(stark, ctrl.houses, ctrl.map, ctrl.diplomacy)
    assert move_paranoid is not None
    assert stark.mode == "PARANOID"

    # Dissolving the alliance must reset all 3 houses back to DECOMPOSED
    ctrl.diplomacy.dissolve_alliance(lannister, targaryen)
    assert stark.mode == "DECOMPOSED"
    assert lannister.mode == "DECOMPOSED"
    assert targaryen.mode == "DECOMPOSED"

    # Switching allies while already allied must trigger automatic betrayal (-30 trust + log)
    ctrl.diplomacy.form_alliance(stark, lannister, turn=1)
    trust_before = ctrl.diplomacy.get_trust(stark, lannister)
    ctrl.diplomacy.resolve_proposal(targaryen, stark, accepted=True, turn=2)
    assert ctrl.diplomacy.are_allied(stark, targaryen)
    assert not ctrl.diplomacy.are_allied(stark, lannister)
    assert ctrl.diplomacy.get_trust(stark, lannister) == trust_before - 30.0
    assert any("betrayed Lannister" in str(e["text"]) for e in ctrl.diplomacy.event_log)

    # Minimax must have populated A* throne-corridor costs on the map
    assert hasattr(ctrl.map, "_astar_throne_costs")
    assert ctrl.map._astar_throne_costs["KING'S LANDING"] == 0.0
    assert ctrl.map._astar_throne_costs["THE TWINS"] < ctrl.map._astar_throne_costs["WINTERFELL"]

    print(
        f"[PASS] 6. Minimax (alpha-beta + A* corridor) & Alliance Modes: "
        f"DECOMPOSED -> {move_solo.name}, PARANOID -> {move_paranoid.name}; "
        "auto-betrayal on ally switch & 3-house mode sync verified"
    )


def test_mcts_and_sim_consistency() -> None:
    random.seed(42)
    ctrl = _fresh_controller()
    stark = ctrl.by_name["STARK"]
    lannister = ctrl.by_name["LANNISTER"]
    targaryen = ctrl.by_name["TARGARYEN"]

    # Make Targaryen dominant so Stark wants to ally with Lannister
    targaryen.armies = 40
    stark.armies = 8
    lannister.armies = 12
    fuzzy_a = evaluate_diplomacy(90.0, 80.0, 70.0)
    action_a, target_a = get_diplomacy_decision(
        stark, ctrl.houses, ctrl.map, fuzzy_a, ctrl.diplomacy
    )
    assert action_a in ("propose_alliance", "solo", "betray")

    # Context B: Stark receives proposal from Lannister while weak & threatened
    fuzzy_b = evaluate_diplomacy(90.0, 80.0, 80.0)
    decision_b = get_proposal_response(
        stark, lannister, ctrl.houses, ctrl.map, fuzzy_b, ctrl.diplomacy
    )
    assert decision_b in ("accept", "reject")

    # Verify MCTS _Sim invariants:
    # 1) Economy enforces supply cap (12 + 6 * owned), 15 gold reserve, MAX_RECRUITS_PER_TURN
    sim = _Sim(ctrl.houses, ctrl.map)
    sim.gold["STARK"] = 500.0
    sim.armies["STARK"] = 17.0  # owns 1 hold -> supply cap = 18
    sim.economy()
    assert sim.armies["STARK"] <= 18.0, f"MCTS _Sim economy exceeded supply cap: {sim.armies['STARK']}"

    # 2) Candidates skip King's Landing when attacker cannot beat its defense threshold
    sim2 = _Sim(ctrl.houses, ctrl.map)
    twins_idx = next(i for i, t in enumerate(sim2.territories) if t.name == "THE TWINS")
    sim2.owner[twins_idx] = "STARK"
    sim2.armies["STARK"] = 10.0  # KL neutral defense is 14 * 4 = 56
    cands = [t.name for t in sim2.candidates("STARK", protected=None)]
    assert "KING'S LANDING" not in cands, "MCTS _Sim should not suicide into King's Landing"

    # 3) Surviving armies after attack never drop below 1.0
    sim3 = _Sim(ctrl.houses, ctrl.map)
    sim3.armies["STARK"] = 2.0
    sim3.attack("STARK", ctrl.map.by_name["THE TWINS"])
    assert sim3.armies["STARK"] >= 1.0

    target_label = target_a.name if target_a is not None else "None"
    print(
        f"[PASS] 7. MCTS (UCT) & _Sim Parity: Context A -> ({action_a}, {target_label}), "
        f"Context B -> {decision_b}; supply cap, KL guard, and >=1 army floor verified"
    )


def test_game_logic_invariants() -> None:
    # 1) Effective defense formula: neutral uses full multiplier, house uses 1 + 0.15 * bonus
    assert effective_defense(14, 4, is_house=False) == 56.0
    assert abs(effective_defense(10, 4, is_house=True) - 16.0) < 1e-9

    # 2) Human ally proposal does NOT end turn and blocks duplicate proposals in same turn
    ctrl = _fresh_controller(mode="Human vs AI", human_house="STARK")
    ctrl.active_index = 0
    ended1 = ctrl.handle_human_action("ally_lannister")
    assert ended1 is False, "Proposing alliance must not end the human's turn"
    assert len(ctrl.by_name["LANNISTER"].inbox) == 1
    ended2 = ctrl.handle_human_action("ally_targaryen")
    assert ended2 is False
    assert len(ctrl.by_name["TARGARYEN"].inbox) == 0, "Cannot send two proposals in one turn"

    # 3) Holding repeatedly respects supply cap (12 + 6 * holds) -> no infinite army exploit
    ctrl_hold = _fresh_controller(mode="Human vs AI", human_house="STARK")
    stark = ctrl_hold.by_name["STARK"]
    for _ in range(15):
        stark.gold += 50
        ctrl_hold._end_of_round()
    supply_cap = 12 + 6 * len(stark.territories)
    assert stark.armies <= supply_cap, f"Supply cap violated: {stark.armies} > {supply_cap}"

    # 4) BFS/DFS telemetry is persisted on House during step_house_turn
    ctrl_ai = _fresh_controller()
    ai_stark = ctrl_ai.by_name["STARK"]
    ctrl_ai.step_house_turn(ai_stark)
    assert len(ai_stark.reachable_holds) > 0, "BFS reachable_holds not saved on House"
    assert len(ai_stark.expansion_paths) > 0, "DFS expansion_paths not saved on House"

    # 5) Eliminated houses cannot send/hold proposals or form alliances
    ctrl_elim = _fresh_controller(mode="Human vs AI", human_house="LANNISTER")
    targ = ctrl_elim.by_name["TARGARYEN"]
    lann = ctrl_elim.by_name["LANNISTER"]
    ctrl_elim.diplomacy.queue_proposal(targ, lann, turn=1)
    assert lann.get_pending_proposal() is not None
    # Eliminate Targaryen
    for t in list(targ.territories):
        targ.lose_territory(t)
        t.owner = "STARK"
    ctrl_elim.diplomacy.purge_eliminated(targ)
    assert lann.get_pending_proposal() is None, "Stale proposal from eliminated house was not purged"
    ctrl_elim.diplomacy.queue_proposal(targ, lann, turn=2)
    assert lann.get_pending_proposal() is None, "Eliminated house must not be able to queue proposals"
    ctrl_elim.diplomacy.form_alliance(targ, lann, turn=2)
    assert not ctrl_elim.diplomacy.are_allied(targ, lann), "Eliminated house must not form alliances"

    print(
        f"[PASS] 8. Game-Logic Invariants: effective_defense, human ally+move turn rule, "
        f"supply cap ({stark.armies}/{supply_cap}), BFS/DFS telemetry, and eliminated-house diplomacy guard verified"
    )


def test_ai_vs_ai_simulation(num_games: int = 8) -> None:
    random.seed(12345)
    winners: dict[str, int] = {}
    house_vs_house_battles = 0
    total_turns = 0

    for g in range(num_games):
        ctrl = _fresh_controller()
        # Hook Combat.resolve_combat to count house-vs-house battles
        orig_resolve = Combat.resolve_combat

        def _counting_resolve(attacker, defender, territory, game_map, _orig=orig_resolve):
            nonlocal house_vs_house_battles
            if defender is not None:
                house_vs_house_battles += 1
            return _orig(attacker, defender, territory, game_map)

        Combat.resolve_combat = staticmethod(_counting_resolve)
        try:
            for _ in range(60):
                if ctrl.winner is not None:
                    break
                for house in ctrl.houses:
                    if house.is_eliminated() or ctrl.winner is not None:
                        continue
                    ctrl.step_house_turn(house)
                if ctrl.winner is None:
                    ctrl._end_of_round()
        finally:
            Combat.resolve_combat = orig_resolve

        total_turns += ctrl.turn
        label = ctrl.winner.name if ctrl.winner else "TIMEOUT"
        winners[label] = winners.get(label, 0) + 1

    assert house_vs_house_battles > 0, "Expected rival houses to engage in house-vs-house combat"
    assert winners.get("TIMEOUT", 0) == 0, f"Games did not conclude within 60 turns: {winners}"
    print(
        f"[PASS] 9. AI vs AI Simulation ({num_games} games): "
        f"winners={winners}, avg_turns={total_turns / num_games:.1f}, "
        f"house_vs_house_battles={house_vs_house_battles}"
    )


if __name__ == "__main__":
    print("=== Game of Thrones: AI Conquest — Verification Suite ===")
    test_bfs()
    test_dfs()
    test_greedy()
    test_astar()
    test_fuzzy()
    test_minimax_and_alliance_modes()
    test_mcts_and_sim_consistency()
    test_game_logic_invariants()
    test_ai_vs_ai_simulation()
    print("=== ALL 9 CHECKS PASSED ===")
