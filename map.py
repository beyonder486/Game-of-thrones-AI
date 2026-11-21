"""Graph-based territory map and hex terrain model for Game of Thrones: AI Conquest."""

from __future__ import annotations

import math

from constants import DRAGONSTONE_COORD, GRID_COLS, GRID_ROWS


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
    (8, 1): ("THE WALL", "snow", 3, None),
    (12, 1): ("CASTLE BLACK", "castle", 2, None),
    (16, 1): ("DREADFORT", "castle", 3, None),
    (1, 2): ("PYKE", "harbor", 3, None),
    (5, 2): ("WINTERFELL", "castle", 8, "STARK"),
    (9, 2): ("MOAT CAILIN", "ruins", 3, None),
    (14, 2): ("WHITE HARBOR", "harbor", 3, None),
    (17, 3): ("THE EYRIE", "castle", 3, None),
    (1, 4): ("LANNISPORT", "harbor", 3, None),
    (4, 4): ("RIVERRUN", "castle", 4, None),
    (7, 4): ("THE TWINS", "castle", 3, None),
    (10, 4): ("KING'S LANDING", "royal", 14, None),
    (13, 4): ("HARRENHAL", "ruins", 4, None),
    (2, 6): ("CASTERLY ROCK", "mine", 8, "LANNISTER"),
    (5, 7): ("OLDTOWN", "harbor", 3, None),
    (8, 6): ("HIGHGARDEN", "farm", 4, None),
    (12, 7): ("DORNE", "farm", 4, None),
    (15, 6): ("STORM'S END", "castle", 4, None),
    (18, 6): ("DRAGONSTONE", "castle", 7, "TARGARYEN"),
}

TERRITORY_SPECS: list[tuple[str, int, int, str, int, int, int, str | None, bool]] = [
    # (name, col, row, feature, resource_value, defense_bonus, armies, owner, is_iron_throne)
    # `armies` is the neutral garrison; house-owned seats are defended by the house's army pool.
    ("THE WALL", 8, 1, "snow", 4, 3, 3, None, False),
    ("CASTLE BLACK", 12, 1, "castle", 5, 2, 2, None, False),
    ("DREADFORT", 16, 1, "castle", 5, 3, 3, None, False),
    ("PYKE", 1, 2, "harbor", 4, 2, 3, None, False),
    ("WINTERFELL", 5, 2, "castle", 9, 3, 0, "STARK", False),
    ("MOAT CAILIN", 9, 2, "ruins", 5, 2, 3, None, False),
    ("WHITE HARBOR", 14, 2, "harbor", 6, 2, 3, None, False),
    ("THE EYRIE", 17, 3, "castle", 6, 3, 3, None, False),
    ("LANNISPORT", 1, 4, "harbor", 5, 2, 3, None, False),
    ("RIVERRUN", 4, 4, "castle", 5, 2, 4, None, False),
    ("THE TWINS", 7, 4, "castle", 5, 3, 3, None, False),
    ("KING'S LANDING", 10, 4, "royal", 15, 3, 10, None, True),
    ("HARRENHAL", 13, 4, "ruins", 4, 1, 4, None, False),
    ("CASTERLY ROCK", 2, 6, "mine", 9, 2, 0, "LANNISTER", False),
    ("OLDTOWN", 5, 7, "harbor", 6, 2, 3, None, False),
    ("HIGHGARDEN", 8, 6, "farm", 6, 2, 4, None, False),
    ("DORNE", 12, 7, "farm", 5, 2, 4, None, False),
    ("STORM'S END", 15, 6, "castle", 5, 2, 4, None, False),
    ("DRAGONSTONE", 18, 6, "castle", 8, 4, 0, "TARGARYEN", False),
]

TERRITORY_EDGES: list[tuple[str, str]] = [
    ("THE WALL", "CASTLE BLACK"),
    ("THE WALL", "WINTERFELL"),
    ("THE WALL", "THE TWINS"),
    ("CASTLE BLACK", "DREADFORT"),
    ("CASTLE BLACK", "WHITE HARBOR"),
    ("CASTLE BLACK", "MOAT CAILIN"),
    ("DREADFORT", "WHITE HARBOR"),
    ("DREADFORT", "THE EYRIE"),
    ("WINTERFELL", "PYKE"),
    ("WINTERFELL", "RIVERRUN"),
    ("WINTERFELL", "THE TWINS"),
    ("PYKE", "LANNISPORT"),
    ("PYKE", "RIVERRUN"),
    ("WHITE HARBOR", "MOAT CAILIN"),
    ("WHITE HARBOR", "THE EYRIE"),
    ("WHITE HARBOR", "KING'S LANDING"),
    ("MOAT CAILIN", "THE TWINS"),
    ("MOAT CAILIN", "HARRENHAL"),
    ("MOAT CAILIN", "KING'S LANDING"),
    ("THE EYRIE", "KING'S LANDING"),
    ("THE EYRIE", "DRAGONSTONE"),
    ("LANNISPORT", "RIVERRUN"),
    ("LANNISPORT", "CASTERLY ROCK"),
    ("RIVERRUN", "THE TWINS"),
    ("RIVERRUN", "CASTERLY ROCK"),
    ("RIVERRUN", "HIGHGARDEN"),
    ("THE TWINS", "HIGHGARDEN"),
    ("THE TWINS", "HARRENHAL"),
    ("KING'S LANDING", "HARRENHAL"),
    ("KING'S LANDING", "DORNE"),
    ("KING'S LANDING", "STORM'S END"),
    ("HARRENHAL", "HIGHGARDEN"),
    ("HARRENHAL", "DORNE"),
    ("CASTERLY ROCK", "OLDTOWN"),
    ("OLDTOWN", "HIGHGARDEN"),
    ("HIGHGARDEN", "DORNE"),
    ("DORNE", "STORM'S END"),
    ("STORM'S END", "DRAGONSTONE"),
]

