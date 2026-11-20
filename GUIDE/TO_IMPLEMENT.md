# TO_IMPLEMENT — Spec Gaps & Deviations

Audit of the codebase against [`instructions.md`](instructions.md), recorded 2026-11-20.

**Headline: the spec is substantially implemented.** All seven algorithms exist, both fuzzy
contexts are wired, both Minimax modes switch correctly, the MCTS API matches, the diplomacy
proposal queue is complete, and the HUD renders the required indicators. What follows is the
residue: values that drifted from the spec, behaviours the code added without the spec saying so,
and a small number of genuine gaps.

Items are ordered by how much they would matter to a grader or a player.

---

## A. Deviations from specified values

These are places where the code and `instructions.md` disagree on a number. Each needs a decision:
**change the code, or update the spec.** Leaving them divergent is the only wrong answer, because
the spec is the submitted design document.

### A1. Starting gold and armies do not match the spec

`constants.py:58-60` vs `instructions.md` "Starting Values".

| House | Spec gold | Code gold | Spec armies | Code armies |
|---|---|---|---|---|
| Stark | 50 | **60** | 10 | **14** |
| Lannister | 70 | **65** | 15 | **14** |
| Targaryen | 40 | **45** | 12 | 12 ✅ |

The code's values are noticeably **flatter** — Stark and Lannister are identical at 14 armies,
where the spec gave Lannister a clear early-army lead (15 vs 10) in exchange for Stark's
positioning. This looks like deliberate balance tuning rather than an oversight, but it is
undocumented.

**Action:** if the flatter spread was intentional, amend the spec table and note the reason
(fairness across the three playable houses). Otherwise restore the spec values.

### A2. Starting territory resource values do not match the spec

`map.py:66, 73` vs the spec's "Starting territories" table.

| Territory | Spec resource | Code resource | Defense |
|---|---|---|---|
| Winterfell | 8 | **9** | 3 ✅ |
| Casterly Rock | 10 | **9** | 2 ✅ |
| Dragonstone | 6 | 6 ✅ | 4 ✅ |
| King's Landing | 15 | 15 ✅ | 2 ✅ |

Same pattern as A1 — the two seats were levelled to 9/9. Defence values and King's Landing are
untouched.

**Action:** same decision as A1; keep them consistent with each other.

---

## B. Undocumented behaviour the code adds

The code works, but these behaviours appear nowhere in `instructions.md`. For a project graded
against its design document, **unspecified behaviour is as much a gap as missing behaviour.** Each
should be written into the spec.

### B1. `MAX_RECRUITS_PER_TURN = 3` — a hard cap the spec never mentions

`constants.py:52`, applied at `main.py:241`.

The spec says step 9 is `recruit_armies()` **"based on available gold."** The code adds a cap of 3
armies per turn plus a 15-gold reserve floor.

