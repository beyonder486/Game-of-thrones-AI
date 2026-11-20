# Game of Thrones: AI Conquest — Implementation Instructions

You are an expert Python game developer and AI systems engineer.
I have a partially built **"Game of Thrones: AI Conquest"** game. It was built using an earlier plan and is not yet functional.
Your job is to modify and complete it based on the refined design described below.
**Do not rebuild from scratch** — work with what exists and patch/extend as needed.

---

## Core Concept

Three houses (**Stark**, **Lannister**, **Targaryen**) compete for the Iron Throne through territorial expansion, resource management, and political maneuvering.

- Supports **AI-vs-AI** simulation and **Human-vs-AI** gameplay.
- Each house is strictly limited to **ONE action per turn**.

---

## Critical Design Rules

1. One action per house per turn — no exceptions.
2. Diplomatic proposals are asynchronous — queued in the receiver's inbox, evaluated next turn.
3. Betrayal is unilateral — no proposal needed.
4. No resource sharing between allied houses ever.
5. Territories captured from a defeated house go to whoever physically captured each one.
6. Fuzzy Logic outputs scores only — never decisions.
7. MCTS makes all final diplomatic decisions.
8. Greedy is used as MCTS rollout opponent model only — not random rollouts.

---

## Turn Structure — Implement Exactly as Specified

Each turn, per house, in order (skip if eliminated):

**If `house.inbox` has a pending proposal:**

1. **Fuzzy Logic** — evaluate proposal sender's state
2. **MCTS** — simulate accept vs reject outcome
3. **Send YES/NO** — update diplomacy state
4. **Minimax** — select combat/expansion move
5. **A\*** — route troop movement
6. **Combat** — resolve attack

**Else (no pending proposal):**

1. **BFS/DFS** — update reachability map
2. **Fuzzy Logic** — evaluate diplomatic landscape
3. **MCTS** — decide: propose ally / betray / solo
4. **If propose** — queue proposal in target's inbox
5. **Minimax** — select combat/expansion move
6. **A\*** — route troop movement
7. **Combat** — resolve attack

**After every house acts:**

8. `collect_income()` for all houses
9. `recruit_armies()` based on available gold
10. Update trust history
11. Check win condition

---

## Asynchronous Diplomacy Cycle

### Alliance formation (2-turn handshake)

**Turn N — Proposing house:**
- MCTS decides → propose alliance to target house
- Proposal queued in `target.inbox`
- Proposing house still makes its military move this turn

**Turn N+1 — Receiving house:**
- Fuzzy Logic evaluates proposal sender's state
- MCTS simulates accept vs reject consequences
- Sends YES or NO
  - **YES** → `alliance_active = True` for both houses; both switch Minimax to **Paranoid** mode
  - **NO** → no change, proposer notified

### Betrayal (unilateral, any turn)

- MCTS decides → betray
- Attack ally's territory this turn
- `diplomacy.break_alliance(betrayer, victim)`
- `trust -= BETRAYAL_PENALTY` (30 points)
- Both houses revert to **Decomposed** Minimax immediately

### No resource sharing

- Captured territories → go to capturing house only
- Defeated house gold → goes to capturing house only
- Allied houses remain fully independent economically

---

## House Inbox System — Add to `house.py`

Add to the `House` class:

```python
inbox = []   # pending diplomatic proposals
```

Proposal structure:

```python
{
    "from": house_name,
    "type": "alliance_proposal",
    "turn": turn_number
}
```

Methods to add:

- `receive_proposal(proposal)`
- `get_pending_proposal() -> proposal or None`
- `clear_inbox()`

---

## Algorithms 1 & 2 — BFS / DFS (no change)

- **BFS:** `get_reachable(map, start, n) -> set`
- **DFS:** `get_expansion_paths(map, start, depth) -> list`

No modifications needed.

---

## Algorithm 3 — Greedy (modify role)

**Role 1 (unchanged): standalone attack target selection**

- `get_greedy_move(house, map, enemies) -> territory`
- Criteria: `argmax(resource_value - defense_bonus)` over all adjacent enemy/neutral territories

**Role 2: MCTS rollout opponent model**

- During MCTS rollout simulations, all houses use `get_greedy_move()` to pick moves.
- This replaces random rollouts entirely.
- Must be importable by `mcts.py`.

---

## Algorithm 4 — A* (no change)

- `get_path(map, start, goal) -> list`
- Edge weight: `defense_bonus` of destination territory

No modifications needed.

---

## Algorithm 5 — Fuzzy Logic (modify scope)

Fuzzy Logic runs in two contexts.

