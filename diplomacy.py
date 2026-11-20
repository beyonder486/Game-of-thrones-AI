"""Diplomacy, alliance pacts, trust tracking, proposals and event logging."""

from __future__ import annotations

from typing import TYPE_CHECKING

from constants import ALLY_BONUS, BETRAYAL_PENALTY, HOUSE_NAMES

if TYPE_CHECKING:
    from house import House


def _house_key(h: object | str) -> str:
    return (h if isinstance(h, str) else getattr(h, "name", str(h))).upper()


class Diplomacy:
    """Manages alliances, bilateral trust, asynchronous proposals and the Raven's Log."""

    def __init__(self, houses: list[House] | None = None) -> None:
        self.houses: dict[str, House] = {h.name: h for h in houses} if houses else {}
        self.alliances: dict[str, str | None] = {name: None for name in HOUSE_NAMES}
        self.trust_scores: dict[tuple[str, str], float] = {}
        for h1 in HOUSE_NAMES:
            for h2 in HOUSE_NAMES:
                if h1 != h2:
                    self.trust_scores[(h1, h2)] = 50.0
        # target house name -> {"from": proposer, "type": "alliance_proposal", "turn": n}
        self.pending_proposals: dict[str, dict[str, object]] = {}
        self.event_log: list[dict[str, str | int]] = []

    # ── Helpers ────────────────────────────────────────────
    def _is_alive(self, name: str) -> bool:
        house = self.houses.get(name)
        return house is None or not house.is_eliminated()

    def _surviving_count(self) -> int:
        if not self.houses:
            return len(HOUSE_NAMES)
        return sum(1 for h in self.houses.values() if not h.is_eliminated())

    def _sync_house(self, name: str) -> None:
        house = self.houses.get(name)
        if house is None:
            return
        house.allied_with = self.alliances.get(name)
        for other in HOUSE_NAMES:
            if other != name:
                house.trust_history[other] = self.trust_scores[(name, other)]

    def purge_eliminated(self, house: object | str) -> None:
        """Dissolve any pact and purge all pending proposals to/from an eliminated house."""
        k = _house_key(house)
        ally = self.alliances.get(k)
        if ally:
            self.dissolve_alliance(k, ally)
        self.pending_proposals.pop(k, None)
        if k in self.houses:
            self.houses[k].clear_inbox()
        for target_key in list(self.pending_proposals.keys()):
            prop = self.pending_proposals.get(target_key)
            if prop and _house_key(str(prop.get("from", ""))) == k:
                self.pending_proposals.pop(target_key, None)
                if target_key in self.houses:
                    self.houses[target_key].clear_inbox()
        for h in self.houses.values():
            pending = h.get_pending_proposal()
            if pending and _house_key(str(pending.get("from", ""))) == k:
                h.clear_inbox()

    # ── Alliances ──────────────────────────────────────────
    def are_allied(self, h1: object | str, h2: object | str) -> bool:
        k1, k2 = _house_key(h1), _house_key(h2)
        return self.alliances.get(k1) == k2 and self.alliances.get(k2) == k1

    def form_alliance(self, h1: object | str, h2: object | str, turn: int = 0) -> None:
        k1, k2 = _house_key(h1), _house_key(h2)
        if not self._is_alive(k1) or not self._is_alive(k2) or self._surviving_count() < 3:
            return
        for k, new_ally in ((k1, k2), (k2, k1)):
            prev = self.alliances.get(k)
            if prev and prev != new_ally:
                # Switching to a new ally while already allied is an automatic betrayal.
                self.alliances[prev] = None
                self.alliances[k] = None
                self.update_trust(k, prev, "betray")
                self.log_diplomacy(turn, k, f"betrayed {prev.title()} to ally with {new_ally.title()}")
        self.alliances[k1] = k2
        self.alliances[k2] = k1
        # All houses now operate in coalition context → Paranoid Minimax (including lone target).
        for name in HOUSE_NAMES:
            self._sync_house(name)
            if name in self.houses and not self.houses[name].is_eliminated():
                self.houses[name].mode = "PARANOID"

    def dissolve_alliance(self, h1: object | str, h2: object | str) -> None:
        """End a pact without a trust penalty (e.g. a partner was eliminated)."""
        k1, k2 = _house_key(h1), _house_key(h2)
        if self.alliances.get(k1) == k2:
            self.alliances[k1] = None
        if self.alliances.get(k2) == k1:
            self.alliances[k2] = None
        any_active = any(v is not None for v in self.alliances.values())
        for name in HOUSE_NAMES:
            self._sync_house(name)
            if name in self.houses and not any_active:
                self.houses[name].mode = "DECOMPOSED"

    def break_alliance(self, h1: object | str, h2: object | str) -> None:
        """Unilateral betrayal by h1 against h2."""
        self.dissolve_alliance(h1, h2)
        self.update_trust(h1, h2, "betray")

    # ── Trust ──────────────────────────────────────────────
    def update_trust(self, actor: object | str, other: object | str, action: str) -> float:
        k1, k2 = _house_key(actor), _house_key(other)
        current = self.trust_scores.get((k2, k1), 50.0)
        if action.lower() == "betray":
            current += BETRAYAL_PENALTY  # BETRAYAL_PENALTY is -30
        elif action.lower() == "keep":
            current += ALLY_BONUS
        current = max(0.0, min(100.0, current))
        self.trust_scores[(k2, k1)] = current
        self.trust_scores[(k1, k2)] = current
        self._sync_house(k1)
        self._sync_house(k2)
        return current

    def get_trust(self, h1: object | str, h2: object | str) -> float:
        k1, k2 = _house_key(h1), _house_key(h2)
        return self.trust_scores.get((k1, k2), 50.0)

    # ── Asynchronous proposals ─────────────────────────────
    def queue_proposal(self, proposer: object | str, target: object | str, turn: int) -> None:
        k1, k2 = _house_key(proposer), _house_key(target)
        if not self._is_alive(k1) or not self._is_alive(k2) or self._surviving_count() < 3:
            return
        proposal = {"from": k1, "type": "alliance_proposal", "turn": turn}
        self.pending_proposals[k2] = proposal
        if k2 in self.houses:
            self.houses[k2].receive_proposal(proposal)
        self.log_diplomacy(turn, k1, f"proposed alliance to {k2.title()}")

    def get_proposal(self, target_house: object | str) -> dict[str, object] | None:
        return self.pending_proposals.get(_house_key(target_house))

    def resolve_proposal(
        self,
        proposer: object | str,
        target: object | str,
        accepted: bool,
        turn: int = 0,
    ) -> None:
        k1, k2 = _house_key(proposer), _house_key(target)
        self.pending_proposals.pop(k2, None)
        if k2 in self.houses:
            self.houses[k2].clear_inbox()
        if accepted and self._is_alive(k1) and self._is_alive(k2) and self._surviving_count() >= 3:
            self.form_alliance(k1, k2, turn=turn)
            self.log_diplomacy(turn, k2, f"accepted alliance with {k1.title()}")
        elif not accepted:
            self.log_diplomacy(turn, k2, f"rejected alliance with {k1.title()}")

    # ── Raven's Log ────────────────────────────────────────
    def _push(self, entry: dict[str, str | int]) -> None:
        self.event_log.append(entry)
        if len(self.event_log) > 24:
            del self.event_log[:-24]

    def log_event(self, turn: int, house: object | str, algo: str, decision: str) -> None:
        """Format: "[Turn N] [House] used [Algo]: [Decision]"."""
        self._push({"turn": turn, "house": _house_key(house), "text": f"used {algo}: {decision}"})

    def log_diplomacy(self, turn: int, house: object | str, text: str) -> None:
        self._push({"turn": turn, "house": _house_key(house), "text": text})