This is not a minor detail — **it changes the entire economic shape of the game.** Gold ceases to
be a meaningful resource (a house with 167 gold recruits exactly as fast as one with 20), and every
house grows at an identical +3/turn. The in-code comment gives the rationale ("prevent instant
snowball") and it is a defensible design choice, but it must be in the spec.

**Action:** document the cap, the 15-gold floor, and the snowball rationale. Consider whether gold
should retain *some* role — the current rules leave it nearly inert once a house clears 15.

### B2. MCTS reward scaling and the rival-throne rule

`algorithms/mcts.py:38, 185-189`. Three additions to the specified reward function:

- `REWARD_SCALE = 100` divides every reward before it enters UCT, so `Q/N` stays comparable with
  the exploration term and the fuzzy bias (both ~0–1). Without it, UCT degenerates into pure
  exploitation — **this one is load-bearing**, not cosmetic.
- A rival capturing the throne returns `0.5 ×` the positional reward rather than 0, to keep actions
  distinguishable when rivals often win the race.
- `max(0.0, …)` clamps negative rewards.

**Action:** add all three to the spec's reward section with their rationales.

### B3. `alliance_risk_penalty` is never defined in the spec

The spec's reward formula includes a `-0.4 × alliance_risk_penalty` term but never says how the
penalty is computed. The code defines it in `_rollout`: seeded at `30.0` for a root `betray`
action, `+10` per alliance break, and `+(1 - trust/100) × 5` per surviving allied step.

**Action:** document the accumulator. It is a real modelling decision, not an implementation
detail.

### B4. Greedy tie-break and `enemies=None` semantics

`algorithms/greedy.py:19, 29`.

- Ties in `resource_value - defense_bonus` resolve toward the Iron Throne. Needed for determinism,
  since candidates come from a `set` whose iteration order is not stable.
- `enemies=None` means "anyone not me" rather than "no valid targets."

**Action:** one line each in the Greedy section.

### B5. MCTS partner selection heuristic

`algorithms/mcts.py:237`. With no existing ally, a house courts the **most-trusted** house, ties
broken toward the **weaker** one (ally against the strongest). Acceptance is modelled as
probability `trust/100`.

The spec defines the API's return type but never says how `target_house` is chosen. This is a
substantive strategic rule.

**Action:** document it.

### B6. Minimax hold-move and army-sufficiency restraint

`algorithms/minimax.py:92-93` and the `None` entry in `root_moves`.

- Below `MIN_ATTACK_ARMIES = 5`, generated moves are restricted to neutral territories only.
- `None` is included among root moves, which is how "hold this turn" becomes scoreable.

`MIN_ATTACK_ARMIES` itself appears in `constants.py` but in no spec section.

**Action:** document both, and note explicitly that the restraint applies **only to Minimax move
generation** — it is *not* enforced on the human player's attacks (see D2).

### B7. Trust is symmetric, despite pair-keyed storage

`diplomacy.py:92-93` writes `(k1, k2)` **and** `(k2, k1)` to the same value. So although the data
structure is directional, trust is effectively bilateral — a betrayer's own trust toward the victim
drops by 30 as well.

**Action:** either document that trust is bilateral by design, or make it directional, which would
be the more interesting model (a betrayer is not themselves made distrustful by their own act).

### B8. `dissolve_alliance` — a third lifecycle method

`diplomacy.py:65`. The spec lists only `form_alliance` and `break_alliance`. The code adds
`dissolve_alliance` for ending a pact **without** a trust penalty — used when a partner is
eliminated (`main.py:146`). `break_alliance` is implemented on top of it.

Note also that the spec's "switch both to Decomposed immediately" requirement is satisfied *inside*
`dissolve_alliance`, not in `break_alliance`. Correct, but it reads as a gap when tracing the spec
line by line.

**Action:** add `dissolve_alliance` to the spec's method list and note the delegation.

---

## C. UI / presentation defects

### C1. The defence tooltip is misleading — reads additive, is multiplicative

`renderer.py:2285` renders `Fortifications: +{def_bonus} Defense`, and `renderer.py:2294` renders
`Defense Fortification: +{def_bonus}`.

Both imply **addition**. The mechanic is **multiplication** (`combat.py:31`):

> King's Landing shows "+2 Defense" with a 14-army garrison. A player reasonably reads this as
> defence 16 and attacks with 21 armies — but the true defence is 14 × 2 = **28**, and the attack
> succeeds only ~4% of the time.

This is the single most player-hostile issue in the audit: the HUD actively causes losing
decisions.

**Action:** render `Fortifications: ×{def_bonus} Defense` and, better, show the computed effective
defence (`garrison × bonus`) for neutral territories so the player can compare directly against
their own army count.

### C2. Effective defence is not shown anywhere

Following from C1 — a player cannot see `garrison × defense_bonus` without doing the arithmetic,
and that product is the only number that actually matters when choosing a target.

**Action:** add an "Effective Defence" line to the territory tooltip.

---

## D. Genuine gaps

### D1. Interaction Chain 3 is asserted but never verified

`instructions.md` chain 3 claims:

> Third house eliminated → MCTS immediately re-evaluates alliance utility → Fuzzy detects rising
> betray desirability → alliance breaks naturally, no scripting needed.

The machinery plausibly supports this (`get_proposal_response` rejects when ≤2 houses survive, and
`get_diplomacy_decision` offers `betray` whenever an ally exists), but **nothing tests it**, and the
claim "no scripting needed" is an emergent-behaviour assertion that should be demonstrated.

**Action:** add a scenario test — eliminate the third house with an alliance active and assert the
pact breaks within N turns. This is the most defensible single claim in the design document and
currently rests on nothing.

### D2. `MIN_ATTACK_ARMIES` is not enforced on the human player

`algorithms/minimax.py:93` is the only consumer. The human attack path (`main.py:363-370`) applies
no army-sufficiency check, so a human house may attack a house-held territory with 1 army where an
AI house in the same position would be restricted to neutrals.

**Action:** decide whether this is an intentional human affordance or an asymmetry bug, then
document or fix it.

### D3. No automated test suite

There are no tests anywhere in the repository. For a project whose core claims are probabilistic
(4% capture odds, alliance breakdown rates, UCT convergence), the absence is significant — none of
the design document's quantitative claims are verified.

**Action (minimum viable):**
- `combat.resolve_combat` — win/loss casualty arithmetic and territory transfer.
- `fuzzy_diplomacy.evaluate_diplomacy` — the NumPy fallback matches `skfuzzy` within tolerance, and
  the all-zero no-rule-fired case.
- `bfs.get_reachable` — radius semantics, including that `start` is in the result.
- `diplomacy` — the full propose → accept → betray lifecycle, including mode switching.

### D4. `instructions.txt` and `instructions.md` are duplicate sources of truth

Both files carry the same spec in different formats. They will drift — and any fix from section A
or B has to be applied twice.

**Action:** keep `instructions.md`, delete `instructions.txt` (it is in git history if needed).

---

## Suggested order of work

1. **C1** — one-line fix, removes an actively misleading HUD element.
2. **A1, A2** — reconcile spec and code values; cheapest way to close a grader's most obvious
   finding.
3. **B1** — document the recruitment cap; it has the largest unstated effect on gameplay.
4. **D4** — collapse the duplicate spec before editing it further.
5. **B2–B8** — fold the remaining undocumented behaviour into the spec.
6. **D3, D1** — add the test suite, starting with the Chain 3 scenario.
7. **C2, D2** — polish and the human/AI asymmetry decision.
