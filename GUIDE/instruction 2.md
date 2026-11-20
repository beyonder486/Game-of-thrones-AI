# Game of Thrones: AI Conquest — Mechanics Reference (Instruction 2)

Companion to [`instructions.md`](instructions.md). Where `instructions.md` says **what to build**,
this document is the **exact mechanics reference** for what was built.

**Every rule, formula and number below carries a `file:line` citation.** Nothing here is
descriptive hand-waving — if a value is stated, the line that defines it is named, so any claim can
be checked in seconds.

Spec gaps and deviations are tracked separately in [`TO_IMPLEMENT.md`](TO_IMPLEMENT.md).

---

## Table of Contents

- [0. Master constant table](#0-master-constant-table--where-every-number-lives)
- [1. Map data — every territory](#1-map-data--every-territory)
- [2. Combat — exact casualty arithmetic](#2-combat--exact-casualty-arithmetic)
- [3. Economy — income, recruitment, elimination](#3-economy--income-recruitment-elimination)
- [4. Attack legality — who can hit what](#4-attack-legality--who-can-hit-what)
- [5. BFS / DFS](#5-bfs--dfs)
- [6. A\*](#6-a)
- [7. Greedy](#7-greedy)
- [8. Fuzzy Logic](#8-fuzzy-logic)
- [9. Minimax](#9-minimax)
- [10. MCTS](#10-mcts)
- [11. Diplomacy](#11-diplomacy)
- [12. Turn pipeline](#12-turn-pipeline--exact-call-order)
- [13. Win / elimination conditions](#13-win--elimination-conditions)
- [14. Worked example — King's Landing](#14-worked-example--kings-landing-with-exact-casualties)
- [15. Known approximations](#15-known-approximations)

---

## 0. Master constant table — where every number lives

Every tunable in the game, with its defining line. All in [`constants.py`](../constants.py).

### AI parameters

| Constant | Value | Line | Used by |
|---|---|---|---|
| `MINIMAX_DEPTH` | `3` | `constants.py:45` | `minimax.py:206`, `minimax.py:231` (default `depth` arg) |
| `MCTS_ITER` | `500` | `constants.py:46` | `mcts.py:200` — rollouts per decision |
| `MCTS_ROLLOUT_DEPTH` | `10` | `constants.py:47` | `mcts.py:158` — simulated turns per rollout |
| `UCT_C` | `1.414` | `constants.py:48` | `mcts.py:207` — exploration coefficient (≈√2) |
| `MIN_ATTACK_ARMIES` | `5` | `constants.py:51` | `minimax.py:93` **only** |

### Economy

| Constant | Value | Line | Used by |
|---|---|---|---|
| `BASE_INCOME` | `10` | `constants.py:49` | `house.py:50`, `mcts.py:121` |
| `ARMY_COST` | `5` | `constants.py:50` | `house.py:55`, `main.py:241`, `mcts.py:122` |
| `MAX_RECRUITS_PER_TURN` | `3` | `constants.py:52` | `main.py:241` |

### Diplomacy

| Constant | Value | Line | Used by |
|---|---|---|---|
| `BETRAYAL_PENALTY` | `-30` | `constants.py:53` | `diplomacy.py:87` |
| `ALLY_BONUS` | `+5` | `constants.py:54` | `diplomacy.py:89` |

### Iron Throne

| Constant | Value | Line | Used by |
|---|---|---|---|
| `IRON_THRONE` | `"KING'S LANDING"` | `constants.py:74` | `map.py` throne lookup |
| `THRONE_BONUS` | `500` | `constants.py:75` | `minimax.py:56` — Minimax evaluation only |
| `REWARD_THRONE` | `1000` | `constants.py:81` | `mcts.py:182` — MCTS reward only |

> **These are two different numbers for two different algorithms.** `500` is the Minimax
> evaluation bonus; `1000` is the MCTS terminal reward. Not a bug — they live on different scales.

### MCTS reward weights

| Constant | Value | Line | Term |
|---|---|---|---|
| `REWARD_TERRITORY` | `0.5` | `constants.py:82` | `mcts.py:137` |
| `REWARD_MILITARY` | `0.3` | `constants.py:83` | `mcts.py:138` |
| `REWARD_RESOURCE` | `0.2` | `constants.py:84` | `mcts.py:139` |
| `REWARD_ALLIANCE_RISK` | `-0.4` | `constants.py:85` | `mcts.py:140` (weight is **negative**) |
| `REWARD_SCALE` | `100.0` | `mcts.py:38` | divisor before UCT — **not** in `constants.py` |

### Starting values — `constants.py:57-66`

| House | Gold | Armies | Seat | Line |
|---|---|---|---|---|
| Stark | 60 | 14 | Winterfell | `constants.py:58`, `constants.py:63` |
| Lannister | 65 | 14 | Casterly Rock | `constants.py:59`, `constants.py:64` |
| Targaryen | 45 | 12 | Dragonstone | `constants.py:60`, `constants.py:65` |

> ⚠️ These **differ from `instructions.md`** (spec: 50/10, 70/15, 40/12). See `TO_IMPLEMENT.md` §A1.

### Hard-coded magic numbers *not* in `constants.py`

Worth knowing, because they cannot be tuned without editing logic:

| Value | Meaning | Line |
|---|---|---|
| `0.8 … 1.2` | combat randomness range | `combat.py:30-31`, `mcts.py:99-100` |
| `0.5 / 0.8` | win-case casualty fractions | `combat.py:34-35` |
| `0.6 / 0.2` | loss-case casualty fractions | `combat.py:38-39` |
| `1` | army floor — nobody drops below | `combat.py:42`, `combat.py:44`, `combat.py:46` |
| `15` | gold reserve kept back from recruiting | `main.py:241` |
| `2.5` | military-strength → 0–100 scaling factor | `main.py:36` |
| `2`, `1.5`, `0.5` | Minimax evaluation weights | `minimax.py:59-62` |
| `30.0 / 10.0 / 5.0` | alliance risk penalty components | `mcts.py:156`, `mcts.py:165`, `mcts.py:167` |
| `0.5` | reward multiplier when a rival takes the throne | `mcts.py:189` |
| `24` | Raven's Log entry cap | `diplomacy.py:143` |
| `2` | DFS "weakly defended" threshold (`defense_bonus < 2`) | `dfs.py:17` |

---

## 1. Map data — every territory

Defined in `TERRITORY_SPECS`, `map.py:62-80`. Tuple order (`map.py:63`):

```
(name, col, row, feature, resource_value, defense_bonus, armies, owner, is_iron_throne)
```

`armies` is the **neutral garrison**; house-owned seats are set to `0` because they are defended by
the owning house's army pool instead (`map.py:64`).

| Territory | Line | Resource | Defense | Garrison | Owner | **Effective defence** |
|---|---|---|---|---|---|---|
| The Wall | `map.py:65` | 4 | 3 | 3 | — | **9** |
| Castle Black | `map.py:66` | 5 | 2 | 2 | — | **4** |
| Dreadfort | `map.py:67` | 5 | 3 | 3 | — | **9** |
| Pyke | `map.py:68` | 4 | 2 | 3 | — | **6** |
| **Winterfell** | `map.py:69` | 9 | 3 | 0 | STARK | pool × 3 |
| Moat Cailin | `map.py:70` | 5 | 2 | 3 | — | **6** |
| White Harbor | `map.py:71` | 6 | 2 | 3 | — | **6** |
| The Eyrie | `map.py:72` | 6 | 3 | 3 | — | **9** |
| Lannisport | `map.py:73` | 5 | 2 | 3 | — | **6** |
| Riverrun | `map.py:74` | 5 | 2 | 4 | — | **8** |
| The Twins | `map.py:75` | 5 | 3 | 3 | — | **9** |
| **King's Landing** 👑 | `map.py:76` | 15 | 2 | 14 | — | **28** |
| **Harrenhal** | `map.py:77` | 4 | **1** | 4 | — | **4** ← softest |
| **Casterly Rock** | `map.py:78` | 9 | 2 | 0 | LANNISTER | pool × 2 |
| Oldtown | `map.py:79` | 6 | 2 | 3 | — | **6** |
| Highgarden | `map.py:80` | 6 | 2 | 4 | — | **8** |
| Dorne | `map.py:81` | 5 | 2 | 4 | — | **8** |
| Storm's End | `map.py:82` | 5 | 2 | 4 | — | **8** |
| **Dragonstone** | `map.py:83` | 6 | **4** | 0 | TARGARYEN | pool × 4 ← hardest |

**Effective defence = `garrison × defense_bonus`** — the quantity that actually resists an attack
(`combat.py:31`). It is the only number that matters when picking a target, and **the HUD never
shows it** (see `TO_IMPLEMENT.md` §C2).

### King's Landing adjacency — `map.py:102-117`

Six approaches: White Harbor, Moat Cailin, The Eyrie, Harrenhal, Dorne, Storm's End.

### `Territory` attributes — `map.py:10-34`

`name`, `col`, `row`, `feature`, `resource_value`, `defense_bonus`, `armies`, `owner`,
`is_iron_throne`, `neighbors`.

---

## 2. Combat — exact casualty arithmetic

`Combat.resolve_combat(attacker, defender, territory, game_map)` — `combat.py:15-66`.

### Step 1 — determine the defending force (`combat.py:29`)

```python
defender_armies = defender.armies if defender is not None else territory.armies
```

| Target | `defender_armies` |
|---|---|
| House-owned | that house's **entire army pool** (`house.armies`) |
| Neutral (`defender is None`) | the territory's own garrison (`territory.armies`) |

The attacker likewise commits **`attacker.armies` — the whole house pool** (`combat.py:30`). There
is no per-province stack; every battle is all-in.

### Step 2 — roll the powers (`combat.py:30-31`)

```python
attacker_power = attacker.armies  * random.uniform(0.8, 1.2)
defender_power = defender_armies * territory.defense_bonus * random.uniform(0.8, 1.2)
```

`defense_bonus` **multiplies**. Two independent uniform rolls in `[0.8, 1.2]`, so each side varies
±20%.

### Step 3 — resolve (`combat.py:33`)

```python
if attacker_power > defender_power:   # strict — TIES GO TO THE DEFENDER
```

### Step 4 — casualties — **the exact loss formulas**

| Outcome | Attacker loses | Defender loses | Line |
|---|---|---|---|
| **Attacker wins** | `int(defender_armies × 0.5)` | `int(defender_armies × 0.8)` | `combat.py:34-35` |
| **Attacker loses** | `int(attacker.armies × 0.6)` | `int(defender_armies × 0.2)` | `combat.py:38-39` |

**Both figures in the win row are computed from `defender_armies`, not from the attacker's size.**
The attacker's casualties on a *win* scale with how big the defender was — not with how big the
attacker is. This is the single most counter-intuitive rule in the combat model.

`int()` truncates toward zero, so fractional losses round **down** — a 3-army defender inflicts
`int(1.5) = 1` casualty on a winning attacker.

### Step 5 — apply, with a floor of 1 (`combat.py:42-46`)

```python
attacker.armies = max(1, attacker.armies - attacker_losses)
# defender is a house:
defender.armies = max(1, defender.armies - defender_losses)
# defender is neutral:
territory.armies = max(1, territory.armies - defender_losses)
```

**Nobody is ever reduced below 1 army by combat.** A house is eliminated by losing all
*territories* (`house.py:74-75`), never by losing all armies.

### Step 6 — transfer on a win (`combat.py:48-56`)

1. `defender.lose_territory(territory)` — removes it and clears `owner` (`house.py:63-67`)
2. `attacker.gain_territory(territory)` — sets `owner`, appends (`house.py:69-72`)
3. `game_map.capture(territory, attacker)`
4. `territory.armies = 0` — the garrison is absorbed into the attacker's pool (`combat.py:53`)
5. **If the defender is now eliminated, the attacker takes all its gold** (`combat.py:54-56`)

### Step 7 — the returned dict (`combat.py:60-66`)

`winner`, `loser`, `territory`, `attacker_losses`, `defender_losses`, `territory_transferred`.

### Worked casualty examples

**A — 21 armies attack neutral King's Landing (garrison 14, ×2):**

| | Win | Loss |
|---|---|---|
| Attacker losses | `int(14 × 0.5)` = **7** → 21 → **14** | `int(21 × 0.6)` = **12** → 21 → **9** |
| Defender losses | `int(14 × 0.8)` = **11** → garrison 0 | `int(14 × 0.2)` = **2** → garrison **12** |

**B — 20 armies attack a 30-army house at Winterfell (×3):**

| | Win | Loss |
|---|---|---|
| Attacker losses | `int(30 × 0.5)` = **15** → 20 → **5** | `int(20 × 0.6)` = **12** → 20 → **8** |
| Defender losses | `int(30 × 0.8)` = **24** → 30 → **6** | `int(30 × 0.2)` = **6** → 30 → **24** |

Example B shows the trap: *winning* against a larger enemy costs the attacker 15 of 20 armies —
worse than the 12 lost by failing. Beating a bigger house can leave you weaker than losing to it.

### The strategic asymmetry

- Losing costs **60% of your own** army.
- Winning costs **50% of theirs**.

Against a much smaller target, winning is nearly free. Against a comparable target, failure is
ruinous. This is exactly why Greedy scores `resource_value − defense_bonus` rather than resource
alone (`greedy.py:19`).

### Guard

Attacking your own territory raises `ValueError` (`combat.py:25-26`).

---

## 3. Economy — income, recruitment, elimination

### Income — `house.py:49-52`, called at `main.py:229`

```python
income = BASE_INCOME + sum(t.resource_value for t in self.territories)
```

`BASE_INCOME = 10` (`constants.py:49`). A house holding only Winterfell (resource 9) earns
`10 + 9 = 19` gold/turn.

### Recruitment — `main.py:241`, executing `house.py:54-60`

```python
recruits = min(MAX_RECRUITS_PER_TURN, max(0, (house.gold - 15) // ARMY_COST))
```

Three rules compounded:

1. **Cap of 3 per turn** — `MAX_RECRUITS_PER_TURN = 3` (`constants.py:52`)
2. **15-gold reserve** kept back (hard-coded, `main.py:241`)
3. **5 gold each** — `ARMY_COST = 5` (`constants.py:50`)

**There is no manual "buy army" action.** Recruitment is automatic in the end-of-round phase. The
only player actions are attack / propose / betray / hold (`main.py:364-391`).

### The consequence: gold is nearly inert

| Gold | Recruits/turn |
|---|---|
| 14 | 0 |
| 30 | 3 (cap) |
| 167 | **3** (cap) |

Past 30 gold, extra wealth buys nothing. **Every surviving house grows at exactly +3 armies/turn**,
so no house can out-economy another. The only ways past that ceiling:

- **Capture territory** → more `resource_value` → more income (still capped at +3 armies, but
  compounding toward it from turn 1)
- **Eliminate a house** → take all its gold (`combat.py:54-56`)

In-code rationale: *"capped per turn to prevent instant snowball"* (`main.py:240`).

> ⚠️ `MAX_RECRUITS_PER_TURN` and the 15-gold floor appear **nowhere in `instructions.md`**, which
> says only "based on available gold." See `TO_IMPLEMENT.md` §B1.

### Military strength — `house.py:77-78`

```python
return float(self.armies + sum(t.defense_bonus for t in self.territories))
```

Here `defense_bonus` is **additive**, not multiplicative. Feeds Decomposed Minimax weighting
(`minimax.py:210-212`) and the fuzzy inputs (`main.py:73`).

### Elimination — `house.py:74-75`

```python
return len(self.territories) == 0
```

**Zero territories, not zero armies.** Combat's floor of 1 (`combat.py:42`) means armies never
reach zero.

---

## 4. Attack legality — who can hit what

`GameController._execute_attack` — `main.py:92-146`.

| # | Rule | Line |
|---|---|---|
| 1 | Attacker must own ≥1 territory, target must not already be theirs | `main.py:93` |
| 2 | If the target borders an owned territory → strike it directly | `main.py:99-100` |
| 3 | Otherwise A\* routes from the nearest owned territory and **attacks the first border hop instead** | `main.py:102-113` |
| 4 | Leading owned territories are trimmed so `step_target` is the first *crossing* | `main.py:106-107` |
| 5 | If no route exists (`len(best_route) < 2`) → the attack silently aborts | `main.py:110-111` |
| 6 | Final adjacency re-check before resolving | `main.py:114-115` |
| 7 | Attacking an **active ally** auto-breaks the pact *before* combat | `main.py:120-123` |
| 8 | If the defender is eliminated and had an ally, that pact dissolves cleanly | `main.py:145-146` |

**Capture is always one hop per turn.** Clicking a distant territory does not fail — it silently
becomes an attack on the nearest border hop toward it.

### What is *not* checked on the human path

`MIN_ATTACK_ARMIES = 5` is consulted **only** at `minimax.py:93`, during AI move generation. The
human attack path (`main.py:364-368`) applies no army-sufficiency check — a human may attack a
house-held territory with 1 army where an AI in the same position could not. See
`TO_IMPLEMENT.md` §D2.

### One action per turn — `main.py:364-391`

`attack` / `ally_<HOUSE>` / `betray` / `hold`, then the turn ends. Responding to a pending proposal
(`accept` / `reject`) is handled first and **does not consume** the action (`main.py:354-362`
returns `False`).

---

## 5. BFS / DFS

### BFS — `algorithms/bfs.py:10-23`

```python
get_reachable(game_map, start, n_steps) -> set[Territory]
```

`n` (`n_steps`) is a **hop limit, not a node count**. Returns the *ball of radius n* — every
territory at distance `0 … n`, start included (seeded into `visited` at `bfs.py:12`).

The cutoff is `if dist >= n_steps: continue` (`bfs.py:17-18`) — a node at distance `n` is kept but
never expanded. Standard BFS: `deque` of `(territory, distance)`, marked visited on enqueue
(`bfs.py:21`) so each territory is added once.

Called with `n_steps=3` at `main.py:186`.

### DFS — `algorithms/dfs.py:8-28`

```python
get_expansion_paths(game_map, start, depth_limit) -> list[list[Territory]]
```

Same depth meaning, different return shape: **paths**, not a node set.

A path is recorded only when its endpoint is **neutral or weakly defended** (`dfs.py:17`):

```python
if depth > 0 and (current.owner is None or current.defense_bonus < 2):
```

- `depth > 0` excludes the trivial single-node path at `start`
- `defense_bonus < 2` means only **Harrenhal** (bonus 1, `map.py:77`) qualifies as "weakly defended"
  among owned territories — every other territory has bonus ≥ 2

Cycles are prevented by `if neighbor not in path` (`dfs.py:22`), with backtracking via
`path.pop()` (`dfs.py:25`). Called with `depth_limit=3` at `main.py:187`.

---

## 6. A\*

`algorithms/astar.py:15-45`.

```python
get_path(game_map, start, goal) -> list[Territory]
```

| Component | Definition | Line |
|---|---|---|
| **Edge cost** | `float(neighbor.defense_bonus)` — cost of *entering* a territory | `astar.py:36` |
| **Heuristic** | `math.hypot(a.col - b.col, a.row - b.row)` — Euclidean on grid coords | `astar.py:11-12` |
| **Open set** | `heapq` with a monotonic `counter` tiebreaker for stable ordering | `astar.py:21-22` |

So A\* finds the **lowest-risk** route (least total fortification crossed), not the shortest hop
count. Returns `[start]` when `start == goal` (`astar.py:17-18`).

Used at `main.py:104` to route an attack toward a non-adjacent target.

---

## 7. Greedy

`algorithms/greedy.py`.

### `greedy_pick(candidates)` — `greedy.py:16-22`

```python
max(pool, key=lambda t: (t.resource_value - t.defense_bonus, t.is_iron_throne))
```

| Element | Meaning |
|---|---|
| `resource_value - defense_bonus` | reward minus cost — prefers *cheap value* |
| `t.is_iron_throne` | tiebreaker toward the throne (`False < True`) |

The tiebreaker exists because candidates arrive from a `set` (`greedy.py:33`) whose iteration order
is not stable across runs. Returns `None` on an empty pool (`greedy.py:19-20`).

> ⚠️ The tiebreaker is not in `instructions.md`. See `TO_IMPLEMENT.md` §B4.

**Takes a bare iterable** — no `House`, no `Map`. That is what makes it importable by
`mcts.py:19` as the rollout opponent model (Role 2).

### `get_greedy_move(house, game_map, enemies)` — `greedy.py:25-41`

Role 1: builds the frontier, then delegates scoring.

1. For each owned territory (`greedy.py:34`), take its neighbours (`greedy.py:35`)
2. Skip those already owned (`greedy.py:36-37`)
3. Keep neutrals (`owner is None`) and enemy-held ones in the `enemies` list (`greedy.py:38-39`)
4. `enemies=None` → **no filter at all**, i.e. "anyone not me" (`greedy.py:31`)
5. Gathered into a `set`, so a territory bordering two of your provinces counts once

**One hop only** — no BFS or A\* involved. No lookahead: Greedy never evaluates the reply.

### Scores on the current board

| Target | `resource − defense` | Line |
|---|---|---|
| King's Landing | 15 − 2 = **13** | `map.py:76` |
| Winterfell | 9 − 3 = 6 | `map.py:69` |
| Casterly Rock | 9 − 2 = 7 | `map.py:78` |
| White Harbor / Oldtown / Highgarden | 6 − 2 = 4 | `map.py:71`, `79`, `80` |
| Harrenhal | 4 − 1 = **3** | `map.py:77` |
| The Wall | 4 − 3 = 1 | `map.py:65` |

Note Greedy ranks **King's Landing highest at 13** — it weighs `defense_bonus` but is blind to the
14-army garrison, since `resource_value - defense_bonus` never reads `territory.armies`. Greedy
alone would throw itself at the throne repeatedly. The guard that prevents this lives in Minimax
(§9), not in Greedy.

---

## 8. Fuzzy Logic

`algorithms/fuzzy_diplomacy.py`. Entry point `evaluate_diplomacy(enemy_strength, own_weakness,
trust_history) -> dict` at `fuzzy_diplomacy.py:95-153`.

### The three outputs

| Key | Posture | Driving rule | Line |
|---|---|---|---|
| `alliance` | seek/accept a pact | enemies strong **and** you weak | `fuzzy_diplomacy.py:76` |
| `betrayal` | break a pact, strike an ally | you strong **and** enemies weak; or trust low | `fuzzy_diplomacy.py:78`, `:81` |
| `solo` | stay independent | you strong **and** trust high | `fuzzy_diplomacy.py:79` |

**Not a probability distribution** — they do not sum to 1. Each is computed independently, so
`{alliance: 0.7, betrayal: 0.65, solo: 0.1}` is legitimate and means "pulled two ways." Scores
only, never decisions (`fuzzy_diplomacy.py:11`).

Two things that are easy to get wrong:

- **Betrayal targets an ally**, not the enemies in `enemy_strength`. You cannot betray someone you
  are already at war with.
- **`solo` is not the leftover.** It has its own rule. If no rule fires, all three return `0.0`
  (`fuzzy_diplomacy.py:52-53`) — that is "no signal," not "go solo."

### Input derivation — `main.py:35-36`, `main.py:71-90`

```python
def _scale_military(strength):
    return max(0.0, min(100.0, strength * 2.5))      # main.py:36
```

| Input | Context A (`main.py:71-82`) | Context B (`main.py:84-90`) |
|---|---|---|
| `enemy_strength` | `_scale_military(Σ all enemies' strength)` — `main.py:73` | `_scale_military(proposer strength)` — `main.py:85` |
| `own_weakness` | `100 − _scale_military(own strength)` — `main.py:74` | identical — `main.py:86` |
| `trust_history` | mean trust toward all enemies — `main.py:75-79` | trust toward the sender — `main.py:87` |

The `× 2.5` means strength **40 saturates at 100**. A house with 14 armies + 3 defence = 17
strength scales to 42.5. Both contexts write back to `house.fuzzy_scores` for the HUD
(`main.py:81`, `main.py:88`).

### Membership functions — `fuzzy_diplomacy.py:70-72`

All six variables (3 inputs, 3 outputs) share one universe `0…100` and one triangle set:

| Term | `trimf` points | Full membership at | Zero at |
|---|---|---|---|
| `low` | `[0, 0, 60]` | 0 | ≥ 60 |
| `medium` | `[20, 50, 80]` | 50 | ≤ 20, ≥ 80 |
| `high` | `[40, 100, 100]` | 100 | ≤ 40 |

They **overlap deliberately** — at 50, `medium` = 1.0 while `low` and `high` ≈ 0.17 each. That
overlap is what removes the threshold cliff: `if enemy_strength > 70` would flip at 69.9 → 70.1,
whereas membership degrades smoothly.

### The six rules — `fuzzy_diplomacy.py:75-82`

| # | IF | THEN | Line |
|---|---|---|---|
| 1 | enemy HIGH ∧ weakness HIGH | alliance HIGH | `:76` |
| 2 | trust LOW ∧ enemy MEDIUM | alliance LOW | `:77` |
| 3 | weakness LOW ∧ enemy LOW | betrayal HIGH | `:78` |
| 4 | weakness LOW ∧ trust HIGH | solo HIGH | `:79` |
| 5 | enemy HIGH ∧ trust HIGH | alliance MEDIUM | `:80` |
| 6 | trust LOW | betrayal MEDIUM | `:81` |

`alliance` is driven by **three rules at three different levels** (1, 2, 5), which can partially
contradict; aggregation blends them rather than letting one win.

### The four-stage pipeline (NumPy fallback, `fuzzy_diplomacy.py:111-153`)

| Stage | Operation | Line |
|---|---|---|
| **1. Fuzzify** | `np.interp` of the value against each triangle | `:47-48`, `:118-128` |
| **2. Apply** | Mamdani AND = `min` of antecedent memberships | `:131-136` |
| **3. Aggregate** | clip consequent by firing strength (`np.minimum`), combine with `np.maximum` | `:138-150` |
| **4. Defuzzify** | centroid `Σ(x·y) / Σy`, then `/100` and `round(…, 2)` | `:51-55`, `:151-153` |

If total area ≤ `1e-9`, the centroid returns `0.0` — "no rule fired → no desirability"
(`fuzzy_diplomacy.py:52-53`).

### Two backends

`scikit-fuzzy` is used when importable (`fuzzy_diplomacy.py:22-27`, `:58-92`); otherwise a
hand-written Mamdani implementation runs (`:111-153`). The `try/except` at `:106-109` also catches
the case where `skfuzzy` raises because a consequent received no activation — so the game runs with
**no fuzzy dependency installed**.

### Declared limitation — `fuzzy_diplomacy.py:15-17`

Stateless. Judges the current snapshot only; cannot see that defecting now gets you crushed in
three turns. Lookahead is MCTS's job.

---

## 9. Minimax

`algorithms/minimax.py`.

### Evaluation function — `_evaluate_state`, `minimax.py:51-68`

```
own_territory_score · 2  +  armies · 1.5  +  gold · 0.5  +  throne_bonus  −  enemy_score
```

| Term | Definition | Line |
|---|---|---|
| `own_territory_score` | `Σ(resource_value + defense_bonus)` over owned | `:52-54` |
| `throne_bonus` | `500` if you hold King's Landing, else 0 | `:56` |
| `enemy_score` | `Σ over enemies (Σ resource_value + armies × 1.5)` | `:57-61` |

Matches the spec formula exactly. Weights `2`, `1.5`, `0.5` are hard-coded at `minimax.py:64-66`.

### Move generation — `_moves`, `minimax.py:85-100`

Two filters beyond plain adjacency:

| Guard | Rule | Line |
|---|---|---|
| **Army sufficiency** | below `MIN_ATTACK_ARMIES = 5`, only **neutral** territories are generated | `:92-93` |
| **Throne rush guard** | the Iron Throne is excluded unless `a_armies ≥ d_armies × defense_bonus` | `:96-99` |

The throne guard is what stops the AI suiciding into King's Landing — it requires at least
`14 × 2 = 28` armies before the throne is even a legal move. **Neither guard is in
`instructions.md`** (`TO_IMPLEMENT.md` §B6).

`root_moves` also includes `None` (`main.py` → `minimax.py:286`), which is how **"hold this turn"**
becomes a scoreable option.

### Decomposed mode — `minimax.py:200-224`

```
score = Σᵢ wᵢ · minimax(me vs Hᵢ),    wᵢ = Hᵢ.get_military_strength() / Σ strength
```

Separate 2-player search per enemy (`minimax.py:215-217`), blended by strength share
(`:210-213`). `or 1.0` guards division by zero (`:210`). **Cannot see coordination** between
enemies — declared approximation (`minimax.py:7-8`).

### Paranoid mode — `minimax.py:225-240`

One search; **all** enemy names passed as a single `opponents` list (`:238`). At the MIN node
(`minimax.py:160-174`) every opponent's moves go into **one shared reply list** (`:161-164`), so
the search picks whichever enemy's move hurts most — a merged coalition with combined armies and
territories, acting with one will.

### Switch logic — `get_best_move`, `minimax.py:248-290`

| Condition | Mode | Line |
|---|---|---|
| This house is in an alliance (ally excluded via `my_forbidden`) | **PARANOID** | `:283-285` |
| The two enemies are allied with each other | **PARANOID** | `:286-288` |
| Otherwise | **DECOMPOSED** | `:290-291` |

Paranoid is **switched on by actual diplomatic state**, not used as a generic hedge. When your ally
is excluded, only one real enemy remains — a clean 2-player game.

`house.mode` is set on each call (`:284`, `:287`, `:290`) and rendered on the HUD
(`renderer.py:1935`). `diplomacy.form_alliance` also forces `PARANOID` immediately
(`diplomacy.py:59-61`), and `dissolve_alliance` reverts to `DECOMPOSED` (`diplomacy.py:73-74`).

### Search machinery

| Feature | Line |
|---|---|
| Alpha-beta cutoff `if alpha >= beta: break` | `:172-173` (MIN), MAX node equivalent |
| Depth limit `MINIMAX_DEPTH = 3` | `constants.py:45` |
| `_State` copy-on-write snapshot (owner / garrison / armies / gold) | `:22-49` |
| Deterministic combat — random factors averaged to 1.0 | `minimax.py:3-5` |
| Root tiebreak prefers a real move over `None` | `:243-245` |

### Declared approximations — `minimax.py:6-11`

1. **Decomposed** — opponents evaluated independently; may underestimate coordination.
2. **Paranoid** — assumes full coalition cooperation; **valid while the alliance holds, not after
   breakdown.** Breakdown is MCTS's job (§10).

---

## 10. MCTS

`algorithms/mcts.py`.

### Rollout policy — `_rollout`, `mcts.py:146-194`

Every house moves via `greedy_pick()` (`mcts.py:171`), in `sim.order` turn order (`:168`), for
`MCTS_ROLLOUT_DEPTH = 10` simulated turns (`:158`). **No random moves anywhere.**

Rationale: random rollouts in a territory game produce incoherent play, so the value estimate is
noise. A greedy model is weak but *coherent*. Declared approximation at `mcts.py:8-11`.

### Alliance breakdown — `mcts.py:160-167`

```python
if random.random() < 1.0 - trust / 100.0:
    allied = False          # solo for the remainder
    risk += 10.0
else:
    risk += (1.0 - trust / 100.0) * 5.0
```

**This is what makes trust a durability estimate:**

| Trust | `p_break`/step | P(pact survives 10 steps) |
|---|---|---|
| 90 | 0.10 | 0.9¹⁰ ≈ **35%** |
| 70 | 0.30 | 0.7¹⁰ ≈ **2.8%** |
| 50 | 0.50 | 0.5¹⁰ ≈ **0.1%** |
| 30 | 0.70 | 0.3¹⁰ ≈ **0.0006%** |

At the starting trust of 50 (`diplomacy.py:27`), an alliance almost never survives a full rollout —
so MCTS values pacts mainly for their **early** steps. No rule says "don't ally with someone you
burned"; the simulation reveals it.

This also covers Minimax's blind spot: Paranoid assumes the coalition is permanent (§9), and these
rollouts are where breakdown is priced in.

### `alliance_risk_penalty` — defined here, **not** in the spec

| Component | Value | Line |
|---|---|---|
| Root action is `betray` | seed `risk = 30.0` (matches `BETRAYAL_PENALTY`) | `:156` |
| Each alliance break | `+10.0` | `:165` |
| Each surviving allied step | `+(1 − trust/100) × 5.0` | `:167` |

Enters the reward with weight `-0.4` (`constants.py:85`). See `TO_IMPLEMENT.md` §B3.

### Reward — `_Sim.reward`, `mcts.py:127-143`

```python
territory_score   = Σ(resource_value + defense_bonus)   # :129-130
military_strength = armies + Σ defense_bonus             # :131
resource_score    = Σ resource_value                     # :132
```

```
0.5 · territory_score + 0.3 · military_strength + 0.2 · resource_score + (−0.4) · risk
```

The three positional terms deliberately **overlap** — a rich fortified province counts in all
three.

### Terminal conditions — `mcts.py:181-191`

| Condition | Return | Line |
|---|---|---|
| You hold the throne | `REWARD_THRONE / 100` = **10.0** | `:182-183` |
| You have no territories | `0.0` | `:184-185` |
| A **rival** holds the throne | `0.5 × max(0, reward) / 100` | `:186-189` |
| Depth exhausted | `max(0, reward) / 100` | `:194` |

The throne **short-circuits** — positional terms never run, because 1000 dwarfs them.

Three undocumented additions (`TO_IMPLEMENT.md` §B2):

1. **`REWARD_SCALE = 100`** (`mcts.py:38`) — load-bearing, not cosmetic. Without it the raw reward
   swamps both the exploration term and the fuzzy bias (each ~0–1), and UCT degenerates into pure
   exploitation.
2. **Rival-throne halving** rather than zeroing — in-code reason: if rivals often win the race,
   flattening to zero makes all actions look identical (`:186-188`).
3. **`max(0.0, …)` clamping** so a heavy risk penalty cannot go below "dead."

### UCT — `_run_uct`, `mcts.py:197-214`

```
UCT = Q/N + 1.414 · √(ln N_parent / N) + fuzzy_score[action]
```

| Step | Behaviour | Line |
|---|---|---|
| Unvisited children expanded first | `:203-205` |
| Selection by max UCT | `:206-212` |
| `MCTS_ITER = 500` iterations | `:200` |
| **Final answer = most-visited child** (ties → total reward) | `:214` |

Fuzzy scores are **additive biases** — a high score gets an action simulated *more often*, never
chosen outright. That is the entire fuzzy → MCTS contract. Returning the most-visited rather than
highest-mean child is the standard robust-child criterion.

### Rollout simulation model — `_Sim`, `mcts.py:52-143`

Index-based snapshot for speed: `adjacency` as integer lists (`:59`), `clone()` copying only the
mutable parts (`:65-75`). `attack()` (`:95-117`) mirrors `combat.py` exactly — same `0.8–1.2`
rolls, same `0.5/0.8/0.6/0.2` casualties. `economy()` (`:119-125`) grants
`BASE_INCOME + Σ resource` then recruits `(gold // ARMY_COST) // 2` — **a different rule from the
real game's `min(3, (gold−15)//5)`** at `main.py:241`.

Allies do not attack each other during a rollout: `protected` excludes the partner
(`mcts.py:173-178`).

### Exposed API

**`get_diplomacy_decision(...)` — `mcts.py:217-254`** → `("propose_alliance" | "betray" | "solo", target_house)`

| Situation | Actions offered | Line |
|---|---|---|
| Has an ally | `solo`, `betray` (target = ally) | `:232-236` |
| No ally, ≥2 others | `solo`, `propose_alliance` | `:237-245` |
| Fewer than 2 others | returns `("solo", None)` immediately | `:246-247` |

**Partner selection (not in the spec):** courts the **most-trusted** house, ties broken toward the
**weaker** one — ally against the strongest (`mcts.py:237`):

```python
max(others, key=lambda h: (diplomacy.get_trust(house, h), -h.get_military_strength()))
```

Acceptance is modelled probabilistically as `random.random() < trust / 100.0` (`:244`). See
`TO_IMPLEMENT.md` §B5.

**`get_proposal_response(...)` — `mcts.py:257-284`** → `"accept" | "reject"`

| Guard | Line |
|---|---|
| Eliminated proposer or receiver → `"reject"` | `:265-266` |
| ≤2 surviving houses → `"reject"` (an alliance is meaningless) | `:267-269` |

Biases: `accept ← alliance`, `reject ← max(betrayal, solo)` (`:272-275`) — both of the latter mean
"no pact."

---

## 11. Diplomacy

`diplomacy.py`.

### State — `Diplomacy.__init__`, `diplomacy.py:20-32`

| Field | Initial value | Line |
|---|---|---|
| `alliances` | `{name: None}` for all three | `:24` |
| `trust_scores` | **every ordered pair starts at `50.0`** | `:25-29` |
| `pending_proposals` | `{}` — keyed by **target** | `:30-31` |
| `event_log` | `[]` — capped at 24 entries | `:32`, `:143` |

### Trust — `update_trust`, `diplomacy.py:84-96`

```python
if action == "betray":  current += BETRAYAL_PENALTY   # -30   (:86-87)
elif action == "keep":  current += ALLY_BONUS         # +5    (:88-89)
current = max(0.0, min(100.0, current))               #       (:90)
```

**Trust is symmetric.** Despite pair-keyed storage, both directions are written
(`diplomacy.py:91-92`):

```python
self.trust_scores[(k2, k1)] = current
self.trust_scores[(k1, k2)] = current
```

So a betrayer's own trust toward the victim drops by 30 as well. Clamped to `[0, 100]`.

`"keep"` is applied once per turn to every surviving alliance (`main.py:245-246`), so a pact that
holds recovers +5/turn — **6 turns to undo one betrayal.**

### Alliance lifecycle — three methods, not two

| Method | Effect | Trust penalty | Mode after | Line |
|---|---|---|---|---|
| `form_alliance` | links both ways, clears any prior pact | — | **PARANOID** | `:48-62` |
| `dissolve_alliance` | unlinks both | **none** | **DECOMPOSED** | `:65-74` |
| `break_alliance` | `dissolve_alliance` + `update_trust(…, "betray")` | **−30** | DECOMPOSED | `:76-79` |

`dissolve_alliance` is **not in the spec** — it exists for clean endings such as a partner being
eliminated (`main.py:145-146`). Note the spec's "switch both to Decomposed immediately" is
satisfied *inside* `dissolve_alliance` (`:73-74`), not in `break_alliance`. See
`TO_IMPLEMENT.md` §B8.

`_sync_house` (`:35-41`) pushes `allied_with` and `trust_history` down onto the `House` objects for
the HUD.

### Proposals — the 2-turn handshake

| Method | Behaviour | Line |
|---|---|---|
| `queue_proposal(proposer, target, turn)` | writes `{"from", "type": "alliance_proposal", "turn"}`, pushes to the target's inbox, logs | `:101-108` |
| `get_proposal(target_house)` | lookup by target | `:110-111` |
| `resolve_proposal(proposer, target, accepted, turn=0)` | pops the proposal, clears the inbox; accept → `form_alliance` + log, else log rejection | `:113-129` |

`House.receive_proposal` keeps **one outstanding proposal per sender** — a new one replaces the old
(`house.py:84`). `get_pending_proposal` returns `inbox[0]` (`house.py:88`).

The extra `turn=0` default on `resolve_proposal` keeps spec-shaped 3-argument calls working.

**Turn N:** proposer queues into the target's inbox and *still makes its own military move*
(`main.py:200-212`). **Turn N+1:** the receiver runs Fuzzy B → MCTS B → `resolve_proposal`
(`main.py:156-172`).

### Raven's Log — `diplomacy.py:132-150`

Capped at the last 24 entries (`:143-144`). Two formats:

- `log_event` → `[Turn N] [House] used [Algo]: [Decision]` (`:146-148`)
- `log_diplomacy` → free text, used for proposed / accepted / rejected / betrayed (`:150`)

---

## 12. Turn pipeline — exact call order

`GameController.step_house_turn` — `main.py:148-223`.

### Branch A — inbox has a pending proposal (`main.py:155-180`)

| # | Step | Call | Line |
|---|---|---|---|
| 1 | Fuzzy **Context B** | `_update_context_b_fuzzy` | `:162` |
| 2 | MCTS **Context B** | `get_proposal_response` | `:164-166` |
| 3 | Send YES/NO | `resolve_proposal` | `:168-170` |
| 4 | Minimax | `get_best_move` | `:175` |
| 5–6 | A\* + Combat | `_execute_attack` | `:177` |

### Branch B — no pending proposal (`main.py:181-223`)

| # | Step | Call | Line |
|---|---|---|---|
| 1 | BFS + DFS | `get_reachable(…, 3)`, `get_expansion_paths(…, 3)` | `:186-187` |
| 2 | Fuzzy **Context A** | `_update_context_a_fuzzy` | `:190` |
| 3 | MCTS **Context A** | `get_diplomacy_decision` | `:193-195` |
| 4a | If propose | `queue_proposal` + raven animation | `:198-208` |
| 4b | If betray | `break_alliance`, set `betray_target` | `:209-212` |
| 5 | Minimax | `get_best_move(…, betray_target=…)` | `:215-217` |
| 6–7 | A\* + Combat | `_execute_attack` | `:219` |

### End of round — `_end_of_round`, `main.py:224-252`

| # | Step | Line |
|---|---|---|
| 8 | `collect_income()` for all houses | `:229` |
| 9 | `recruit_armies()` — capped at 3 | `:240-243` |
| 10 | `update_trust(…, "keep")` for surviving alliances | `:245-246` |
| 11 | `check_winner()`; if none, `turn += 1` | `:250-252` |

Note step 10 runs **only** for alliances still active, and step 11 increments the turn counter only
when nobody has won.

---

## 13. Win / elimination conditions

### Victory — `check_winner`, `main.py:403-406`

```python
if self.map.iron_throne.owner is not None:
    holder = self.by_name.get(self.map.iron_throne.owner)
```

**Any owner of King's Landing wins immediately.** The throne starts neutral (`map.py:76`,
`owner=None`), so the first capture ends the game. Checked after each human action
(`main.py:393-396`) and at end of round (`main.py:250`).

### Elimination — `house.py:74-75`

`len(self.territories) == 0`. Armies are irrelevant — the floor of 1 at `combat.py:42` means they
never reach zero.

On elimination the capturer takes **all** the loser's gold (`combat.py:54-56`), and any orphaned
alliance is dissolved penalty-free (`main.py:145-146`).

---

## 14. Worked example — King's Landing, with exact casualties

Real position, Turn 06: **House Lannister 21 armies / 167 gold**, attacking **neutral King's
Landing** (garrison 14, `defense_bonus` 2 — `map.py:76`). Lannister borders it via **Dorne**
(`map.py:116`).

### The roll (`combat.py:30-31`)

```
attacker_power = 21      × U(0.8, 1.2)  →  16.8 … 25.2
defender_power = 14 × 2  × U(0.8, 1.2)  →  22.4 … 33.6
```

Best attacker roll (25.2) barely exceeds worst defender roll (22.4). Monte Carlo, 400 000 trials:
**≈4.2%.**

### Exact outcomes

| | Win (4.2%) | Loss (95.8%) |
|---|---|---|
| Formula | `int(14 × 0.5)` / `int(14 × 0.8)` | `int(21 × 0.6)` / `int(14 × 0.2)` |
| Attacker losses | **7** → 21 → **14 armies** | **12** → 21 → **9 armies** |
| Defender losses | **11** → garrison → **0** | **2** → garrison → **12** |
| Territory | transfers → **GAME WON** | stays neutral |

### Armies needed

| Armies | P(capture) | Note |
|---|---|---|
| 21 | 4% | current |
| 25 | 26% | |
| **28** | **50%** | coin-flip line: armies = garrison × bonus |
| 30 | 66% | |
| 35 | 90% | |
| 40 | 99% | |
| **43+** | **100%** | guaranteed — `43 × 0.8 > 28 × 1.2` |

**28** is also the exact threshold the AI's throne-rush guard enforces (`minimax.py:96-99`), so an
AI house would not even generate this move below 28 armies.

### Why 167 gold does not help

The recruitment cap (`main.py:241`) gives **+3 armies/turn regardless of wealth** (§3):

| Turn | Armies | P(capture) |
|---|---|---|
| 06 | 21 | 4% |
| 09 | 30 | 66% |
| 12 | 39 | ~98% |
| 14 | 45 | 100% |

Rivals also gain +3/turn, so the race stays even.

### The better play

**Harrenhal** — effective defence `4 × 1 = 4` (`map.py:77`), the softest hex on the board. At 21
armies it is near-certain. It adds resource 4 to income and opens a second approach to King's
Landing alongside Dorne (`map.py:115`).

---

## 15. Known approximations

Declared in `instructions.md` and documented in each module header.

| # | Approximation | Documented at | Covered by |
|---|---|---|---|
| 1 | **Decomposed Minimax** — opponents evaluated independently; underestimates coordination | `minimax.py:7-8` | Paranoid mode when a coalition actually forms |
| 2 | **Paranoid Minimax** — assumes full coalition cooperation forever | `minimax.py:10-11` | MCTS rollout breakdown (§10) |
| 3 | **MCTS rollouts** — Greedy opponent model, not recursive MCTS | `mcts.py:8-11` | accepted tractability tradeoff |
| 4 | **Fuzzy Logic** — stateless; current snapshot only | `fuzzy_diplomacy.py:15-17` | MCTS lookahead (§10) |

Each layer's blind spot is covered by the layer above it — which is the core architectural argument
of the design.