### Context A — Evaluating own diplomatic landscape

| Input | Meaning |
|---|---|
| `enemy_strength` | combined military threat (0–100) |
| `own_weakness` | current vulnerability (0–100) |
| `trust_history` | avg trust toward enemies (0–100) |

Output: `{"alliance": float, "betrayal": float, "solo": float}`

### Context B — Evaluating incoming alliance proposal

| Input | Meaning |
|---|---|
| `enemy_strength` | proposal sender's military (0–100) |
| `own_weakness` | receiver's current weakness (0–100) |
| `trust_history` | trust score toward sender (0–100) |

Output: same structure — scores passed to MCTS for the accept vs reject decision.

### Single function for both contexts

```python
evaluate_diplomacy(enemy_strength, own_weakness, trust_history) -> dict
```

> Fuzzy outputs **scores ONLY**. It never outputs a decision directly. MCTS always makes the final call.

**Membership functions:** `trimf`, low / medium / high

### Rules (unchanged)

1. `enemy_strength` HIGH & `own_weakness` HIGH → **alliance HIGH**
2. `trust_history` LOW & `enemy_strength` MEDIUM → **alliance LOW**
3. `own_weakness` LOW & `enemy_strength` LOW → **betrayal HIGH**
4. `own_weakness` LOW & `trust_history` HIGH → **solo HIGH**
5. `enemy_strength` HIGH & `trust_history` HIGH → **alliance MEDIUM**
6. `trust_history` LOW → **betrayal MEDIUM**

---

## Algorithm 6 — Minimax (modify evaluation function)

Replace the old flat evaluation function with:

```python
def evaluate(house, enemies, map):
    own_territory_score = sum(
        t.resource_value + t.defense_bonus
        for t in house.territories
    )
    throne_bonus = 500 if map.iron_throne in house.territories else 0
    enemy_score = sum(
        sum(t.resource_value for t in e.territories) + e.armies * 1.5
        for e in enemies
    )
    return (
        own_territory_score * 2 +
        house.armies * 1.5 +
        house.gold * 0.5 +
        throne_bonus -
        enemy_score
    )
```

### Decomposed mode (no active enemy alliance)

```python
total = H2.get_military_strength() + H3.get_military_strength()
w2 = H2.get_military_strength() / total
w3 = H3.get_military_strength() / total
score = w2 * evaluate(H1, [H2], map) + w3 * evaluate(H1, [H3], map)
# Heuristic approximation — opponent interactions evaluated independently.
```

### Paranoid mode (enemy alliance active)

```python
score = evaluate(H1, [H2, H3], map)
# Assumption literally valid while alliance holds. MCTS accounts for breakdown.
```

### Switch logic (unchanged)

```python
if diplomacy.are_allied(H2, H3):
    # use paranoid mode
else:
    # use decomposed mode
```

- Alpha-Beta Pruning in both modes.
- Depth limit: `MINIMAX_DEPTH = 3`

---

## Algorithm 7 — MCTS (modify for two contexts)

**Context A — Own diplomatic decision**
- Actions: `["propose_alliance", "betray", "solo"]`
- Fuzzy biases from Context A evaluation

**Context B — Responding to incoming proposal**
- Actions: `["accept", "reject"]`
- Fuzzy biases from Context B evaluation

### UCT formula (both contexts)

```
UCT = (Q/N) + UCT_C * sqrt(ln(N_parent) / N) + fuzzy_score[action]
UCT_C = 1.414
```

### Rollout policy

All houses use `get_greedy_move()` during simulation — **NOT random moves**.

### Alliance breakdown in rollouts

Each rollout step:

```python
p_break = 1 - (trust_history / 100)
if random() < p_break:
    # alliance breaks; switch to solo play for remainder of rollout
```

### Reward function (strictly prioritized)

```python
if iron_throne_captured:
    return 1000
return (0.5 * territory_score +
        0.3 * military_strength +
        0.2 * resource_score -
        0.4 * alliance_risk_penalty)
```

- Iterations: `MCTS_ITER = 500`
- Rollout depth: `MCTS_ROLLOUT_DEPTH = 10`

### Exposed API

```python
get_diplomacy_decision(house, all_houses, map, fuzzy_scores, diplomacy)
    -> ("propose_alliance" | "betray" | "solo", target_house)

get_proposal_response(house, proposer, all_houses, map, fuzzy_scores, diplomacy)
    -> ("accept" | "reject")
```

---

## Diplomacy System (modify `diplomacy.py`)

Add to the `Diplomacy` class:

- `pending_proposals` (dict) — tracks who proposed to whom and on which turn

