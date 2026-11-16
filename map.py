"""Graph-based territory map and hex terrain model for Game of Thrones: AI Conquest."""

from __future__ import annotations

import math


class Territory:
    """Named seat of power on the Westeros map."""

    def __init__(
        self,
        name: str,
        col: int,
        row: int,
        feature: str,
        resource_value: int,
        defense_bonus: int,
        armies: int = 3,
        owner: str | None = None,
        is_iron_throne: bool = False,
    ) -> None:
        self.name = name
        self.col = col
        self.row = row
        self.feature = feature
        self.resource_value = resource_value
        self.defense_bonus = defense_bonus
        self.armies = armies
        self.owner = owner
        self.is_iron_throne = is_iron_throne
        self.neighbors: list[Territory] = []

    def __repr__(self) -> str:
        return f"Territory({self.name!r}, owner={self.owner!r}, armies={self.armies})"


LANDMARKS: dict[tuple[int, int], tuple[str, str, int, str | None]] = {
    (6, 1): ("THE WALL", "snow", 3, None),
    (9, 1): ("CASTLE BLACK", "castle", 2, "STARK"),
    (4, 2): ("WINTERFELL", "castle", 8, "STARK"),
    (7, 3): ("MOAT CAILIN", "ruins", 3, None),
    (1, 2): ("PYKE", "harbor", 2, None),
    (4, 4): ("RIVERRUN", "castle", 3, None),
    (11, 2): ("THE EYRIE", "castle", 2, None),
    (7, 5): ("HARRENHAL", "ruins", 4, None),
    (10, 4): ("KING'S LANDING", "royal", 5, None),
    (12, 6): ("DRAGONSTONE", "castle", 7, "TARGARYEN"),
    (10, 6): ("STORM'S END", "castle", 3, None),
    (5, 6): ("HIGHGARDEN", "farm", 3, None),
    (2, 6): ("CASTERLY ROCK", "mine", 8, "LANNISTER"),
    (1, 4): ("LANNISPORT", "harbor", 3, None),
    (8, 7): ("DORNE", "farm", 3, None),
}

TERRITORY_SPECS: list[tuple[str, int, int, str, int, int, int, str | None, bool]] = [
    # (name, col, row, feature, resource_value, defense_bonus, armies, owner, is_iron_throne)
    # `armies` is the neutral garrison; house-owned seats are defended by the house's army pool.
    ("THE WALL", 6, 1, "snow", 4, 3, 3, None, False),
    ("CASTLE BLACK", 9, 1, "castle", 5, 2, 2, None, False),
    ("WINTERFELL", 4, 2, "castle", 9, 3, 0, "STARK", False),
    ("MOAT CAILIN", 7, 3, "ruins", 5, 2, 3, None, False),
    ("PYKE", 1, 2, "harbor", 4, 2, 3, None, False),
    ("RIVERRUN", 4, 4, "castle", 5, 2, 4, None, False),
    ("THE EYRIE", 11, 2, "castle", 6, 3, 3, None, False),
    ("HARRENHAL", 7, 5, "ruins", 4, 1, 4, None, False),
    ("KING'S LANDING", 10, 4, "royal", 15, 2, 14, None, True),
    ("DRAGONSTONE", 12, 6, "castle", 6, 4, 0, "TARGARYEN", False),
    ("STORM'S END", 10, 6, "castle", 5, 2, 4, None, False),
    ("HIGHGARDEN", 5, 6, "farm", 6, 2, 4, None, False),
    ("CASTERLY ROCK", 2, 6, "mine", 9, 2, 0, "LANNISTER", False),
    ("LANNISPORT", 1, 4, "harbor", 5, 2, 3, None, False),
    ("DORNE", 8, 7, "farm", 5, 2, 4, None, False),
]

TERRITORY_EDGES: list[tuple[str, str]] = [
    ("THE WALL", "CASTLE BLACK"),
    ("CASTLE BLACK", "WINTERFELL"),
    ("THE WALL", "WINTERFELL"),
    ("WINTERFELL", "MOAT CAILIN"),
    ("WINTERFELL", "THE EYRIE"),
    ("MOAT CAILIN", "RIVERRUN"),
    ("MOAT CAILIN", "HARRENHAL"),
    ("MOAT CAILIN", "THE EYRIE"),
    ("PYKE", "RIVERRUN"),
    ("PYKE", "LANNISPORT"),
    ("RIVERRUN", "CASTERLY ROCK"),
    ("RIVERRUN", "HARRENHAL"),
    ("RIVERRUN", "HIGHGARDEN"),
    ("THE EYRIE", "HARRENHAL"),
    ("THE EYRIE", "KING'S LANDING"),
    ("HARRENHAL", "KING'S LANDING"),
    ("HARRENHAL", "HIGHGARDEN"),
    ("KING'S LANDING", "STORM'S END"),
    ("KING'S LANDING", "DRAGONSTONE"),
    ("KING'S LANDING", "HIGHGARDEN"),
    ("KING'S LANDING", "DORNE"),
    ("DRAGONSTONE", "STORM'S END"),
    ("STORM'S END", "DORNE"),
    ("HIGHGARDEN", "CASTERLY ROCK"),
    ("HIGHGARDEN", "DORNE"),
    ("CASTERLY ROCK", "LANNISPORT"),
]

RIVERS: list[list[tuple[int, int]]] = [
    [(5, 1), (5, 2), (5, 3), (4, 4), (3, 5)],
    [(8, 2), (8, 3), (8, 4), (9, 4), (9, 5)],
]

