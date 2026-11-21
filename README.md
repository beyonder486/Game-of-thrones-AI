# Game of Thrones: AI Conquest

A turn-based 2.5D isometric strategy game set in Westeros where three Great Houses — **House Stark**, **House Lannister**, and **House Targaryen** — compete for the **Iron Throne** through territorial conquest, economy management, battle tactics, and political diplomacy powered by **7 Artificial Intelligence (AI) algorithms**.

---

## Table of Contents
1. [Quick Glossary (Terms & Symbols Explained)](#quick-glossary-terms--symbols-explained)
2. [How the Game Works & How to Win](#how-the-game-works--how-to-win)
3. [The Map, Great Houses & Starting Stats](#the-map-great-houses--starting-stats)
4. [Economy, Recruitment & Supply Cap (With Math)](#economy-recruitment--supply-cap-with-math)
5. [Combat & Casualties (With Math & Examples)](#combat--casualties-with-math--examples)
6. [Diplomacy, Alliances, Trust & Betrayal](#diplomacy-alliances-trust--betrayal)
7. [The 7 AI Algorithms Explained Simply (With Formulas)](#the-7-ai-algorithms-explained-simply-with-formulas)
8. [Step-by-Step Turn Flow](#step-by-step-turn-flow)
9. [How All 7 Algorithms Connect Together](#how-all-7-algorithms-connect-together)
10. [Visuals, Dragons, Armies, Audio & Controls](#visuals-dragons-armies-audio--controls)
11. [How to Run & Verify the Game](#how-to-run--verify-the-game)
12. [Project File Map](#project-file-map)

---

## Quick Glossary (Terms & Symbols Explained)

Before diving into the rules and equations, here is what every game and AI term means in plain English:

### Game Terms
- **Hold / Territory:** One of the 19 castles/regions on the map (e.g., *Winterfell*, *The Twins*, *King's Landing*).
- **Hex Grid & Voronoi Region:** The map is made of hexagonal tiles (`21 × 8`). Every land tile automatically belongs to whichever castle is closest to it (called a *Voronoi region*). Two castles are considered **neighbors** if and only if their colored tile regions physically touch.
- **Garrison:** The neutral defending soldiers guarding an unclaimed hold before any Great House captures it.
- **Resource Value (`+Gold`):** How much extra gold a hold pays its owner at the end of every round.
- **Defense Bonus (`1` to `4`):** How strongly fortified a hold is. Higher numbers make it harder to conquer.
- **Supply Cap:** The maximum number of armies a house is allowed to recruit, based on how many holds it owns.
- **Asynchronous Inbox:** A mailbox on each house (`house.inbox`) that holds incoming alliance offers. Sending an offer puts a letter in the other house's inbox so they answer on *their* next turn.
- **Unilateral Betrayal:** Breaking an alliance on your own without asking the other house's permission.

### AI Terms
- **BFS (Breadth-First Search):** A map search that explores outward ring by ring (1 step away, then 2 steps away) to find all holds within reach.
- **DFS (Depth-First Search):** A map search that follows one path deep to its end before backtracking, used to scout multi-step expansion routes.
- **Greedy Algorithm:** A simple, fast rule that always picks whichever single option looks best *right now*, without looking ahead.
- **A\* (A-Star) Pathfinding:** A smart shortest-path algorithm that finds the cheapest route from Castle A to Castle B using both actual cost traveled so far ($g$) and an estimated remaining distance called a **heuristic** ($h$).
- **Fuzzy Logic (Mamdani):** Instead of rigid `if/else` cutoffs (like "weak if armies < 10"), Fuzzy Logic rates inputs smoothly as degrees of **Low**, **Medium**, and **High** (e.g., "70% threatened and 60% weak") and blends rules into smooth scores from `0.00` to `1.00`. Converting those blended rules back into a single number is called **defuzzification**.
- **Minimax with Alpha-Beta Pruning:** A game-tree search that looks 3 turns ahead, assuming *your* house tries to **maximize** its score while enemies try to **minimize** your score. **Alpha-Beta Pruning** skips branches that cannot possibly beat a move already found, making it much faster with the exact same answer.
  - **Decomposed Minimax:** Used when no enemies are allied — evaluates each rival separately and blends the results.
  - **Paranoid Minimax:** Used when an alliance exists — assumes the two allied enemies coordinate as one single mega-enemy against the lone house.
- **MCTS (Monte Carlo Tree Search) & UCT:** Instead of checking every possible future move, MCTS plays out **500 fast simulated mini-games** (called **rollouts**) to see which diplomatic choice leads to the highest average score. **UCT (Upper Confidence Bound for Trees)** is the formula MCTS uses to balance trying promising options (*exploitation*) and testing less-explored options (*exploration*).

---

## How the Game Works & How to Win

### Two Game Modes
1. **AI vs AI (Observer Mode):** All 3 houses are played by AI. Click **`ADVANCE TURN >>`** (or press `SPACE` / `ENTER`) to watch the realm unfold one turn at a time.
2. **Human vs AI (Player Command):** You command one Great House (Stark, Lannister, or Targaryen) against two AI rivals.

### How a House Wins
A house wins immediately when **either** of these happens:
1. **Iron Throne Victory:** Capture **King's Landing** (instant win).
2. **Elimination Victory:** Be the last surviving house with at least 1 hold (both rival houses have 0 holds).

### Core Rules
- **Randomized Turn Order:** At the start of every new game, the order of Stark, Lannister, and Targaryen is shuffled randomly so no house always gets to move first.
- **One Military Move Per Turn:** Each house may only Attack one hold, Betray + strike, or Hold fortifications on its turn.
- **No Resource or Army Sharing:** Allied houses never combine armies or share gold. Whoever physically captures a hold gets that hold (and all remaining gold if they eliminate its last hold).
- **Clean AI Separation:**
  - **Fuzzy Logic** only produces scores (`0.00` to `1.00`) — it never makes the final choice.
  - **MCTS** makes all final **diplomacy** choices (propose alliance, accept, reject, betray, stay solo).
  - **Minimax + A\*** make all **military** choices (which hold to attack, or whether to **Hold**).

---

## The Map, Great Houses & Starting Stats

Westeros has **19 named holds** across a `21 × 8` hex map (`map.py`). Each Great House starts with 1 capital hold, balanced troops, and a starting treasury (`constants.py`):

| House | Starting Capital | Motto | Starting Gold | Starting Armies | Capital Income | Capital Defense |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: |
| **House Stark** | Winterfell | *Winter Is Coming* | 60 | 14 | +9 / round | 3 |
| **House Lannister** | Casterly Rock | *Hear Me Roar* | 65 | 14 | +9 / round | 2 |
| **House Targaryen** | Dragonstone | *Fire and Blood* | 60 | 14 | +8 / round | 4 |
| **Iron Throne** | **King's Landing** *(Neutral)* | *Win Objective* | — | 10 *(Neutral Garrison)* | +15 / round | 3 |

- The other 15 holds start neutral with `2–4` garrison troops and `1–3` defense.
- Every pair of houses starts with neutral trust: **`50 / 100`**.

**Why these numbers were chosen:**
- **King's Landing** has `10` neutral soldiers × `3` defense = **`30` effective defense**. That is high enough that nobody can rush it on Turns 1–7 (when armies are ~`14–22`), yet reachable in the mid/late game (`31+` armies), creating a balanced mix of **~80% Iron Throne victories** and **~20% Elimination victories**.
- Giving all 3 houses `14` starting armies and shuffling turn order ensures fair competition (`~33%` win rate each across simulated matches).

---

## Economy, Recruitment & Supply Cap (With Math)

At the end of every full round (after all surviving houses have acted), each surviving house collects gold and automatically recruits new troops (`main.py:_end_of_round`).

### 1. Gold Income Per Round
Every surviving house receives a base income of `10` gold plus the resource value of every hold it owns:

$$
\text{Income}(h) = 10 + \sum_{t \in T(h)} r(t)
$$

**What each symbol means:**
- $h$ = a Great House (Stark, Lannister, or Targaryen).
- $T(h)$ = the set of all holds currently owned by house $h$.
- $r(t)$ = the gold income (`resource_value`) of hold $t$.

*Example:* At Turn 1, Stark owns only Winterfell ($r = 9$), so Stark earns $10 + 9 = 19$ gold at the end of Round 1.

### 2. Army Supply Cap & Automatic Recruitment
To prevent an infinite-resource exploit (sitting on 1 castle pressing `HOLD TURN` forever until you have 100 troops), every house has an **Army Supply Cap** based on how many holds it owns:

$$
\text{SupplyCap}(h) = 12 + 6 \cdot |T(h)|
$$

Each round, a house automatically buys as many new troops as allowed by **three limits** (whichever is smallest):

$$
\text{Recruits}(h) = \min\left(3, \ \max\left(0, \ \left\lfloor \frac{\text{Gold}(h) - 15}{5} \right\rfloor\right), \ \max\left(0, \ \text{SupplyCap}(h) - A(h)\right)\right)
$$

**What each symbol means:**
- $|T(h)|$ = number of holds owned by house $h$.
- $A(h)$ = current number of armies house $h$ has.
- $\text{Gold}(h)$ = current gold treasury of house $h$.
- `3` = maximum troops any house can recruit in a single round (`MAX_RECRUITS_PER_TURN`).
- `15` = minimum gold reserve a house always keeps in its treasury.
- `5` = gold cost of 1 army (`ARMY_COST`).
- $\lfloor x \rfloor$ = round down to a whole number (cannot recruit half a soldier).

*Why this matters:* With 1 hold, $\text{SupplyCap} = 12 + 6(1) = 18$ armies — far below King's Landing's `30` defense. A house **must** conquer at least 3–4 holds ($\text{SupplyCap} = 30\text{–}36$) to build an army strong enough to take the Iron Throne.

---

## Combat & Casualties (With Math & Examples)

All battles are resolved in [`combat.py`](combat.py).

### 1. Effective Defense (Neutral Fortresses vs. Great Houses)
How strongly a territory defends depends on whether it is a small neutral garrison or a rival Great House:

$$
\text{EffectiveDefense}(d, b) = \begin{cases}
d \cdot b & \text{if the hold is Neutral} \\
d \cdot (1 + 0.05 \cdot b) & \text{if the hold belongs to a rival Great House}
\end{cases}
$$

**What each symbol means:**
- $d$ = defending army count (the neutral garrison size, or the rival house's army pool).
- $b$ = the territory's `defense_bonus` (`1` to `4`).

**Why two different formulas?**
- Neutral garrisons are tiny (`2–10` troops), so multiplying by full `defense_bonus` makes castles meaningfully tough (e.g., King's Landing $= 10 \times 3 = 30$).
- Rival Great Houses defend with their **entire army pool** (`14–40` troops). If you multiplied a rival's 25-troop army by `3`, it would have `75` defense — making rival wars impossible and causing all 3 houses to sit still! Using $+5\%$ per defense level (`1.05×` to `1.20×`) keeps fortifications valuable while letting houses with a `10–15%` troop lead actively invade neighbors.

### 2. Battle Outcome & Random Variance (`±20%`)
Every battle rolls a random battlefield luck factor between `0.80` (`-20%`) and `1.20` (`+20%`) for each side:

$$
P_{\text{att}} = A_{\text{att}} \cdot U_{\text{att}}, \qquad P_{\text{def}} = \text{EffectiveDefense}(A_{\text{def}}, b) \cdot U_{\text{def}}
$$

**What each symbol means:**
- $A_{\text{att}}$ = attacking house's army count.
- $A_{\text{def}}$ = defending garrison or rival house's army count.
- $U_{\text{att}}, U_{\text{def}}$ = two independent random decimal numbers chosen uniformly between `0.80` and `1.20`.
- $P_{\text{att}}, P_{\text{def}}$ = final battle power of attacker and defender for that clash.

| Result | Condition | Attacker Loses | Defender Loses | What Happens |
| :--- | :---: | :---: | :---: | :--- |
| **Attacker Wins** | $P_{\text{att}} > P_{\text{def}}$ | $\lfloor 0.50 \cdot A_{\text{def}} \rfloor$ | $\lfloor 0.80 \cdot A_{\text{def}} \rfloor$ | Attacker takes the hold. If defender now has `0` holds, attacker takes all defender's gold. |
| **Defender Holds** | $P_{\text{att}} \le P_{\text{def}}$ | $\lfloor 0.60 \cdot A_{\text{att}} \rfloor$ | $\lfloor 0.20 \cdot A_{\text{def}} \rfloor$ | Attacker is repelled; defender keeps the hold. |

Both sides' surviving armies never drop below `1` ($\max(1, \text{armies} - \text{losses})$).

### 3. Understanding Win Odds (Why a Good Move Can Still Be Repelled)
- **Better than 50/50 odds:** Whenever $A_{\text{att}} > \text{EffectiveDefense}$, the attacker is favored to win.
- **100% Guaranteed Win (even on worst possible luck):** Even if the attacker rolls the lowest possible `0.80` and the defender rolls the highest possible `1.20`, the attacker still wins if:

$$
0.80 \cdot A_{\text{att}} > 1.20 \cdot \text{EffectiveDefense} \iff A_{\text{att}} > 1.50 \cdot \text{EffectiveDefense}
$$

*Example (King's Landing, Effective Defense = 30):*
- Attacking with **31 armies** gives slightly over **50% chance** to capture the Iron Throne (can still be repelled on an unlucky roll).
- Attacking with **46+ armies** ($46 > 1.5 \times 30 = 45$) **guarantees** capture 100% of the time.

---

## Diplomacy, Alliances, Trust & Betrayal

Managed by [`diplomacy.py`](diplomacy.py) and `house.inbox` (`house.py`).

### Trust Score (`0` to `100`)
- Every pair of houses starts at **Trust = `50`**.
- **Alliance Kept:** Each full round an alliance survives adds **`+5` trust** (up to `100`).
- **Betrayal:** Betraying an ally subtracts **`-30` trust** (down to `0`).

### What an Active Alliance Actually Does
1. **Strict Non-Aggression:** An allied AI puts its ally on its forbidden list and **will never attack its ally** unless MCTS explicitly decides to betray first (even if boxed in with no other targets, it will choose `Hold`).
2. **Focus Against the 3rd House:** Both allies attack neutral holds and the 3rd house, hitting that 3rd house twice per round without worrying about their shared border.
3. **Switches All Houses to Paranoid Minimax:** The instant an alliance forms, all surviving houses (both allies *and* the lone 3rd house) switch from `DECOMPOSED` to `PARANOID` Minimax. When the alliance ends, all houses return to `DECOMPOSED`.
4. **Builds Trust:** `+5` trust each round.
5. **No Shared Gold or Armies:** Each house still fights with its own army on its own turn and keeps what it conquers.

### How an Alliance Forms (2-Turn Handshake)
- **Turn N (Proposer):** Sends a proposal to the target's inbox (`house.inbox`), then still makes its normal military move that turn.
- **Turn N+1 (Receiver):** Evaluates the offer (AI uses Context B Fuzzy + MCTS; Human clicks `ACCEPT` or `REJECT`).

### All 3 Ways Betrayal Happens (All Apply `-30` Trust & Log It)
1. **Explicit Betrayal:** AI MCTS chooses `"betray"`, or Human clicks `BETRAY <ALLY>` — breaks the pact and strikes the former ally immediately.
2. **Direct Attack (Human):** Clicking directly on your ally's hold automatically breaks the alliance as a betrayal right before combat begins.
3. **Switching Allies Automatically:** Accepting a new alliance with House C while already allied with House B automatically counts as betraying House B (`-30` trust and logs `"betrayed B to ally with C"`).

### Eliminated-House Guard
When a house loses its last hold (`0` holds), `diplomacy.purge_eliminated()` immediately cancels any pact it was in and deletes every pending proposal sent **to or from** it. Once only 2 houses remain alive, alliances are disabled (the last 2 rivals must fight for the throne).

---

## The 7 AI Algorithms Explained Simply (With Formulas)

### 1. Breadth-First Search (BFS) — [`algorithms/bfs.py`](algorithms/bfs.py)
- **Plain English:** Starts at a house's capital and checks all holds 1 step away, then 2 steps away, building a set of everything within quick striking range.
- **Function:** `get_reachable(game_map, start, n_steps=2)` — saved on `house.reachable_holds` every turn.

### 2. Depth-First Search (DFS) — [`algorithms/dfs.py`](algorithms/dfs.py)
- **Plain English:** Explores chains of up to 3 connected holds without revisiting any hold, scouting deep expansion corridors into neutral or weakly fortified (`defense_bonus < 2`) regions.
- **Function:** `get_expansion_paths(game_map, start, depth_limit=3)` — saved on `house.expansion_paths` every turn.

### 3. Greedy Search — [`algorithms/greedy.py`](algorithms/greedy.py)
- **Plain English:** Looks at all adjacent attackable holds and immediately picks the one with the highest net payoff (`gold income minus defense difficulty`), favoring King's Landing on ties.
- **Formula:**

$$
t^{\ast} = \arg\max_{t \in \text{Candidates}} \bigl(r(t) - b(t)\bigr)
$$

  **What each symbol means:**
  - $t^{\ast}$ = the chosen best territory.
  - $\text{Candidates}$ = all adjacent non-owned, non-ally holds.
  - $r(t)$ = gold income (`resource_value`) of hold $t$.
  - $b(t)$ = fortification level (`defense_bonus`) of hold $t$.
- **Why it matters:** Besides working standalone, `greedy_pick()` is used inside **MCTS rollouts** so every simulated future house plays smartly instead of making random moves.

### 4. A\* (A-Star) Pathfinding — [`algorithms/astar.py`](algorithms/astar.py)
- **Plain English:** Finds the **safest (lowest total defense) multi-turn route** between any two castles on the map.
- **Formula:**

$$
f(n) = g(n) + h(n), \qquad g(n) = \sum_{t \in \text{steps taken}} b(t), \qquad h(n) = d_{\text{hex}}(n, \text{goal})
$$

  **What each symbol means:**
  - $n$ = a territory currently being explored.
  - $g(n)$ = total `defense_bonus` accumulated along the route from start to $n$.
  - $h(n)$ = cube-coordinate hex distance (`map.py:hex_distance`) from $n$ to the goal castle (an estimate of remaining steps).
  - $f(n)$ = total estimated route cost; A\* always expands the lowest $f(n)$ first.
- **Where A\* is used in the game:**
  1. **Inside AI Minimax:** Minimax computes the A\* defense cost from every hold to `KING'S LANDING` and rewards AI moves that shorten that safest corridor to the Iron Throne.
  2. **For Human Clicks:** Clicking a distant (non-adjacent) castle automatically runs A\* and marches 1 border step along the safest route toward it.

### 5. Mamdani Fuzzy Logic — [`algorithms/fuzzy_diplomacy.py`](algorithms/fuzzy_diplomacy.py)
- **Plain English:** Measures how strongly a house *feels* about allying, betraying, or fighting solo — using smooth overlapping concepts (**Low**, **Medium**, **High**) instead of brittle cutoffs.
- **3 Inputs (all scaled from `0` to `100`):**
  1. `enemy_strength` — how strong the threat is.
  2. `own_weakness` — how vulnerable this house is (`100` minus its own scaled military strength, where raw military strength $= \text{armies} + \sum \text{defense bonus}$, scaled by $\times 2.5$ and capped at `100`).
  3. `trust_history` — bilateral trust score (`0` to `100`).
- **Triangular Membership Curves (`trimf`) over `0..100`:**
  - **LOW:** peaks at `0`, drops to zero at `60` — triangle $(0, 0, 60)$.
  - **MEDIUM:** rises from `20`, peaks at `50`, drops to zero at `80` — triangle $(20, 50, 80)$.
  - **HIGH:** rises from `40`, peaks at `100` — triangle $(40, 100, 100)$.
- **6 Linguistic Rules:**
  1. IF enemy is **HIGH** AND own weakness is **HIGH** → Alliance is **HIGH** *(weak house facing a giant wants an ally)*.
  2. IF trust is **LOW** AND enemy is **MEDIUM** → Alliance is **LOW** *(don't trust an unreliable partner)*.
  3. IF own weakness is **LOW** AND enemy is **LOW** → Betrayal is **HIGH** *(dominant house can stab its ally and win)*.
  4. IF own weakness is **LOW** AND trust is **HIGH** → Solo is **HIGH** *(strong enough to win alone without betraying)*.
  5. IF enemy is **HIGH** AND trust is **HIGH** → Alliance is **MEDIUM** *(trusted ally helps against strong threat)*.
  6. IF trust is **LOW** → Betrayal is **MEDIUM** *(low trust breeds paranoia)*.
- **Two Contexts:**
  - **Context A (Own Diplomacy):** `enemy_strength` = combined enemies; `trust` = average trust toward rivals.
  - **Context B (Incoming Proposal):** `enemy_strength` = the **3rd (common enemy) house's strength** (so two weaker houses recognize their shared giant enemy and accept an alliance against it); `trust` = trust toward the sender.
- **Output:** Smooth scores `{"alliance", "betrayal", "solo"}` between `0.00` and `1.00`, passed to MCTS as biases (Fuzzy Logic never makes the final yes/no choice by itself).

### 6. Minimax with Alpha-Beta Pruning — [`algorithms/minimax.py`](algorithms/minimax.py)
- **Plain English:** Looks **3 moves ahead** (`MINIMAX_DEPTH = 3`) to choose the best adjacent hold to attack — or **`Hold`** (`None`) if every attack would lose more than it gains. To stay fast, it uses expected-value combat (`luck = 1.0`, meaning any attack with `armies > EffectiveDefense` is predicted to win).
- **Board Score Formula (`_evaluate_state`):**

$$
V(s, h) = 2 \sum_{t \in T(h)} \bigl(r(t) + b(t)\bigr) + 1.5 A(h) + 0.5 G(h) + 500 I_{\text{KL}}(h) + 1.5 \max\bigl(0, \ 12 - C_{\text{throne}}(h)\bigr) - \sum_{e \in E} \left(\sum_{t \in T(e)} r(t) + 1.5 A(e)\right)
$$

  **What every symbol means:**
  - $V(s, h)$ = overall score of board state $s$ from house $h$'s point of view (higher is better).
  - $T(h)$ = holds owned by house $h$; $r(t)$ = hold's gold value; $b(t)$ = hold's defense bonus.
  - $A(h)$ = house $h$'s army count; $G(h)$ = house $h$'s gold treasury.
  - $I_{\text{KL}}(h)$ = `1` if house $h$ owns **King's Landing**, otherwise `0` (so capturing King's Landing adds a massive `+500` score).
  - $C_{\text{throne}}(h)$ = the shortest **A\* defense-cost path** from house $h$'s closest hold to King's Landing (moving closer to King's Landing increases this bonus!).
  - $E$ = the list of enemy houses; $T(e)$ and $A(e)$ = each enemy's holds and armies (subtracted so weakening enemies raises your score).
- **Two Search Modes:**
  - **Decomposed Mode (when no alliance exists):** Evaluates two separate 1v1 searches (Me vs. Enemy 1, Me vs. Enemy 2) and combines them weighted by how strong each enemy is:

$$
V_{\text{decomp}}(m) = \sum_{e \in E} \frac{S(e)}{S_{\text{total}}} \cdot \text{Minimax}_{1\text{v}1}(h \text{ vs. } e; \ m)
$$

    where $m$ is a candidate move, $S(e)$ is enemy $e$'s military strength, and $S_{\text{total}}$ is the sum of all enemy strengths.
  - **Paranoid Mode (when an alliance exists):** Merges opposing houses into one combined enemy team that never attacks itself and always picks the reply that hurts house $h$ the most.
- **Smart Safety Filters & Variety:**
  - Never attacks own holds or active ally holds.
  - Won't attack a rival Great House if below `5` armies (`MIN_ATTACK_ARMIES`).
  - Won't rush `KING'S LANDING` unless `armies >= EffectiveDefense` (`30` when neutral).
  - Randomly picks among top attacks within `2.0` score points of the best move so every AI game plays out uniquely instead of repeating the exact same map.
- **Human Hover Preview:** During your turn, hovering over any valid adjacent hold displays its exact Minimax score (`Minimax: +86.8 · BEST`) compared directly against `Hold`.

### 7. Monte Carlo Tree Search / UCT — [`algorithms/mcts.py`](algorithms/mcts.py)
- **Plain English:** Makes every AI **diplomatic decision** by running **500 fast 10-turn simulated futures** (`MCTS_ITER = 500`, `MCTS_ROLLOUT_DEPTH = 10`) where all houses play using the Greedy policy and real `±20%` combat rolls.
  - **Context A choices:** `propose_alliance`, `betray`, or `solo`. (When proposing, picks the highest-trust rival, breaking ties toward the *weaker* rival so two weaker houses team up against the leader.)
  - **Context B choices (answering an inbox offer):** `accept` or `reject`.
- **UCT Selection Formula (how MCTS picks which option to simulate next):**

$$
\text{UCT}(a) = \frac{Q(a)}{N(a)} + 1.414 \sqrt{\frac{\ln N_{\text{parent}}}{N(a)}} + \text{FuzzyBias}(a)
$$

  **What every symbol means:**
  - $a$ = a diplomatic action being tested (e.g., `accept` or `reject`).
  - $Q(a)$ = total reward accumulated across all simulations that tried action $a$.
  - $N(a)$ = number of times action $a$ has been simulated so far (so $Q(a) / N(a)$ is its average score).
  - $N_{\text{parent}}$ = total simulations run across all actions so far.
  - `1.414` = exploration constant (`UCT_C`, roughly $\sqrt{2}$), which encourages trying less-tested actions.
  - $\text{FuzzyBias}(a)$ = the score (`0.00–1.00`) from Fuzzy Logic (`propose_alliance` / `accept` use `alliance`; `betray` uses `betrayal`; `solo` uses `solo`; `reject` uses $\max(\text{betrayal}, \text{solo})$).
- **Alliance Breakdown in Simulations:** After the first simulated turn, an active alliance has a per-turn chance to collapse based on how low trust is:

$$
p_{\text{break}} = 0.25 \cdot \left(1 - \frac{\text{Trust}}{100}\right)
$$

  *(Example: at `Trust = 50`, there is a `12.5%` chance per simulated turn that the alliance falls apart, adding `+10` risk penalty; betraying first immediately adds `+30` risk penalty.)*
- **Simulation Score (Reward at the end of a 10-turn rollout):**

$$
R = \begin{cases}
10.0 & \text{if self captures King's Landing (1000 / 100)} \\
0.0 & \text{if self is eliminated} \\
\dfrac{\max(0, \ 0.5 T_{\text{val}} + 0.3 S_{\text{mil}} + 0.2 G_{\text{val}} - 0.4 \text{Risk})}{100} & \text{otherwise (halved if a rival takes King's Landing)}
\end{cases}
$$

  **What every symbol means:**
  - $T_{\text{val}}$ = total value of holds owned by self (`resource_value + defense_bonus`).
  - $S_{\text{mil}}$ = self's military strength (`armies + sum of owned defense bonuses`).
  - $G_{\text{val}}$ = self's gold treasury.
  - $\text{Risk}$ = accumulated alliance-breakdown or betrayal risk penalty.
  - Dividing by `100` (`REWARD_SCALE`) keeps simulation rewards on the same `~0–1` scale as the Fuzzy Bias and exploration term.

---

## Step-by-Step Turn Flow

Every round runs through all surviving houses in the shuffled turn order (`main.py`):

1. **If the house has a pending alliance offer in `house.inbox`:**
   - Run **Fuzzy Logic (Context B)** using the 3rd house's threat and trust toward the sender.
   - Run **MCTS (Context B)** to choose `accept` or `reject`.
   - If accepted: alliance activates and all surviving houses switch to `PARANOID` Minimax.
   - Run **BFS / DFS** reachability update → **Minimax** target choice → **A\*** route → **Combat**.
2. **If `house.inbox` is empty:**
   - Run **BFS / DFS** reachability update.
   - Run **Fuzzy Logic (Context A)** → **MCTS (Context A)** to choose `propose_alliance`, `betray`, or `solo`.
   - If `propose_alliance`: send offer to target's inbox (proposer still gets its military move this turn!).
   - If `betray`: break alliance (`-30` trust) and immediately attack the former ally.
   - Run **Minimax** target choice → **A\*** route → **Combat**.
3. **End of Round (after all houses act):**
   - Collect gold income → Recruit troops (capped by `15G` reserve, `3/turn`, and `SupplyCap`) → Add `+5` trust to surviving alliances → Refresh Fuzzy HUD scores → Check win conditions → Advance to next turn.

---

## How All 7 Algorithms Connect Together

```text
[1] Own Diplomacy (No Pending Offer):
    Fuzzy Logic (Context A) ──► prior bias ──► MCTS (Context A + Greedy rollouts)
                                                ├── propose_alliance ──► target.inbox
                                                ├── betray           ──► -30 trust + strike ally
                                                └── solo             ──► continue solo

[2] Answering an Incoming Offer:
    Fuzzy Logic (Context B, 3rd-house threat) ──► prior bias ──► MCTS (Context B)
                                                                   ├── accept ──► Alliance + PARANOID Minimax
                                                                   └── reject ──► Clear inbox

[3] Military Move & Battle:
    BFS / DFS (scouting) + A* (cheapest corridor to King's Landing)
        ──► Minimax (Decomposed or Paranoid, Alpha-Beta pruning)
        ──► A* (first border crossing when clicking distant holds)
        ──► Combat (EffectiveDefense + ±20% rolls + casualties)
        ──► Elimination check (plunder gold + purge dead house's diplomacy)
```

---

## Visuals, Dragons, Armies, Audio & Controls

- **Top Status Bar:** Shows Gold, Armies, Holds for all 3 houses, Turn number, and Mode.
- **`FUZZY [H]` Drawer (Pairwise Fuzzy Intelligence):** Click `STARK`, `LANNISTER`, or `TARGARYEN` tabs to inspect any house's live pairwise `ALLIANCE` and `BETRAYAL` scores (along with exact Trust, Threat, and Weakness inputs) against each rival, plus its general `SOLO WAR` bar.
- **`RAVEN LOG [L]` Drawer:** Chronological log of every AI move, battle result, proposal, acceptance, rejection, and betrayal.
- **Minimax Hover Preview:** Hover over any adjacent attackable hold on your turn to see its live `Minimax` score (`BEST` highlighted green) compared against `Hold`.
- **3 Flapping, Fire-Breathing House Dragons:**
  - **House Stark:** Custom 8-frame wing-flapping **Frost Dragon** breathing **blue-white Frostfire**.
  - **House Lannister:** Custom 8-frame wing-flapping **Golden Dragon** breathing **molten Golden Flame**.
  - **House Targaryen:** 4-direction **Valyrian Red Dragon** breathing **crimson Dragonfire**.
  - All 3 patrol their capitals with periodic fire bursts and swoop high overhead in battles (`altitude 66–74px`) with a 6-layer volumetric flame cone, rolling fireballs, mouth flash, burning ground tongues, smoke/frost mist, and streaking sparks.
- **Animated Ground Armies:**
  - **Stark & Lannister attackers:** 3 `Medieval Warrior Pack` fighters.
  - **Targaryen attackers & defenders:** Mixed squad of `2` front-line Medieval Warriors + `2` flanking `EVil Wizard 2` casters positioned cleanly outside the dragon.
  - **Opposing / Neutral defenders:** `Hero Knight` squad (`Run`, `Attack1`, `Attack2`, `Idle`, `Hurt`, `Death`).
- **Battle SFX & Toggleable Ducking Music:**
  - **Sword Fight** (`dragon-studio-sword-fight-393849.mp3`) and **Dragon Fireball** (`floraphonic-fireball-whoosh-5-179129.mp3`) play automatically in sync with every battle and are **always enabled**.
  - **Background Music** (`Lament of the War - MP3 Preview.mp3`) starts **OFF by default**. Click **`MUSIC: OFF`** (or press `M`) to turn it ON/OFF. When ON, it automatically **ducks (dims)** smoothly from `0.42` to `0.12` during sword/dragon clashes and swells back up afterward.

---

## How to Run & Verify the Game

### Requirements
- Python 3.10+
- `pygame`, `numpy`, `Pillow` *(optional: `scikit-fuzzy`; a pure-NumPy Mamdani implementation is built in)*

### Launch the Game
```bash
python main.py
```

### Controls
| Control | What It Does |
| :--- | :--- |
| **Click Territory** *(Human turn)* | Attack an adjacent hold, or march 1 step along the A\* path to a distant hold |
| **`ALLY <HOUSE>` / `BETRAY` / `HOLD TURN`** | Send proposal (doesn't end turn), betray & strike, or fortify & pass |
| **`ACCEPT` / `REJECT`** | Answer a pending alliance offer in your inbox |
| **`ADVANCE TURN >>` / `SPACE` / `ENTER` / `→`** | Advance one turn in AI vs AI mode (or close victory screen) |
| **`H`** or **`FUZZY [H]`** | Open/close the Fuzzy Diplomacy Intelligence drawer |
| **`L`** or **`RAVEN LOG [L]`** | Open/close the Raven's Log drawer |
| **`M`** or **`MUSIC: OFF/ON`** | Turn background music ON/OFF *(battle SFX stay active)* |
| **`F11`** | Toggle fullscreen |
| **`ESC`** | Close victory modal / return to startup menu / exit |

### Run the Automated Algorithm & Logic Verification Suite
To verify all 7 AI algorithms, game-logic rules, and a multi-game AI vs AI simulation in seconds (great for demos and grading):

```bash
python test_algorithms.py
```

It runs **9 automated checks**:
1. **BFS** reachability at depth 1 and depth 2.
2. **DFS** valid cycle-free expansion corridors at depth 3.
3. **Greedy** target selection maximizing `resource - defense`.
4. **A\*** lowest-defense route to King's Landing using `hex_distance`.
5. **Mamdani Fuzzy Logic** extreme scenarios for Context A & Context B.
6. **Minimax + A\* Corridor & Alliance Modes** (`DECOMPOSED` ↔ `PARANOID` sync across all 3 houses + automatic `-30` betrayal when switching allies).
7. **MCTS (UCT) & `_Sim` Parity** (Context A & B decisions, supply cap, King's Landing guard, `>= 1` army floor).
8. **Game-Logic Invariants** (`effective_defense`, human ally+move turn rule, supply cap on 1 hold, BFS/DFS telemetry, and eliminated-house proposal purging).
9. **8-Game Headless AI vs AI Simulation** confirming balanced winners, active house-vs-house wars, and clean game completion.

---

## Project File Map

```text
├── main.py                      # Entry point, GameController, turn loop, battle audio & music ducking
├── constants.py                 # Window/hex layout, colors, economy & AI settings
├── map.py                       # 19 Westeros holds, Voronoi neighbor graph, terrain & hex_distance
├── house.py                     # House state (gold, armies, holds, inbox, fuzzy/BFS/DFS data)
├── diplomacy.py                 # Alliances, trust scores, async inbox, betrayal & dead-house purge
├── combat.py                    # Effective defense, ±20% combat rolls, casualties & elimination loot
├── renderer.py                  # 2.5D map, 3 flapping dragons + fire VFX, ground units, HUD & tooltips
├── test_algorithms.py           # Automated 9-check verification & teacher demo script
├── instructions.txt             # Full technical specification of all mechanics and AI systems
├── algorithms/
│   ├── bfs.py                   # Breadth-First Search reachability
│   ├── dfs.py                   # Depth-First Search expansion corridors
│   ├── greedy.py                # Greedy target selection & MCTS rollout model
│   ├── astar.py                 # A* lowest-defense pathfinding with hex_distance heuristic
│   ├── fuzzy_diplomacy.py       # Mamdani Fuzzy Logic (Context A & Context B)
│   ├── minimax.py               # Alpha-Beta Minimax (Decomposed & Paranoid + A* corridor bonus)
│   └── mcts.py                  # UCT Monte Carlo Tree Search diplomacy engine
└── assets/
    ├── buildings/               # 2.5D isometric castle & landmark sprites
    ├── sounds/                  # Sword fight SFX, dragon fireball SFX & background music
    ├── tiles/                   # Seamless isometric terrain tiles
    ├── ui/                      # HUD icons, crests, Evil Wizard 2, Hero Knight, Medieval Warrior Pack & Red Dragon
    └── units/                   # Frost Dragon & Golden Dragon sprites + 8-frame wingbeat sheets
```

### Known AI Approximations
1. **Decomposed Minimax** evaluates unallied rivals independently via weighted averages, which may slightly underestimate accidental coordination between unallied houses.
2. **Paranoid Minimax** assumes full cooperation between allied rivals while the pact stands; possible future betrayals are handled by MCTS rollouts instead.
3. **Expected-Value Combat in Minimax** assumes average battle luck (`1.0`) so depth-3 search runs instantly, whereas real battles and MCTS rollouts roll `±20%` randomness.