Methods to add/modify:

- `queue_proposal(proposer, target, turn)`
- `get_proposal(target_house) -> proposal or None`
- `resolve_proposal(proposer, target, accepted: bool)`
  - if accepted: `form_alliance(proposer, target)`
  - else: log rejection
- `break_alliance(h1, h2)`
  - `allied_with = None` for both
  - `update_trust(h1, h2, "betray")`
  - switch both to Decomposed Minimax immediately

Trust updates (unchanged):

- `"betray"` → `trust -= 30`
- `"keep"` → `trust += 5`

---

## Combat System (modify `combat.py`)

Update `resolve_combat()` with the casualty model:

```python
attacker_power = attacker.armies * random(0.8, 1.2)
defender_power = defender.armies * territory.defense_bonus * random(0.8, 1.2)

if attacker_power > defender_power:
    attacker.armies -= int(defender.armies * 0.5)
    defender.armies -= int(defender.armies * 0.8)
    # territory transfers to attacker
    if defender had gold and no territories left:
        attacker.gold += defender.gold
        defender.gold = 0
else:
    attacker.armies -= int(attacker.armies * 0.6)
    defender.armies -= int(defender.armies * 0.2)
    # territory stays with defender
```

Both sides always take casualties. The result dict must include:

- `winner`, `loser`, `territory`
- `attacker_losses`, `defender_losses`
- `territory_transferred` (bool)

---

## Starting Values (update `constants.py`)

| House | Gold | Armies |
|---|---|---|
| Stark | 50 | 10 |
| Lannister | 70 | 15 |
| Targaryen | 40 | 12 |

**Starting territories:**

| Territory | Resource | Defense | Owner |
|---|---|---|---|
| Winterfell | 8 | 3 | Stark |
| Casterly Rock | 10 | 2 | Lannister |
| Dragonstone | 6 | 4 | Targaryen |
| King's Landing (Iron Throne) | 15 | 2 | Neutral |
| All others | — | — | Neutral |

The Iron Throne (King's Landing) is worth a **500 bonus** in Minimax evaluation.

---

## Renderer — Update HUD (modify `renderer.py`)

Add to each house card:

- **Inbox indicator:** "PROPOSAL PENDING" if inbox has a pending proposal
- **Active Minimax mode:** Decomposed / Paranoid
- **Fuzzy scores:** ALLY / BETRAY / SOLO (0.0–1.0) shown as labeled progress bars

Turn log format:

```
[Turn N] [House] used [Algo]: [Decision]
```

Diplomacy events:

```
[Turn N] [House] proposed alliance to [House]
[Turn N] [House] accepted/rejected alliance
[Turn N] [House] betrayed [House]
```

---

## Algorithm Interaction Chains — Preserve These

1. **Own diplomacy:** Fuzzy (Context A) → biases MCTS (Context A) → propose/betray/solo decision → if propose: queue in target inbox → if betray: break alliance, switch Minimax mode
2. **Responding to proposal:** Fuzzy (Context B) → biases MCTS (Context B) → accept/reject decision → if accept: alliance active, Paranoid Minimax
3. **Post-elimination:** Third house eliminated → MCTS immediately re-evaluates alliance utility → Fuzzy detects rising betray desirability → alliance breaks naturally, no scripting needed
4. **Combat:** Minimax → picks target territory → A* → routes troops to target → Combat → resolves with casualty model
5. **Greedy reuse:** Greedy → standalone attack selection; Greedy → MCTS rollout opponent model

---

## Known Approximations — Document in Code

1. **Decomposed Minimax:** opponent interactions evaluated independently — may underestimate coordination.
2. **Paranoid Minimax:** assumes full coalition cooperation — valid while alliance holds, not after breakdown.
3. **MCTS rollouts:** use Greedy opponent model, not true recursive MCTS — computationally tractable tradeoff.
4. **Fuzzy Logic:** stateless — evaluates current snapshot only, not future trajectory.

---

## Modification Order

Modify files in this order:

1. `constants.py` — update starting values
2. `house.py` — add inbox system
3. `diplomacy.py` — add proposal queue, break logic
4. `algorithms/fuzzy_diplomacy.py` — add Context B
5. `algorithms/minimax.py` — update evaluation function
6. `algorithms/mcts.py` — add Context B response
7. `algorithms/greedy.py` — verify rollout exportability
8. `combat.py` — update casualty model
9. `renderer.py` — update HUD
10. `main.py` — update turn loop

> Paste the existing file before requesting each modification. Modify only what is specified. Do not rewrite unrelated logic.
