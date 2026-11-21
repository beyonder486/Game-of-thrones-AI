# Game of Thrones: AI Conquest

A turn-based 2.5D isometric grand-strategy game set in Westeros where three Great Houses — **House Stark**, **House Lannister**, and **House Targaryen** — compete for the **Iron Throne** through territorial expansion, economy management, stochastic combat, and emergent asynchronous diplomacy powered by **seven classical and modern AI algorithms**.

---

## Table of Contents
1. [Overview & Victory Conditions](#overview--victory-conditions)
2. [Critical Design Rules](#critical-design-rules)
3. [Map, Great Houses & Starting Balance](#map-great-houses--starting-balance)
4. [Mathematical Model of Economy & Supply](#mathematical-model-of-economy--supply)
5. [Mathematical Model of Combat & Casualties](#mathematical-model-of-combat--casualties)
6. [Diplomacy, Alliances, Trust & Betrayal](#diplomacy-alliances-trust--betrayal)
7. [The 7 AI Algorithms & Mathematical Formulations](#the-7-ai-algorithms--mathematical-formulations)
8. [Exact Turn & Round Pipeline](#exact-turn--round-pipeline)
9. [Algorithm Interaction Chains](#algorithm-interaction-chains)
10. [UI, Visuals, Dragons, Units & Audio](#ui-visuals-dragons-units--audio)
11. [Controls & Running the Game](#controls--running-the-game)
12. [Automated Verification Suite](#automated-verification-suite)
13. [Project Structure & Known Approximations](#project-structure--known-approximations)

---

## Overview & Victory Conditions

The continent of Westeros is modeled as a **21 × 8 offset hex grid** partitioned into **19 named territories (holds)** via Voronoi regions (`map.py`). Each territory provides:
- **Resource Value (`+Gold/turn`):** Added to its ruling house's base income every round.
- **Defense Bonus (`1` to `4`):** Fortification level protecting the territory during sieges.
- **Neutral Garrison (`2` to `10` armies):** Initial defending force when unclaimed.
- **Adjacency Graph (`Territory.neighbors`):** Derived strictly from physically touching hex regions on the map.

A house wins when **either** victory condition is met (checked after every combat and at the end of every round):
1. **Conquest of the Iron Throne:** Capture **King's Landing** (instant victory).
2. **Last House Standing:** Eliminate all rival houses (0 territories remaining).

**Randomized Turn Order:** At the start of every new game, `random.shuffle(self.houses)` randomizes the round order among Stark, Lannister, and Targaryen so no house enjoys a permanent first-mover advantage to King's Landing.

---

## Critical Design Rules

1. **One military action per house per turn:** Attack a territory, Betray + strike, or Hold fortifications.
2. **Asynchronous diplomatic proposals:** Sending an alliance proposal queues it in the receiver's inbox (`house.inbox`) and does **not** end the proposer's turn — the proposer still makes its military move that turn, and the receiver evaluates the offer on their next turn.
3. **Unilateral betrayal:** Breaking an alliance never requires consent.
4. **No resource or army sharing:** Allied houses remain strictly independent economically. Captured holds and plundered treasuries belong solely to the house that physically conquers them.
5. **Eliminated-house & 3-house minimum guards:** Eliminating a house immediately dissolves any alliance it held and purges every pending proposal to or from it (`diplomacy.purge_eliminated()`). Alliances cannot be proposed or formed once fewer than 3 houses remain alive.
6. **Clean AI separation of concerns:**
   - **Fuzzy Logic** outputs continuous desirability scores (`0.00–1.00`) *only* — never final decisions.
   - **MCTS** makes *all* final diplomatic decisions (using Fuzzy scores as UCT prior biases).
   - **Greedy** serves both as a standalone target heuristic and as the deterministic rollout opponent model inside MCTS (never random rollouts).
   - **Minimax + A\*** make *all* tactical military decisions (including deciding when to **Hold** — Hold is a combat decision, not a Fuzzy diplomacy output).

---

## Map, Great Houses & Starting Balance

| House | Starting Seat | Motto | Starting Gold | Starting Armies | Capital Resource | Capital Defense |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: |
| **House Stark** | Winterfell | *Winter Is Coming* | 60 | 14 | +9 | 3 |
| **House Lannister** | Casterly Rock | *Hear Me Roar* | 65 | 14 | +9 | 2 |
| **House Targaryen** | Dragonstone | *Fire and Blood* | 60 | 14 | +8 | 4 |
| **Iron Throne** | **King's Landing** *(Neutral)* | *Objective* | — | 10 *(Garrison)* | +15 | 3 |

- **Why King's Landing is `10` armies × `3` defense = `30` effective defense:**
  - High enough to block Turn 1–7 opening rushes when houses only field `14–22` armies.
  - Low enough that a strong mid/late-game house (`31+` armies) can storm the capital, producing a healthy mix of **Iron Throne victories (~80%)** and **Elimination victories (~20%)** rather than forcing pure attrition.
- **Why starting values are balanced (`14` armies each, `60–65` gold):**
  - Combined with shuffled turn order and Minimax near-tie variety, all three houses win roughly one-third of simulated AI vs AI matches (`~33% / 33% / 33%`).

---

## Mathematical Model of Economy & Supply

At the end of every round (`main.py:_end_of_round`), each surviving house executes income collection and automatic recruitment:

### 1. Turn Income

$$
\text{Income}(h) = B + \sum_{t \in T(h)} r(t)
$$

where $B = 10$ (`BASE_INCOME`) and $r(t)$ is each owned territory's `resource_value`.

### 2. Army Supply Cap & Recruitment

$$
\text{SupplyCap}(h) = 12 + 6 \cdot |T(h)|
$$

$$
\text{Recruits}(h) = \min\left(R_{\max}, \ \max\left(0, \ \left\lfloor \frac{\text{Gold}(h) - G_{\text{res}}}{C_{\text{army}}} \right\rfloor\right), \ \max\left(0, \ \text{SupplyCap}(h) - A(h)\right)\right)
$$

with constants (`constants.py`):
- $R_{\max} = 3$ armies/round (`MAX_RECRUITS_PER_TURN`)
- $G_{\text{res}} = 15$ Gold treasury reserve
- $C_{\text{army}} = 5$ Gold per army (`ARMY_COST`)

**Mathematical Rationale (Preventing the Infinite-Hold Exploit):**
- Without `SupplyCap`, a player could repeatedly click `HOLD TURN` on a single hold forever, accumulating unlimited armies to one-shot King's Landing without ever fighting.
- With $\text{SupplyCap} = 12 + 6|T|$, a 1-hold house caps at **18 armies** (well below King's Landing's `30` defense), forcing territorial expansion to field armies large enough to take the Iron Throne (at least 3–4 holds $\Rightarrow 30\text{–}36$ supply cap).
- **MCTS Rollout Parity:** The exact same reserve (`15G`), per-turn limit (`3`), and supply cap (`12 + 6|T|`) are enforced inside MCTS's `_Sim.economy()` so simulated diplomacy futures match live game physics.

---

## Mathematical Model of Combat & Casualties

All battles are resolved in [`combat.py`](combat.py).

### 1. Effective Defense Formula

$$
\text{EffectiveDefense}(d, b) = \begin{cases}
d \cdot b & \text{if territory is Neutral (garrison } d \in [2, 10]\text{)} \\
d \cdot (1 + 0.05 \cdot b) & \text{if territory is owned by a rival Great House}
\end{cases}
$$

**Mathematical Rationale (Preventing Rival Standoffs):**
- Neutral garrisons are small static forces (`2–10` armies), so multiplying by full `defense_bonus` (`1×–4×`) creates realistic fortress thresholds (e.g., King's Landing $= 10 \times 3 = 30$).
- Great Houses defend with their **entire army pool** (`14–40` armies). Multiplying a full rival army pool by `2×–4×` made house-vs-house attacks mathematically unwinnable in Minimax, freezing all 3 houses into passive `Hold` standoffs.
- Scaling rival Great House fortifications to $(1 + 0.05b)$ (`+5%` to `+20%`) preserves the defensive edge of fortified holds while ensuring any house with a `10–15%` troop lead actively invades its neighbor.

### 2. Stochastic Combat Resolution

$$
P_{\text{att}} = A_{\text{att}} \cdot U_{\text{att}}, \qquad P_{\text{def}} = \text{EffectiveDefense}(A_{\text{def}}, b) \cdot U_{\text{def}}
$$

where $U_{\text{att}}, U_{\text{def}} \stackrel{\text{i.i.d.}}{\sim} \text{Uniform}(0.80, 1.20)$.

| Outcome | Condition | Attacker Losses | Defender Losses | Territory & Treasury |
| :--- | :---: | :---: | :---: | :--- |
| **Attacker Wins** | $P_{\text{att}} > P_{\text{def}}$ | $\lfloor 0.50 \cdot A_{\text{def}} \rfloor$ | $\lfloor 0.80 \cdot A_{\text{def}} \rfloor$ | Territory transfers to attacker. If defender has `0` holds left, attacker plunders all remaining defender gold. |
| **Defender Holds** | $P_{\text{att}} \le P_{\text{def}}$ | $\lfloor 0.60 \cdot A_{\text{att}} \rfloor$ | $\lfloor 0.20 \cdot A_{\text{def}} \rfloor$ | Territory remains with defender. |

Both sides' surviving armies are clamped to $\max(1, A - \text{losses})$.

### 3. Win-Probability Thresholds

- **Expected-Value Threshold (>50% win odds, used by deterministic Minimax):**

$$
A_{\text{att}} > \text{EffectiveDefense}(A_{\text{def}}, b)
$$

  Because $\mathbb{E}[U] = 1.0$ and the distribution is symmetric, beating `EffectiveDefense` means strictly better than 50/50 odds.

- **100% Guaranteed Victory Threshold (worst-case RNG):**

$$
0.80 \cdot A_{\text{att}} > 1.20 \cdot \text{EffectiveDefense} \iff A_{\text{att}} > 1.50 \cdot \text{EffectiveDefense}
$$

  *(Example: Neutral King's Landing has effective defense `30`, so `31+` armies give >50% odds and `46+` armies guarantee capture regardless of dice rolls.)*

---

## Diplomacy, Alliances, Trust & Betrayal

Managed by [`diplomacy.py`](diplomacy.py) and each house's `inbox` (`house.py`).

### Pairwise Trust Matrix
- Every pair of houses starts at $\text{Trust}(h_1, h_2) = 50.0 \in [0, 100]$.
- **Alliance Kept (end of round):** $\text{Trust} \leftarrow \min(100, \text{Trust} + 5)$ (`ALLY_BONUS = +5`).
- **Betrayal:** $\text{Trust} \leftarrow \max(0, \text{Trust} - 30)$ (`BETRAYAL_PENALTY = -30`).

### What an Active Alliance Does
1. **Strict Non-Aggression:** Active allies are placed in `my_forbidden` inside Minimax, so an allied AI **never** attacks its ally without first choosing MCTS betrayal (even if completely boxed in by ally holds, it chooses `Hold`).
2. **Coordinated Targeting:** Both allies focus their separate turns on neutral holds and the 3rd house.
3. **Immediate Paranoid Mode Sync:** `form_alliance()` immediately flips **all surviving houses** (both allies *and* the lone 3rd house) to `PARANOID` Minimax; `dissolve_alliance()` resets all houses to `DECOMPOSED` once no alliance remains.
4. **Trust Growth:** `+5` bilateral trust each round the pact holds.
5. **No Resource/Army Sharing:** Economies and conquests remain strictly separate.

### Three Betrayal Paths (All Apply `-30` Trust & Raven's Log Entry)
1. **Explicit Betrayal:** AI MCTS chooses `"betray"`, or Human clicks **`BETRAY <ALLY>`** — dissolves the pact and launches an immediate strike on the same turn.
2. **Direct Attack on Ally (Human):** Clicking an allied territory in `_execute_attack()` automatically triggers `break_alliance()` before combat resolves.
3. **Automatic Betrayal on Ally Switch:** Accepting an alliance with House C while already allied with House B inside `form_alliance()` automatically betrays House B (`-30` trust and logs `"betrayed B to ally with C"`).

### Post-Elimination Hygiene
When any house reaches `0` holds, `diplomacy.purge_eliminated(defender)` immediately dissolves any alliance involving it and clears all pending proposals sent **to or from** it across every inbox. Once `< 3` houses remain, new proposals and alliances are disabled.

---

## The 7 AI Algorithms & Mathematical Formulations

### 1. Breadth-First Search (BFS) — [`algorithms/bfs.py`](algorithms/bfs.py)
- `get_reachable(game_map, start, n_steps=2) -> set[Territory]`
- Unweighted shortest-hop graph traversal computing all holds reachable within `n` marches. Persisted each turn on `house.reachable_holds`.

### 2. Depth-First Search (DFS) — [`algorithms/dfs.py`](algorithms/dfs.py)
- `get_expansion_paths(game_map, start, depth_limit=3) -> list[list[Territory]]`
- Cycle-free backtracking search cataloging all simple corridors up to depth `3` into neutral or weakly defended (`defense_bonus < 2`) regions. Persisted each turn on `house.expansion_paths`.

### 3. Greedy Heuristic Search — [`algorithms/greedy.py`](algorithms/greedy.py)
- `greedy_pick(candidates)` and `get_greedy_move(house, game_map, enemies)`
- Selection rule:

$$
t^{\ast} = \arg\max_{t \in \text{Candidates}} \bigl(r(t) - b(t), \ \mathbb{I}[t = \text{King's Landing}]\bigr)
$$

- **Dual Role:** Standalone tactical baseline AND the deterministic rollout policy inside MCTS (`algorithms/mcts.py` imports `greedy_pick` directly so rollouts never play randomly).

### 4. A\* Pathfinding — [`algorithms/astar.py`](algorithms/astar.py)
- `get_path(game_map, start, goal) -> list[Territory]`
- Minimizes total fortification risk along multi-hop routes:

$$
f(n) = g(n) + h(n), \qquad g(n) = \sum_{t \in \text{path}(s \to n) \setminus \{s\}} b(t), \qquad h(n) = d_{\text{hex}}(n, \text{goal})
$$

  where $d_{\text{hex}}$ is cube-coordinate hex distance (`map.py:hex_distance`).
- **Dual Role:**
  1. **AI Minimax Guidance:** `_throne_path_costs()` caches the A\* defense cost from every territory to `KING'S LANDING`, rewarding AI moves that advance along the lowest-defense A\* corridor.
  2. **Human Multi-Turn Routing:** Clicking a distant non-adjacent territory plots the A\* path and automatically marches 1 step across the first border crossing.

### 5. Mamdani Fuzzy Logic — [`algorithms/fuzzy_diplomacy.py`](algorithms/fuzzy_diplomacy.py)
- `evaluate_diplomacy(enemy_strength, own_weakness, trust_history) -> dict[str, float]`
- **Triangular Membership Functions (`trimf`) over $[0, 100]$:**

$$
\text{LOW} = (0, 0, 60), \qquad \text{MEDIUM} = (20, 50, 80), \qquad \text{HIGH} = (40, 100, 100)
$$

- **6 Mamdani Inference Rules** (min-implication, max-aggregation, centroid defuzzification; `scikit-fuzzy` with pure-NumPy fallback):
  1. $\text{Enemy HIGH} \land \text{Weakness HIGH} \Rightarrow \text{Alliance HIGH}$
  2. $\text{Trust LOW} \land \text{Enemy MEDIUM} \Rightarrow \text{Alliance LOW}$
  3. $\text{Weakness LOW} \land \text{Enemy LOW} \Rightarrow \text{Betrayal HIGH}$
  4. $\text{Weakness LOW} \land \text{Trust HIGH} \Rightarrow \text{Solo HIGH}$
  5. $\text{Enemy HIGH} \land \text{Trust HIGH} \Rightarrow \text{Alliance MEDIUM}$
  6. $\text{Trust LOW} \Rightarrow \text{Betrayal MEDIUM}$
- **Military Scaling:**

$$
S_{\text{scaled}}(h) = \text{clip}\left(2.5 \cdot \left(A(h) + \sum_{t \in T(h)} b(t)\right), \ 0, \ 100\right), \qquad \text{Weakness}(h) = 100 - S_{\text{scaled}}(h)
$$

- **Two Contexts:**
  - **Context A (Own Diplomacy):** `enemy_strength` = combined surviving rivals; `trust` = mean trust toward rivals.
  - **Context B (Incoming Proposal):** `enemy_strength` = **3rd (common enemy) house's strength** when alive (so two weaker houses accurately perceive the dominant 3rd house's threat and form coalitions); `trust` = trust toward the proposer.
- Outputs `{"alliance", "betrayal", "solo"}` in $[0, 1]$ as prior biases for MCTS — **never** makes final decisions directly.

### 6. Minimax with Alpha-Beta Pruning — [`algorithms/minimax.py`](algorithms/minimax.py)
- `get_move_scores(...) -> dict[str | None, float]` and `get_best_move(...) -> Territory | None`
- Depth limit: `MINIMAX_DEPTH = 3`, with Alpha-Beta pruning and expected-value combat (`U = 1.0`).
- **Board Evaluation Function (`_evaluate_state`):**

$$
V(s, h) = 2 \sum_{t \in T(h)} \bigl(r(t) + b(t)\bigr) + 1.5 A(h) + 0.5 G(h) + 500 \mathbb{I}[\text{KL} \in T(h)] + 1.5 \max\bigl(0, \ 12 - C_{\text{throne}}(h)\bigr) - \sum_{e \in E} \left(\sum_{t \in T(e)} r(t) + 1.5 A(e)\right)
$$

  where $C_{\text{throne}}(h) = \min_{t \in T(h)} \text{cost}_{\text{Astar}}(t \to \text{King's Landing})$.
- **Two Modes:**
  - **Decomposed Mode** (no active alliance): weighted sum of independent 1v1 Minimax searches:

$$
V_{\text{decomp}}(m) = \sum_{e \in E} \frac{S(e)}{\sum_{e' \in E} S(e')} \cdot \text{Minimax}_{1\text{v}1}(h \text{ vs. } e; \ m)
$$

  - **Paranoid Mode** (any active alliance): merges opposing houses into a single minimizing coalition that never attacks itself.
- **Candidate Pruning (`_moves`):** Excludes owned holds, active ally holds (`my_forbidden`), rival House holds when $A(h) < 5$ (`MIN_ATTACK_ARMIES`), and `KING'S LANDING` when $A(h) < \text{EffectiveDefense}(\text{KL})$.
- **Opening Variety (`_pick`):** Randomly breaks ties among top attacks within `2.0` points of optimal so AI matches explore diverse borders.
- **Human Hover Preview:** `get_move_scores()` computes scores for every valid adjacent hold plus `None` (`Hold`) and displays `Minimax: +XX.X · BEST` vs. `Hold` directly inside the map hover tooltip.

### 7. Monte Carlo Tree Search (UCT) — [`algorithms/mcts.py`](algorithms/mcts.py)
- Context A: `get_diplomacy_decision(...) -> ("propose_alliance" | "betray" | "solo", target)`
- Context B: `get_proposal_response(...) -> "accept" | "reject"`
- Hyperparameters: `MCTS_ITER = 500`, `MCTS_ROLLOUT_DEPTH = 10`, `UCT_C = 1.414`, `REWARD_SCALE = 100.0`.
- **Fuzzy-Biased UCT Formula:**

$$
\text{UCT}(a) = \frac{Q(a)}{N(a)} + c\sqrt{\frac{\ln N_{\text{parent}}}{N(a)}} + \text{FuzzyBias}(a), \qquad c = 1.414
$$

  - Context A biases: `propose_alliance` $\leftarrow$ `alliance`, `betray` $\leftarrow$ `betrayal`, `solo` $\leftarrow$ `solo`. Partner choice maximizes `(trust, -military_strength)`, preferring the weaker rival on equal trust so two weaker houses unite against the leader.
  - Context B biases: `accept` $\leftarrow$ `alliance`, `reject` $\leftarrow \max(\text{betrayal}, \text{solo})$.
- **Stochastic Rollouts (`_Sim` + `_rollout`):**
  - All houses act with `greedy_pick()` under full live combat RNG (`Uniform(0.80, 1.20)`), `effective_defense`, `>= 1` army floor, King's Landing threshold guard, and exact supply-capped economy.
  - **Per-Turn Alliance Breakdown:** For each rollout step $k > 0$, an active pact breaks with probability

$$
p_{\text{break}} = 0.25 \cdot \left(1 - \frac{\text{trust}}{100}\right)
$$

    adding $+10.0$ risk penalty if it collapses (betraying first incurs $+30.0$ risk).
- **Prioritized Rollout Reward:**

$$
R = \begin{cases}
\dfrac{1000}{100} = 10.0 & \text{if Iron Throne captured by self} \\
0.0 & \text{if self eliminated} \\
\dfrac{\max(0, \ 0.5 T_{\text{val}} + 0.3 S_{\text{mil}} + 0.2 G_{\text{val}} - 0.4 \text{Risk})}{100} & \text{otherwise (halved if rival takes Throne)}
\end{cases}
$$

---

## Exact Turn & Round Pipeline

Each round steps through all surviving houses in the shuffled turn order:

1. **If `house.inbox` has a pending proposal (from a surviving proposer):**
   - `Fuzzy Logic (Context B)` $\rightarrow$ `MCTS (Context B)` $\rightarrow$ `Accept` (form alliance, switch all houses to `PARANOID`) or `Reject`
   - `BFS / DFS` (update `reachable_holds` & `expansion_paths`)
   - `Minimax` (Alpha-Beta + A\* throne-corridor bonus) $\rightarrow$ `A*` route $\rightarrow$ `Combat`
2. **Else (no pending proposal):**
   - `BFS / DFS` $\rightarrow$ `Fuzzy Logic (Context A)` $\rightarrow$ `MCTS (Context A)`
   - If `propose_alliance`: queue in `target.inbox` (proposer still attacks/holds this turn)
   - If `betray`: break pact (`-30` trust), strike former ally immediately via Minimax
   - `Minimax` $\rightarrow$ `A*` route $\rightarrow$ `Combat`
3. **End of Round (after all houses act):**
   - Collect income $\rightarrow$ Recruit armies (respecting `15G` reserve, `MAX_RECRUITS_PER_TURN = 3`, and `SupplyCap = 12 + 6|T|`) $\rightarrow$ Add `+5` trust to surviving alliances $\rightarrow$ Refresh Context A Fuzzy scores $\rightarrow$ Check win conditions $\rightarrow$ Increment Turn.

---

## Algorithm Interaction Chains

```text
Chain 1 (Own Diplomacy):
  Fuzzy(Context A) ──► UCT bias ──► MCTS(Context A, Greedy rollouts)
                                      ├── propose_alliance ──► target.inbox (next turn)
                                      ├── betray           ──► -30 trust + immediate Minimax strike
                                      └── solo             ──► continue normally

Chain 2 (Incoming Proposal):
  Fuzzy(Context B, 3rd-house threat) ──► UCT bias ──► MCTS(Context B)
                                                        ├── accept ──► Alliance active + PARANOID Minimax
                                                        └── reject ──► Clear inbox + log

Chain 3 (Military & Conquest):
  BFS/DFS (reachability) + A* (throne-corridor cost)
      ──► Minimax (Decomposed / Paranoid, Alpha-Beta)
      ──► A* (first border crossing)
      ──► Combat (effective_defense + Uniform(0.80, 1.20) casualties)
      ──► Elimination check & purge_eliminated()
```

---

## UI, Visuals, Dragons, Units & Audio

- **Top Realm Bar:** Live Gold, Armies, Holds for all 3 houses, Turn counter, and Mode indicator.
- **Collapsible `FUZZY [H]` Drawer (Pairwise Fuzzy Diplomacy Intelligence):**
  - Clickable **`STARK` | `LANNISTER` | `TARGARYEN`** tabs to inspect any house's live perspective.
  - Displays pairwise **`ALLIANCE`** & **`BETRAYAL`** bars + exact Fuzzy inputs (`Trust`, 3rd-house `Threat`, `Weakness`) against each of the other two houses, plus the house's general **`SOLO WAR`** bar at the bottom.
- **Collapsible `RAVEN LOG [L]` Drawer:** Chronological feed of every AI algorithm move, battle outcome, alliance proposal, acceptance, rejection, and betrayal.
- **Live Minimax Hover Tooltip:** During Human turns, hovering any valid adjacent territory displays its exact `Minimax: +XX.X` score (`BEST` highlighted in green) compared directly against `Hold`.
- **Animated House Dragons & 6-Layer Fire-Breathing VFX:**
  - **House Stark:** Custom **Frost Dragon** (`assets/units/dragon_stark_flap.png`, 8-frame wingbeat cycle) breathing **blue-white Frostfire**.
  - **House Lannister:** Custom **Golden Dragon** (`assets/units/dragon_lannister_flap.png`, 8-frame wingbeat cycle) breathing **molten Golden Flame**.
  - **House Targaryen:** **Valyrian Red Dragon** (`reddragonfly.png`–`reddragonfly4.png`, 4-direction sprite sheets) breathing **crimson-orange Dragonfire**.
  - All 3 dragons patrol their capitals with periodic fire bursts and swoop high over battles (`altitude 66–74px`) unleashing a 6-layer volumetric flame cone, rolling fireballs, mouth flash, ground blaze tongues, smoke/mist, and streaking sparks.
- **Animated Ground Armies:**
  - **Stark & Lannister attackers:** `Medieval Warrior Pack` (3 front-line warriors).
  - **Targaryen attackers & defenders:** Mixed 4-unit formation — `2` front-line Medieval Warriors + `2` flanking `EVil Wizard 2` units positioned cleanly outside the dragon's silhouette.
  - **Opposing / Neutral defenders:** `Hero Knight` squad (`Run`, `Attack1`, `Attack2`, `Idle`, `Hurt`, `Death`).
- **Dual-Channel Battle Audio & Ducking Background Music:**
  - **Battle SFX (always active):** Sword-fight audio (`dragon-studio-sword-fight-393849.mp3`) triggers at 30% battle progress; dragon fireball whoosh (`floraphonic-fireball-whoosh-5-179129.mp3`) ignites at 34%; both fade out cleanly at 80%.
  - **Background Music (`Lament of the War - MP3 Preview.mp3`):** **Disabled by default**; toggleable anytime via the top-right **`MUSIC: OFF / ON`** button or **`M`** key. When enabled, it smoothly ducks from `0.42` down to `0.12` during sword/dragon clashes and swells back afterward. Battle SFX are never disabled by the music toggle.

---

## Controls & Running the Game

### Requirements
- Python 3.10+
- `pygame`, `numpy`, `Pillow` *(optional: `scikit-fuzzy` — pure-NumPy Mamdani fallback is built in)*

### Launch
```bash
python main.py
```

### Controls & Shortcuts
| Input | Action |
| :--- | :--- |
| **Click Territory** *(Human turn)* | Attack adjacent hold directly, or march 1 step along A\* route toward a distant hold |
| **`ALLY <HOUSE>` / `BETRAY` / `HOLD TURN`** | Queue alliance proposal (does not end turn), betray & strike, or fortify & pass |
| **`ACCEPT` / `REJECT`** | Respond to an incoming alliance proposal in your inbox |
| **`ADVANCE TURN >>` / `SPACE` / `ENTER` / `→`** | Step turns in AI vs AI mode (or dismiss victory modal) |
| **`H`** or **`FUZZY [H]`** | Toggle Fuzzy Diplomacy Intelligence drawer |
| **`L`** or **`RAVEN LOG [L]`** | Toggle chronological Raven's Log drawer |
| **`M`** or **`MUSIC: OFF/ON`** | Toggle background music ON/OFF *(sword & dragon SFX stay active)* |
| **`F11`** | Toggle fullscreen |
| **`ESC`** | Close victory modal / return to startup menu / exit |

---

## Automated Verification Suite

Run the standalone verification & demo script to prove all 7 AI algorithms, game-logic invariants, and multi-game AI balance in one command:

```bash
python test_algorithms.py
```

Checks verified:
1. **BFS:** Reachability at depth 1 (`5` holds) and depth 2 (`12` holds including King's Landing).
2. **DFS:** Cycle-free expansion corridors (`64` valid simple paths at depth 3 from Winterfell).
3. **Greedy:** Maximizes `resource_value - defense_bonus` (`RIVERRUN` from Winterfell).
4. **A\*:** Optimal defense-weighted route with `hex_distance` heuristic (`WINTERFELL -> THE TWINS -> KING'S LANDING`, cost `6`, hex distance `5`).
5. **Mamdani Fuzzy Logic:** Extreme threat/weakness/trust responses across Context A & Context B.
6. **Minimax + A\* Corridor & Alliance Modes:** Decomposed/Paranoid switching across all 3 houses, A\* throne-cost cache, and automatic `-30` betrayal when switching allies.
7. **MCTS (UCT) & `_Sim` Parity:** Context A & B decisions, supply cap enforcement, King's Landing threshold guard, and `>= 1` army floor.
8. **Game-Logic Invariants:** `effective_defense`, human ally+move turn rule, supply cap (`18/18` on 1 hold), BFS/DFS persistence, and eliminated-house proposal purging.
9. **Multi-Game Headless AI vs AI Simulation:** Confirms all 3 houses win competitively, both Iron Throne and Elimination wins occur, active house-vs-house border wars take place, and zero runtime errors occur.

---

## Project Structure & Known Approximations

```text
├── main.py                      # Entry point, DPI setup, GameController, audio/ducking & main loop
├── constants.py                 # Window/hex geometry, palette, economy & AI hyperparameters
├── map.py                       # 19 Westeros holds, Voronoi adjacency graph, terrain & hex_distance
├── house.py                     # House state (gold, armies, territories, inbox, fuzzy/BFS/DFS telemetry)
├── diplomacy.py                 # Alliances, trust matrix, async inbox, betrayal & purge_eliminated
├── combat.py                    # effective_defense, stochastic combat resolution & elimination plunder
├── renderer.py                  # 2.5D isometric renderer, dragons/6-layer fire VFX, units, HUD & tooltips
├── test_algorithms.py           # Automated 9-check algorithm & invariant verification suite
├── instructions.txt             # Complete mechanics & AI architecture specification
├── algorithms/
│   ├── bfs.py                   # Breadth-First Search reachability
│   ├── dfs.py                   # Depth-First Search expansion corridors
│   ├── greedy.py                # Greedy target heuristic & MCTS rollout opponent model
│   ├── astar.py                 # A* defense-weighted pathfinding with hex_distance heuristic
│   ├── fuzzy_diplomacy.py       # Mamdani Fuzzy Logic (Context A & Context B)
│   ├── minimax.py               # Alpha-Beta Minimax (Decomposed & Paranoid + A* corridor bonus)
│   └── mcts.py                  # UCT Monte Carlo Tree Search diplomacy engine
└── assets/
    ├── buildings/               # 2.5D isometric castle & landmark sprites
    ├── sounds/                  # Sword fight SFX, dragon fireball SFX & looping background score
    ├── tiles/                   # Seamless isometric terrain tiles
    ├── ui/                      # HUD icons, crests, Evil Wizard 2, Hero Knight, Medieval Warrior Pack & Red Dragon sheets
    └── units/                   # Frost Dragon & Golden Dragon RGBA sprites + 8-frame wingbeat sheets
```

### Documented AI Approximations
1. **Decomposed Minimax:** Evaluates unallied opponents independently via military-strength-weighted sums, which can underestimate incidental coordination between two unallied rivals.
2. **Paranoid Minimax:** Assumes full coalition cooperation while an alliance holds; future pact breakdown is modeled instead by MCTS rollouts.
3. **Deterministic Expected-Value Combat inside Minimax:** Replaces `Uniform(0.80, 1.20)` with its expectation `1.0` to keep depth-3 Alpha-Beta search instantaneous, while live combat and MCTS rollouts sample the true stochastic rolls.