RIVERS: list[list[tuple[int, int]]] = [
    [(8, 1), (7, 2), (7, 3), (7, 4), (8, 5), (9, 6)],
    [(12, 1), (12, 2), (12, 3), (13, 4), (14, 5), (15, 6)],
]

ROADS: list[tuple[tuple[int, int], tuple[int, int]]] = [
    ((8, 1), (5, 2)),
    ((8, 1), (12, 1)),
    ((12, 1), (16, 1)),
    ((5, 2), (1, 2)),
    ((5, 2), (9, 2)),
    ((5, 2), (4, 4)),
    ((9, 2), (10, 4)),
    ((12, 1), (9, 2)),
    ((14, 2), (13, 4)),
    ((16, 1), (17, 3)),
    ((17, 3), (13, 4)),
    ((4, 4), (1, 4)),
    ((4, 4), (2, 6)),
    ((4, 4), (7, 4)),
    ((7, 4), (10, 4)),
    ((10, 4), (13, 4)),
    ((10, 4), (8, 6)),
    ((10, 4), (12, 7)),
    ((13, 4), (15, 6)),
    ((2, 6), (5, 7)),
    ((5, 7), (8, 6)),
    ((8, 6), (12, 7)),
    ((12, 7), (15, 6)),
]

VILLAGES: list[tuple[int, int]] = [(4, 2), (6, 3), (11, 4), (5, 6), (10, 7), (12, 4)]

FIELD_SQUADS: list[tuple[int, int, str]] = []


def on_land(col: int, row: int) -> bool:
    """Return True if hex (col, row) is part of the Westeros landmass."""
    nx = (col - 9.6) / 9.7
    ny = (row - 3.5) / 4.25
    coastline = (
        1.03
        + 0.065 * math.sin(col * 1.6 + row * 0.9)
        + 0.045 * math.cos(row * 2.1 - col * 0.6)
    )
    inside = nx * nx + ny * ny < coastline
    # Dragonstone sits offshore across the Narrow Sea.
    return inside and (col, row) != DRAGONSTONE_COORD


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
    if row <= 1 or (col <= 3 and row <= 3):
        return "snow" if (col + row) % 3 else "mountain"
    if col in (16, 17, 18) and row in (2, 3):
        return "mountain"
    if row >= 7 and col >= 10:
        return "dry"
    if row in (3, 4) and col in (9, 10, 11):
        return "marsh"
    if 2 <= row <= 6 and (col + row) % 4 in (0, 1):
        return "forest"
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

        self.iron_throne: Territory = next(t for t in self.territories if t.is_iron_throne)

        # Partition every land hex cleanly into nearest territory Voronoi region.
        self._regions: dict[tuple[int, int], Territory | None] = {}
        for col in range(GRID_COLS):
            for row in range(GRID_ROWS):
                if not on_land(col, row) and (col, row) not in self.by_coord:
                    continue
                nearest = min(
                    self.territories,
                    key=lambda t: (
                        hex_distance((col, row), (t.col, t.row)),
                        math.hypot((col - t.col) * 1.5, (row - t.row) * 1.732),
                    ),
                )
                self._regions[(col, row)] = nearest

        # Derive graph neighbors strictly from touching regions on the hex map.
        for t in self.territories:
            t.neighbors.clear()
        touching_pairs: set[tuple[str, str]] = set()
        for (col, row), t1 in self._regions.items():
            if t1 is None:
                continue
            hex_nbs = (
                [(col + 1, row), (col, row + 1), (col - 1, row), (col - 1, row - 1), (col, row - 1), (col + 1, row - 1)]
                if col % 2 == 0
                else [(col + 1, row + 1), (col, row + 1), (col - 1, row + 1), (col - 1, row), (col, row - 1), (col + 1, row)]
            )
            for nc, nr in hex_nbs:
                t2 = self._regions.get((nc, nr))
                if t2 is not None and t2 is not t1:
                    if t2 not in t1.neighbors:
                        t1.neighbors.append(t2)
                    if t1 not in t2.neighbors:
                        t2.neighbors.append(t1)
                    pair = tuple(sorted((t1.name, t2.name)))
                    touching_pairs.add(pair)  # type: ignore[arg-type]
        if touching_pairs:
            TERRITORY_EDGES[:] = sorted(touching_pairs)

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