ROADS: list[tuple[tuple[int, int], tuple[int, int]]] = [
    ((6, 1), (4, 2)),
    ((9, 1), (7, 3)),
    ((4, 2), (7, 3)),
    ((7, 3), (4, 4)),
    ((4, 4), (2, 6)),
    ((4, 4), (7, 5)),
    ((7, 5), (10, 4)),
    ((10, 4), (10, 6)),
    ((7, 5), (8, 7)),
    ((7, 3), (11, 2)),
    ((2, 6), (1, 4)),
    ((2, 6), (5, 6)),
]

VILLAGES: list[tuple[int, int]] = [(4, 2), (6, 3), (11, 4), (5, 6), (10, 7), (12, 4)]

FIELD_SQUADS: list[tuple[int, int, str]] = []


def on_land(col: int, row: int) -> bool:
    """Return True if hex (col, row) is part of the Westeros landmass."""
    nx = (col - 7) / 7.4
    ny = (row - 3.5) / 4.25
    coastline = (
        1.03
        + 0.075 * math.sin(col * 1.9 + row * 0.8)
        + 0.045 * math.cos(row * 2.1 - col * 0.7)
    )
    inside = nx * nx + ny * ny < coastline
    # Dragonstone sits offshore, separated from the mainland by the Narrow Sea.
    return inside and (col, row) != (12, 6)


def _cube(col: int, row: int) -> tuple[int, int, int]:
    # Odd columns are shifted down half a hex ("odd-q" offset layout).
    x = col
    z = row - (col - (col & 1)) // 2
    return x, -x - z, z


def hex_distance(a: tuple[int, int], b: tuple[int, int]) -> int:
    ax, ay, az = _cube(*a)
    bx, by, bz = _cube(*b)
    return max(abs(ax - bx), abs(ay - by), abs(az - bz))


def owner_at(col: int, row: int, game_map: Map | None = None) -> str | None:
    """Return the controlling house at hex (col, row).

    With a live map, each land hex belongs to the region of its nearest seat,
    so the painted borders follow actual territory ownership.
    """
    if game_map is not None:
        territory = game_map.region_of(col, row)
        return territory.owner if territory is not None else None
    if row <= 3 and 4 <= col <= 10:
        return "STARK"
    if 3 <= row <= 7 and col <= 5:
        return "LANNISTER"
    if 4 <= row <= 7 and col >= 10:
        return "TARGARYEN"
    return None


def terrain_at(col: int, row: int) -> str:
    """Return the terrain kind at hex (col, row)."""
    if row <= 1 or (col <= 2 and row <= 4):
        return "snow" if (col + row) % 3 else "mountain"
    if row >= 7 and col >= 8:
        return "dry"
    if 3 <= row <= 6 and (col + row) % 4 in (0, 1):
        return "forest"
    if row in (3, 4, 5) and col in (7, 8, 9):
        return "marsh"
    return "grass"


class Map:
    """Graph of named Westeros territories and hex lookup."""

    def __init__(self) -> None:
        self.territories: list[Territory] = []
        self.by_name: dict[str, Territory] = {}
        self.by_coord: dict[tuple[int, int], Territory] = {}

        for name, col, row, feature, res, defense, armies, owner, is_throne in TERRITORY_SPECS:
            territory = Territory(
                name=name,
                col=col,
                row=row,
                feature=feature,
                resource_value=res,
                defense_bonus=defense,
                armies=armies,
                owner=owner,
                is_iron_throne=is_throne,
            )
            self.territories.append(territory)
            self.by_name[name] = territory
            self.by_coord[(col, row)] = territory

        for a_name, b_name in TERRITORY_EDGES:
            t_a = self.by_name[a_name]
            t_b = self.by_name[b_name]
            if t_b not in t_a.neighbors:
                t_a.neighbors.append(t_b)
            if t_a not in t_b.neighbors:
                t_b.neighbors.append(t_a)

        self.iron_throne: Territory = next(t for t in self.territories if t.is_iron_throne)

        # Precompute which seat each land hex belongs to (nearest within 2 hexes).
        self._regions: dict[tuple[int, int], Territory | None] = {}
        for col in range(15):
            for row in range(8):
                if not on_land(col, row) and (col, row) not in self.by_coord:
                    continue
                nearest = min(self.territories, key=lambda t: hex_distance((col, row), (t.col, t.row)))
                close = hex_distance((col, row), (nearest.col, nearest.row)) <= 3
                self._regions[(col, row)] = nearest if close else None

    def region_of(self, col: int, row: int) -> Territory | None:
        return self._regions.get((col, row))

    def get_neighbors(self, territory: Territory | str) -> list[Territory]:
        target = self.by_name[territory] if isinstance(territory, str) else territory
        return list(target.neighbors)

    def get_owned_by(self, house: object | str) -> list[Territory]:
        house_name = house if isinstance(house, str) else getattr(house, "name", str(house))
        house_upper = house_name.upper()
        return [t for t in self.territories if (t.owner or "").upper() == house_upper]

    def get_neutral(self) -> list[Territory]:
        return [t for t in self.territories if t.owner is None]

    def capture(self, territory: Territory | str, house: object | str | None) -> None:
        target = self.by_name[territory] if isinstance(territory, str) else territory
        if house is None:
            target.owner = None
        else:
            house_name = house if isinstance(house, str) else getattr(house, "name", str(house))
            target.owner = house_name.upper()

    def get_all(self) -> list[Territory]:
        return list(self.territories)
