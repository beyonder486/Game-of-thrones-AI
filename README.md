# Game of Thrones: AI Conquest

A turn-based 2.5D grand-strategy game set in Westeros where three Great Houses — **House Stark**, **House Lannister**, and **House Targaryen** — compete for the **Iron Throne** through territorial expansion, economy management, tactical combat, and asynchronous diplomacy powered by **seven classical and modern AI algorithms**.

---

## Overview & Victory Conditions

The map of Westeros consists of **15 named holds (territories)** connected across a hexagonal continent. Each territory provides:
- **Resource Value (`+Gold/turn`):** Added to its ruling house's base income every round.
- **Defense Bonus (`×1` to `×4`):** Multiplies the defender's strength when besieged.
- **Neutral Garrison:** Initial defending forces on unclaimed territories.

A house wins immediately at the end of a round when either condition is met:
1. **Conquest of the Iron Throne:** The house captures and holds **King's Landing**.
2. **Last House Standing:** All rival houses are eliminated (0 territories remaining).

---

## Great Houses & Starting Balance

| House | Starting Seat | Motto | Starting Gold | Starting Armies |
| :--- | :--- | :--- | :---: | :---: |
| **House Stark** | Winterfell | *Winter Is Coming* | 60 | 14 |
| **House Lannister** | Casterly Rock | *Hear Me Roar* | 65 | 14 |
| **House Targaryen** | Dragonstone | *Fire and Blood* | 45 | 12 |

---

## The 7 AI Algorithms

Every AI house executes an integrated decision pipeline combining graph search, fuzzy inference, adversarial tree search, and Monte Carlo simulation:

1. **Breadth-First Search (BFS) — [`algorithms/bfs.py`](algorithms/bfs.py)**
   - Computes `get_reachable(map, start, n_steps=3)` to map all territories reachable within `n_steps` marches from a house's seat.
2. **Depth-First Search (DFS) — [`algorithms/dfs.py`](algorithms/dfs.py)**
   - Computes `get_expansion_paths(map, start, depth_limit=3)` to scout deep multi-step expansion corridors across Westeros.
3. **Greedy Search — [`algorithms/greedy.py`](algorithms/greedy.py)**
   - Evaluates immediate targets via `argmax(resource_value - defense_bonus)` and serves as the fast **rollout policy** inside MCTS simulations (replacing random rollouts).
4. **A\* Pathfinding — [`algorithms/astar.py`](algorithms/astar.py)**
   - Routes troop movement (`get_path(map, start, goal)`) from a house's nearest controlled hold toward its chosen target, minimizing cumulative `defense_bonus` along the path.
5. **Mamdani Fuzzy Logic — [`algorithms/fuzzy_diplomacy.py`](algorithms/fuzzy_diplomacy.py)**
   - Evaluates three continuous inputs (`enemy_strength`, `own_weakness`, `trust_history` on `0–100` scales) using triangular membership functions (`LOW`, `MEDIUM`, `HIGH`) and 6 Mamdani rules to output soft disposition scores `{"alliance", "betrayal", "solo"}` that bias MCTS.
   - **Context A:** Evaluates the overall diplomatic landscape against all surviving enemies.
   - **Context B:** Evaluates an incoming alliance proposal in the house's inbox against the sender's strength and trust.
6. **Monte Carlo Tree Search (MCTS) — [`algorithms/mcts.py`](algorithms/mcts.py)**
   - Makes all final diplomatic decisions using UCT biased by Fuzzy Logic scores:
     ```text
     UCT = (Q / N) + UCT_C * sqrt(ln(N_parent) / N) + fuzzy_score[action]
     ```
   - Simulates multi-turn greedy rollouts (including probabilistic alliance breakdown `p_break = 1 - trust / 100`) to choose between `propose_alliance`, `betray`, or `solo` (Context A), and `accept` or `reject` (Context B).
7. **Minimax with Alpha-Beta Pruning — [`algorithms/minimax.py`](algorithms/minimax.py)**
   - Searches up to depth `3` to select the optimal tactical attack target (or `None` to hold fortifications).
   - **Decomposed Mode:** When no enemy coalition exists, evaluates 1v1 sub-trees against each opponent weighted by their relative military strength.
   - **Paranoid Mode:** When facing an active alliance (or acting within a pact), merges allied opponents into a single coordinated minimizing coalition.

---

## Exact 11-Step Turn Structure

Each round processes surviving houses in order (**Stark → Lannister → Targaryen**), strictly enforcing **one action per house per turn**:

- **If `house.inbox` has a pending alliance proposal:**
  1. **Fuzzy Logic (Context B):** Evaluate the proposing house's military strength and trust.
  2. **MCTS (Context B):** Simulate accepting vs. rejecting the pact.
  3. **Resolve Proposal:** Send `YES` (forming an active alliance and switching to Paranoid Minimax) or `NO`.
  4. **Minimax:** Select the best combat/expansion move.
  5. **A\*:** Route troop movement from the nearest owned hold.
  6. **Combat:** Resolve the battle and log the outcome in **The Raven's Log**.

