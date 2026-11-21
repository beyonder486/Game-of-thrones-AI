"""Combat resolution mechanics for Game of Thrones: AI Conquest."""

from __future__ import annotations

import random

from house import House
from map import Map, Territory


def effective_defense(defender_armies: float, defense_bonus: int, is_house: bool) -> float:
    """Compute effective defensive strength.

    Neutral garrisons (small 2–14 forces) scale directly by defense_bonus,
    while full Great House army pools receive a light fortification multiplier
    (1.0 + 0.05 * defense_bonus) so neighboring kingdoms actively clash instead
    of stalling in a standoff.
    """
    if is_house:
        return defender_armies * (1.0 + 0.05 * defense_bonus)
    return defender_armies * defense_bonus


class Combat:
    """Resolves battles over contested or neutral territories."""

    @staticmethod
    def resolve_combat(
        attacker: House,
        defender: House | None,
        territory: Territory,
        game_map: Map,
    ) -> dict[str, object]:
        """Casualty model — both sides always take losses.

        A neutral territory (defender is None) is defended by its own garrison.
        Captured territories and a defeated house's gold go to the capturer only.
        """
        if defender is not None and defender.name == attacker.name:
            raise ValueError("A house cannot attack its own territory.")

        defender_armies = defender.armies if defender is not None else territory.armies
        attacker_power = attacker.armies * random.uniform(0.8, 1.2)
        base_def = effective_defense(defender_armies, territory.defense_bonus, is_house=(defender is not None))
        defender_power = base_def * random.uniform(0.8, 1.2)

        if attacker_power > defender_power:
            attacker_losses = int(defender_armies * 0.5)
            defender_losses = int(defender_armies * 0.8)
            transferred = True
        else:
            attacker_losses = int(attacker.armies * 0.6)
            defender_losses = int(defender_armies * 0.2)
            transferred = False

        attacker.armies = max(1, attacker.armies - attacker_losses)
        if defender is not None:
            defender.armies = max(1, defender.armies - defender_losses)
        else:
            territory.armies = max(1, territory.armies - defender_losses)

        if transferred:
            if defender is not None:
                defender.lose_territory(territory)
            attacker.gain_territory(territory)
            game_map.capture(territory, attacker)
            territory.armies = 0  # garrison is now the attacker's army pool
            if defender is not None and defender.is_eliminated() and defender.gold > 0:
                attacker.gold += defender.gold
                defender.gold = 0

        winner = attacker if transferred else defender
        loser = defender if transferred else attacker
        return {
            "winner": winner,
            "loser": loser,
            "territory": territory,
            "attacker_losses": attacker_losses,
            "defender_losses": defender_losses,
            "territory_transferred": transferred,
        }
