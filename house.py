"""House state and economy logic for Game of Thrones: AI Conquest."""

from __future__ import annotations

from constants import (
    ARMY_COST,
    BASE_INCOME,
    HOUSE_COLORS,
    HOUSE_MOTTOS,
    HOUSE_NAMES,
    STARTING_VALUES,
)
from map import Map, Territory


class House:
    """Represents one of the Great Houses competing for the Iron Throne."""

    def __init__(
        self,
        name: str,
        color: tuple[int, int, int] | None = None,
        gold: int = 40,
        armies: int = 15,
        motto: str = "",
        status: str = "ACTIVE",
        mode: str = "DECOMPOSED",
        fuzzy_scores: dict[str, float] | None = None,
    ) -> None:
        self.name = name.upper()
        self.color = color or HOUSE_COLORS.get(self.name, (200, 200, 200))
        self.gold = gold
        self.armies = armies
        self.territories: list[Territory] = []
        self.allied_with: str | None = None
        self.trust_history: dict[str, float] = {}
        self.inbox: list[dict[str, object]] = []  # pending diplomatic proposals
        self.motto = motto
        self.status = status
        self.mode = mode
        self.is_human = False
        self.fuzzy_scores: dict[str, float] = fuzzy_scores or {
            "alliance": 0.0,
            "betrayal": 0.0,
            "solo": 0.0,
        }
        self.reachable_holds: set[Territory] = set()
        self.expansion_paths: list[list[Territory]] = []
        self.last_trace: dict[str, object] = {}

    # ── Economy ────────────────────────────────────────────
    def collect_income(self) -> int:
        income = BASE_INCOME + sum(t.resource_value for t in self.territories)
        self.gold += income
        return income

    def recruit_armies(self, n: int) -> bool:
        cost = n * ARMY_COST
        if n > 0 and self.gold >= cost:
            self.gold -= cost
            self.armies += n
            return True
        return False

    # ── Territory ──────────────────────────────────────────
    def lose_territory(self, territory: Territory) -> None:
        if territory in self.territories:
            self.territories.remove(territory)
        if territory.owner == self.name:
            territory.owner = None

    def gain_territory(self, territory: Territory) -> None:
        territory.owner = self.name
        if territory not in self.territories:
            self.territories.append(territory)

    def is_eliminated(self) -> bool:
        return len(self.territories) == 0

    def get_military_strength(self) -> float:
        return float(self.armies + sum(t.defense_bonus for t in self.territories))

    # ── Diplomatic inbox ───────────────────────────────────
    def receive_proposal(self, proposal: dict[str, object]) -> None:
        """Queue a proposal: {"from": house_name, "type": "alliance_proposal", "turn": n}."""
        # Only one outstanding proposal per sender.
        self.inbox = [p for p in self.inbox if p.get("from") != proposal.get("from")]
        self.inbox.append(proposal)

    def get_pending_proposal(self) -> dict[str, object] | None:
        return self.inbox[0] if self.inbox else None

    def clear_inbox(self) -> None:
        self.inbox.clear()


def create_initial_houses(game_map: Map) -> list[House]:
    """Create the three Great Houses with their starting gold, armies and seat."""
    houses: list[House] = []
    for name in HOUSE_NAMES:
        start = STARTING_VALUES[name]
        house = House(
            name=name,
            color=HOUSE_COLORS[name],
            gold=start["gold"],
            armies=start["armies"],
            motto=HOUSE_MOTTOS[name],
        )
        for territory in game_map.get_owned_by(name):
            house.gain_territory(territory)
        houses.append(house)

    for h1 in houses:
        for h2 in houses:
            if h1.name != h2.name:
                h1.trust_history[h2.name] = 50.0
    return houses