- **Else (no pending proposal in `house.inbox`):**
  1. **BFS / DFS:** Update reachability and deep expansion paths.
  2. **Fuzzy Logic (Context A):** Evaluate the overall diplomatic landscape.
  3. **MCTS (Context A):** Decide between `propose_alliance`, `betray`, or `solo`.
  4. **Queue / Execute Diplomacy:** Queue a proposal in the target's inbox (evaluated on their next turn) or unilaterally break an alliance (`-30` trust penalty).
  5. **Minimax:** Select the best combat/expansion move.
  6. **A\*:** Route troop movement.
  7. **Combat:** Resolve the attack.

- **End of Round (after all houses act):**
  8. **Collect Income:** Each house gains `BASE_INCOME (10) + sum(territory.resource_value)`.
  9. **Recruit Armies:** Houses recruit up to `MAX_RECRUITS_PER_TURN (3)` armies at `5 Gold` per army (keeping a `15 Gold` reserve).
  10. **Update Trust:** Surviving alliances gain `+5` bilateral trust.
  11. **Check Win Condition:** Check whether **King's Landing** is held by a house or only one house survives.

---

## Combat & Diplomacy Rules

- **Combat Resolution ([`combat.py`](combat.py)):**
  - `Attack Power = attacker.armies * Uniform(0.80, 1.20)`
  - `Defense Power = effective_defense * Uniform(0.80, 1.20)` where `effective_defense = defender_armies * defense_bonus` for neutral garrisons and `defender_armies * (1.0 + 0.15 * defense_bonus)` for rival Great House pools.
  - If `Attack Power > Defense Power`, the attacker captures the territory (`50%` of defender count lost by attacker; `80%` lost by defender). If a house loses its final territory, the conqueror seizes its remaining gold treasury.
  - Otherwise, the attack is repelled (`60%` of attacker armies lost; `20%` of defender armies lost).
- **Army Supply Cap:** Recruitment is capped at `12 + 6 * holds` armies (up to `3` recruits/turn at `5 Gold` each) so houses must expand to field larger forces.
- **No Resource Sharing:** Allied houses never pool gold, armies, or territories—every captured hold belongs strictly to the house that conquered it.

---

## Game Modes & Controls

1. **AI vs AI (Observer Mode):**
   - Watch all three AI houses compete autonomously while inspecting live **House Intelligence** cards, **Fuzzy Logic** bars, and **The Raven's Log**.
   - Click **`ADVANCE TURN >>`** or press `SPACE` / `ENTER` to step forward turn by turn.
2. **Human vs AI (Player Command):**
   - Command **House Stark**, **House Lannister**, or **House Targaryen** directly against two AI rivals.
   - **Attack:** Click any territory on the map to march via A\* and attack.
   - **Diplomacy:** Click **`ACCEPT` / `REJECT`** when a raven arrives in your inbox, **`ALLY <HOUSE>`** to send a proposal, **`BETRAY`** to break a pact and strike, or **`HOLD TURN`** to fortify in place.
3. **Post-Game Board Review:**
   - When a house wins, click **`REVIEW REALM / BOARD`** (or **`X`**) on the victory modal to inspect final territory garrisons and **The Raven's Log**, or click **`NEW CONQUEST`** to return to the startup menu.
   - Press `R` at any time to reset to the startup menu, or `ESC` to quit.

---

## Running the Game

### Requirements
- Python 3.10+
- `pygame`, `numpy`, `Pillow`

### Launch
```bash
python main.py
```

---

## Project Structure

```text
├── main.py                     # Entry point, window/DPI setup, GameController & 11-step turn loop
├── constants.py                # Resolution, hex geometry, palette, economy & AI hyperparameters
├── map.py                      # 15 Westeros territories, adjacency graph, hex terrain & regions
├── house.py                    # House state (gold, armies, territories, inbox, fuzzy scores)
├── diplomacy.py                # Alliances, trust matrix, async proposal inbox & Raven's Log
├── combat.py                   # Randomized tactical combat resolution & elimination plunder
├── renderer.py                 # 2.5D isometric map renderer, HUD panels, modals & tooltips
├── algorithms/
│   ├── bfs.py                  # Breadth-First Search reachability
│   ├── dfs.py                  # Depth-First Search expansion scouting
│   ├── greedy.py               # Greedy target selection & MCTS rollout policy
│   ├── astar.py                # A* pathfinding weighted by territory defense
│   ├── fuzzy_diplomacy.py      # Mamdani Fuzzy Logic (Context A & Context B)
│   ├── minimax.py              # Alpha-Beta Minimax (Decomposed & Paranoid modes)
│   └── mcts.py                 # UCT Monte Carlo Tree Search for diplomacy
└── assets/
    ├── buildings/              # Isometric castle & landmark sprites
    ├── tiles/                  # Terrain tile textures
    ├── ui/                     # Supersampled HUD icons & house crests
    └── units/                  # Isometric knight squad sprite
```

---

## Documentation

Full design and reference documentation lives in [`GUIDE/`](GUIDE/):

| Document | What it covers |
|---|---|
| [`GUIDE/instructions.md`](GUIDE/instructions.md) | The specification — what was to be built |
| [`GUIDE/instruction 2.md`](GUIDE/instruction%202.md) | Mechanics reference — every rule and formula with `file:line` citations |
| [`GUIDE/CODE_MAP.md`](GUIDE/CODE_MAP.md) | Per-file function reference and data-flow diagrams |
| [`GUIDE/TO_IMPLEMENT.md`](GUIDE/TO_IMPLEMENT.md) | Spec-gap audit and outstanding work |
