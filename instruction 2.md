# Game of Thrones: AI Conquest — Design Companion (Instruction 2)

Companion to [`instructions.md`](instructions.md). Where `instructions.md` says **what to build**,
this document explains **what the built code actually does and why** — the semantics behind each
algorithm, the mechanics a player or examiner needs to reason about, and every place the
implementation goes beyond or deviates from the original spec.

Gaps and deviations are tracked separately in [`TO_IMPLEMENT.md`](TO_IMPLEMENT.md).

---

## Table of Contents

1. [BFS / DFS — what the depth parameters mean](#1-bfs--dfs--what-the-depth-parameters-mean)
2. [Greedy — the dual role](#2-greedy--the-dual-role)
3. [Fuzzy Logic — alliance / betrayal / solo](#3-fuzzy-logic--alliance--betrayal--solo)
4. [Minimax — Paranoid vs Decomposed](#4-minimax--paranoid-vs-decomposed)
5. [MCTS — rollouts, reward, and the exposed API](#5-mcts--rollouts-reward-and-the-exposed-api)
6. [Diplomacy — proposals, trust, alliance lifecycle](#6-diplomacy--proposals-trust-alliance-lifecycle)
7. [Combat — when a house can capture a territory](#7-combat--when-a-house-can-capture-a-territory)
8. [`defense_bonus` — one stat, four jobs](#8-defense_bonus--one-stat-four-jobs)
9. [Economy — income and the recruitment cap](#9-economy--income-and-the-recruitment-cap)
10. [Worked example — assaulting King's Landing](#10-worked-example--assaulting-kings-landing)

---

## 1. BFS / DFS — what the depth parameters mean

| Spec signature | Actual signature | File |
|---|---|---|
| `get_reachable(map, start, n) -> set` | `get_reachable(game_map, start, n_steps)` | `algorithms/bfs.py:10` |
| `get_expansion_paths(map, start, depth) -> list` | `get_expansion_paths(game_map, start, depth_limit)` | `algorithms/dfs.py:8` |

### `n` is a hop limit, not a node count

`n` (`n_steps` in code) means **"at most n edge traversals from `start`."** The function returns the
*ball of radius n* around the start territory — every territory at distance `0, 1, … n` — not the
territories at exactly distance `n`. The start itself is always included, seeded into `visited` at
distance 0.

BFS expands level by level and simply refuses to enqueue a node's neighbours once that node's
recorded distance has reached `n_steps`:

```python
if dist >= n_steps:
    continue
```

### Relationship to the DFS `depth`

`depth` in `get_expansion_paths` carries the **same meaning** — how far to search — but the two
functions differ in *return shape*, not in semantics:

- **BFS** → a `set` of reachable territories ("where can I get to?")
- **DFS** → a `list` of paths ("by which routes?")

Both are called with `3` from the turn pipeline (`main.py:186-187`), where they update each AI
house's reachability map and deep expansion scouting before diplomacy is evaluated.

---

## 2. Greedy — the dual role

`algorithms/greedy.py` exposes two functions, and the split is deliberate.

### Role 1 — standalone attack target selection

`get_greedy_move(house, game_map, enemies)` is a **one-step, no-lookahead** chooser:

1. **Build the candidate set.** Walk every territory the house owns, collect their neighbours, drop
   any the house already owns. What remains is the attackable frontier: enemy-held (filtered against
   the `enemies` list) or unowned (`owner is None`). Adjacency is the only reach constraint — one
   hop, so no BFS or A\* is involved.
2. **Score each candidate** as `resource_value - defense_bonus` — reward minus cost. A rich but
   heavily fortified seat scores the same as a poor undefended one; the heuristic prefers *cheap
   value*.
3. **Take the argmax.** Commit to the locally best option; never evaluate the opponent's reply.

Candidates are gathered into a `set`, so a territory adjacent to two of your provinces is not
double-counted.

### Role 2 — MCTS rollout opponent model

`greedy_pick(candidates)` takes a **bare iterable of territories** — no `House`, no `Map`. That is
precisely what makes it importable by `algorithms/mcts.py`, where the simulated state already has
its own candidate list. `get_greedy_move` is the map-aware wrapper; `greedy_pick` is the reusable
scoring core.

### Two behaviours beyond the literal spec

1. **Tie-break toward the Iron Throne.** The sort key is the tuple
   `(resource_value - defense_bonus, is_iron_throne)`. The spec does not mandate this; it is a
   deterministic tie-break, which matters because `set` iteration order is not stable across runs.
2. **`enemies=None` means "anyone not me."** Passing `None` skips the enemy filter entirely rather
   than yielding an empty candidate set.

### Return value

Returns `None`, not a territory, when the frontier is empty — a fully encircled house has no greedy
move, so every caller must handle that.

---

## 3. Fuzzy Logic — alliance / betrayal / solo

`algorithms/fuzzy_diplomacy.py`

### The three outputs are three diplomatic postures

Each is a **desirability score in `[0.0, 1.0]`** for one stance:

| Output | Posture | Rule that drives it |
|---|---|---|
| `alliance` | Seek or accept a pact — pool strength against a bigger threat | enemies strong **and** you weak |
| `betrayal` | Break a pact, strike an ally opportunistically | you strong **and** enemies weak; or trust low |
| `solo` | Stay independent — no pact, no backstab | you strong **and** trust high |

### They are scores, not decisions

The outputs are **not a probability distribution** — they do not sum to 1. Each is computed
independently, so `{alliance: 0.7, betrayal: 0.65, solo: 0.1}` is a legitimate result meaning
"ally with someone, but you are also tempted to defect." That ambiguity is the point. The module
header states it directly: *continuous desirability scores in [0.0, 1.0] only — never final
decisions.*

The correct reading of a result is **"allying looks 0.7 good, betraying 0.65, going solo 0.1 — now
MCTS, decide."**

Two clarifications that are easy to get wrong:

- **Who gets betrayed.** The inputs describe *enemies*, but betrayal applies to an **ally** — you
  cannot betray someone you are already at war with. A high `betrayal` score means "the strategic
  climate rewards defection," not "betray the house in `enemy_strength`."
- **`solo` is not the leftover.** It is not "whatever is left after alliance and betrayal." It has
  its own rule (strong **and** high trust): you do not need help, and you have no grievance worth
  exploiting. If no rule fires at all, **all three return `0.0`** — that is "no signal," not
  "go solo."

### What "fuzzy" means here

Classical logic would need a cutoff: `if enemy_strength > 70: ally`. At 69.9 you refuse, at 70.1 you
commit — a magic number with a cliff. Fuzzy logic replaces that with **degrees of membership**,
across four stages:

**1. Fuzzify.** Each 0–100 input is mapped onto three overlapping triangles — `low`, `medium`,
`high`. A single value belongs to several at once: `enemy_strength = 50` is `medium` to degree 1.0,
and `low`/`high` to roughly 0.17 each. "Strong enemy" becomes a matter of degree.

**2. Apply rules.** Six human-readable `IF … THEN …` rules. This is the real design argument for
fuzzy logic in this project: the rules read like strategic doctrine ("if enemies are strong and I am
weak, alliance is highly desirable") rather than tuned constants. Rule strength is the `min` of its
input memberships (Mamdani AND), so a half-matched rule contributes half.

**3. Aggregate.** For each output, the firing rules' clipped consequent shapes are combined with
`max`. Note that `alliance` receives three rules at *different* levels — low, medium and high —
which can partially contradict; aggregation blends them instead of letting one win.

**4. Defuzzify.** The aggregated shape collapses to a single number via its **centroid** (the
balance point of the area), then divides by 100 into `[0, 1]`.

### Context A vs Context B

One function, two input meanings:

| | Context A | Context B |
|---|---|---|
| Question | "What posture suits my overall position?" | "Should I accept *this* proposal?" |
| `enemy_strength` | combined military threat of all enemies | the proposal sender's military |
| `own_weakness` | own vulnerability | receiver's weakness |
| `trust_history` | average trust toward enemies | trust toward the sender |

The reuse is the fuzzy module's equivalent of Greedy's dual role: one rule base, two entry
situations. Context A is wired at `main.py:71`, Context B at `main.py:84`.

### Implementation note — the NumPy fallback

The module prefers `scikit-fuzzy` when installed, but ships a **pure-NumPy Mamdani implementation**
with hand-written `trimf`, membership interpolation and centroid defuzzification. The fallback also
catches the case where `skfuzzy` raises because a consequent received no activation at all. The game
therefore runs with no fuzzy dependency installed.

### Declared limitation

Fuzzy evaluation is **stateless** — it judges the current snapshot only. A high `betrayal` score
cannot see that defecting now gets you crushed three turns later. Lookahead is MCTS's job; fuzzy
only shapes the priors.

---

## 4. Minimax — Paranoid vs Decomposed

`algorithms/minimax.py`

### The problem being solved

Textbook Minimax is **two-player zero-sum**: one maximiser, one minimiser. This game has three
houses, so there is no single "the opponent." The two modes are two different answers to that.

### Decomposed mode

Runs a **separate 2-player search per enemy** and blends the scores, weighted by each enemy's share
of total military strength:

```
score = w₂ · minimax(me vs H2) + w₃ · minimax(me vs H3),   wᵢ = strengthᵢ / Σ strength
```

Each enemy is handled as if the other did not exist. Cheap, but it **cannot see coordination** —
the declared approximation in the module header.

### Paranoid mode

One search, all enemy names passed as a single `opponents` list. Inside the MIN node the enemies'
moves go into **one shared reply list**, so the search picks whichever enemy's move hurts you most.
That is the merged coalition: combined armies, combined territories, one will. Hence "paranoid" —
the pessimistic assumption that everyone is ganging up on you.

### Switch logic — `get_best_move`

| Situation | Mode | Why |
|---|---|---|
| The two enemies are allied with each other | **Paranoid** | They genuinely do coordinate — the assumption is *true*, not pessimism |
| This house is in an alliance | **Paranoid** | The ally is excluded via `my_forbidden`, leaving one real enemy — a clean 2-player game |
| No alliances anywhere | **Decomposed** | Nobody is coordinating, so modelling a coalition would be needlessly defensive |

Paranoid is therefore **switched on by actual diplomatic state**, not used as a generic worst-case
hedge. `diplomacy.form_alliance` flips `mode = "PARANOID"` on both partners the moment a pact
forms, and `dissolve_alliance` reverts both to `"DECOMPOSED"`. `house.mode` is surfaced on the HUD.

### Shared machinery

- **Alpha-beta pruning in both modes**, via `_alphabeta`, cutting on `alpha >= beta`.
- **Depth limit `MINIMAX_DEPTH = 3`.**
- The search runs over `_State`, a **copy-on-write snapshot** (ownership, garrison, armies, gold),
  so it never mutates real game state.
- Simulated attacks resolve with the **expected** outcome of the combat model — random factors
  averaged to 1.0 — so the search is deterministic.
- **Army sufficiency restraint:** below `MIN_ATTACK_ARMIES = 5`, generated moves are restricted to
  neutral territories only.
- `root_moves` includes `None`, which is how "hold this turn" becomes a scoreable option.

### Evaluation function

`_evaluate_state` matches the spec formula exactly:

```
own_territory_score · 2  +  armies · 1.5  +  gold · 0.5  +  throne_bonus  −  enemy_score
```

with `own_territory_score = Σ(resource_value + defense_bonus)`, `THRONE_BONUS = 500`, and
`enemy_score = Σ(Σ resource_value + armies · 1.5)`.

### Costs of being paranoid

A merged coalition has a larger branching factor at MIN nodes, and the returned scores are more
pessimistic — Paranoid play is conservative and sometimes passes up gains a bolder read would take.
The sharper limitation is the second declared approximation: **it assumes the coalition holds
forever.** It cannot model the alliance cracking, because that is not a minimax question. Alliance
breakdown is left to MCTS.

---

## 5. MCTS — rollouts, reward, and the exposed API

`algorithms/mcts.py`

### Rollout policy

Every house in a rollout attacks via `greedy_pick()`, in turn order, each simulated turn. **No
random moves anywhere.** The justification: random rollouts in a territory game produce incoherent
play, so the resulting value estimate is noise. A greedy opponent model is weak but *coherent*, so
the averaged reward means something. The cost is the declared approximation — it is not true
recursive MCTS per opponent, just a tractable stand-in.

### Alliance breakdown in rollouts

```python
if random.random() < 1.0 - trust / 100.0:
    allied = False          # solo play for the remainder of the rollout
    risk += 10.0
else:
    risk += (1.0 - trust / 100.0) * 5.0
```

This is what makes **trust a durability estimate rather than a flavour number**:

- Trust 90 → ~10% break chance per step, so a pact likely survives all 10 steps.
- Trust 30 → 70% per step, so it dies almost immediately and `propose_alliance` rolls out as
  near-solo play.

No rule says "do not ally with someone you have burned" — the simulation simply reveals it. This is
also the piece that covers Minimax's blind spot: Paranoid mode assumes the coalition holds forever,
and these rollouts are where breakdown is actually priced in.

**`alliance_risk_penalty` is defined here, not in the spec.** The `risk` accumulator is seeded with
a flat `30.0` when the root action is `betray` (matching the real trust cost), then grows by `10`
per break and drips `(1 - trust/100) × 5` per surviving step.

### Reward function

Weights come from `constants.py` and match the spec: `0.5 / 0.3 / 0.2 / −0.4`, throne `1000`.

```
territory_score   = Σ(resource_value + defense_bonus) over owned
military_strength = armies + Σ defense_bonus over owned
resource_score    = Σ resource_value over owned
```

"Strictly prioritized" means the **throne short-circuits**: holding it returns immediately and the
positional terms never run, because 1000 dwarfs anything they could produce. The three positional
terms deliberately overlap, so a rich fortified province counts in all three.

Three behaviours the code adds beyond the spec:

1. **Scaling.** Everything is divided by `REWARD_SCALE = 100` before entering UCT, so `Q/N` lands
   near the exploration term and the fuzzy bias (both ~0–1). Without this the raw reward would
   swamp both and UCT would degenerate into pure greedy selection.
2. **Rival throne capture halves the reward** rather than zeroing it. The in-code reasoning: if
   rivals usually win the race, flattening to zero makes all your actions look identical.
3. **`max(0.0, …)` clamping**, so a heavy alliance penalty cannot produce a reward below "dead."

### UCT and the fuzzy handoff

```
UCT = Q/N + UCT_C · √(ln N_parent / N) + fuzzy_score[action]
```

with `UCT_C = 1.414`, `MCTS_ITER = 500`, `MCTS_ROLLOUT_DEPTH = 10`.

Fuzzy scores enter as **additive biases**. A high fuzzy score gets an action simulated *more often*;
it never selects the action outright. That is the entire fuzzy → MCTS contract. Unvisited children
are expanded first, and the final answer is the **most-visited** child (ties broken by total
reward), not the highest-mean one — the standard robust-child criterion.

### Exposed API

Both signatures match the spec:

```python
get_diplomacy_decision(house, all_houses, map, fuzzy_scores, diplomacy)
    -> ("propose_alliance" | "betray" | "solo", target_house)

get_proposal_response(house, proposer, all_houses, map, fuzzy_scores, diplomacy)
    -> ("accept" | "reject")
```

Context B maps `reject` to `max(betrayal, solo)`, since both mean "no pact."

**Target selection is not in the spec.** With no existing ally, the house courts the **most-trusted**
house, breaking ties toward the **weaker** one — ally against the strongest. Acceptance by that
partner is modelled probabilistically as `trust/100`.

Guard conditions in Context B: an eliminated proposer or receiver auto-rejects, and with only two
surviving houses an alliance is meaningless, so it rejects.

---

## 6. Diplomacy — proposals, trust, alliance lifecycle

`diplomacy.py` — every spec item is present:

| Spec item | Location | Note |
|---|---|---|
| `pending_proposals` | `diplomacy.py:30` | keyed by **target**, holding `{from, type, turn}` |
| `queue_proposal` | `diplomacy.py:101` | also pushes to the house inbox and logs the event |
| `get_proposal` | `diplomacy.py:110` | |
| `resolve_proposal` | `diplomacy.py:113` | accept → `form_alliance`; reject → log. Extra `turn=0` parameter, defaulted, so spec-shaped calls still work |
| `break_alliance` | `diplomacy.py:76` | `dissolve_alliance` + `update_trust(…, "betray")` |
| Trust −30 / +5 | `constants.py:53-54` | `BETRAYAL_PENALTY = -30`, `ALLY_BONUS = 5` |

### Two things worth knowing when tracing the spec

1. **"Switch both to Decomposed immediately" lives inside `dissolve_alliance`**, not in
   `break_alliance` itself. Tracing the spec line by line will otherwise look like a gap.
2. **`update_trust` writes both directions symmetrically.** Despite the keyed-pair storage
   `(h1, h2)`, trust is effectively bilateral — the betrayer's own trust toward the victim drops
   too. Trust is clamped to `[0, 100]`.

### `dissolve_alliance` vs `break_alliance`

- `dissolve_alliance` — ends a pact **without** a trust penalty (for example, a partner was
  eliminated). Called from `main.py:146`.
- `break_alliance` — unilateral betrayal: dissolve **plus** the −30 penalty.

### The 2-turn handshake

Proposals are asynchronous by design. Turn *N*: the proposer queues into the target's inbox and
still makes its own military move. Turn *N+1*: the receiver runs Fuzzy Context B → MCTS Context B →
`resolve_proposal`. A new proposal from the same sender replaces the previous one rather than
stacking.

### Raven's Log

`event_log` keeps the last 24 entries, in two formats:
`[Turn N] [House] used [Algo]: [Decision]` and the diplomacy events (proposed / accepted / rejected
/ betrayed).

---

## 7. Combat — when a house can capture a territory

There are **two gates**: being allowed to launch the attack, and winning the roll.

### Gate 1 — can you attack it at all? (`main.py:92-122`)

- You must **own at least one territory**, and the target must not already be yours.
- **Adjacency.** If the target borders any territory you own, you strike it directly. If it does
  not, A\* routes from your nearest province and you attack **the first border hop instead** — not
  the territory you clicked. A distant click does not fail; it silently becomes a nearer attack.
  Capture is always one hop per turn.
- **One action per turn** — attack, propose, betray, or hold, then the turn ends.
- **Attacking an active ally auto-triggers betrayal**: the pact breaks and the −30 trust penalty
  lands *before* the battle resolves.

Note what is **not** required: there is no per-territory garrison to move, and no minimum-army check
on the human path. `MIN_ATTACK_ARMIES = 5` is only consulted by Minimax when generating its own
candidate moves.

### Gate 2 — do you win the battle? (`combat.py:30-40`)

```python
attacker_power = attacker.armies   * random.uniform(0.8, 1.2)
defender_power = defender_armies * territory.defense_bonus * random.uniform(0.8, 1.2)
```

Capture happens **iff `attacker_power > defender_power`** — **ties go to the defender.** Two inputs
decide it:

- **`defender_armies` depends on who holds the territory.** Owned by a house → that house's
  **entire army pool**. Neutral → only the territory's own garrison, the badge shown on the hex.
  This is why neutrals are the cheap expansion targets and house-held provinces are expensive.
- **`defense_bonus` multiplies the defender only.**

Your side is likewise your **whole house pool**, not a per-province stack — every attack is all-in.

### Outcomes (`combat.py:42-58`)

| | Attacker loses | Defender loses | Territory |
|---|---|---|---|
| **Win** | 50% of defender's size | 80% of their armies | transfers to attacker |
| **Loss** | **60% of attacker's own armies** | 20% of theirs | stays with defender |

Both sides always take casualties, and nobody drops below 1 army. On a win the attacker also takes
**all the gold** of a house it eliminates, and the captured hex's garrison resets to 0 — folded into
the attacker's pool.

**The asymmetry is the key strategic fact:** losing costs 60% of *your* army; winning costs 50% of
*theirs*. Attacking something much smaller than you is nearly free; attacking something comparable
is ruinous when it fails. That is exactly why Greedy scores `resource_value − defense_bonus` rather
than resource alone.

### Win condition

`check_winner` declares a winner the moment the Iron Throne has **any** owner — capturing King's
Landing ends the game immediately.

---

## 8. `defense_bonus` — one stat, four jobs

A per-territory terrain/fortification rating, set once in `TERRITORY_SPECS` and never changing.
Range **1 to 4**:

| Value | Territories |
|---|---|
| 1 | Harrenhal (ruins — the soft spot) |
| 2 | King's Landing, Casterly Rock, Dorne, most harbours and farms |
| 3 | The Wall, Winterfell, Dreadfort, The Eyrie, The Twins |
| 4 | Dragonstone (hardest on the board) |

### It is a multiplier, not an addition

`combat.py:31` multiplies. King's Landing's 14-army garrison does not defend at 16 — it defends at
**28**. Dragonstone's ×4 means a 22-army Targaryen defends there at **88**.

Because the multiplier scales with the defender's *current* size, fortified provinces get **harder
as their owner grows**, rather than being a flat bonus.

> The HUD tooltip renders this as `Fortifications: +N Defense`, which reads as additive and badly
> understates the mechanic. Logged in `TO_IMPLEMENT.md`.

### The other three uses

| Use | Sign | Where |
|---|---|---|
| Combat defence | multiplicative | `combat.py:31`, `mcts.py:100` |
| House military strength | **additive** — holding Winterfell adds a flat 3 | `house.py:78` |
| Greedy target score | **subtracted** — the only "cost" term the heuristic has | `greedy.py:19` |
| MCTS reward | **added** — in both `territory_score` and `military_strength` | `mcts.py:130-131` |
| A\* edge weight | path cost of entering a territory | `astar.py:36` |

Land you **hold** is worth more when fortified; land you **want** is worth less. Same number,
opposite signs depending on which side of the border it sits on — which is the correct modelling.

### Reading it off the board

A neutral hex defends at `garrison × bonus`:

| Territory | Garrison × Bonus | Effective |
|---|---|---|
| Harrenhal | 4 × 1 | **4** |
| Highgarden | 4 × 2 | 8 |
| Dorne / Storm's End | 4 × 2 | 8 |
| King's Landing | 14 × 2 | **28** |

Harrenhal is the cheapest target on the map by a wide margin, and it borders King's Landing.

---

## 9. Economy — income and the recruitment cap

**There is no manual "buy army" action.** Recruitment happens automatically in the end-of-round
phase (`main.py:240-243`), not as a player choice:

```python
recruits = min(MAX_RECRUITS_PER_TURN, max(0, (house.gold - 15) // ARMY_COST))
```

With `MAX_RECRUITS_PER_TURN = 3`, `ARMY_COST = 5`, `BASE_INCOME = 10`. The in-code rationale is
*"capped per turn to prevent instant snowball."* The only player turn actions are attack, propose,
betray, or hold.

**The consequence: gold is almost never the binding constraint — turns are.** Three recruits cost
15 gold; a house sitting on 167 gold still gains only +3 armies per turn. Every house accrues at the
same +3 ceiling, so no house can out-economy another into a win. The only ways to break past that
ceiling are:

- **Capturing territory** — more resource value, and all the gold of a house you eliminate.
- **Alliance play** — keeping one flank quiet while you build.

Which is precisely why the diplomacy layer exists.

---

## 10. Worked example — assaulting King's Landing

A concrete application of §7–§9, from an actual mid-game position (Turn 06, House Lannister:
21 armies, 167 gold; King's Landing neutral with a 14-army royal garrison, ×2 defence).

### The roll

```
attacker_power = 21 × U(0.8, 1.2)      →  16.8 … 25.2
defender_power = 14 × 2 × U(0.8, 1.2)  →  22.4 … 33.6
```

The best possible attacker roll (25.2) barely overlaps the worst defender roll (22.4). Monte-Carlo
over 400 000 trials: **≈4.2% win probability.**

### Armies required

| Armies | P(capture) |
|---|---|
| 21 | 4% |
| 25 | 26% |
| **28** | **50%** — the coin-flip line (armies = garrison × bonus) |
| 30 | 66% |
| 35 | 90% |
| 40 | 99% |
| **43+** | **guaranteed**, even on the worst roll |

### Cost of guessing wrong

A failed assault takes 60% of the attacker's armies — 21 → 9 — while the garrison drops only 20%, to
12. With 9 armies against two rivals at 22, the attacker becomes the obvious next target. The
downside vastly outweighs a 4% upside.

### Why gold does not rescue it

167 gold looks decisive but buys only +3 armies per turn (§9). The coin-flip threshold of 28 arrives
around turn 8–9; a safe assault around turn 12+. Meanwhile both rivals build at the same +3, so the
race stays even.

### The real lesson

The cheap play is **Harrenhal** (effective defence 4), which both expands the economy and opens a
second approach to the throne alongside Dorne. And the window matters: once a rival captures King's
Landing it stops being a 14-army neutral — but by then the game has already ended, since any owner
of the Iron Throne wins immediately.

---

## Known approximations — summary

Carried from `instructions.md` and documented in the respective module headers:

1. **Decomposed Minimax** — opponent interactions evaluated independently; may underestimate
   coordination.
2. **Paranoid Minimax** — assumes full coalition cooperation; valid while the alliance holds, not
   after breakdown.
3. **MCTS rollouts** — Greedy opponent model, not true recursive MCTS; a tractability tradeoff.
4. **Fuzzy Logic** — stateless; evaluates the current snapshot only, not future trajectory.

Each is covered by a later layer: Minimax's blind spot (#2) is priced in by MCTS rollout breakdown,
and Fuzzy's blind spot (#4) is covered by MCTS lookahead.
