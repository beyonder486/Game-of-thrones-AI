"""Fuzzy Logic diplomacy evaluation before MCTS decision-making.

This replaces magic-number thresholds with linguistically grounded evaluation.
Outputs continuous desirability scores in [0.0, 1.0] only — never final decisions.

A single function serves two contexts:
  Context A — own diplomatic landscape:
      enemy_strength = combined military threat, own_weakness = own vulnerability,
      trust_history = average trust toward enemies.
  Context B — incoming alliance proposal:
      enemy_strength = proposal sender's military, own_weakness = receiver's weakness,
      trust_history = trust toward the sender.

KNOWN APPROXIMATION: Fuzzy Logic is stateless — it evaluates the current snapshot
only, not the future trajectory. MCTS rollouts account for what happens next.
"""

from __future__ import annotations

import numpy as np

try:
    import skfuzzy as fuzz
    from skfuzzy import control as ctrl

    _HAS_SKFUZZY = True
except ImportError:
    _HAS_SKFUZZY = False


def _trimf(x: np.ndarray, abc: tuple[float, float, float]) -> np.ndarray:
    """Triangular membership function matching skfuzzy.trimf."""
    a, b, c = abc
    y = np.zeros_like(x, dtype=float)
    if a != b:
        idx = (a < x) & (x < b)
        y[idx] = (x[idx] - a) / (b - a)
    if b != c:
        idx = (b < x) & (x < c)
        y[idx] = (c - x[idx]) / (c - b)
    y[x == b] = 1.0
    if a == b:
        y[x <= a] = 1.0
    if b == c:
        y[x >= c] = 1.0
    return np.clip(y, 0.0, 1.0)


def _interp_membership(universe: np.ndarray, mf: np.ndarray, value: float) -> float:
    return float(np.interp(np.clip(value, 0.0, 100.0), universe, mf))


def _defuzz_centroid(universe: np.ndarray, aggregated: np.ndarray) -> float:
    total = float(np.sum(aggregated))
    if total <= 1e-9:
        return 0.0  # no rule fired → no desirability
    return float(np.sum(universe * aggregated) / total)


def _evaluate_skfuzzy(e_val: float, w_val: float, t_val: float) -> dict[str, float]:
    universe = np.arange(0, 101, 1, dtype=float)
    enemy = ctrl.Antecedent(universe, "enemy_strength")
    weakness = ctrl.Antecedent(universe, "own_weakness")
    trust = ctrl.Antecedent(universe, "trust_history")

    alliance = ctrl.Consequent(universe, "alliance_desirability")
    betrayal = ctrl.Consequent(universe, "betrayal_desirability")
    solo = ctrl.Consequent(universe, "solo_desirability")

    for var in (enemy, weakness, trust, alliance, betrayal, solo):
        var["low"] = fuzz.trimf(universe, [0, 0, 60])
        var["medium"] = fuzz.trimf(universe, [20, 50, 80])
        var["high"] = fuzz.trimf(universe, [40, 100, 100])

    rules = [
        ctrl.Rule(enemy["high"] & weakness["high"], alliance["high"]),
        ctrl.Rule(trust["low"] & enemy["medium"], alliance["low"]),
        ctrl.Rule(weakness["low"] & enemy["low"], betrayal["high"]),
        ctrl.Rule(weakness["low"] & trust["high"], solo["high"]),
        ctrl.Rule(enemy["high"] & trust["high"], alliance["medium"]),
        ctrl.Rule(trust["low"], betrayal["medium"]),
    ]
    sim = ctrl.ControlSystemSimulation(ctrl.ControlSystem(rules))
    sim.input["enemy_strength"] = e_val
    sim.input["own_weakness"] = w_val
    sim.input["trust_history"] = t_val
    sim.compute()
    return {
        "alliance": round(float(sim.output.get("alliance_desirability", 0.0)) / 100.0, 2),
        "betrayal": round(float(sim.output.get("betrayal_desirability", 0.0)) / 100.0, 2),
        "solo": round(float(sim.output.get("solo_desirability", 0.0)) / 100.0, 2),
    }


def evaluate_diplomacy(
    enemy_strength: float,
    own_weakness: float,
    trust_history: float,
) -> dict[str, float]:
    """Evaluate diplomatic state using triangular fuzzy membership functions.

    This replaces magic-number thresholds with linguistically grounded evaluation.
    """
    e_val = float(np.clip(enemy_strength, 0.0, 100.0))
    w_val = float(np.clip(own_weakness, 0.0, 100.0))
    t_val = float(np.clip(trust_history, 0.0, 100.0))

    if _HAS_SKFUZZY:
        try:
            return _evaluate_skfuzzy(e_val, w_val, t_val)
        except Exception:  # skfuzzy raises when a consequent receives no activation
            pass

    # Pure-NumPy Mamdani trimf inference when scikit-fuzzy is not installed
    universe = np.linspace(0.0, 100.0, 101)
    low = _trimf(universe, (0.0, 0.0, 60.0))
    med = _trimf(universe, (20.0, 50.0, 80.0))
    high = _trimf(universe, (40.0, 100.0, 100.0))

    e_low = _interp_membership(universe, low, e_val)
    e_med = _interp_membership(universe, med, e_val)
    e_high = _interp_membership(universe, high, e_val)

    w_low = _interp_membership(universe, low, w_val)
    w_high = _interp_membership(universe, high, w_val)

    t_low = _interp_membership(universe, low, t_val)
    t_high = _interp_membership(universe, high, t_val)

    # Rule activations (Mamdani min-implication, max-aggregation)
    r1_alliance_high = min(e_high, w_high)
    r2_alliance_low = min(t_low, e_med)
    r3_betrayal_high = min(w_low, e_low)
    r4_solo_high = min(w_low, t_high)
    r5_alliance_med = min(e_high, t_high)
    r6_betrayal_med = t_low

    agg_alliance = np.maximum.reduce([
         np.minimum(r2_alliance_low, low),
        np.minimum(r5_alliance_med, med),
        np.minimum(r1_alliance_high, high),
    ])
    agg_betrayal = np.maximum(
        np.minimum(r6_betrayal_med, med),
        np.minimum(r3_betrayal_high, high),
    )
    agg_solo = np.minimum(r4_solo_high, high)

    return {
        "alliance": round(_defuzz_centroid(universe, agg_alliance) / 100.0, 2),
        "betrayal": round(_defuzz_centroid(universe, agg_betrayal) / 100.0, 2),
        "solo": round(_defuzz_centroid(universe, agg_solo) / 100.0, 2),
    }
