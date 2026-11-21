"""Pygame rendering and UI presentation layer for Game of Thrones: AI Conquest.

Implements a 2.5D isometric medieval RTS visual style inspired by classic RTS games
(Age of Empires, Travian, Kingdoms):
- 2.5D isometric terrain tiles (grass, snow, mountain, marsh, dry).
- Textured 2.5D landmark fortress and castle sprites with soft ground drop shadows.
- Animated ocean waves, coastal foam, drifting chimney smoke, and fluttering heraldic banners.
- Skeuomorphic medieval stone and gold frames with resource icons (gold, swords, fortress, crown).
- Distinct House crests and interactive medieval tooltips.
- Chronological Raven's Log positioned to the right of house stats with large readable text.
- Manual turn progression permission in AI vs AI mode.
"""

from __future__ import annotations

import math
import os
import pygame

from algorithms.fuzzy_diplomacy import evaluate_diplomacy

from constants import (
    DRAGONSTONE_COORD,
    GOLD,
    GRID_COLS,
    GRID_ROWS,
    HEIGHT,
    HEX_H,
    HEX_R,
    HOUSE_COLORS,
    INK,
    INK_GLASS,
    IVORY,
    LANNISTER,
    MAP_RECT_BOUNDS,
    MUTED,
    SEA,
    STARK,
    TARGARYEN,
    WIDTH,
    X_STEP,
    Y_STEP,
)
from diplomacy import Diplomacy
from house import House
from map import (
    FIELD_SQUADS,
    LANDMARKS,
    RIVERS,
    ROADS,
    VILLAGES,
    Map,
    Territory,
    on_land,
    owner_at,
    terrain_at,
)

MAP_RECT = pygame.Rect(*MAP_RECT_BOUNDS)
_FONTS_CACHE: dict[str, pygame.font.Font] | None = None
_SPRITE_CACHE: dict[tuple[str, tuple[int, int] | None], pygame.Surface] = {}


def make_font(size: int, bold: bool = False, serif: bool = False) -> pygame.font.Font:
    return pygame.font.SysFont("georgia" if serif else "segoeui", size, bold=bold)


def make_fonts() -> dict[str, pygame.font.Font]:
    return {
        "hero": make_font(34, True, True),
        "title": make_font(23, True, True),
        "maptitle": make_font(15, True, True),
        "turn": make_font(26, True, True),
        "subhead": make_font(15, True),
        "small": make_font(13, True),
        "stat": make_font(16, True),
        "log": make_font(13, True),
        "micro": make_font(12, True),
        "tiny": make_font(11, True),
        "cardtitle": make_font(14, True),
        "place": make_font(11, True),
        "army": make_font(12, True),
    }


def _get_fonts(fonts: dict[str, pygame.font.Font] | None = None) -> dict[str, pygame.font.Font]:
    global _FONTS_CACHE
    if fonts is not None:
        return fonts
    if _FONTS_CACHE is None:
        _FONTS_CACHE = make_fonts()
    return _FONTS_CACHE


def get_sprite(path: str, scale: tuple[int, int] | None = None) -> pygame.Surface | None:
    """Load and cache an image sprite from disk, scaled to target dimensions if requested."""
    key = (path, scale)
    if key in _SPRITE_CACHE:
        return _SPRITE_CACHE[key]
    if not os.path.exists(path):
        return None
    try:
        surf = pygame.image.load(path)
        if pygame.display.get_surface() is not None:
            try:
                surf = surf.convert_alpha()
            except Exception:
                pass
        if scale is not None and surf.get_size() != scale:
            surf = pygame.transform.smoothscale(surf, scale)
        _SPRITE_CACHE[key] = surf
        return surf
    except Exception as e:
        print(f'Warning: failed loading sprite {path}: {e}')
        return None


def write(
    surface: pygame.Surface,
    value: str,
    position: tuple[int, int],
    face: pygame.font.Font,
    color: tuple[int, int, int] = IVORY,
    shadow: bool = True,
) -> None:
    if shadow:
        surface.blit(face.render(value, True, (8, 12, 16)), (position[0] + 1, position[1] + 1))
    surface.blit(face.render(value, True, color), position)


def write_right(
    surface: pygame.Surface,
    value: str,
    right: int,
    y: int,
    face: pygame.font.Font,
    color: tuple[int, int, int] = IVORY,
    shadow: bool = True,
) -> None:
    rendered = face.render(value, True, color)
    x = right - rendered.get_width()
    if shadow:
        surface.blit(face.render(value, True, (8, 12, 16)), (x + 1, y + 1))
    surface.blit(rendered, (x, y))


def mix(
    color: tuple[int, int, int],
    tint: tuple[int, int, int],
    amount: float,
) -> tuple[int, int, int]:
    return tuple(int(a * (1 - amount) + b * amount) for a, b in zip(color, tint))


def hex_points(center: tuple[float, float], radius: float = HEX_R) -> list[tuple[int, int]]:
    cx, cy = center
    return [
        (
            round(cx + radius * math.cos(math.radians(angle))),
            round(cy + radius * math.sin(math.radians(angle))),
        )
        for angle in range(0, 360, 60)
    ]


def center_of(col: int, row: int) -> tuple[float, float]:
    grid_width = (GRID_COLS - 1) * X_STEP + 2 * HEX_R
    grid_height = (GRID_ROWS - 1) * Y_STEP + Y_STEP / 2 + 2 * HEX_R
    left = MAP_RECT.centerx - grid_width / 2
    top = MAP_RECT.centery - grid_height / 2 + 6
    return left + HEX_R + col * X_STEP, top + HEX_R + row * Y_STEP + (col % 2) * Y_STEP / 2


# 2.5D Landmark Building Specifications: (sprite_path, (width, height), y_offset)
LANDMARK_SPRITE_DEFS: dict[str, tuple[str, tuple[int, int], int]] = {
    "THE WALL": ("assets/buildings/the_wall.png", (150, 160), 18),
    "CASTLE BLACK": ("assets/buildings/winterfell.png", (110, 106), 14),
    "DREADFORT": ("assets/buildings/ruins.png", (114, 112), 14),
    "PYKE": ("assets/buildings/casterly_rock.png", (114, 108), 14),
    "WINTERFELL": ("assets/buildings/winterfell.png", (152, 146), 20),
    "MOAT CAILIN": ("assets/buildings/ruins.png", (110, 108), 14),
    "WHITE HARBOR": ("assets/buildings/casterly_rock.png", (114, 110), 14),
    "THE EYRIE": ("assets/buildings/eyrie.png", (124, 156), 18),
    "LANNISPORT": ("assets/buildings/casterly_rock.png", (108, 102), 14),
    "RIVERRUN": ("assets/buildings/highgarden.png", (118, 114), 15),
    "THE TWINS": ("assets/buildings/winterfell.png", (114, 110), 14),
    "KING'S LANDING": ("assets/buildings/kings_landing.png", (166, 162), 22),
    "HARRENHAL": ("assets/buildings/ruins.png", (116, 114), 15),
    "CASTERLY ROCK": ("assets/buildings/casterly_rock.png", (150, 142), 20),
    "OLDTOWN": ("assets/buildings/highgarden.png", (130, 126), 14),
    "HIGHGARDEN": ("assets/buildings/highgarden.png", (142, 138), 18),
    "DORNE": ("assets/buildings/sunspear.png", (146, 146), 16),
    "STORM'S END": ("assets/buildings/casterly_rock.png", (120, 114), 15),
    "DRAGONSTONE": ("assets/buildings/dragonstone.png", (150, 146), 20),
}

PLAQUE_OFFSETS: dict[str, tuple[int, int]] = {
    "THE WALL": (0, 36),
    "CASTLE BLACK": (0, 32),
    "DREADFORT": (0, 32),
    "PYKE": (0, 32),
    "WINTERFELL": (0, 38),
    "MOAT CAILIN": (0, 32),
    "WHITE HARBOR": (0, 32),
    "THE EYRIE": (0, 36),
    "LANNISPORT": (0, 32),
    "RIVERRUN": (0, 33),
    "THE TWINS": (0, 32),
    "KING'S LANDING": (0, 40),
    "HARRENHAL": (0, 33),
    "CASTERLY ROCK": (0, 38),
    "OLDTOWN": (0, 18),
    "HIGHGARDEN": (0, 36),
    "DORNE": (0, 26),
    "STORM'S END": (0, 33),
    "DRAGONSTONE": (0, 38),
}

_SEA_BASE_CACHE: dict[tuple[int, int], pygame.Surface] = {}
_PANEL_GRADIENT_CACHE: dict[tuple[int, int, tuple[int, int, int]], pygame.Surface] = {}


def _build_sea_base(size: tuple[int, int]) -> pygame.Surface:
    """Pre-render deep ocean gradient, coastal shoals, rhumb lines, and compass rose."""
    w, h = size
    surf = pygame.Surface((w, h))
    for y in range(h):
        t = y / max(h - 1, 1)
        r = int(10 + 9 * t)
        g = int(42 + 28 * t)
        b = int(66 + 26 * t)
        pygame.draw.line(surf, (r, g, b), (0, y), (w, y))

    # Coastal turquoise shoal glow around landmass
    centers = [(cx - MAP_RECT.x, cy - MAP_RECT.y) for _, _, (cx, cy) in _land_cells()]
    shoal = _hex_mask(centers, HEX_R * 1.45, (w, h), (34, 128, 146, 85))
    surf.blit(_soften(shoal, 10), (0, 0))
    inner_shoal = _hex_mask(centers, HEX_R * 1.15, (w, h), (58, 162, 174, 70))
    surf.blit(_soften(inner_shoal, 6), (0, 0))

    # Faint nautical rhumb lines + antique compass rose in SW corner
    overlay = pygame.Surface((w, h), pygame.SRCALPHA)
    rx, ry = 104, h - 134
    for angle in range(0, 360, 30):
        rad = math.radians(angle)
        pygame.draw.line(
            overlay,
            (130, 178, 188, 22),
            (rx, ry),
            (rx + math.cos(rad) * 420, ry + math.sin(rad) * 420),
            1,
        )
    # Compass rose rings and cardinal points
    pygame.draw.circle(overlay, (195, 170, 110, 58), (rx, ry), 38, 1)
    pygame.draw.circle(overlay, (195, 170, 110, 40), (rx, ry), 26, 1)
    for idx, angle in enumerate((0, 90, 180, 270)):
        rad = math.radians(angle)
        tip = (rx + math.cos(rad) * 42, ry + math.sin(rad) * 42)
        p1 = (rx + math.cos(rad + 0.35) * 10, ry + math.sin(rad + 0.35) * 10)
        p2 = (rx + math.cos(rad - 0.35) * 10, ry + math.sin(rad - 0.35) * 10)
        pygame.draw.polygon(overlay, (220, 185, 105, 85), [(rx, ry), p1, tip])
        pygame.draw.polygon(overlay, (140, 115, 65, 65), [(rx, ry), tip, p2])
    for angle in (45, 135, 225, 315):
        rad = math.radians(angle)
        tip = (rx + math.cos(rad) * 26, ry + math.sin(rad) * 26)
        p1 = (rx + math.cos(rad + 0.35) * 7, ry + math.sin(rad + 0.35) * 7)
        p2 = (rx + math.cos(rad - 0.35) * 7, ry + math.sin(rad - 0.35) * 7)
        pygame.draw.polygon(overlay, (180, 155, 95, 55), [(rx, ry), p1, tip, p2])
    pygame.draw.circle(overlay, (236, 185, 94, 110), (rx, ry), 4)
    surf.blit(overlay, (0, 0))
    return surf


def draw_sea_animated(surface: pygame.Surface, rect: pygame.Rect) -> None:
    """Render atmospheric ocean bathymetry with gentle organic animated wave glints."""
    size = (rect.width, rect.height)
    if size not in _SEA_BASE_CACHE:
        _SEA_BASE_CACHE[size] = _build_sea_base(size)
    surface.blit(_SEA_BASE_CACHE[size], rect.topleft)

    ticks = pygame.time.get_ticks()
    glint_layer = pygame.Surface(size, pygame.SRCALPHA)
    for idx in range(28):
        seed_x = (idx * 173 + 47) % max(1, rect.width - 80) + 40
        seed_y = (idx * 97 + 29) % max(1, rect.height - 60) + 30
        drift = math.sin(ticks * 0.0014 + idx * 1.3) * 12
        pulse = (math.sin(ticks * 0.0022 + idx * 0.9) + 1.0) * 0.5
        alpha = int(28 + 56 * pulse)
        length = int(14 + 14 * pulse)
        gx = int(seed_x + drift)
        gy = seed_y
        pygame.draw.line(glint_layer, (145, 212, 225, alpha), (gx - length // 2, gy), (gx + length // 2, gy), 1)
        pygame.draw.line(
            glint_layer,
            (215, 244, 250, int(alpha * 0.65)),
            (gx - length // 4, gy - 1),
            (gx + length // 4, gy - 1),
            1,
        )
    surface.blit(glint_layer, rect.topleft)


def draw_isometric_tile(
    surface: pygame.Surface,
    center: tuple[float, float],
    col: int,
    row: int,
    owner: str | None,
) -> None:
    """Render a 2.5D isometric terrain tile with 3D slab depth and territory control rim."""
    cx, cy = round(center[0]), round(center[1])
    kind = terrain_at(col, row)
    tile_img = get_sprite(f"assets/tiles/{kind}.png", (96, 78)) or get_sprite("assets/tiles/grass.png", (96, 78))

    if tile_img is not None:
        # Blit 2.5D slab centered on hex coordinate
        surface.blit(tile_img, (cx - tile_img.get_width() // 2, cy - tile_img.get_height() // 2 + 10))
    else:
        # Vector fallback if image missing
        points = hex_points(center)
        pygame.draw.polygon(surface, (80, 115, 60), points)

    # Territory control illumination on the top face
    top_poly = hex_points(center)
    if owner:
        glow_color = mix(HOUSE_COLORS[owner], (255, 245, 210), 0.15)
        # 3D border glow in house heraldry
        pygame.draw.polygon(surface, (*glow_color, 70), top_poly, 3)
        pygame.draw.polygon(surface, glow_color, top_poly, 1)
    else:
        pygame.draw.polygon(surface, (55, 75, 70), top_poly, 1)


def draw_roads_and_rivers(surface: pygame.Surface) -> None:
    """Render soft, organic medieval rivers and subtle dirt trails across Westeros."""
    overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)

    # Rivers (curved multi-point streams with soft banks)
    for route in RIVERS:
        raw_pts = [center_of(col, row) for col, row in route]
        smooth_pts: list[tuple[float, float]] = []
        for idx in range(len(raw_pts) - 1):
            ax, ay = raw_pts[idx]
            bx, by = raw_pts[idx + 1]
            mx = (ax + bx) * 0.5 + ((idx % 2) * 2 - 1) * 8
            my = (ay + by) * 0.5
            smooth_pts.extend([(ax, ay), (mx, my)])
        smooth_pts.append(raw_pts[-1])
        pygame.draw.lines(overlay, (26, 68, 82, 130), False, smooth_pts, 5)
        pygame.draw.lines(overlay, (68, 148, 166, 145), False, smooth_pts, 2)

    # Roads (subtle worn earth trails curved between holds)
    for idx, (start, end) in enumerate(ROADS):
        ax, ay = center_of(*start)
        bx, by = center_of(*end)
        mx = (ax + bx) * 0.5 + ((idx % 2) * 2 - 1) * 6
        my = (ay + by) * 0.5 + ((idx % 3) - 1) * 5
        pts = [(ax, ay), (mx, my), (bx, by)]
        pygame.draw.lines(overlay, (76, 62, 44, 95), False, pts, 3)
        pygame.draw.lines(overlay, (152, 130, 88, 90), False, pts, 1)

    surface.blit(overlay, (0, 0))


def draw_castle_banner(
    surface: pygame.Surface,
    top_pos: tuple[int, int],
    house: str | None,
    scale: float = 1.0,
) -> None:
    """Render an animated fluttering swallowtail heraldic banner on castle tower."""
    tx, ty = top_pos
    ticks = pygame.time.get_ticks()
    wave = math.sin(ticks * 0.006 + tx * 0.1) * 3
    accent = HOUSE_COLORS.get(house, GOLD) if house else GOLD

    # Wooden flagpole
    pygame.draw.line(surface, (80, 65, 45), (tx, ty), (tx, ty - int(24 * scale)), max(1, round(2 * scale)))
    flag_top = ty - int(24 * scale)
    w = int(22 * scale)
    h = int(12 * scale)

    # Animated swallowtail flag
    pts = [
        (tx, flag_top),
        (tx + w + int(wave), flag_top + 2),
        (tx + w - int(5 * scale) + int(wave * 0.7), flag_top + h // 2),
        (tx + w + int(wave), flag_top + h),
        (tx, flag_top + h),
    ]
    pygame.draw.polygon(surface, accent, pts)
    pygame.draw.polygon(surface, mix(accent, (255, 240, 200), 0.3), pts, 1)


def draw_smoke_wisps(
    surface: pygame.Surface,
    origin: tuple[int, int],
    seed: int = 0,
) -> None:
    """Render gentle translucent chimney smoke particles drifting in the wind."""
    ox, oy = origin
    ticks = pygame.time.get_ticks()
    for i in range(3):
        t = (ticks * 0.025 + seed * 20 + i * 25) % 65
        sx = ox + math.sin((ticks * 0.003) + i + seed) * 5 + t * 0.25
        sy = oy - t * 0.65
        alpha = int(max(0, 140 * (1 - t / 65.0)))
        radius = int(2 + (t / 65.0) * 5)
        smoke = pygame.Surface((radius * 2 + 2, radius * 2 + 2), pygame.SRCALPHA)
        pygame.draw.circle(smoke, (220, 225, 230, alpha), (radius + 1, radius + 1), radius)
        surface.blit(smoke, (sx - radius, sy - radius))


def draw_isometric_landmark(
    surface: pygame.Surface,
    center: tuple[float, float],
    name: str,
    armies: int,
    house: str | None,
    fonts: dict[str, pygame.font.Font],
    mode: str = "all",
    shake_x: int = 0,
) -> None:
    """Render a grounded 2.5D isometric landmark fortress. mode: all | body | plaque."""
    cx, cy = round(center[0]) + shake_x, round(center[1])
    spec = LANDMARK_SPRITE_DEFS.get(name)
    if mode == "plaque":
        _draw_plaque(surface, cx, cy, name, armies, house, fonts)
        return

    # 1. Grounded Isometric Contact Shadow & Footprint Rim anchored directly to castle base
    if spec is not None:
        sw_full, sh_full = spec[1]
        y_off = spec[2]
        bottom_y = cy + 18 + y_off
    else:
        sw_full, sh_full, bottom_y = 84, 84, cy + 20

    foot_w = int(sw_full * 0.50)
    foot_h = max(20, int(sh_full * 0.24))
    foot_cy = bottom_y - foot_h + 2
    pad_w = foot_w * 2 + 28
    pad_h = foot_h * 2 + 24
    pad_surf = pygame.Surface((pad_w, pad_h), pygame.SRCALPHA)
    pcx, pcy = pad_w // 2, pad_h // 2

    # Outer soft ambient-occlusion shadow hugging the ground beneath the fortress walls
    outer_shadow = [
        (pcx, pcy - foot_h - 4),
        (pcx + foot_w + 8, pcy + 2),
        (pcx, pcy + foot_h + 6),
        (pcx - foot_w - 8, pcy + 2),
    ]
    pygame.draw.polygon(pad_surf, (6, 12, 16, 82), outer_shadow)

    # Tight dark contact shadow directly under the castle's diamond foundation
    inner_shadow = [
        (pcx, pcy - foot_h + 2),
        (pcx + foot_w + 1, pcy + 2),
        (pcx, pcy + foot_h + 2),
        (pcx - foot_w - 1, pcy + 2),
    ]
    pygame.draw.polygon(pad_surf, (6, 10, 14, 155), inner_shadow)

    # Subtle grounded heraldic base trim (King's Landing gold or ruling house accent)
    if name == "KING'S LANDING":
        pygame.draw.polygon(pad_surf, (*GOLD, 185), outer_shadow, 2)
    elif house:
        pygame.draw.polygon(pad_surf, (*HOUSE_COLORS[house], 165), outer_shadow, 2)

    surface.blit(pad_surf, (cx - pcx, foot_cy - pcy))

    # 2. Building Sprite (bottom corner planted flush onto bottom_y)
    if spec is not None:
        sprite_path, size, y_off = spec
        sprite = get_sprite(sprite_path, size)
        if sprite is not None:
            bx = cx - sprite.get_width() // 2
            by = cy - sprite.get_height() + 18 + y_off
            surface.blit(sprite, (bx, by))

            # Steady Royal Crown crest above King's Landing (The Iron Throne)
            if name == "KING'S LANDING":
                crown_icon = get_sprite("assets/ui/crown.png", (26, 26))
                if crown_icon:
                    surface.blit(crown_icon, (cx - 13, by - 14))

            # Chimney smoke for major seats
            if name in ("KING'S LANDING", "WINTERFELL", "DRAGONSTONE"):
                draw_smoke_wisps(surface, (cx - 10, by + 18), seed=len(name))
        else:
            _draw_fallback_castle(surface, cx, cy, house)
    else:
        _draw_fallback_castle(surface, cx, cy, house)

    if mode == "all":
        _draw_plaque(surface, cx, cy, name, armies, house, fonts)


def _draw_plaque(
    surface: pygame.Surface,
    cx: int,
    cy: int,
    name: str,
    armies: int,
    house: str | None,
    fonts: dict[str, pygame.font.Font],
) -> None:
    is_throne = name == "KING'S LANDING"
    crown_spr = get_sprite("assets/ui/crown.png", (16, 16)) if is_throne else None
    accent = HOUSE_COLORS[house] if house else (GOLD if is_throne else (205, 193, 159))
    display_title = "KING'S LANDING" if is_throne else name
    text_col = GOLD if is_throne else IVORY
    name_txt = fonts["place"].render(display_title, True, text_col)
    name_shadow = fonts["place"].render(display_title, True, (6, 8, 10))
    count_txt = fonts["army"].render(str(armies), True, (16, 20, 24))
    chip_w = max(24, count_txt.get_width() + 12)

    crown_pad = 18 if crown_spr else 0
    total_w = name_txt.get_width() + chip_w + 18 + crown_pad
    off_x, off_y = PLAQUE_OFFSETS.get(name, (0, 20))
    plaque = pygame.Rect(0, cy + off_y, total_w, 22)
    plaque.centerx = cx + off_x

    # Soft outer shadow + dark slate metallic plaque
    pygame.draw.rect(surface, (0, 0, 0), plaque.move(0, 2), border_radius=10)
    bg_col = (34, 28, 18) if is_throne else (20, 29, 34)
    border_col = GOLD if is_throne else accent
    pygame.draw.rect(surface, bg_col, plaque, border_radius=10)
    pygame.draw.rect(surface, border_col, plaque, 2, border_radius=10)

    text_start_x = plaque.x + 8
    if crown_spr:
        surface.blit(crown_spr, (plaque.x + 6, plaque.centery - 8))
        text_start_x += crown_pad
    ty = plaque.centery - name_txt.get_height() // 2
    surface.blit(name_shadow, (text_start_x + 1, ty + 1))
    surface.blit(name_txt, (text_start_x, ty))

    # Army garrison badge
    chip = pygame.Rect(plaque.right - chip_w - 3, plaque.y + 3, chip_w, plaque.height - 6)
    pygame.draw.rect(surface, accent, chip, border_radius=7)
    surface.blit(count_txt, (chip.centerx - count_txt.get_width() // 2, chip.centery - count_txt.get_height() // 2))


def _draw_fallback_castle(surface: pygame.Surface, cx: int, cy: int, house: str | None) -> None:
    stone = (140, 140, 130)
    pygame.draw.rect(surface, stone, (cx - 20, cy - 24, 40, 26))
    pygame.draw.polygon(surface, (180, 180, 170), [(cx - 24, cy - 24), (cx, cy - 38), (cx + 24, cy - 24)])
    if house:
        draw_castle_banner(surface, (cx, cy - 38), house)


def draw_knight_squad(
    surface: pygame.Surface,
    center: tuple[float, float],
    house: str,
    fonts: dict[str, pygame.font.Font],
    armies: int = 4,
) -> None:
    """Render a grounded 2.5D isometric knight troop squad standing on field terrain."""
    cx, cy = round(center[0]), round(center[1])

    # Angled contact shadows directly beneath the 4 diagonal soldiers' feet
    shadow_surf = pygame.Surface((56, 28), pygame.SRCALPHA)
    for i in range(4):
        sx = 4 + i * 11
        sy = 4 + i * 4
        pygame.draw.ellipse(shadow_surf, (8, 14, 18, 135), (sx, sy, 16, 8))
    surface.blit(shadow_surf, (cx - 26, cy - 8))

    # Unit sprite (steady on the ground, no vertical bobbing)
    knights_img = get_sprite("assets/units/knights.png", (50, 56))
    if knights_img is not None:
        surface.blit(knights_img, (cx - 25, cy - 42))
    else:
        color = HOUSE_COLORS.get(house, GOLD)
        pygame.draw.circle(surface, color, (cx, cy - 12), 8)

    # House pennant
    accent = HOUSE_COLORS.get(house, GOLD)
    pennant = pygame.Rect(cx + 8, cy - 36, 20, 14)
    pygame.draw.rect(surface, accent, pennant, border_radius=4)
    pygame.draw.rect(surface, (20, 26, 30), pennant, 1, border_radius=4)
    num_txt = fonts["tiny"].render(str(armies), True, (15, 20, 25))
    surface.blit(num_txt, (pennant.centerx - num_txt.get_width() // 2, pennant.centery - num_txt.get_height() // 2))


_DRAGON_FRAME_CACHE: dict[tuple[str, str, tuple[int, int]], list[pygame.Surface]] = {}
_DRAGON_SHEETS: dict[str, str] = {
    "right": "assets/ui/reddragonfly.png",
    "down": "assets/ui/reddragonfly2.png",
    "left": "assets/ui/reddragonfly3.png",
    "up": "assets/ui/reddragonfly4.png",
}
_CUSTOM_DRAGON_PATHS: dict[str, str] = {
    "STARK": "assets/units/dragon_stark_flap.png",
    "LANNISTER": "assets/units/dragon_lannister_flap.png",
}
_CUSTOM_DRAGON_FRAMES_COUNT = 8
# Normalized (x, y) mouth anchor inside each 8-frame padded flap cell (right-facing)
_CUSTOM_DRAGON_MOUTH: dict[str, tuple[float, float]] = {
    "STARK": (0.800, 0.516),
    "LANNISTER": (0.742, 0.480),
}
_CUSTOM_DRAGON_CACHE: dict[tuple[str, int, int], list[pygame.Surface]] = {}

# House-themed elemental fire-breath palettes: (core, inner, outer, smoke, spark)
_DRAGON_FIRE_PALETTES: dict[str, tuple[tuple[int, int, int], ...]] = {
    "STARK": (
        (238, 253, 255),  # white-hot frost core
        (110, 224, 255),  # electric ice-cyan flame
        (34, 118, 238),   # glacial blue outer plume
        (150, 195, 235),  # icy mist smoke
        (210, 248, 255),  # frostfire sparks
    ),
    "LANNISTER": (
        (255, 252, 218),  # white-gold blazing core
        (255, 206, 56),   # molten Lannister gold
        (232, 74, 22),    # crimson-orange inferno
        (58, 44, 38),     # scorched smoke
        (255, 236, 128),  # golden sparks
    ),
    "TARGARYEN": (
        (255, 246, 198),  # white-yellow dragonfire core
        (255, 146, 32),   # searing orange inner flame
        (214, 34, 20),    # Valyrian crimson outer plume
        (46, 36, 36),     # volcanic ash smoke
        (255, 196, 82),   # glowing embers
    ),
}


def _dragon_direction(dx: float, dy: float) -> str:
    if abs(dx) >= abs(dy):
        return "right" if dx >= 0 else "left"
    return "down" if dy >= 0 else "up"


DRAGON_PATROL_SIZE: tuple[int, int] = (102, 82)   # Ambient circling dragon (width, height)
DRAGON_BATTLE_SIZE: tuple[int, int] = (128, 102)  # Attacking dragon in battle (width, height)


def _get_dragon_frames(
    direction: str,
    kind: str = "fly",
    size: tuple[int, int] = (72, 58),
) -> list[pygame.Surface]:
    """Slice and cache 4x4 directional red dragon sprite-sheet frames."""
    key = (direction, kind, size)
    if key in _DRAGON_FRAME_CACHE:
        return _DRAGON_FRAME_CACHE[key]
    path = _DRAGON_SHEETS.get(direction, _DRAGON_SHEETS["right"])
    sheet = get_sprite(path)
    if sheet is None:
        _DRAGON_FRAME_CACHE[key] = []
        return []
    cw, ch = sheet.get_width() // 4, sheet.get_height() // 4
    if kind == "attack":
        cells = [(1, 2), (2, 2), (3, 2), (0, 3), (1, 3), (2, 3), (3, 3)]
    else:
        cells = [(c, r) for r in (0, 1) for c in range(4)]
    frames: list[pygame.Surface] = []
    for c, r in cells:
        sub = sheet.subsurface(pygame.Rect(c * cw, r * ch, cw, ch))
        frames.append(pygame.transform.smoothscale(sub, size))
    _DRAGON_FRAME_CACHE[key] = frames
    return frames


def _get_custom_dragon_frames(house: str, max_size: tuple[int, int]) -> list[pygame.Surface]:
    """Slice and cache the 8-frame wing-flapping sprite sheet for a custom house dragon."""
    key = (house, max_size[0], max_size[1])
    if key in _CUSTOM_DRAGON_CACHE:
        return _CUSTOM_DRAGON_CACHE[key]
    path = _CUSTOM_DRAGON_PATHS.get(house)
    if not path:
        _CUSTOM_DRAGON_CACHE[key] = []
        return []
    sheet = get_sprite(path)
    if sheet is None:
        _CUSTOM_DRAGON_CACHE[key] = []
        return []
    sw_total, sh_total = sheet.get_size()
    cw = max(1, sw_total // _CUSTOM_DRAGON_FRAMES_COUNT)
    ch = sh_total
    # Compensate for the wing-sweep vertical padding so body size matches DRAGON_*_SIZE cleanly
    box_w = round(max_size[0] * 1.24)
    box_h = round(max_size[1] * 1.48)
    scale = min(box_w / cw, box_h / ch)
    out_w, out_h = max(1, round(cw * scale)), max(1, round(ch * scale))
    frames: list[pygame.Surface] = []
    for i in range(_CUSTOM_DRAGON_FRAMES_COUNT):
        sub = sheet.subsurface(pygame.Rect(i * cw, 0, cw, ch))
        frames.append(pygame.transform.smoothscale(sub, (out_w, out_h)))
    _CUSTOM_DRAGON_CACHE[key] = frames
    return frames


def _draw_house_dragon(
    surface: pygame.Surface,
    house: str,
    px: float,
    py: float,
    dx: float,
    dy: float,
    size: tuple[int, int],
    time_sec: float,
    attacking: bool = False,
    altitude: float = 28.0,
) -> tuple[float, float]:
    """Draw any house's flying/roaring dragon with animated wingbeats and shadow.

    Returns the exact screen coordinates `(mouth_x, mouth_y)` of the dragon's jaws.
    """
    h_key = house.upper()
    flap_fps = 13.0 if attacking else 9.0
    cycle_angle = time_sec * (flap_fps / _CUSTOM_DRAGON_FRAMES_COUNT) * math.tau
    flap = -math.cos(cycle_angle)

    # Dynamic ground contact shadow shrinking slightly as the dragon lifts on downstroke
    sh_w = max(24, round(size[0] * (0.44 - 0.05 * flap)))
    sh_h = max(10, round(size[1] * 0.18))
    shadow = pygame.Surface((sh_w, sh_h), pygame.SRCALPHA)
    pygame.draw.ellipse(shadow, (8, 12, 16, 110 if attacking else 96), (0, 0, sh_w, sh_h))
    surface.blit(shadow, (round(px - sh_w / 2), round(py + 6)))

    if h_key == "TARGARYEN":
        direction = _dragon_direction(dx, dy)
        frames = _get_dragon_frames(direction, "attack" if attacking else "fly", size)
        if not frames:
            return (px, py - altitude)
        fps = 8.0 if attacking else 7.4
        frame = frames[int(time_sec * fps) % len(frames)]
        bob = -flap * 3.0
        draw_x = round(px - frame.get_width() / 2)
        draw_y = round(py - altitude + bob - frame.get_height() / 2)
        surface.blit(frame, (draw_x, draw_y))
        ln = math.hypot(dx, dy) or 1.0
        mx = px + (dx / ln) * (frame.get_width() * 0.28)
        my = py - altitude + bob + (dy / ln) * (frame.get_height() * 0.16) - 2
        return (mx, my)

    # Custom Frost Dragon (STARK) & Golden Dragon (LANNISTER) 8-frame wing-flapping cycle
    frames = _get_custom_dragon_frames(h_key, size)
    if not frames:
        return (px, py - altitude)

    frame_idx = int(time_sec * flap_fps) % len(frames)
    spr = frames[frame_idx]
    flip_left = dx < 0
    if flip_left:
        spr = pygame.transform.flip(spr, True, False)

    # Slight rear-up pitch while breathing fire
    tilt = 5.0 if attacking else 0.0
    if flip_left:
        tilt = -tilt
    final_spr = pygame.transform.rotate(spr, tilt) if tilt else spr

    draw_cx = px
    draw_cy = py - altitude
    surface.blit(final_spr, (round(draw_cx - final_spr.get_width() / 2), round(draw_cy - final_spr.get_height() / 2)))

    # Compute exact open-mouth anchor in screen coordinates (including body bob baked in frame)
    fw, fh = spr.get_size()
    m_nx, m_ny = _CUSTOM_DRAGON_MOUTH.get(h_key, (0.78, 0.50))
    if flip_left:
        m_nx = 1.0 - m_nx
    body_bob_px = -flap * (fh * 0.025)
    mouth_x = draw_cx + (m_nx - 0.5) * fw
    mouth_y = draw_cy + (m_ny - 0.5) * fh + body_bob_px
    return (mouth_x, mouth_y)


def _draw_dragon_breath(
    surface: pygame.Surface,
    house: str,
    mouth: tuple[float, float],
    target: tuple[float, float],
    time_sec: float,
    reach: float = 1.0,
    intensity: float = 1.0,
    show_ground_blaze: bool = True,
) -> None:
    """Render a cinematic 6-layer volumetric dragonfire torrent from mouth to target."""
    reach = max(0.05, min(1.0, reach))
    intensity = max(0.0, min(1.0, intensity))
    if intensity <= 0.02:
        return

    core_col, inner_col, outer_col, smoke_col, spark_col = _DRAGON_FIRE_PALETTES.get(
        house.upper(), _DRAGON_FIRE_PALETTES["TARGARYEN"]
    )
    mx, my = mouth
    tx = mx + (target[0] - mx) * reach
    ty = my + (target[1] - my) * reach
    dx, dy = tx - mx, ty - my
    dist = math.hypot(dx, dy)
    if dist < 6.0:
        return
    ux, uy = dx / dist, dy / dist
    px_perp, py_perp = -uy, ux  # perpendicular unit vector for flame cone width

    # Local alpha canvas around the flame bounding box for smooth additive-style layering
    pad = 64
    min_x = int(min(mx, tx)) - pad
    min_y = int(min(my, ty)) - pad
    w = max(4, int(max(mx, tx)) - min_x + pad)
    h = max(4, int(max(my, ty)) - min_y + pad)
    fx = pygame.Surface((w, h), pygame.SRCALPHA)
    lmx, lmy = mx - min_x, my - min_y
    ltx, lty = tx - min_x, ty - min_y

    # Layer 1: Dark smoke / icy mist billows rising near the impact end
    for i in range(8):
        p = (time_sec * 1.65 + i / 8.0) % 1.0
        if p < 0.35:
            continue
        sp = (p - 0.35) / 0.65
        swirl = math.sin(time_sec * 7.0 + i * 2.3) * (10.0 * sp)
        sx = lmx + dx * (0.45 + 0.65 * sp) + px_perp * swirl
        sy = lmy + dy * (0.45 + 0.65 * sp) + py_perp * swirl - sp * 18.0
        sr = max(4, round((8 + 14 * sp) * intensity))
        sa = int(95 * (1.0 - sp) * intensity)
        pygame.draw.circle(fx, (*smoke_col, sa), (round(sx), round(sy)), sr)

    # Layer 2: 3-tier turbulent volumetric flame cone (outer → inner → white-hot core)
    segments = 9
    tiers = (
        (outer_col, 1.00, 145, 22.0, 1.00),
        (inner_col, 0.88, 200, 14.5, 0.92),
        (core_col, 0.68, 235, 7.2, 0.80),
    )
    for col, length_frac, base_alpha, max_half_w, wave_amp in tiers:
        left_edge: list[tuple[float, float]] = []
        right_edge: list[tuple[float, float]] = []
        for s in range(segments + 1):
            frac = (s / segments) * length_frac
            cx = lmx + dx * frac
            cy = lmy + dy * frac
            # Expand cone smoothly from narrow jaws to roaring fan, then taper slightly at tip
            taper = math.sin(min(1.0, frac / max(0.01, length_frac)) * math.pi * 0.78)
            half_w = (2.5 + max_half_w * taper) * (0.55 + 0.45 * intensity)
            wobble = math.sin(time_sec * 18.0 - s * 1.15) * (4.2 * frac * wave_amp)
            flicker = math.cos(time_sec * 23.0 + s * 1.7) * (2.4 * frac)
            left_edge.append((cx + px_perp * (half_w + wobble), cy + py_perp * (half_w + wobble)))
            right_edge.append((cx - px_perp * (half_w - wobble - flicker), cy - py_perp * (half_w - wobble - flicker)))
        poly = left_edge + list(reversed(right_edge))
        pygame.draw.polygon(fx, (*col, int(base_alpha * intensity)), poly)

    # Layer 3: 16 billowing high-velocity fireballs rushing down the cone
    for i in range(16):
        p = (time_sec * 2.85 + i / 16.0) % 1.0
        jitter = math.sin(i * 3.1 + time_sec * 14.0) * (11.0 * p)
        bx = lmx + dx * p + px_perp * jitter
        by = lmy + dy * p + py_perp * jitter - p * 4.0
        br = max(3, round((4.5 + 11.5 * p) * (0.65 + 0.35 * intensity)))
        if p < 0.28:
            bcol = core_col
            ba = int(225 * intensity)
        elif p < 0.68:
            bcol = inner_col
            ba = int(190 * (1.0 - p * 0.25) * intensity)
        else:
            bcol = outer_col
            ba = int(165 * (1.0 - (p - 0.68) / 0.38) * intensity)
        pygame.draw.circle(fx, (*bcol, max(0, min(255, ba))), (round(bx), round(by)), br)

    # Layer 4: Roaring mouth ignition flash right inside the dragon's jaws
    pulse = 0.85 + 0.15 * math.sin(time_sec * 28.0)
    pygame.draw.circle(fx, (*outer_col, int(115 * intensity)), (round(lmx), round(lmy)), round(14 * pulse * intensity))
    pygame.draw.circle(fx, (*inner_col, int(185 * intensity)), (round(lmx), round(lmy)), round(9 * pulse * intensity))
    pygame.draw.circle(fx, (*core_col, int(245 * intensity)), (round(lmx), round(lmy)), round(5 * pulse * intensity))

    # Layer 5: Target engulfment ground blaze & licking flame tongues
    if show_ground_blaze and reach > 0.72:
        blaze_s = intensity * min(1.0, (reach - 0.72) / 0.28)
        bw = round(48 * blaze_s)
        bh = round(22 * blaze_s)
        if bw > 4 and bh > 4:
            pygame.draw.ellipse(
                fx,
                (*outer_col, int(130 * blaze_s)),
                (round(ltx - bw / 2), round(lty - bh / 2 + 4), bw, bh),
            )
            pygame.draw.ellipse(
                fx,
                (*inner_col, int(165 * blaze_s)),
                (round(ltx - bw * 0.34), round(lty - bh * 0.34 + 4), round(bw * 0.68), round(bh * 0.68)),
            )
        # Dancing vertical flame tongues engulfing the defending squad
        for j in range(7):
            off_x = (j - 3) * 7.5 + math.sin(time_sec * 15.0 + j * 1.9) * 3.0
            fh = (14.0 + 12.0 * abs(math.sin(time_sec * 16.0 + j * 1.4))) * blaze_s
            fw = 5.5 * blaze_s
            base_x = ltx + off_x
            base_y = lty + 5.0
            tip_x = base_x + math.sin(time_sec * 19.0 + j * 2.1) * 4.5
            tip_y = base_y - fh
            tcol = inner_col if j % 2 == 0 else outer_col
            pygame.draw.polygon(
                fx,
                (*tcol, int(195 * blaze_s)),
                [(base_x - fw, base_y), (tip_x, tip_y), (base_x + fw, base_y)],
            )
            pygame.draw.polygon(
                fx,
                (*core_col, int(205 * blaze_s)),
                [(base_x - fw * 0.45, base_y), (tip_x, base_y - fh * 0.55), (base_x + fw * 0.45, base_y)],
            )

    # Layer 6: 20 high-velocity streaking sparks & embers curling upward
    for i in range(20):
        ep = (time_sec * 3.4 + i * 0.13) % 1.0
        spread = math.sin(i * 4.7 + time_sec * 9.0) * (18.0 * ep + 3.0)
        lift = -ep * ep * 20.0
        ex = lmx + dx * (ep * 1.15) + px_perp * spread
        ey = lmy + dy * (ep * 1.15) + py_perp * spread + lift
        tail_x = ex - ux * 7.5
        tail_y = ey - uy * 7.5 + 2.0
        ea = int(235 * (1.0 - ep) * intensity)
        pygame.draw.line(fx, (*spark_col, ea), (round(tail_x), round(tail_y)), (round(ex), round(ey)), 2)
        pygame.draw.circle(fx, (*core_col, ea), (round(ex), round(ey)), max(1, round(2.5 * (1.0 - ep * 0.6))))

    surface.blit(fx, (min_x, min_y))


def _draw_patrol_dragon(
    surface: pygame.Surface,
    game_map: Map | None,
    houses: list[House] | None,
    animations: list[dict[str, object]] | None,
) -> None:
    """Render ambient flying dragons circling each surviving house's capital, with periodic fire bursts."""
    marching_houses = {
        str(a.get("house", "")).upper()
        for a in (animations or [])
        if a.get("type") == "march"
    }
    ticks_sec = pygame.time.get_ticks() * 0.001
    house_by_name = {h.name: h for h in houses} if houses else {}
    default_coords = {
        "STARK": (5, 2),
        "LANNISTER": (2, 6),
        "TARGARYEN": DRAGONSTONE_COORD,
    }

    for idx, h_name in enumerate(("STARK", "LANNISTER", "TARGARYEN")):
        if h_name in marching_houses:
            continue
        h_obj = house_by_name.get(h_name)
        if h_obj is not None and h_obj.is_eliminated():
            continue
        anchor = h_obj.territories[0] if (h_obj is not None and h_obj.territories) else None
        if anchor is None and game_map is not None:
            owned = game_map.get_owned_by(h_name)
            anchor = owned[0] if owned else None
        col, row = (anchor.col, anchor.row) if anchor is not None else default_coords[h_name]
        cx, cy = center_of(col, row)

        phase = idx * 2.1
        theta = ticks_sec * 0.55 + phase
        rx, ry = 40.0, 22.0
        px = cx + math.cos(theta) * rx
        py = cy + math.sin(theta) * ry
        dx = -math.sin(theta) * rx
        dy = math.cos(theta) * ry

        # Periodic 1.3s ambient fire-breath display every 6.5s (staggered per house)
        cycle_t = (ticks_sec + idx * 2.2) % 6.5
        breathing = cycle_t < 1.3
        mouth = _draw_house_dragon(
            surface,
            h_name,
            px,
            py,
            dx,
            dy,
            DRAGON_PATROL_SIZE,
            ticks_sec + phase,
            attacking=breathing,
            altitude=30.0,
        )
        if breathing:
            ln = math.hypot(dx, dy) or 1.0
            aim_x = mouth[0] + (dx / ln) * 62.0
            aim_y = mouth[1] + (dy / ln) * 32.0 + 18.0
            reach = min(1.0, cycle_t / 0.25)
            fade = min(1.0, (1.3 - cycle_t) / 0.30)
            _draw_dragon_breath(
                surface,
                h_name,
                mouth,
                (aim_x, aim_y),
                ticks_sec + phase,
                reach=reach,
                intensity=0.88 * fade,
                show_ground_blaze=False,
            )


def _draw_sailing_ships(surface: pygame.Surface, rect: pygame.Rect) -> None:
    """Render animated medieval warships patrolling the Sunset, Narrow, and Summer Seas."""
    ticks = pygame.time.get_ticks() * 0.00022
    routes = [
        # (x1, y1, x2, y2, sail_color, phase) — open ocean lanes outside 21x8 coastline
        (rect.x + 56, rect.y + 180, rect.x + 112, rect.y + 580, LANNISTER, 0.0),
        (rect.x + 140, rect.bottom - 108, rect.x + 360, rect.bottom - 62, GOLD, 1.8),
        (rect.right - 122, rect.y + 165, rect.right - 56, rect.y + 520, TARGARYEN, 3.1),
        (rect.right - 340, rect.bottom - 72, rect.right - 120, rect.bottom - 140, STARK, 4.7),
    ]
    for x1, y1, x2, y2, sail_col, phase in routes:
        cycle = (ticks + phase) % 2.0
        going = cycle < 1.0
        u = cycle if going else (2.0 - cycle)
        ease = u * u * (3.0 - 2.0 * u)
        px = x1 + (x2 - x1) * ease
        py = y1 + (y2 - y1) * ease
        dx = (x2 - x1) if going else (x1 - x2)
        dy = (y2 - y1) if going else (y1 - y2)
        ln = math.hypot(dx, dy) or 1.0
        ux, uy = dx / ln, dy / ln
        bob = math.sin(pygame.time.get_ticks() * 0.004 + phase) * 2.0

        # Trailing foam wake
        wake = pygame.Surface((96, 96), pygame.SRCALPHA)
        for i in range(1, 5):
            wx = 48 - ux * i * 7
            wy = 48 - uy * i * 7
            alpha = max(18, 120 - i * 24)
            pygame.draw.circle(wake, (210, 238, 245, alpha), (round(wx), round(wy)), max(1, 5 - i))
        surface.blit(wake, (round(px - 48), round(py - 48 + bob)))

        # Wooden galley hull + mast + billowing sail
        sx, sy = round(px), round(py + bob)
        flip = -1 if dx < 0 else 1
        hull = [(sx - 13 * flip, sy + 2), (sx + 15 * flip, sy + 2), (sx + 10 * flip, sy + 7), (sx - 9 * flip, sy + 7)]
        pygame.draw.polygon(surface, (82, 56, 36), hull)
        pygame.draw.polygon(surface, (132, 96, 62), hull, 1)
        pygame.draw.line(surface, (66, 46, 28), (sx, sy + 2), (sx, sy - 16), 2)
        sail = [
            (sx, sy - 15),
            (sx + 12 * flip, sy - 9),
            (sx + 10 * flip, sy - 1),
            (sx, sy - 2),
        ]
        pygame.draw.polygon(surface, IVORY, sail)
        pygame.draw.polygon(surface, sail_col, [(sx, sy - 11), (sx + 11 * flip, sy - 8), (sx + 10 * flip, sy - 5), (sx, sy - 6)])
        pygame.draw.polygon(surface, (42, 34, 28), sail, 1)


_WARRIOR_FRAME_CACHE: dict[tuple[str, str, tuple[int, int]], list[pygame.Surface]] = {}
_WARRIOR_SHEETS: dict[str, str] = {
    "run": "assets/ui/Medieval Warrior Pack/Run.png",
    "attack1": "assets/ui/Medieval Warrior Pack/Attack1.png",
    "attack2": "assets/ui/Medieval Warrior Pack/Attack2.png",
    "idle": "assets/ui/Medieval Warrior Pack/Idle.png",
    "hit": "assets/ui/Medieval Warrior Pack/Hit.png",
    "death": "assets/ui/Medieval Warrior Pack/Death.png",
}
_WIZARD_SHEETS: dict[str, str] = {
    "run": "assets/ui/EVil Wizard 2/Sprites/Run.png",
    "attack1": "assets/ui/EVil Wizard 2/Sprites/Attack1.png",
    "attack2": "assets/ui/EVil Wizard 2/Sprites/Attack2.png",
    "idle": "assets/ui/EVil Wizard 2/Sprites/Idle.png",
    "hit": "assets/ui/EVil Wizard 2/Sprites/Take hit.png",
    "death": "assets/ui/EVil Wizard 2/Sprites/Death.png",
}
_HERO_KNIGHT_DIRS: dict[str, str] = {
    "run": "assets/ui/Hero Knight/Sprites/HeroKnight/Run",
    "attack1": "assets/ui/Hero Knight/Sprites/HeroKnight/Attack1",
    "attack2": "assets/ui/Hero Knight/Sprites/HeroKnight/Attack2",
    "idle": "assets/ui/Hero Knight/Sprites/HeroKnight/Idle",
    "hit": "assets/ui/Hero Knight/Sprites/HeroKnight/Hurt",
    "death": "assets/ui/Hero Knight/Sprites/HeroKnight/Death",
}


def _get_warrior_frames(
    kind: str = "run",
    size: tuple[int, int] = (54, 54),
    style: str = "warrior",
) -> list[pygame.Surface]:
    """Load and cache animated ground-unit frames for 'warrior', 'wizard', or 'hero_knight'."""
    key = (style, kind, size)
    if key in _WARRIOR_FRAME_CACHE:
        return _WARRIOR_FRAME_CACHE[key]

    frames: list[pygame.Surface] = []
    if style == "wizard":
        path = _WIZARD_SHEETS.get(kind, _WIZARD_SHEETS["run"])
        sheet = get_sprite(path)
        if sheet is not None:
            cell_w = sheet.get_height()  # 250x250 square cells
            cell_h = sheet.get_height()
            count = max(1, sheet.get_width() // max(1, cell_w))
            # Feet locked at y=167 inside 250x250 cell; keep generous width for staff/fire swings
            crop_x, crop_y = 44, 48
            crop_w = min(162, cell_w - crop_x)
            crop_h = min(124, cell_h - crop_y)
            target_h = round(size[1] * 1.18)
            target_w = round(target_h * (crop_w / crop_h))
            for i in range(count):
                sub = sheet.subsurface(pygame.Rect(i * cell_w + crop_x, crop_y, crop_w, crop_h))
                frames.append(pygame.transform.smoothscale(sub, (target_w, target_h)))
    elif style == "hero_knight":
        folder = _HERO_KNIGHT_DIRS.get(kind, _HERO_KNIGHT_DIRS["run"])
        abs_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), folder)
        if os.path.isdir(abs_folder):
            pngs = sorted(
                (f for f in os.listdir(abs_folder) if f.lower().endswith(".png")),
                key=lambda fn: int(fn.rsplit("_", 1)[-1].split(".")[0]) if "_" in fn and fn.rsplit("_", 1)[-1].split(".")[0].isdigit() else fn,
            )
            # 100x55 frames with feet locked at y=53; preserve aspect ratio cleanly
            target_h = round(size[1] * 0.88)
            target_w = round(target_h * (100.0 / 55.0))
            for fn in pngs:
                spr = get_sprite(f"{folder}/{fn}")
                if spr is not None:
                    frames.append(pygame.transform.smoothscale(spr, (target_w, target_h)))
    else:
        path = _WARRIOR_SHEETS.get(kind, _WARRIOR_SHEETS["run"])
        sheet = get_sprite(path)
        if sheet is not None:
            cell_w = 184
            cell_h = sheet.get_height()
            count = max(1, sheet.get_width() // cell_w)
            # Consistent crop inside each 184x137 cell so feet stay pixel-locked across all actions
            crop_x, crop_y = 38, 22
            crop_w, crop_h = min(108, cell_w - crop_x), min(108, cell_h - crop_y)
            for i in range(count):
                sub = sheet.subsurface(pygame.Rect(i * cell_w + crop_x, crop_y, crop_w, crop_h))
                frames.append(pygame.transform.smoothscale(sub, size))

    _WARRIOR_FRAME_CACHE[key] = frames
    return frames


def _draw_road_patrols(
    surface: pygame.Surface,
    game_map: Map | None,
    houses: list[House] | None,
) -> None:
    """Render animated running ground troops patrolling between owned holds (Evil Wizard 2 for Targaryen)."""
    if game_map is None or not houses:
        return
    ticks_ms = pygame.time.get_ticks()
    ticks = ticks_ms * 0.00032
    warrior_run = _get_warrior_frames("run", (48, 48), style="warrior")
    wizard_run = _get_warrior_frames("run", (48, 48), style="wizard")
    fallback = get_sprite("assets/units/knights.png", (34, 38)) if not warrior_run else None
    for idx, house in enumerate(houses):
        if house.is_eliminated() or not house.territories:
            continue
        t_a = house.territories[0]
        owned_nb = next((nb for nb in t_a.neighbors if nb.owner == house.name), None)
        ax, ay = center_of(t_a.col, t_a.row)
        if owned_nb is not None:
            bx, by = center_of(owned_nb.col, owned_nb.row)
            p1x, p1y = ax + (bx - ax) * 0.28, ay + (by - ay) * 0.28
            p2x, p2y = ax + (bx - ax) * 0.72, ay + (by - ay) * 0.72
        else:
            p1x, p1y = ax - 28, ay + 18
            p2x, p2y = ax + 28, ay + 18

        cycle = (ticks + idx * 0.67) % 2.0
        going = cycle < 1.0
        u = cycle if going else (2.0 - cycle)
        px = p1x + (p2x - p1x) * u
        py = p1y + (p2y - p1y) * u
        dx = (p2x - p1x) if going else (p1x - p2x)
        accent = HOUSE_COLORS.get(house.name, GOLD)

        # Grounded contact shadow + subtle house team ring beneath feet
        foot_surf = pygame.Surface((32, 14), pygame.SRCALPHA)
        pygame.draw.ellipse(foot_surf, (8, 12, 16, 125), (3, 3, 26, 9))
        pygame.draw.ellipse(foot_surf, (*accent, 195), (4, 3, 24, 8), 2)
        surface.blit(foot_surf, (round(px - 16), round(py - 5)))

        run_frames = wizard_run if (house.name == "TARGARYEN" and wizard_run) else warrior_run
        if run_frames:
            frame = run_frames[(ticks_ms // 85 + idx * 2) % len(run_frames)]
            spr = pygame.transform.flip(frame, True, False) if dx < 0 else frame
            surface.blit(spr, (round(px - spr.get_width() / 2), round(py - spr.get_height() + 4)))
        elif fallback is not None:
            spr = pygame.transform.flip(fallback, True, False) if dx < 0 else fallback
            surface.blit(spr, (round(px - 17), round(py - 32)))


def _draw_drifting_clouds(surface: pygame.Surface, rect: pygame.Rect) -> None:
    """Render soft translucent cloud shadows gliding slowly west-to-east across Westeros."""
    ticks = pygame.time.get_ticks() * 0.012
    cloud_specs = [
        (0.0, 0.18, 220, 74, 24),
        (430.0, 0.38, 260, 86, 22),
        (920.0, 0.62, 240, 78, 20),
        (1380.0, 0.28, 210, 68, 22),
        (1680.0, 0.76, 250, 82, 18),
    ]
    span = rect.width + 320
    for offset_x, y_frac, w, h, alpha in cloud_specs:
        cx = rect.x - 160 + ((ticks + offset_x) % span)
        cy = rect.y + rect.height * y_frac + math.sin((ticks + offset_x) * 0.005) * 10
        cloud = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.ellipse(cloud, (6, 14, 22, alpha), (0, 14, w, h - 14))
        pygame.draw.ellipse(cloud, (220, 236, 245, alpha // 2), (w // 5, 4, int(w * 0.6), int(h * 0.62)))
        surface.blit(cloud, (round(cx - w / 2), round(cy - h / 2)))


def _draw_ambient_weather(surface: pygame.Surface, rect: pygame.Rect) -> None:
    """Render falling snow in the North and glowing volcanic embers near Dragonstone."""
    ticks = pygame.time.get_ticks()
    # Northern snowdrift over The Wall / Winterfell / Castle Black / Dreadfort
    nw_x, nw_y = center_of(1, 0)
    ne_x, _ = center_of(17, 0)
    snow_w = max(240, int(ne_x - nw_x + 120))
    snow_h = 230
    for i in range(44):
        sx = nw_x - 40 + ((i * 73 + ticks * 0.025) % snow_w)
        sy = nw_y - 30 + ((i * 41 + ticks * 0.032) % snow_h)
        sx += math.sin(ticks * 0.003 + i) * 6
        rad = 1 if i % 3 else 2
        pygame.draw.circle(surface, (240, 248, 255), (round(sx), round(sy)), rad)

    # Volcanic embers rising softly around Dragonstone
    dx, dy = center_of(*DRAGONSTONE_COORD)
    for i in range(10):
        t = ((ticks * 0.028) + i * 19) % 70
        ex = dx + math.sin(ticks * 0.004 + i * 1.7) * 26 + (i - 5) * 5
        ey = dy + 10 - t * 0.95
        col = (255, 195, 76) if i % 2 == 0 else (238, 92, 42)
        pygame.draw.circle(surface, col, (round(ex), round(ey)), 2 if t < 35 else 1)


def _draw_warrior_unit(
    surface: pygame.Surface,
    x: float,
    y: float,
    frames: list[pygame.Surface],
    frame_idx: int,
    flip_left: bool,
    ring_color: tuple[int, int, int],
    show_ring: bool = True,
) -> None:
    """Draw a single grounded Medieval Warrior with contact shadow and house ring."""
    foot = pygame.Surface((36, 14), pygame.SRCALPHA)
    pygame.draw.ellipse(foot, (8, 12, 16, 130), (3, 3, 30, 9))
    if show_ring:
        pygame.draw.ellipse(foot, (*ring_color, 215), (4, 3, 28, 8), 2)
    surface.blit(foot, (round(x - 18), round(y - 4)))
    if frames:
        spr = frames[frame_idx % len(frames)]
        if flip_left:
            spr = pygame.transform.flip(spr, True, False)
        surface.blit(spr, (round(x - spr.get_width() / 2), round(y - spr.get_height() + 4)))


def _draw_animations(
    surface: pygame.Surface,
    fonts: dict[str, pygame.font.Font],
    animations: list[dict[str, object]] | None,
) -> None:
    """Render castle-vs-castle warrior battles, flying dragons, ravens, & +Gold popups."""
    if not animations:
        return
    for anim in animations:
        kind = anim.get("type")
        elapsed = float(anim.get("elapsed", 0.0))
        duration = max(0.05, float(anim.get("duration", 1.0)))
        t = max(0.0, min(1.0, elapsed / duration))

        if kind == "march":
            house = str(anim.get("house", "STARK"))
            defender_name = str(anim.get("defender", "NEUTRAL"))
            accent = HOUSE_COLORS.get(house, GOLD)
            def_color = HOUSE_COLORS.get(defender_name, (205, 193, 159))
            ax, ay = center_of(*anim["from_coord"])  # type: ignore[misc]
            bx, by = center_of(*anim["to_coord"])  # type: ignore[misc]
            captured = bool(anim.get("captured", False))
            dx, dy = bx - ax, by - ay
            dist = math.hypot(dx, dy) or 1.0
            ux, uy = dx / dist, dy / dist

            # Battlefront midpoint slightly closer to the besieged castle
            mid_x = ax + dx * 0.56
            mid_y = ay + dy * 0.56
            att_meet_x, att_meet_y = mid_x - ux * 18, mid_y - uy * 12
            def_meet_x, def_meet_y = mid_x + ux * 18, mid_y + uy * 12
            att_flip = dx < 0
            def_flip = not att_flip

            att_is_targ = house == "TARGARYEN"
            def_is_targ = defender_name == "TARGARYEN"

            w_run = _get_warrior_frames("run", (62, 62), style="warrior")
            w_idle = _get_warrior_frames("idle", (62, 62), style="warrior")
            w_atk1 = _get_warrior_frames("attack1", (66, 66), style="warrior")
            w_atk2 = _get_warrior_frames("attack2", (66, 66), style="warrior")
            w_hit = _get_warrior_frames("hit", (62, 62), style="warrior")
            w_death = _get_warrior_frames("death", (62, 62), style="warrior")

            wiz_run = _get_warrior_frames("run", (66, 66), style="wizard")
            wiz_idle = _get_warrior_frames("idle", (66, 66), style="wizard")
            wiz_atk1 = _get_warrior_frames("attack1", (70, 70), style="wizard")
            wiz_atk2 = _get_warrior_frames("attack2", (70, 70), style="wizard")
            wiz_hit = _get_warrior_frames("hit", (66, 66), style="wizard")
            wiz_death = _get_warrior_frames("death", (66, 66), style="wizard")

            hk_run = _get_warrior_frames("run", (62, 62), style="hero_knight")
            hk_idle = _get_warrior_frames("idle", (62, 62), style="hero_knight")
            hk_atk1 = _get_warrior_frames("attack1", (66, 66), style="hero_knight")
            hk_atk2 = _get_warrior_frames("attack2", (66, 66), style="hero_knight")
            hk_hit = _get_warrior_frames("hit", (62, 62), style="hero_knight")
            hk_death = _get_warrior_frames("death", (62, 62), style="hero_knight")

            # (fx, fy, frame_offset, unit_kind) — Targaryen fields 2 front Warriors + 2 flanking Evil Wizards
            back_x = round(-ux * 24)
            fwd_x = round(ux * 6)
            if att_is_targ:
                att_slots: tuple[tuple[int, int, int, str], ...] = (
                    (back_x, -26, 0, "wizard"),
                    (fwd_x, -10, 2, "warrior"),
                    (fwd_x, 12, 4, "warrior"),
                    (back_x, 30, 6, "wizard"),
                )
            else:
                att_slots = (
                    (-10, -14, 0, "warrior"),
                    (0, 0, 2, "warrior"),
                    (-8, 14, 4, "warrior"),
                )

            if def_is_targ:
                def_slots: tuple[tuple[int, int, int, str], ...] = (
                    (-back_x, -26, 1, "wizard"),
                    (-fwd_x, -10, 3, "warrior"),
                    (-fwd_x, 12, 5, "warrior"),
                    (-back_x, 30, 7, "wizard"),
                )
            else:
                def_slots = (
                    (10, -14, 1, "hero_knight"),
                    (0, 0, 3, "hero_knight"),
                    (8, 14, 5, "hero_knight"),
                )

            def _unit_pack(kind: str) -> tuple[list[pygame.Surface], ...]:
                if kind == "wizard":
                    return (wiz_run, wiz_idle, wiz_atk1, wiz_atk2, wiz_hit, wiz_death)
                if kind == "hero_knight":
                    return (hk_run, hk_idle, hk_atk1, hk_atk2, hk_hit, hk_death)
                return (w_run, w_idle, w_atk1, w_atk2, w_hit, w_death)

            # Subtle pulsing battlefield glow between the two castles
            if 0.25 <= t <= 0.90:
                bf_surf = pygame.Surface((130, 68), pygame.SRCALPHA)
                bf_alpha = int(55 + 35 * math.sin(elapsed * 8.0))
                pygame.draw.ellipse(bf_surf, (*GOLD, bf_alpha), (6, 8, 118, 52))
                pygame.draw.ellipse(bf_surf, (*accent, bf_alpha + 40), (6, 8, 118, 52), 2)
                surface.blit(bf_surf, (round(mid_x - 65), round(mid_y - 30)))

            if t < 0.34:
                # Phase 1: Attacker charges out AND defending garrison sallies out to meet them
                mt = t / 0.34
                ease = mt * mt * (3.0 - 2.0 * mt)
                apx = ax + (att_meet_x - ax) * ease
                apy = ay + (att_meet_y - ay) * ease
                dpx = bx + (def_meet_x - bx) * ease
                dpy = by + (def_meet_y - by) * ease

                # Dragon flies high overhead so ground troops stay clearly visible
                arc = math.sin(mt * math.pi) * 16.0
                _draw_house_dragon(
                    surface,
                    house,
                    apx - ux * 36.0,
                    apy - uy * 18.0,
                    dx,
                    dy,
                    DRAGON_BATTLE_SIZE,
                    elapsed,
                    attacking=False,
                    altitude=66.0 + arc,
                )

                # Opposing defending warriors
                for fx, fy, foff, ukind in def_slots:
                    u_run = _unit_pack(ukind)[0]
                    _draw_warrior_unit(
                        surface, dpx + fx, dpy + fy, u_run, int(elapsed * 11) + foff, def_flip, def_color
                    )

                # Attacking ground vanguard (2 Wizards + 2 Warriors for Targaryen, 3 Warriors for Stark/Lannister)
                for fx, fy, foff, ukind in att_slots:
                    u_run = _unit_pack(ukind)[0]
                    _draw_warrior_unit(
                        surface, apx + fx, apy + fy, u_run, int(elapsed * 11) + foff, att_flip, accent
                    )

            elif t < 0.78:
                # Phase 2: Extended face-to-face clash & roaring dragonfire barrage!
                ct = (t - 0.34) / 0.44
                clash_cycle = int(elapsed * 3.5)

                # Opposing defenders fighting back
                for idx_w, (fx, fy, foff, ukind) in enumerate(def_slots):
                    _, _, u_atk1, u_atk2, u_hit, _ = _unit_pack(ukind)
                    taking_hit = ((clash_cycle + idx_w) % 3 == 0)
                    if taking_hit and u_hit:
                        fset = u_hit
                        fidx = int(elapsed * 9 + foff) % len(fset)
                    else:
                        fset = u_atk1 if (idx_w % 2 == 0) else u_atk2
                        fidx = int(elapsed * 9 + foff) % max(1, len(fset))
                    lunge = (-4 if def_flip else 4) * math.sin(elapsed * 12 + idx_w)
                    _draw_warrior_unit(
                        surface, def_meet_x + fx + lunge, def_meet_y + fy, fset, fidx, def_flip, def_color
                    )

                # Attacking ground squad fighting clearly in the foreground (never hidden by dragon)
                for idx_w, (fx, fy, foff, ukind) in enumerate(att_slots):
                    _, _, u_atk1, u_atk2, u_hit, _ = _unit_pack(ukind)
                    taking_hit = ((clash_cycle + idx_w + 1) % 3 == 0)
                    if taking_hit and u_hit:
                        fset = u_hit
                        fidx = int(elapsed * 9 + foff) % len(fset)
                    else:
                        fset = u_atk1 if (idx_w % 2 == 0) else u_atk2
                        fidx = int(elapsed * 9 + foff) % max(1, len(fset))
                    lunge = (-4 if att_flip else 4) * math.sin(elapsed * 12 + idx_w + 1.5)
                    _draw_warrior_unit(
                        surface, att_meet_x + fx + lunge, att_meet_y + fy, fset, fidx, att_flip, accent
                    )

                # Dragon hovers high above & slightly behind the squad, breathing fire downward onto defenders
                dragon_x = att_meet_x - ux * 46.0
                dragon_y = att_meet_y - uy * 24.0
                mouth = _draw_house_dragon(
                    surface,
                    house,
                    dragon_x,
                    dragon_y,
                    def_meet_x - dragon_x,
                    def_meet_y - dragon_y,
                    DRAGON_BATTLE_SIZE,
                    elapsed,
                    attacking=True,
                    altitude=74.0,
                )
                breath_reach = min(1.0, ct * 4.2)
                breath_fade = min(1.0, (1.0 - ct) * 5.0)
                _draw_dragon_breath(
                    surface,
                    house,
                    mouth,
                    (def_meet_x + ux * 14.0, def_meet_y + 4.0),
                    elapsed,
                    reach=breath_reach,
                    intensity=max(0.25, breath_fade),
                    show_ground_blaze=True,
                )

                # Live steel clash sparks flying between the two squads
                for i in range(7):
                    sp_p = (elapsed * 3.2 + i * 0.17) % 1.0
                    ang = i * (math.tau / 7) + elapsed * 3.0
                    rad = 4 + sp_p * 22
                    sx = round(mid_x + math.cos(ang) * rad)
                    sy = round(mid_y - 12 + math.sin(ang) * rad * 0.6)
                    pygame.draw.circle(surface, GOLD if i % 2 == 0 else IVORY, (sx, sy), max(1, round(3.5 * (1.0 - sp_p))))

                # Battle progress label clearly above the elevated dragon's wings
                clash_lbl = "DRAGONFIRE!" if house == "TARGARYEN" else ("FROSTFIRE!" if house == "STARK" else "GOLDEN FLAME!")
                write(surface, clash_lbl, (round(mid_x - fonts["micro"].size(clash_lbl)[0] / 2), round(mid_y - 116)), fonts["micro"], GOLD)

            else:
                # Phase 3: Defeated warriors fall, victors hold the field
                it = (t - 0.78) / 0.22

                if captured:
                    # Defenders collapse; attackers & victorious dragon claim the castle
                    for fx, fy, _, ukind in def_slots:
                        u_death = _unit_pack(ukind)[5]
                        d_idx = min(max(0, len(u_death) - 1), int(it * len(u_death)))
                        _draw_warrior_unit(
                            surface, def_meet_x + fx, def_meet_y + fy, u_death, d_idx, def_flip, def_color, show_ring=False
                        )
                    for fx, fy, foff, ukind in att_slots:
                        u_idle = _unit_pack(ukind)[1]
                        _draw_warrior_unit(
                            surface, att_meet_x + fx, att_meet_y + fy, u_idle, int(elapsed * 8) + foff, att_flip, accent
                        )
                    _draw_house_dragon(
                        surface,
                        house,
                        bx,
                        by,
                        dx,
                        dy,
                        DRAGON_BATTLE_SIZE,
                        elapsed,
                        attacking=False,
                        altitude=68.0,
                    )
                else:
                    # Attackers collapse & dragon banks away; defenders stand triumphant
                    for fx, fy, _, ukind in att_slots:
                        u_death = _unit_pack(ukind)[5]
                        a_idx = min(max(0, len(u_death) - 1), int(it * len(u_death)))
                        _draw_warrior_unit(
                            surface, att_meet_x + fx, att_meet_y + fy, u_death, a_idx, att_flip, accent, show_ring=False
                        )
                    for fx, fy, foff, ukind in def_slots:
                        u_idle = _unit_pack(ukind)[1]
                        _draw_warrior_unit(
                            surface, def_meet_x + fx, def_meet_y + fy, u_idle, int(elapsed * 8) + foff, def_flip, def_color
                        )
                    rx = att_meet_x - ux * 42.0 * it
                    ry = att_meet_y - uy * 42.0 * it
                    _draw_house_dragon(
                        surface,
                        house,
                        rx,
                        ry,
                        -dx,
                        -dy,
                        DRAGON_BATTLE_SIZE,
                        elapsed,
                        attacking=False,
                        altitude=66.0 + 14.0 * it,
                    )

                # Expanding outcome shockwave ring at the target castle
                ring_r = round(16 + it * 46)
                ring_surf = pygame.Surface((ring_r * 2 + 6, ring_r * 2 + 6), pygame.SRCALPHA)
                alpha = int(220 * (1.0 - it))
                pygame.draw.ellipse(
                    ring_surf,
                    (*(GOLD if captured else accent), alpha),
                    (3, ring_r // 2, ring_r * 2, ring_r),
                    3,
                )
                surface.blit(ring_surf, (round(bx - ring_r - 3), round(by - ring_r // 2)))

                # Floating outcome popup
                label = "CAPTURED!" if captured else "REPELLED"
                col = GOLD if captured else (235, 115, 95)
                write(surface, label, (round(bx - fonts["small"].size(label)[0] / 2), round(by - 52 - it * 18)), fonts["small"], col)

        elif kind == "raven":
            ax, ay = center_of(*anim["from_coord"])  # type: ignore[misc]
            bx, by = center_of(*anim["to_coord"])  # type: ignore[misc]
            ease = t * t * (3.0 - 2.0 * t)
            px = ax + (bx - ax) * ease
            py = ay + (by - ay) * ease - math.sin(t * math.pi) * 34
            raven = get_sprite("assets/ui/raven.png", (28, 28))
            if raven:
                spr = pygame.transform.flip(raven, True, False) if (bx - ax) < 0 else raven
                surface.blit(spr, (round(px - 14), round(py - 14)))

        elif kind == "gold":
            cx, cy = center_of(*anim["coord"])  # type: ignore[misc]
            amount = int(anim.get("amount", 0))
            fy = round(cy - 26 - t * 28)
            coin = get_sprite("assets/ui/gold_coin.png", (16, 16))
            if coin:
                surface.blit(coin, (round(cx - 24), fy))
            write(surface, f"+{amount}G", (round(cx - 5), fy), fonts["small"], GOLD)


def draw_crest(
    surface: pygame.Surface,
    center: tuple[int, int],
    house: str,
    radius: int = 20,
) -> None:
    """Render a crisp supersampled metallic-rimmed House crest."""
    x, y = center
    d = max(16, radius * 2 + 4)
    crest_img = get_sprite(f"assets/ui/crest_{house.lower()}.png", (d, d))
    if crest_img is not None:
        surface.blit(crest_img, (x - d // 2, y - d // 2))
        return

    color = HOUSE_COLORS.get(house, GOLD)
    pygame.draw.circle(surface, (18, 26, 30), center, radius + 3)
    pygame.draw.circle(surface, mix(color, GOLD, 0.4), center, radius + 3, 2)
    pygame.draw.circle(surface, (30, 42, 46), center, radius)

    if house == "STARK":
        # Direwolf profile
        pygame.draw.polygon(
            surface,
            color,
            [
                (x - 12, y - 7),
                (x - 6, y - 14),
                (x - 1, y - 7),
                (x + 5, y - 14),
                (x + 12, y - 7),
                (x + 8, y + 9),
                (x, y + 14),
                (x - 8, y + 9),
            ],
        )
        pygame.draw.circle(surface, (255, 255, 255), (x - 4, y - 1), 2)
        pygame.draw.circle(surface, (255, 255, 255), (x + 4, y - 1), 2)
    elif house == "LANNISTER":
        # Golden lion crest
        pygame.draw.circle(surface, color, center, 9, 2)
        for angle in range(0, 360, 45):
            radians = math.radians(angle)
            start = (x + math.cos(radians) * 10, y + math.sin(radians) * 10)
            end = (x + math.cos(radians) * 15, y + math.sin(radians) * 15)
            pygame.draw.line(surface, color, start, end, 2)
    else:
        # Three-headed dragon crest
        pygame.draw.polygon(
            surface,
            color,
            [
                (x - 11, y + 8),
                (x - 7, y - 10),
                (x, y - 3),
                (x + 8, y - 13),
                (x + 11, y + 7),
                (x + 4, y + 11),
                (x - 3, y + 5),
            ],
        )


def draw_glass_panel(
    surface: pygame.Surface,
    rect: pygame.Rect,
    fill: tuple[int, int, int] = INK_GLASS,
    border: tuple[int, int, int] = (117, 137, 128),
    radius: int = 10,
) -> None:
    """Render a polished obsidian-gradient medieval panel with double metallic bevel."""
    cache_key = (rect.width, rect.height, fill, border, radius)
    panel_surf = _PANEL_GRADIENT_CACHE.get(cache_key)
    if panel_surf is None:
        w, h = rect.size
        panel_surf = pygame.Surface((w + 14, h + 14), pygame.SRCALPHA)
        # Soft drop shadow
        pygame.draw.rect(
            panel_surf,
            (0, 6, 10, 130),
            pygame.Rect(7, 9, w, h),
            border_radius=radius + 2,
        )
        # Vertical gradient body clipped inside rounded mask
        body = pygame.Surface((w, h), pygame.SRCALPHA)
        top_col = mix(fill, (42, 58, 68), 0.35)
        bot_col = mix(fill, (10, 16, 20), 0.45)
        for row in range(h):
            t = row / max(1, h - 1)
            c = mix(top_col, bot_col, t)
            pygame.draw.line(body, (*c, 242), (0, row), (w - 1, row))
        mask = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=radius)
        body.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)

        # Outer dark rim + metallic border + inner subtle specular highlight
        pygame.draw.rect(body, (8, 12, 16, 230), body.get_rect(), 2, border_radius=radius)
        outer_trim = mix(border, GOLD, 0.25)
        pygame.draw.rect(body, (*outer_trim, 225), body.get_rect().inflate(-2, -2), 1, border_radius=max(2, radius - 1))
        pygame.draw.line(
            body,
            (255, 244, 210, 55),
            (radius + 8, 3),
            (max(radius + 8, w - radius - 8), 3),
            1,
        )
        panel_surf.blit(body, (6, 5))

        # Ornate gold corner flourishes on large frames
        if w > 160 and h > 60:
            trim = mix(border, GOLD, 0.65)
            for x, y, sx, sy in (
                (9, 8, 1, 1),
                (6 + w - 4, 8, -1, 1),
                (9, 5 + h - 4, 1, -1),
                (6 + w - 4, 5 + h - 4, -1, -1),
            ):
                pygame.draw.line(panel_surf, trim, (x, y), (x + sx * 14, y), 2)
                pygame.draw.line(panel_surf, trim, (x, y), (x, y + sy * 14), 2)
                pygame.draw.circle(panel_surf, GOLD, (x + sx * 4, y + sy * 4), 2)

        _PANEL_GRADIENT_CACHE[cache_key] = panel_surf

    surface.blit(panel_surf, (rect.x - 6, rect.y - 5))


def draw_backdrop(surface: pygame.Surface) -> None:
    """Render a deep medieval twilight atmosphere with parchment filigree."""
    for y in range(HEIGHT):
        t = y / HEIGHT
        color = (
            int(12 + 6 * t),
            int(20 + 8 * t),
            int(28 + 10 * t),
        )
        pygame.draw.line(surface, color, (0, y), (WIDTH, y))

    # Subtle ambient star/dust particles
    for index in range(70):
        x = (index * 193 + 71) % WIDTH
        y = (index * 127 + 37) % HEIGHT
        color = (40, 62, 68) if index % 2 else (65, 72, 60)
        pygame.draw.circle(surface, color, (x, y), 1)


def draw_top_bar(
    surface: pygame.Surface,
    fonts: dict[str, pygame.font.Font],
    houses: list[House] | None = None,
    turn: int = 1,
    mode: str = "AI vs AI",
) -> None:
    """Render the sleek medieval HUD header bar above the full-screen map."""
    bar = pygame.Rect(14, 10, WIDTH - 28, 60)
    draw_glass_panel(surface, bar, (20, 30, 36), GOLD, 10)

    # Title & Realm Year
    crown_icon = get_sprite("assets/ui/crown.png", (30, 30))
    if crown_icon:
        surface.blit(crown_icon, (bar.x + 14, bar.y + 15))
    write(surface, "GAME OF THRONES", (bar.x + 52, bar.y + 8), fonts["title"], GOLD)
    write(surface, "AI CONQUEST  ·  AUTUMN, 298 AC", (bar.x + 53, bar.y + 34), fonts["tiny"], (185, 198, 185))

    # Center Status Pills for Great Houses
    house_by_name = {h.name: h for h in houses} if houses else {}
    coin_icon = get_sprite("assets/ui/gold_coin.png", (18, 18))
    swords_icon = get_sprite("assets/ui/swords.png", (18, 18))
    tower_icon = get_sprite("assets/ui/tower.png", (18, 18))

    start_x = bar.x + 390
    for idx, h_name in enumerate(("STARK", "LANNISTER", "TARGARYEN")):
        h = house_by_name.get(h_name)
        gold_val = str(h.gold) if h else "60"
        army_val = str(h.armies) if h else "14"
        hold_val = str(len(h.territories)) if h else "1"
        accent = HOUSE_COLORS[h_name]

        pill_rect = pygame.Rect(start_x + idx * 320, bar.y + 7, 304, 46)
        pygame.draw.rect(surface, (18, 27, 33), pill_rect, border_radius=8)
        pygame.draw.rect(surface, mix(accent, GOLD, 0.2), pill_rect, 1, border_radius=8)
        pygame.draw.line(surface, (*mix(accent, (255, 255, 255), 0.3), 75), (pill_rect.x + 8, pill_rect.y + 1), (pill_rect.right - 8, pill_rect.y + 1), 1)

        draw_crest(surface, (pill_rect.x + 24, pill_rect.centery), h_name, 15)
        write(surface, h_name, (pill_rect.x + 48, pill_rect.y + 5), fonts["small"], accent)

        # Resources line
        rx = pill_rect.x + 48
        ry = pill_rect.y + 23
        if coin_icon:
            surface.blit(coin_icon, (rx, ry))
        write(surface, gold_val, (rx + 22, ry + 1), fonts["micro"], GOLD)

        if swords_icon:
            surface.blit(swords_icon, (rx + 80, ry))
        write(surface, army_val, (rx + 102, ry + 1), fonts["micro"], IVORY)

        if tower_icon:
            surface.blit(tower_icon, (rx + 158, ry))
        write(surface, hold_val, (rx + 180, ry + 1), fonts["micro"], IVORY)

    # Turn Display at Far Right
    div_x = bar.right - 224
    pygame.draw.line(surface, (82, 102, 98), (div_x, bar.y + 10), (div_x, bar.bottom - 10), 1)
    write(surface, "TURN", (div_x + 18, bar.y + 8), fonts["tiny"], MUTED)
    write(surface, f"{turn:02d}", (div_x + 18, bar.y + 22), fonts["turn"], GOLD)
    write(surface, mode, (div_x + 76, bar.y + 11), fonts["micro"], IVORY)
    step_note = "AWAITING VIEWER" if "AI vs AI" in mode else "PLAYER ORDERS"
    write(surface, step_note, (div_x + 76, bar.y + 30), fonts["tiny"], GOLD if "PLAYER" in step_note else MUTED)


# ---------------------------------------------------------------------------
# Continuous painted terrain, explicit territory borders, decorations
# ---------------------------------------------------------------------------
_TERRAIN_BASE: dict[str, tuple[tuple[int, int, int], int]] = {
    "grass": ((104, 152, 64), 34),
    "forest": ((58, 108, 56), 30),
    "snow": ((224, 233, 241), 14),
    "mountain": ((126, 127, 121), 36),
    "marsh": ((84, 124, 94), 26),
    "dry": ((200, 164, 100), 28),
}
_TEXTURE_CACHE: dict[tuple[str, tuple[int, int]], pygame.Surface] = {}
_LAYER_CACHE: dict[str, object] = {"key": None, "surf": None}
_DECO_CACHE: dict[str, pygame.Surface] = {}
_VIGNETTE_CACHE: dict[tuple[int, int], pygame.Surface] = {}


_GRASS_ASSET_PATH = "assets/ui/\u2014Pngtree\u2014top down view vibrant grass_23654644.png"
_SNOW_STYL_PATH = "assets/ui/textures/snow_styl_s502_seamless.png"
_MOUNTAIN_GROUND_PATH = "assets/ui/Assets/3D_objects/maps/default_Base_Color.jpg"


def _tile_seamless(tile_img: object, size: tuple[int, int]) -> object:
    from PIL import Image

    w, h = size
    canvas_img = Image.new("RGB", (w, h))
    tw, th = tile_img.size  # type: ignore[attr-defined]
    for y in range(0, h, th):
        for x in range(0, w, tw):
            canvas_img.paste(tile_img, (x, y))  # type: ignore[arg-type]
    return canvas_img


def _terrain_texture(kind: str, size: tuple[int, int]) -> pygame.Surface:
    """Painted texture for a terrain kind using user grass, snow, and alpine rock assets."""
    key = (kind, size)
    if key in _TEXTURE_CACHE:
        return _TEXTURE_CACHE[key]
    import random

    import numpy as np
    from PIL import Image

    w, h = size
    if kind in ("grass", "forest", "marsh") and os.path.exists(_GRASS_ASSET_PATH):
        try:
            raw = Image.open(_GRASS_ASSET_PATH).convert("RGBA").convert("RGB")
            rw, rh = raw.size
            crop = raw.crop((int(rw * 0.24), int(rh * 0.19), int(rw * 0.76), int(rh * 0.80)))
            tile = crop.resize((360, 420), Image.Resampling.LANCZOS)
            tw, th = tile.size
            block = Image.new("RGB", (tw * 2, th * 2))
            t_fx = tile.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            t_fy = tile.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
            t_fxy = t_fx.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
            block.paste(tile, (0, 0))
            block.paste(t_fx, (tw, 0))
            block.paste(t_fy, (0, th))
            block.paste(t_fxy, (tw, th))

            canvas_img = _tile_seamless(block, (w, h))
            arr = np.asarray(canvas_img, dtype=float)
            if kind == "grass":
                arr *= np.array([0.88, 0.92, 0.86])
            elif kind == "forest":
                arr *= np.array([0.62, 0.76, 0.64])
            elif kind == "marsh":
                arr = arr * np.array([0.68, 0.78, 0.76]) + np.array([10.0, 18.0, 22.0])
            arr_u8 = np.clip(arr, 0, 255).astype("uint8")
            rgb = pygame.image.frombuffer(arr_u8.tobytes(), (w, h), "RGB")
            surf = pygame.Surface((w, h), pygame.SRCALPHA)
            surf.blit(rgb, (0, 0))
            _TEXTURE_CACHE[key] = surf
            return surf
        except Exception as e:
            print(f"Warning: failed loading grass texture {_GRASS_ASSET_PATH}: {e}")

    if kind == "snow" and os.path.exists(_SNOW_STYL_PATH):
        try:
            tile = Image.open(_SNOW_STYL_PATH).convert("RGB").resize((256, 256), Image.Resampling.LANCZOS)
            canvas_img = _tile_seamless(tile, (w, h))
            rgb = pygame.image.frombuffer(np.asarray(canvas_img, dtype="uint8").tobytes(), (w, h), "RGB")
            surf = pygame.Surface((w, h), pygame.SRCALPHA)
            surf.blit(rgb, (0, 0))
            _TEXTURE_CACHE[key] = surf
            return surf
        except Exception as e:
            print(f"Warning: failed loading snow texture {_SNOW_STYL_PATH}: {e}")

    if kind == "mountain" and os.path.exists(_MOUNTAIN_GROUND_PATH):
        try:
            raw = Image.open(_MOUNTAIN_GROUND_PATH).convert("RGB")
            rw, rh = raw.size
            crop = raw.crop((0, int(rh * 0.58), int(rw * 0.42), rh))
            tile = crop.resize((256, 256), Image.Resampling.LANCZOS)
            tw, th = tile.size
            block = Image.new("RGB", (tw * 2, th * 2))
            t_fx = tile.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            t_fy = tile.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
            t_fxy = t_fx.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
            block.paste(tile, (0, 0))
            block.paste(t_fx, (tw, 0))
            block.paste(t_fy, (0, th))
            block.paste(t_fxy, (tw, th))
            canvas_img = _tile_seamless(block, (w, h))
            arr = np.asarray(canvas_img, dtype=float) * np.array([0.76, 0.78, 0.80])
            arr_u8 = np.clip(arr, 0, 255).astype("uint8")
            rgb = pygame.image.frombuffer(arr_u8.tobytes(), (w, h), "RGB")
            surf = pygame.Surface((w, h), pygame.SRCALPHA)
            surf.blit(rgb, (0, 0))
            _TEXTURE_CACHE[key] = surf
            return surf
        except Exception as e:
            print(f"Warning: failed loading mountain ground texture {_MOUNTAIN_GROUND_PATH}: {e}")

    seed = sum(ord(c) for c in kind) * 13
    rng = np.random.default_rng(seed)
    acc = np.zeros((h, w))
    for cell, weight in ((110, 0.42), (40, 0.34), (14, 0.24)):
        small = rng.random((h // cell + 2, w // cell + 2))
        img = Image.fromarray((small * 255).astype("uint8")).resize((w, h), Image.BICUBIC)
        acc += np.asarray(img, dtype=float) / 255.0 * weight
    base, var = _TERRAIN_BASE[kind]
    shade = (acc - 0.5) * var * 2.0
    arr = np.stack(
        [np.clip(base[i] + shade * (0.8 if i == 2 else 1.0), 0, 255) for i in range(3)], axis=-1
    ).astype("uint8")
    rgb = pygame.image.frombuffer(arr.tobytes(), (w, h), "RGB")
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    surf.blit(rgb, (0, 0))

    rnd = random.Random(seed)
    if kind in ("grass", "forest", "marsh"):
        for _ in range(2600):
            x, y = rnd.randrange(w), rnd.randrange(h)
            tone = rnd.choice(((150, 190, 92), (70, 112, 44), (176, 205, 110), (58, 96, 40)))
            pygame.draw.line(surf, tone, (x, y), (x + rnd.randint(-1, 2), y - rnd.randint(2, 4)), 1)
    elif kind == "snow":
        for _ in range(1400):
            x, y = rnd.randrange(w), rnd.randrange(h)
            surf.set_at((x, y), rnd.choice(((255, 255, 255, 255), (186, 204, 222, 255))))
    elif kind == "mountain":
        for _ in range(700):
            x, y = rnd.randrange(w), rnd.randrange(h)
            pygame.draw.line(surf, rnd.choice(((86, 88, 86), (160, 160, 152))), (x, y), (x + rnd.randint(3, 9), y + rnd.randint(-2, 3)), 1)
    elif kind == "dry":
        for _ in range(1600):
            x, y = rnd.randrange(w), rnd.randrange(h)
            surf.set_at((x, y), rnd.choice(((224, 190, 130, 255), (170, 130, 76, 255))))
    _TEXTURE_CACHE[key] = surf
    return surf


def _hex_mask(
    centers: list[tuple[float, float]],
    radius: float,
    size: tuple[int, int],
    color: tuple[int, int, int, int] = (255, 255, 255, 255),
    dy: float = 0,
) -> pygame.Surface:
    mask = pygame.Surface(size, pygame.SRCALPHA)
    mask.fill((color[0], color[1], color[2], 0))
    for cx, cy in centers:
        pygame.draw.polygon(mask, color, hex_points((cx, cy + dy), radius))
    return mask


def _soften(mask: pygame.Surface, factor: int = 6) -> pygame.Surface:
    w, h = mask.get_size()
    small = pygame.transform.smoothscale(mask, (max(1, w // factor), max(1, h // factor)))
    return pygame.transform.smoothscale(small, (w, h))


def _land_cells() -> list[tuple[int, int, tuple[float, float]]]:
    cells = []
    for col in range(GRID_COLS):
        for row in range(GRID_ROWS):
            if on_land(col, row) or (col, row) == DRAGONSTONE_COORD:
                cells.append((col, row, center_of(col, row)))
    return cells


def _region_info(game_map: Map | None, col: int, row: int) -> tuple[object, str | None]:
    if game_map is not None:
        territory = game_map.region_of(col, row)
        if territory is not None:
            return territory.name, territory.owner
        return None, None
    owner = owner_at(col, row, None)
    return owner, owner


def build_land_layer(game_map: Map | None) -> pygame.Surface:
    """Compose the cached land layer: painted terrain, territory tint, borders, coastline."""
    size = (WIDTH, HEIGHT)
    cells = _land_cells()
    land = {(c, r) for c, r, _ in cells}
    centers = [ctr for _, _, ctr in cells]
    layer = pygame.Surface(size, pygame.SRCALPHA)

    # Soft cast shadow on the sea, then layered cliff walls for 3D depth.
    layer.blit(_soften(_hex_mask(centers, HEX_R + 2, size, (0, 14, 24, 120), dy=20), 4), (0, 0))
    for dy, color in ((14, (58, 44, 30, 255)), (9, (92, 72, 50, 255)), (4, (122, 98, 66, 255))):
        for cx, cy in centers:
            pygame.draw.polygon(layer, color, hex_points((cx, cy + dy), HEX_R + 1.5))

    land_mask = _hex_mask(centers, HEX_R + 1.5, size)
    terr = pygame.Surface(size, pygame.SRCALPHA)
    base = _terrain_texture("grass", size).copy()
    base.blit(land_mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    terr.blit(base, (0, 0))
    for kind in ("forest", "snow", "mountain", "marsh", "dry"):
        kc = [ctr for c, r, ctr in cells if terrain_at(c, r) == kind]
        if not kc:
            continue
        tex = _terrain_texture(kind, size).copy()
        tex.blit(_soften(_hex_mask(kc, HEX_R + 3, size), 5), (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        terr.blit(tex, (0, 0))
    # Bake rivers and roads directly into terrain layer underneath territory borders
    draw_roads_and_rivers(terr)
    terr.blit(land_mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    layer.blit(terr, (0, 0))

    # Territory tint per house: the whole region glows in heraldic colour.
    owner_cells: dict[str, list[tuple[float, float]]] = {}
    for c, r, ctr in cells:
        _, owner = _region_info(game_map, c, r)
        if owner:
            owner_cells.setdefault(owner, []).append(ctr)
    for owner, oc in owner_cells.items():
        tint = _hex_mask(oc, HEX_R + 1, size, (*HOUSE_COLORS[owner], 92))
        tint.blit(land_mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        layer.blit(tint, (0, 0))

    # Borders: thin lines between regions, thick glowing lines where houses meet.
    for col, row, ctr in cells:
        rid, oa = _region_info(game_map, col, row)
        pts = hex_points(ctr)
        neighbors = (
            [(col + 1, row), (col, row + 1), (col - 1, row), (col - 1, row - 1), (col, row - 1), (col + 1, row - 1)]
            if col % 2 == 0
            else [(col + 1, row + 1), (col, row + 1), (col - 1, row + 1), (col - 1, row), (col, row - 1), (col + 1, row)]
        )
        for side, n in enumerate(neighbors):
            p0, p1 = pts[side], pts[(side + 1) % 6]
            if n in land:
                nid, ob = _region_info(game_map, n[0], n[1])
                if nid == rid:
                    continue
                if (col, row) < n:
                    pygame.draw.line(layer, (36, 34, 24, 150), p0, p1, 1)
                if oa and oa != ob:
                    _draw_border_line(layer, p0, p1, ctr, HOUSE_COLORS[oa])
            else:
                mx, my = (p0[0] + p1[0]) / 2 - ctr[0], (p0[1] + p1[1]) / 2 - ctr[1]
                ln = math.hypot(mx, my) or 1
                ox, oy = mx / ln * 3, my / ln * 3
                pygame.draw.line(layer, (46, 34, 22, 255), (p0[0] + ox, p0[1] + oy), (p1[0] + ox, p1[1] + oy), 4)
                pygame.draw.line(layer, (232, 246, 240, 190), (p0[0] + ox * 2, p0[1] + oy * 2), (p1[0] + ox * 2, p1[1] + oy * 2), 2)
                if oa:
                    _draw_border_line(layer, p0, p1, ctr, HOUSE_COLORS[oa])
    return layer


def _draw_border_line(
    layer: pygame.Surface,
    p0: tuple[int, int],
    p1: tuple[int, int],
    center: tuple[float, float],
    color: tuple[int, int, int],
) -> None:
    def inset(p: tuple[int, int], amt: float) -> tuple[float, float]:
        return p[0] + (center[0] - p[0]) * amt, p[1] + (center[1] - p[1]) * amt

    a, b = inset(p0, 0.07), inset(p1, 0.07)
    pygame.draw.line(layer, (16, 18, 16, 230), a, b, 8)
    pygame.draw.line(layer, (*color, 255), a, b, 5)
    pygame.draw.line(layer, (*mix(color, (255, 255, 255), 0.55), 255), a, b, 1)
    for p in (a, b):
        pygame.draw.circle(layer, (*color, 255), (round(p[0]), round(p[1])), 3)


def get_land_layer(game_map: Map | None) -> pygame.Surface:
    key = tuple(
        (c, r, _region_info(game_map, c, r)[1]) for c, r, _ in _land_cells()
    )
    if _LAYER_CACHE["key"] != key or _LAYER_CACHE["surf"] is None:
        _LAYER_CACHE["surf"] = build_land_layer(game_map)
        _LAYER_CACHE["key"] = key
    return _LAYER_CACHE["surf"]  # type: ignore[return-value]


_TREE_SET_PATH = "assets/ui/Tree Set #1/tree-set.png"
_TREE_SET_RECTS: tuple[tuple[int, int, int, int, int], ...] = (
    (11, 14, 106, 114, 46),
    (145, 5, 100, 123, 50),
    (287, 32, 80, 96, 40),
    (409, 48, 69, 80, 34),
)


def _load_tree_sprite(index: int, snowy: bool = False) -> pygame.Surface | None:
    """Load, scale, optionally frost, and add a grounded shadow to a tree sprite."""
    if not (0 <= index < len(_TREE_SET_RECTS)) or not os.path.exists(_TREE_SET_PATH):
        return None
    try:
        import numpy as np
        from PIL import Image

        x, y, w, h, target_h = _TREE_SET_RECTS[index]
        tw = max(1, round(w * target_h / h))
        th = target_h
        with Image.open(_TREE_SET_PATH) as sheet:
            crop = sheet.convert("RGBA").crop((x, y, x + w, y + h))
        resized = crop.resize((tw, th), Image.Resampling.LANCZOS)

        if snowy:
            arr = np.asarray(resized, dtype=float).copy()
            r, g, b, a = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2], arr[:, :, 3]
            foliage_mask = (a > 40) & (g >= r)
            # Cool green foliage toward muted winter blue-green while leaving trunks intact
            arr[foliage_mask, 0] *= 0.78
            arr[foliage_mask, 1] *= 0.88
            arr[foliage_mask, 2] *= 0.96
            luma = 0.299 * r + 0.587 * g + 0.114 * b
            ys = np.arange(th)[:, None]
            highlight_mask = foliage_mask & (luma >= 115) & (ys < int(th * 0.78))
            arr[highlight_mask, 0] = arr[highlight_mask, 0] * 0.35 + 236.0 * 0.65
            arr[highlight_mask, 1] = arr[highlight_mask, 1] * 0.35 + 244.0 * 0.65
            arr[highlight_mask, 2] = arr[highlight_mask, 2] * 0.35 + 250.0 * 0.65
            arr_u8 = np.clip(arr, 0, 255).astype("uint8")
            tree_surf = pygame.image.frombuffer(arr_u8.tobytes(), (tw, th), "RGBA")
        else:
            tree_surf = pygame.image.frombuffer(resized.tobytes(), (tw, th), "RGBA")

        s = pygame.Surface((tw + 6, th + 5), pygame.SRCALPHA)
        shadow_w = max(16, int(tw * 0.62))
        pygame.draw.ellipse(s, (0, 0, 0, 75), (tw // 2 + 3 - shadow_w // 2, th - 3, shadow_w, 7))
        s.blit(tree_surf, (3, 0))
        return s
    except Exception as e:
        print(f"Warning: failed loading tree sprite {index} from {_TREE_SET_PATH}: {e}")
        return None


def _deco_sprite(kind: str) -> pygame.Surface:
    """Tree sprites (tree-set.png), 3D mountain sprites (mountain_*.png), and fallbacks."""
    if kind in _DECO_CACHE:
        return _DECO_CACHE[kind]
    alias = {"oak": "tree_0", "pine": "tree_1", "snowpine": "snow_1", "mountain": "mountain_0"}.get(kind, kind)
    if alias.startswith(("tree_", "snow_")):
        try:
            idx = int(alias.split("_", 1)[1])
            loaded = _load_tree_sprite(idx, snowy=alias.startswith("snow_"))
            if loaded is not None:
                _DECO_CACHE[kind] = loaded
                return loaded
        except ValueError:
            pass
    if alias.startswith("mountain_"):
        loaded = get_sprite(f"assets/tiles/{alias}.png")
        if loaded is not None:
            _DECO_CACHE[kind] = loaded
            return loaded

    if kind == "mountain" or kind.startswith("mountain_"):
        s = pygame.Surface((68, 52), pygame.SRCALPHA)
        pygame.draw.ellipse(s, (0, 0, 0, 65), (6, 40, 56, 10))
        pygame.draw.polygon(s, (92, 94, 92), [(4, 46), (23, 9), (47, 46)])
        pygame.draw.polygon(s, (138, 139, 132), [(23, 9), (47, 46), (29, 46), (20, 22)])
        pygame.draw.polygon(s, (112, 114, 108), [(30, 46), (47, 18), (64, 46)])
        pygame.draw.polygon(s, (74, 76, 74), [(47, 18), (64, 46), (50, 46)])
        pygame.draw.polygon(s, (246, 248, 250), [(23, 9), (16, 20), (21, 19), (24, 23), (29, 18), (32, 21)])
        pygame.draw.polygon(s, (240, 244, 248), [(47, 18), (42, 27), (46, 25), (49, 29), (53, 25)])
    elif kind == "oak" or kind.startswith("tree_"):
        s = pygame.Surface((32, 40), pygame.SRCALPHA)
        pygame.draw.ellipse(s, (0, 0, 0, 75), (4, 31, 24, 7))
        pygame.draw.rect(s, (84, 62, 38), (14, 19, 4, 15))
        for (x, y, r, col) in ((11, 19, 9, (36, 84, 44)), (21, 17, 9, (46, 100, 52)), (16, 11, 10, (64, 126, 64)), (13, 8, 5, (118, 168, 88))):
            pygame.draw.circle(s, col, (x, y), r)
    elif kind in ("pine", "snowpine") or kind.startswith("snow_"):
        is_snow = kind == "snowpine" or kind.startswith("snow_")
        s = pygame.Surface((28, 42), pygame.SRCALPHA)
        pygame.draw.ellipse(s, (0, 0, 0, 75), (3, 34, 22, 7))
        pygame.draw.rect(s, (70, 52, 34), (12, 29, 4, 9))
        green = (52, 92, 76) if is_snow else (30, 78, 52)
        for i, w in enumerate((22, 17, 12)):
            top = 4 + i * 9
            pygame.draw.polygon(s, green, [(14, top), (14 - w // 2, top + 14), (14 + w // 2, top + 14)])
            pygame.draw.polygon(s, mix(green, (255, 255, 255), 0.55 if is_snow else 0.12), [(14, top), (14 - w // 2, top + 14), (14, top + 12)])
        if is_snow:
            pygame.draw.polygon(s, (248, 250, 252), [(14, 4), (10, 12), (18, 12)])
    else:
        s = pygame.Surface((4, 4), pygame.SRCALPHA)
    _DECO_CACHE[kind] = s
    return s


def _decorations_for(col: int, row: int, center: tuple[float, float]) -> list[tuple[float, pygame.Surface, tuple[int, int]]]:
    kind = terrain_at(col, row)
    cx, cy = center
    seed = col * 31 + row * 17
    out: list[tuple[float, pygame.Surface, tuple[int, int]]] = []
    offsets = ((-14, -6), (13, -8), (2, 9), (-9, 11), (15, 6))
    if kind == "forest":
        forest_choices = ("tree_0", "tree_1", "tree_2", "tree_3")
        for i in range(3):
            ox, oy = offsets[(seed + i) % 5]
            spr = _deco_sprite(forest_choices[(seed + i) % 4])
            out.append((cy + oy, spr, (round(cx + ox - spr.get_width() / 2), round(cy + oy - spr.get_height() + 4))))
    elif kind == "snow" and (col + row) % 2 == 0:
        snow_choices = ("snow_1", "snow_2", "snow_3")
        for i in range(2):
            ox, oy = offsets[(seed + i * 2) % 5]
            spr = _deco_sprite(snow_choices[(seed + i) % 3])
            out.append((cy + oy, spr, (round(cx + ox - spr.get_width() / 2), round(cy + oy - spr.get_height() + 4))))
    elif kind == "mountain":
        spr = _deco_sprite(f"mountain_{seed % 3}")
        out.append((cy + 6, spr, (round(cx - spr.get_width() / 2), round(cy - spr.get_height() + 16))))
    elif kind == "grass" and seed % 3 == 0:
        grass_choices = ("tree_0", "tree_2", "tree_3")
        ox, oy = offsets[seed % 5]
        spr = _deco_sprite(grass_choices[seed % 3])
        out.append((cy + oy, spr, (round(cx + ox - spr.get_width() / 2), round(cy + oy - spr.get_height() + 4))))
    elif kind == "marsh" and seed % 3 == 0:
        ox, oy = offsets[seed % 5]
        spr = _deco_sprite(("tree_2", "tree_3")[seed % 2])
        out.append((cy + oy, spr, (round(cx + ox - spr.get_width() / 2), round(cy + oy - spr.get_height() + 4))))
    return out


def draw_wall_ring(surface: pygame.Surface, cx: int, cy: int, house: str, front: bool) -> None:
    """Stone curtain wall with banner-roofed towers, drawn in two halves for 3D overlap."""
    rx, ry, ccy = 50, 24, cy + 6
    accent = HOUSE_COLORS[house]
    a0, a1 = (0, 180) if front else (180, 360)
    pts = [(cx + rx * math.cos(math.radians(a)), ccy + ry * math.sin(math.radians(a))) for a in range(a0, a1 + 1, 6)]
    pygame.draw.lines(surface, (40, 36, 32), False, pts, 9)
    pygame.draw.lines(surface, (146, 142, 128), False, pts, 6)
    pygame.draw.lines(surface, (204, 199, 180), False, pts, 1)
    for a in range(a0, a1 + 1, 45):
        if (a == 360 and not front) or (a == 180 and front and False):
            continue
        tx = cx + rx * math.cos(math.radians(a))
        ty = ccy + ry * math.sin(math.radians(a))
        pygame.draw.rect(surface, (118, 114, 102), (tx - 4, ty - 14, 8, 15))
        pygame.draw.rect(surface, (176, 171, 154), (tx - 4, ty - 14, 3, 15))
        pygame.draw.polygon(surface, accent, [(tx - 6, ty - 13), (tx, ty - 23), (tx + 6, ty - 13)])
        pygame.draw.polygon(surface, mix(accent, (255, 255, 255), 0.35), [(tx - 6, ty - 13), (tx, ty - 23), (tx, ty - 13)])


def draw_vignette(surface: pygame.Surface, rect: pygame.Rect) -> None:
    key = rect.size
    if key not in _VIGNETTE_CACHE:
        v = pygame.Surface(rect.size, pygame.SRCALPHA)
        for i in range(46):
            alpha = int(110 * (1 - i / 46) ** 2)
            pygame.draw.rect(v, (4, 10, 16, alpha), pygame.Rect(i, i, rect.width - 2 * i, rect.height - 2 * i), 1)
        _VIGNETTE_CACHE[key] = v
    surface.blit(_VIGNETTE_CACHE[key], rect.topleft)


def draw_world(
    surface: pygame.Surface,
    fonts: dict[str, pygame.font.Font],
    rect: pygame.Rect,
    game_map: Map | None = None,
    houses: list[House] | None = None,
    turn: int = 1,
    animations: list[dict[str, object]] | None = None,
) -> None:
    """Render the 2.5D isometric world map with animated sea, terrain slabs, and fortresses."""
    previous_clip = surface.get_clip()
    surface.set_clip(rect)

    shake_by_name: dict[str, int] = {}
    if animations:
        for anim in animations:
            if anim.get("type") == "march":
                t = float(anim.get("elapsed", 0.0)) / max(0.05, float(anim.get("duration", 1.0)))
                if 0.60 <= t <= 0.88:
                    tname = str(anim.get("target_name", ""))
                    shake_by_name[tname] = round(math.sin(t * 95.0) * 4)

    # 1. Living Ocean & Sailing Warships
    draw_sea_animated(surface, rect)
    _draw_sailing_ships(surface, rect)

    # 2. Collect and Render 2.5D Terrain Tiles
    land_cells: list[tuple[int, int, tuple[float, float], str | None]] = []
    house_by_name = {h.name: h for h in houses} if houses else {}

    for col in range(GRID_COLS):
        for row in range(GRID_ROWS):
            if on_land(col, row) or (col, row) == DRAGONSTONE_COORD:
                center = center_of(col, row)
                owner = owner_at(col, row, game_map)
                land_cells.append((col, row, center, owner))

    # Continuous painted terrain with explicit territory tint, roads, rivers, and borders
    surface.blit(get_land_layer(game_map), (0, 0))

    # 4. Y-Sorted Object Rendering (Painter's Algorithm for true 2.5D overlap)
    render_queue: list[tuple[float, str, object]] = []

    # Queue Landmarks
    if game_map is not None:
        for territory in game_map.get_all():
            col, row = territory.col, territory.row
            if not on_land(col, row) and (col, row) != DRAGONSTONE_COORD:
                continue
            center = center_of(col, row)
            owner_house = house_by_name.get(territory.owner) if territory.owner else None
            displayed_armies = owner_house.armies if owner_house is not None else territory.armies
            render_queue.append((center[1], "landmark", (center, territory.name, displayed_armies, territory.owner)))
    else:
        for (col, row), (name, feature, armies, house) in LANDMARKS.items():
            if not on_land(col, row) and (col, row) != DRAGONSTONE_COORD:
                continue
            center = center_of(col, row)
            render_queue.append((center[1], "landmark", (center, name, armies, house)))

    # Queue Field Squads
    for col, row, house in FIELD_SQUADS:
        if on_land(col, row) and (col, row) not in LANDMARKS:
            center = center_of(col, row)
            render_queue.append((center[1] + 12, "squad", (center, house, 4)))

    # Trees, pines and mountains
    seats = {(t.col, t.row) for t in game_map.get_all()} if game_map is not None else set(LANDMARKS)
    for col, row, center, _owner in land_cells:
        if (col, row) in seats or (col, row) in LANDMARKS:
            continue
        for y_sort, spr, pos in _decorations_for(col, row, center):
            render_queue.append((y_sort, "deco", (spr, pos)))

    # Sort strictly by screen Y so foreground objects overlap background objects!
    render_queue.sort(key=lambda item: item[0])

    # Draw all objects in order
    for _, kind, data in render_queue:
        if kind == "deco":
            spr, pos = data  # type: ignore
            surface.blit(spr, pos)
        elif kind == "landmark":
            center, name, armies, house = data  # type: ignore
            draw_isometric_landmark(
                surface, center, name, armies, house, fonts, mode="body", shake_x=shake_by_name.get(name, 0)
            )
        elif kind == "squad":
            center, house, armies = data  # type: ignore
            draw_knight_squad(surface, center, house, fonts, armies=armies)

    # Living Patrols, Dragon, CoC-style Battle Animations, Weather & Drifting Clouds
    _draw_road_patrols(surface, game_map, houses)
    _draw_patrol_dragon(surface, game_map, houses, animations)
    _draw_animations(surface, fonts, animations)
    _draw_ambient_weather(surface, rect)
    _draw_drifting_clouds(surface, rect)

    # Name plaques last so no sprite ever hides a label
    for _, kind, data in render_queue:
        if kind == "landmark":
            center, name, armies, house = data  # type: ignore
            draw_isometric_landmark(surface, center, name, armies, house, fonts, mode="plaque")

    draw_vignette(surface, rect)

    # Map Title Banner in Corner
    header = pygame.Rect(rect.x + 14, rect.y + 12, 230, 48)
    draw_glass_panel(surface, header, (24, 38, 42), GOLD, 8)
    write(surface, "THE SEVEN KINGDOMS", (header.x + 12, header.y + 6), fonts["maptitle"], IVORY)
    write(surface, f"WESTEROS  ·  TURN {turn:02d}", (header.x + 12, header.y + 27), fonts["micro"], MUTED)

    # Bottom Legend
    legend = pygame.Rect(rect.x + 14, rect.bottom - 36, rect.width - 28, 26)
    draw_glass_panel(surface, legend, (20, 32, 36), (90, 110, 108), 6)
    for index, (label, color) in enumerate(
        (("STARK", STARK), ("LANNISTER", LANNISTER), ("TARGARYEN", TARGARYEN), ("NEUTRAL", (205, 193, 159)))
    ):
        x = legend.x + 14 + index * 104
        pygame.draw.circle(surface, color, (x + 5, legend.centery), 5)
        write(surface, label, (x + 16, legend.centery - 7), fonts["micro"], IVORY)
    legend_txt = "KING'S LANDING = THE IRON THRONE (CAPTURE TO WIN)"
    write_right(surface, legend_txt, legend.right - 14, legend.centery - 7, fonts["micro"], GOLD)
    crown_mini = get_sprite("assets/ui/crown.png", (14, 14))
    if crown_mini:
        t_w = fonts["micro"].size(legend_txt)[0]
        surface.blit(crown_mini, (legend.right - 14 - t_w - 18, legend.centery - 7))

    surface.set_clip(previous_clip)


def draw_house_stat_card(
    surface: pygame.Surface,
    rect: pygame.Rect,
    house_data: dict[str, object],
    fonts: dict[str, pygame.font.Font],
) -> None:
    """Render an individual House Intelligence Card with live economic & military telemetry."""
    name = str(house_data.get("name", "STARK"))
    color = HOUSE_COLORS.get(name, IVORY)
    draw_glass_panel(surface, rect, (20, 30, 34), color, 8)

    draw_crest(surface, (rect.x + 28, rect.y + 28), name, 18)
    write(surface, f"HOUSE {name}", (rect.x + 54, rect.y + 10), fonts["cardtitle"], color)
    write(surface, str(house_data.get("motto", "")), (rect.x + 54, rect.y + 29), fonts["tiny"], MUTED)

    status = str(house_data.get("status", "SOLO"))
    is_elim = status == "ELIMINATED"
    status_col = (190, 82, 82) if is_elim else (STARK if "ALLY" in status else (GOLD if "YOUR" in status else MUTED))
    status_badge = pygame.Rect(rect.right - 114, rect.y + 10, 100, 22)
    pygame.draw.rect(surface, (24, 34, 40), status_badge, border_radius=6)
    pygame.draw.rect(surface, status_col, status_badge, 1, border_radius=6)
    write_right(surface, status, status_badge.right - 8, status_badge.y + 3, fonts["tiny"], status_col)

    # Stats Row
    pygame.draw.line(surface, (60, 78, 76), (rect.x + 14, rect.y + 54), (rect.right - 14, rect.y + 54), 1)
    stats = [
        ("GOLD", str(house_data.get("gold", "0")), GOLD),
        ("ARMIES", str(house_data.get("armies", "0")), IVORY),
        ("HOLDS", str(house_data.get("lands", "0")), IVORY),
        ("MINIMAX", str(house_data.get("mode", "AI")), (168, 206, 226)),
    ]
    for idx, (lbl, val, col) in enumerate(stats):
        col_x = rect.x + 14 + idx * 95
        write(surface, lbl, (col_x, rect.y + 60), fonts["tiny"], MUTED)
        write(surface, val, (col_x, rect.y + 77), fonts["small"], col)

    # Live Telemetry Row: Income/turn + Realm Power Share Bar + Pending Proposal Alert
    pygame.draw.line(surface, (50, 68, 66), (rect.x + 14, rect.y + 104), (rect.right - 14, rect.y + 104), 1)
    income = int(house_data.get("income", 10))  # type: ignore[arg-type]
    share = float(house_data.get("power_share", 0.33))  # type: ignore[arg-type]
    pending = bool(house_data.get("pending", False))

    if pending:
        write(surface, "PROPOSAL PENDING IN INBOX", (rect.x + 14, rect.y + 114), fonts["tiny"], GOLD)
    else:
        write(surface, f"INCOME +{income}G", (rect.x + 14, rect.y + 114), fonts["tiny"], GOLD)

    # Military Power Share Progress Bar
    bar_x = rect.x + 132 if not pending else rect.x + 216
    bar_w = rect.right - 14 - bar_x - 38
    if bar_w > 30:
        track = pygame.Rect(bar_x, rect.y + 118, bar_w, 8)
        pygame.draw.rect(surface, (32, 44, 48), track, border_radius=4)
        fill_w = int(track.width * max(0.0, min(1.0, share)))
        if fill_w > 0:
            pygame.draw.rect(surface, color, (track.x, track.y, max(4, fill_w), track.height), border_radius=4)
            pygame.draw.line(surface, mix(color, (255, 255, 255), 0.35), (track.x + 2, track.y + 1), (track.x + max(4, fill_w) - 2, track.y + 1), 1)
        write_right(surface, f"{int(round(share * 100))}%", rect.right - 14, rect.y + 113, fonts["tiny"], IVORY)


def draw_diplomacy_panel(
    surface: pygame.Surface,
    rect: pygame.Rect,
    fonts: dict[str, pygame.font.Font],
    fuzzy_scores: dict[str, float] | None = None,
    perspective_house: str = "STARK",
) -> None:
    """Render the Fuzzy Logic Diplomacy Forecast bars for the active house."""
    draw_glass_panel(surface, rect, (20, 30, 34), GOLD, 8)
    scores = fuzzy_scores or {"alliance": 0.5, "betrayal": 0.1, "solo": 0.4}

    raven_icon = get_sprite("assets/ui/raven.png", (28, 28))
    if raven_icon:
        surface.blit(raven_icon, (rect.x + 14, rect.y + 10))
    write(surface, "DIPLOMACY FORECAST", (rect.x + 48, rect.y + 8), fonts["cardtitle"], IVORY)
    write(surface, f"{perspective_house} PERSPECTIVE · FUZZY LOGIC", (rect.x + 48, rect.y + 28), fonts["tiny"], MUTED)
    pygame.draw.line(surface, (70, 88, 85), (rect.x + 14, rect.y + 50), (rect.right - 14, rect.y + 50), 1)

    for index, (label, value, color) in enumerate(
        (
            ("ALLIANCE", float(scores.get("alliance", 0.0)), STARK),
            ("BETRAYAL", float(scores.get("betrayal", 0.0)), TARGARYEN),
            ("SOLO WAR", float(scores.get("solo", 0.0)), GOLD),
        )
    ):
        y = rect.y + 62 + index * 32
        write(surface, label, (rect.x + 14, y), fonts["micro"], MUTED)
        track = pygame.Rect(rect.x + 96, y + 4, rect.width - 156, 10)
        pygame.draw.rect(surface, (32, 44, 48), track, border_radius=5)
        pygame.draw.rect(surface, (55, 72, 74), track, 1, border_radius=5)
        fill_w = int(track.width * max(0.0, min(1.0, value)))
        if fill_w > 0:
            pygame.draw.rect(surface, color, (track.x, track.y, max(4, fill_w), track.height), border_radius=5)
            pygame.draw.line(surface, mix(color, (255, 255, 255), 0.35), (track.x + 2, track.y + 1), (track.x + max(4, fill_w) - 2, track.y + 1), 1)
        write_right(surface, f"{value:.2f}", rect.right - 14, y, fonts["micro"], IVORY)


def draw_raven_panel(
    surface: pygame.Surface,
    rect: pygame.Rect,
    fonts: dict[str, pygame.font.Font],
    turn_log: list[dict[str, str | int]] | None = None,
) -> None:
    """Render the chronological Raven's Log with distinct house badges and clipped lines."""
    draw_glass_panel(surface, rect, (20, 30, 34), (117, 137, 128), 10)
    raven_icon = get_sprite("assets/ui/raven.png", (30, 30))
    if raven_icon:
        surface.blit(raven_icon, (rect.x + 16, rect.y + 12))
    write(surface, "THE RAVEN'S LOG", (rect.x + 52, rect.y + 12), fonts["subhead"], IVORY)
    write_right(surface, "CHRONOLOGICAL LOG", rect.right - 16, rect.y + 15, fonts["micro"], GOLD)
    pygame.draw.line(surface, GOLD, (rect.x + 16, rect.y + 44), (rect.x + 90, rect.y + 44), 2)
    write(surface, "Every house's moves listed chronologically in turn order.", (rect.x + 16, rect.y + 50), fonts["tiny"], MUTED)
    pygame.draw.line(surface, (70, 88, 85), (rect.x + 14, rect.y + 72), (rect.right - 14, rect.y + 72), 1)

    row_step = 32
    max_rows = max(5, (rect.height - 86) // row_step)
    if turn_log:
        recent = turn_log[-max_rows:]
        events: list[tuple[int, str, str, tuple[int, int, int]]] = []
        for entry in recent:
            t_num = int(entry.get("turn", 1))
            h_name = str(entry.get("house", "STARK")).upper()
            text = str(entry.get("text") or f"used {entry.get('algo', 'AI')}: {entry.get('decision', '')}")
            events.append((t_num, h_name, text, HOUSE_COLORS.get(h_name, IVORY)))
    else:
        events = [
            (1, "STARK", "mobilized northern army at Winterfell", STARK),
            (1, "LANNISTER", "marshaled gold and troops at Casterly Rock", LANNISTER),
            (1, "TARGARYEN", "raised dragon banners at Dragonstone", TARGARYEN),
        ]

    for index, (turn, house, message, color) in enumerate(events):
        y = rect.y + 80 + index * row_step
        row = pygame.Rect(rect.x + 10, y, rect.width - 20, 28)
        if index % 2 == 0:
            pygame.draw.rect(surface, (24, 35, 41), row, border_radius=6)
        pygame.draw.circle(surface, color, (row.x + 12, row.centery), 5)
        turn_badge = f"[T{turn:02d}]"
        write(surface, turn_badge, (row.x + 24, row.y + 5), fonts["log"], GOLD)
        badge_w = fonts["log"].size(turn_badge)[0]
        house_lbl = f" {house.title()} "
        write(surface, house_lbl, (row.x + 24 + badge_w, row.y + 5), fonts["log"], color)
        house_w = fonts["log"].size(house_lbl)[0]

        msg_x = row.x + 24 + badge_w + house_w
        max_msg_w = row.right - 8 - msg_x
        trimmed = message
        if fonts["log"].size(trimmed)[0] > max_msg_w:
            while len(trimmed) > 3 and fonts["log"].size(trimmed + "...")[0] > max_msg_w:
                trimmed = trimmed[:-1]
            trimmed += "..."
        write(surface, trimmed, (msg_x, row.y + 5), fonts["log"], IVORY)


def draw_hud_toggles(
    surface: pygame.Surface,
    fonts: dict[str, pygame.font.Font],
    show_houses: bool = False,
    show_log: bool = False,
    music_enabled: bool = False,
    is_paused: bool = False,
    mouse: tuple[float, float] | None = None,
) -> dict[str, pygame.Rect]:
    """Render top-left Pause/Restart and top-right Music/AI Brain/Raven Log pills."""
    buttons: dict[str, pygame.Rect] = {}
    pause_btn = pygame.Rect(MAP_RECT.x + 256, MAP_RECT.y + 14, 118, 40)
    restart_btn = pygame.Rect(MAP_RECT.x + 382, MAP_RECT.y + 14, 118, 40)
    music_btn = pygame.Rect(MAP_RECT.right - 378, MAP_RECT.y + 14, 112, 40)
    houses_btn = pygame.Rect(MAP_RECT.right - 258, MAP_RECT.y + 14, 116, 40)
    log_btn = pygame.Rect(MAP_RECT.right - 134, MAP_RECT.y + 14, 122, 40)
    buttons["toggle_pause"] = pause_btn
    buttons["restart_game"] = restart_btn
    buttons["toggle_music"] = music_btn
    buttons["toggle_houses"] = houses_btn
    buttons["toggle_log"] = log_btn
    _draw_button(
        surface,
        pause_btn,
        "RESUME [P]" if is_paused else "PAUSE [P]",
        fonts["micro"],
        active=is_paused,
        hovered=bool(mouse and pause_btn.collidepoint(mouse)),
        accent=GOLD if is_paused else STARK,
    )
    _draw_button(
        surface,
        restart_btn,
        "RESTART [R]",
        fonts["micro"],
        active=False,
        hovered=bool(mouse and restart_btn.collidepoint(mouse)),
        accent=LANNISTER,
    )
    _draw_button(
        surface,
        music_btn,
        "MUSIC: ON" if music_enabled else "MUSIC: OFF",
        fonts["micro"],
        active=music_enabled,
        hovered=bool(mouse and music_btn.collidepoint(mouse)),
        accent=GOLD if music_enabled else (112, 128, 126),
    )
    _draw_button(
        surface,
        houses_btn,
        "AI BRAIN [H]",
        fonts["micro"],
        active=show_houses,
        hovered=bool(mouse and houses_btn.collidepoint(mouse)),
        accent=GOLD if show_houses else STARK,
    )
    _draw_button(
        surface,
        log_btn,
        "RAVEN LOG [L]",
        fonts["micro"],
        active=show_log,
        hovered=bool(mouse and log_btn.collidepoint(mouse)),
        accent=GOLD if show_log else TARGARYEN,
    )
    return buttons


def _scale_strength_100(raw_strength: float) -> float:
    return max(0.0, min(100.0, (raw_strength / 30.0) * 100.0))


def _draw_fuzzy_bar(
    surface: pygame.Surface,
    rect_x: int,
    rect_right: int,
    y: int,
    label: str,
    value: float,
    color: tuple[int, int, int],
    fonts: dict[str, pygame.font.Font],
) -> None:
    write(surface, label, (rect_x + 14, y), fonts["micro"], MUTED)
    track = pygame.Rect(rect_x + 96, y + 4, (rect_right - rect_x) - 156, 10)
    pygame.draw.rect(surface, (32, 44, 48), track, border_radius=5)
    pygame.draw.rect(surface, (55, 72, 74), track, 1, border_radius=5)
    fill_w = int(track.width * max(0.0, min(1.0, value)))
    if fill_w > 0:
        pygame.draw.rect(surface, color, (track.x, track.y, max(4, fill_w), track.height), border_radius=5)
        pygame.draw.line(
            surface,
            mix(color, (255, 255, 255), 0.35),
            (track.x + 2, track.y + 1),
            (track.x + max(4, fill_w) - 2, track.y + 1),
            1,
        )
    write_right(surface, f"{value:.2f}", rect_right - 14, y, fonts["micro"], IVORY)


def _trim_text(text: str, font: pygame.font.Font, max_w: int) -> str:
    if font.size(text)[0] <= max_w:
        return text
    trimmed = text
    while len(trimmed) > 3 and font.size(trimmed + "...")[0] > max_w:
        trimmed = trimmed[:-1]
    return trimmed + "..."


def draw_sidebar(
    surface: pygame.Surface,
    fonts: dict[str, pygame.font.Font],
    houses: list[House] | None = None,
    diplomacy: Diplomacy | None = None,
    turn_log: list[dict[str, str | int]] | None = None,
    show_houses: bool = False,
    show_log: bool = False,
    selected_fuzzy_house: str | None = None,
    mouse: tuple[float, float] | None = None,
    brain_tab: str = "trace",
    acting_house: str | None = None,
) -> dict[str, pygame.Rect]:
    """Render collapsible AI Brain (Live Trace / Fuzzy Pairs) & Raven's Log drawers."""
    sidebar_buttons: dict[str, pygame.Rect] = {}
    if not show_houses and not show_log:
        return sidebar_buttons

    drawer_y = MAP_RECT.y + 66
    drawer_h = MAP_RECT.height - 114
    log_w = 436
    house_w = 418

    if show_houses:
        hx = MAP_RECT.right - house_w - (log_w + 26 if show_log else 14)
        rect = pygame.Rect(hx, drawer_y, house_w, drawer_h)
        sidebar_buttons["drawer_fuzzy"] = rect
        draw_glass_panel(surface, rect, (16, 25, 30), GOLD, 10)
        header_title = "AI DECISION BRAIN" if brain_tab == "trace" else "FUZZY DIPLOMACY"
        header_sub = "LIVE ALGORITHMS" if brain_tab == "trace" else "PAIRWISE SCORES"
        write(surface, header_title, (rect.x + 16, rect.y + 12), fonts["subhead"], IVORY)
        write_right(surface, header_sub, rect.right - 16, rect.y + 14, fonts["micro"], MUTED)
        pygame.draw.line(surface, GOLD, (rect.x + 16, rect.y + 36), (rect.x + 88, rect.y + 36), 2)

        active_pacts = []
        if diplomacy is not None:
            seen_pairs: set[tuple[str, str]] = set()
            for h1, h2 in diplomacy.alliances.items():
                if h2 and tuple(sorted((h1, h2))) not in seen_pairs:
                    seen_pairs.add(tuple(sorted((h1, h2))))
                    active_pacts.append(f"{h1.title()} & {h2.title()}")
        pact_line = f"Active alliance: {', '.join(active_pacts)}" if active_pacts else "No active alliances across the realm."
        write(surface, pact_line, (rect.x + 16, rect.y + 42), fonts["tiny"], GOLD if active_pacts else MUTED)

        by_name = {h.name: h for h in houses} if houses else {}
        default_name = next((h.name for h in (houses or []) if h.is_human), "STARK")
        pov_name = (selected_fuzzy_house or default_name).upper()
        if pov_name not in ("STARK", "LANNISTER", "TARGARYEN"):
            pov_name = default_name

        # House perspective selector tabs
        tab_y = rect.y + 64
        tab_w = (rect.width - 36) // 3
        for idx, h_name in enumerate(("STARK", "LANNISTER", "TARGARYEN")):
            tab = pygame.Rect(rect.x + 12 + idx * (tab_w + 6), tab_y, tab_w, 30)
            sidebar_buttons[f"fuzzy_tab_{h_name}"] = tab
            is_sel = h_name == pov_name
            _draw_button(
                surface,
                tab,
                h_name,
                fonts["tiny"],
                active=is_sel,
                hovered=bool(mouse and tab.collidepoint(mouse)),
                accent=HOUSE_COLORS[h_name] if is_sel else (90, 108, 106),
            )

        # Sub-mode switcher: LIVE TRACE (All Algorithms) vs FUZZY PAIRS
        sub_y = tab_y + 36
        sub_w = (rect.width - 30) // 2
        for idx, (b_key, b_val, b_lbl) in enumerate(
            (("brain_tab_trace", "trace", "LIVE TRACE"), ("brain_tab_fuzzy", "fuzzy", "FUZZY PAIRS"))
        ):
            sbt = pygame.Rect(rect.x + 12 + idx * (sub_w + 6), sub_y, sub_w, 26)
            sidebar_buttons[b_key] = sbt
            is_active = brain_tab == b_val
            _draw_button(
                surface,
                sbt,
                b_lbl,
                fonts["tiny"],
                active=is_active,
                hovered=bool(mouse and sbt.collidepoint(mouse)),
                accent=GOLD if is_active else (84, 102, 100),
            )

        pov = by_name.get(pov_name)
        pov_color = HOUSE_COLORS.get(pov_name, GOLD)
        is_acting_now = acting_house is not None and acting_house.upper() == pov_name

        # Selected house status banner
        status_rect = pygame.Rect(rect.x + 12, sub_y + 34, rect.width - 24, 48)
        draw_glass_panel(surface, status_rect, (22, 32, 36), pov_color, 8)
        draw_crest(surface, (status_rect.x + 24, status_rect.centery), pov_name, 13)
        write(surface, f"HOUSE {pov_name}", (status_rect.x + 44, status_rect.y + 7), fonts["cardtitle"], pov_color)
        if is_acting_now:
            write_right(surface, "ACTING NOW", status_rect.right - 12, status_rect.y + 9, fonts["tiny"], (130, 228, 165))
        elif pov is not None and isinstance(pov.last_trace, dict) and pov.last_trace.get("turn"):
            write_right(surface, f"TURN {pov.last_trace['turn']}", status_rect.right - 12, status_rect.y + 9, fonts["tiny"], GOLD)
        if pov is not None:
            status_lbl = (
                "ELIMINATED"
                if pov.is_eliminated()
                else (f"ALLY: {pov.allied_with}" if pov.allied_with else "SOLO")
            )
            mode_lbl = f"MINIMAX: {pov.mode}"
        else:
            status_lbl, mode_lbl = "SOLO", "MINIMAX: DECOMPOSED"
        write(surface, f"{status_lbl} · {mode_lbl}", (status_rect.x + 44, status_rect.y + 27), fonts["tiny"], MUTED)

        if brain_tab == "trace":
            trace = pov.last_trace if (pov is not None and isinstance(pov.last_trace, dict)) else {}
            pov_dead = pov is not None and pov.is_eliminated()

            # ── Card 1: Diplomacy (Fuzzy -> MCTS 500 Rollouts) ─────────
            c1 = pygame.Rect(rect.x + 12, status_rect.bottom + 10, rect.width - 24, 154)
            draw_glass_panel(surface, c1, (20, 30, 34), TARGARYEN, 8)
            write(surface, "DIPLOMACY · FUZZY -> MCTS", (c1.x + 12, c1.y + 9), fonts["micro"], IVORY)
            mcts = trace.get("mcts") if isinstance(trace.get("mcts"), dict) else {}
            f_ctx = str(trace.get("fuzzy_context", "A"))
            ctx_lbl = f"CTX {f_ctx} · {mcts.get('iterations', 500)} ROLLOUTS" if mcts else f"CTX {f_ctx}"
            write_right(surface, ctx_lbl, c1.right - 12, c1.y + 10, fonts["tiny"], GOLD)

            f_scores = trace.get("fuzzy_scores") if isinstance(trace.get("fuzzy_scores"), dict) else (pov.fuzzy_scores if pov else {})
            f_line = (
                f"Fuzzy Bias -> Ally {float(f_scores.get('alliance', 0.0)):.2f} · "
                f"Betray {float(f_scores.get('betrayal', 0.0)):.2f} · "
                f"Solo {float(f_scores.get('solo', 0.0)):.2f}"
            )
            write(surface, f_line, (c1.x + 12, c1.y + 28), fonts["tiny"], MUTED)
            pygame.draw.line(surface, (60, 78, 76), (c1.x + 12, c1.y + 46), (c1.right - 12, c1.y + 46), 1)

            options = mcts.get("options") if isinstance(mcts.get("options"), list) else []
            chosen_dip = str(mcts.get("chosen", ""))
            partner_name = str(mcts.get("partner", "") or "")
            if pov_dead:
                write(surface, "House eliminated — no diplomacy decisions.", (c1.x + 12, c1.y + 64), fonts["tiny"], MUTED)
            elif not options:
                write(surface, "Waiting for next AI turn to run 500 MCTS rollouts...", (c1.x + 12, c1.y + 64), fonts["tiny"], MUTED)
            else:
                total_v = max(1, sum(int(o.get("visits", 0)) for o in options))
                for idx, opt in enumerate(options[:3]):
                    ry = c1.y + 54 + idx * 31
                    act = str(opt.get("action", ""))
                    vis = int(opt.get("visits", 0))
                    avg_q = float(opt.get("avg_q", 0.0))
                    is_pick = act == chosen_dip
                    if act == "propose_alliance":
                        lbl = f"PROPOSE {partner_name[:4]}" if partner_name else "PROPOSE"
                    elif act == "betray":
                        lbl = f"BETRAY {partner_name[:4]}" if partner_name else "BETRAY"
                    else:
                        lbl = act.upper()
                    write(surface, lbl, (c1.x + 12, ry + 3), fonts["tiny"], (130, 228, 165) if is_pick else IVORY)
                    bar = pygame.Rect(c1.x + 114, ry + 6, 122, 9)
                    pygame.draw.rect(surface, (32, 44, 48), bar, border_radius=4)
                    fw = int(bar.width * max(0.0, min(1.0, vis / total_v)))
                    bar_col = (110, 215, 155) if is_pick else STARK
                    if fw > 0:
                        pygame.draw.rect(surface, bar_col, (bar.x, bar.y, max(4, fw), bar.height), border_radius=4)
                    stat_txt = f"Q={avg_q:.2f} ({vis}v)" + (" [PICK]" if is_pick else "")
                    write_right(surface, stat_txt, c1.right - 12, ry + 3, fonts["tiny"], (130, 228, 165) if is_pick else MUTED)

            # ── Card 2: Combat (Minimax Alpha-Beta Ranked Scores) ──────
            c2 = pygame.Rect(rect.x + 12, c1.bottom + 10, rect.width - 24, 198)
            draw_glass_panel(surface, c2, (20, 30, 34), STARK, 8)
            mm_mode = str(trace.get("minimax_mode", pov.mode if pov else "DECOMPOSED"))
            write(surface, "COMBAT · MINIMAX (ALPHA-BETA)", (c2.x + 12, c2.y + 9), fonts["micro"], IVORY)
            write_right(surface, f"{mm_mode} · D3", c2.right - 12, c2.y + 10, fonts["tiny"], GOLD)
            pygame.draw.line(surface, (60, 78, 76), (c2.x + 12, c2.y + 32), (c2.right - 12, c2.y + 32), 1)

            mm_scores = trace.get("minimax_scores") if isinstance(trace.get("minimax_scores"), dict) else {}
            chosen_mv = trace.get("chosen_move")
            if pov_dead:
                write(surface, "House eliminated — no combat moves.", (c2.x + 12, c2.y + 46), fonts["tiny"], MUTED)
            elif not mm_scores:
                write(surface, "No valid attack moves evaluated.", (c2.x + 12, c2.y + 46), fonts["tiny"], MUTED)
            else:
                ranked_mm = sorted(
                    [(("HOLD" if k is None else str(k)), float(v)) for k, v in mm_scores.items()],
                    key=lambda kv: kv[1],
                    reverse=True,
                )
                top_rows = ranked_mm[:5]
                # Ensure HOLD and chosen move are always visible in the top 5 rows
                row_names = {r[0] for r in top_rows}
                for must_name in (chosen_mv, "HOLD"):
                    if must_name and must_name not in row_names:
                        match = next((r for r in ranked_mm if r[0] == must_name), None)
                        if match is not None:
                            top_rows = top_rows[:4] + [match]
                            row_names = {r[0] for r in top_rows}

                vals = [v for _, v in top_rows]
                v_min, v_max = min(vals), max(vals)
                span = max(1.0, v_max - v_min)
                for idx, (m_name, m_val) in enumerate(top_rows):
                    ry = c2.y + 42 + idx * 29
                    is_chosen = chosen_mv == m_name
                    is_hold = m_name == "HOLD"
                    name_col = (130, 228, 165) if is_chosen else (GOLD if is_hold else IVORY)
                    disp_name = _trim_text(m_name, fonts["tiny"], 124)
                    write(surface, disp_name, (c2.x + 12, ry + 3), fonts["tiny"], name_col)
                    bar = pygame.Rect(c2.x + 142, ry + 6, 126, 9)
                    pygame.draw.rect(surface, (32, 44, 48), bar, border_radius=4)
                    frac = 1.0 if v_max == v_min else (m_val - v_min) / span
                    fw = int(bar.width * max(0.08, min(1.0, frac)))
                    b_col = (110, 215, 155) if is_chosen else (GOLD if is_hold else STARK)
                    pygame.draw.rect(surface, b_col, (bar.x, bar.y, max(4, fw), bar.height), border_radius=4)
                    val_str = f"{m_val:+.1f}" + (" [PICK]" if is_chosen else "")
                    write_right(surface, val_str, c2.right - 12, ry + 3, fonts["tiny"], (130, 228, 165) if is_chosen else IVORY)

            # ── Card 3: A* Throne Corridor & Greedy Rollout Model ──────
            c3 = pygame.Rect(rect.x + 12, c2.bottom + 10, rect.width - 24, max(108, rect.bottom - c2.bottom - 20))
            draw_glass_panel(surface, c3, (22, 30, 34), GOLD, 8)
            write(surface, "A* CORRIDOR & GREEDY ROLLOUT", (c3.x + 12, c3.y + 9), fonts["micro"], IVORY)
            pygame.draw.line(surface, (70, 88, 85), (c3.x + 12, c3.y + 30), (c3.right - 12, c3.y + 30), 1)

            a_path = trace.get("astar_path") if isinstance(trace.get("astar_path"), list) else []
            a_cost = float(trace.get("astar_cost", 0.0))
            a_bonus = float(trace.get("astar_bonus", 0.0))
            if a_path and not pov_dead:
                route_str = " -> ".join(str(n) for n in a_path)
                write(surface, _trim_text(f"A*: {route_str}", fonts["tiny"], c3.width - 24), (c3.x + 12, c3.y + 38), fonts["tiny"], GOLD)
                write(
                    surface,
                    f"Defense Cost: {a_cost:.0f}  ·  Minimax Corridor Bonus: +{a_bonus:.1f}",
                    (c3.x + 12, c3.y + 56),
                    fonts["tiny"],
                    MUTED,
                )
            else:
                write(surface, "A*: No active route to King's Landing", (c3.x + 12, c3.y + 38), fonts["tiny"], MUTED)

            greedy = trace.get("greedy") if isinstance(trace.get("greedy"), dict) else None
            if greedy and not pov_dead:
                g_line = f"Greedy (MCTS Rollout): {greedy['name']} (res {greedy['res']} - def {greedy['def']} = {int(greedy['score']):+d})"
                write(surface, _trim_text(g_line, fonts["tiny"], c3.width - 24), (c3.x + 12, c3.y + 82), fonts["tiny"], (170, 224, 240))
            else:
                write(surface, "Greedy (MCTS Rollout): No immediate target", (c3.x + 12, c3.y + 82), fonts["tiny"], MUTED)
        else:
            # ── FUZZY PAIRS sub-tab (Pairwise Fuzzy Cards + General Solo) ──
            others = [n for n in ("STARK", "LANNISTER", "TARGARYEN") if n != pov_name]
            card_top = status_rect.bottom + 10
            card_h = 142

            own_weakness = (
                max(0.0, min(100.0, 100.0 - _scale_strength_100(pov.get_military_strength())))
                if pov is not None and not pov.is_eliminated()
                else 100.0
            )

            for idx, other_name in enumerate(others):
                card = pygame.Rect(rect.x + 12, card_top + idx * (card_h + 10), rect.width - 24, card_h)
                other_h = by_name.get(other_name)
                other_col = HOUSE_COLORS.get(other_name, GOLD)
                draw_glass_panel(surface, card, (20, 30, 34), other_col, 8)
                draw_crest(surface, (card.x + 26, card.y + 24), other_name, 12)
                write(surface, f"WITH HOUSE {other_name}", (card.x + 46, card.y + 9), fonts["cardtitle"], other_col)

                pov_dead = pov is not None and pov.is_eliminated()
                other_dead = other_h is not None and other_h.is_eliminated()
                if pov_dead or other_dead:
                    rel_tag = "ELIMINATED"
                elif pov is not None and pov.allied_with == other_name:
                    rel_tag = "ACTIVE ALLY"
                else:
                    rel_tag = "RIVAL"
                write_right(surface, rel_tag, card.right - 14, card.y + 11, fonts["tiny"], GOLD if rel_tag == "ACTIVE ALLY" else MUTED)

                if pov is not None and other_h is not None and not pov_dead and not other_dead:
                    trust = diplomacy.get_trust(pov, other_h) if diplomacy is not None else 50.0
                    third_name = next((n for n in ("STARK", "LANNISTER", "TARGARYEN") if n not in (pov_name, other_name)), None)
                    third_h = by_name.get(third_name) if third_name else None
                    if third_h is not None and not third_h.is_eliminated():
                        threat_val = _scale_strength_100(third_h.get_military_strength())
                        threat_lbl = f"{third_name[:4]} Threat {int(round(threat_val))}"
                    else:
                        threat_val = _scale_strength_100(other_h.get_military_strength())
                        threat_lbl = f"Enemy {int(round(threat_val))}"
                    pair_scores = evaluate_diplomacy(threat_val, own_weakness, trust)
                    write(
                        surface,
                        f"Trust {int(round(trust))}/100 · {threat_lbl} · Weak {int(round(own_weakness))}",
                        (card.x + 46, card.y + 29),
                        fonts["tiny"],
                        MUTED,
                    )
                    pygame.draw.line(surface, (60, 78, 76), (card.x + 14, card.y + 49), (card.right - 14, card.y + 49), 1)
                    _draw_fuzzy_bar(surface, card.x, card.right, card.y + 64, "ALLIANCE", pair_scores["alliance"], STARK, fonts)
                    _draw_fuzzy_bar(surface, card.x, card.right, card.y + 98, "BETRAYAL", pair_scores["betrayal"], TARGARYEN, fonts)
                else:
                    write(surface, "Diplomacy inactive (house eliminated)", (card.x + 46, card.y + 29), fonts["tiny"], MUTED)
                    pygame.draw.line(surface, (60, 78, 76), (card.x + 14, card.y + 49), (card.right - 14, card.y + 49), 1)
                    _draw_fuzzy_bar(surface, card.x, card.right, card.y + 64, "ALLIANCE", 0.0, (90, 100, 104), fonts)
                    _draw_fuzzy_bar(surface, card.x, card.right, card.y + 98, "BETRAYAL", 0.0, (90, 100, 104), fonts)

            # General SOLO WAR card (overall posture across all rivals)
            solo_rect = pygame.Rect(rect.x + 12, rect.bottom - 114, rect.width - 24, 104)
            draw_glass_panel(surface, solo_rect, (22, 30, 34), GOLD, 8)
            raven_icon = get_sprite("assets/ui/raven.png", (22, 22))
            if raven_icon:
                surface.blit(raven_icon, (solo_rect.x + 14, solo_rect.y + 10))
            write(surface, "GENERAL SOLO POSTURE", (solo_rect.x + 42, solo_rect.y + 10), fonts["cardtitle"], IVORY)
            write(surface, f"{pov_name} overall independence vs. all rivals", (solo_rect.x + 42, solo_rect.y + 29), fonts["tiny"], MUTED)
            pygame.draw.line(surface, (70, 88, 85), (solo_rect.x + 14, solo_rect.y + 48), (solo_rect.right - 14, solo_rect.y + 48), 1)
            solo_val = (
                float(pov.fuzzy_scores.get("solo", 0.0))
                if pov is not None and not pov.is_eliminated()
                else 0.0
            )
            _draw_fuzzy_bar(surface, solo_rect.x, solo_rect.right, solo_rect.y + 64, "SOLO WAR", solo_val, GOLD, fonts)

    if show_log:
        log_entries = turn_log if turn_log is not None else (diplomacy.event_log if diplomacy is not None else None)
        raven_rect = pygame.Rect(MAP_RECT.right - log_w - 14, drawer_y, log_w, drawer_h)
        sidebar_buttons["drawer_log"] = raven_rect
        draw_raven_panel(surface, raven_rect, fonts, log_entries)

    return sidebar_buttons


def hex_at(pos: tuple[float, float]) -> tuple[int, int] | None:
    best, best_dist = None, HEX_R * 0.95
    for col in range(GRID_COLS):
        for row in range(GRID_ROWS):
            if not on_land(col, row) and (col, row) != DRAGONSTONE_COORD:
                continue
            center = center_of(col, row)
            dist = math.hypot(pos[0] - center[0], pos[1] - center[1])
            if dist < best_dist:
                best, best_dist = (col, row), dist
    return best


def handle_click(
    pos: tuple[float, float],
    game_map: Map,
    active_house: House | str | None = None,
) -> Territory | None:
    """Translate screen mouse click into a target Territory."""
    if not MAP_RECT.collidepoint(pos):
        return None
    cell = hex_at(pos)
    if cell is None:
        return None
    territory = game_map.by_coord.get(cell) or game_map.region_of(*cell)
    if territory is None:
        return None
    if active_house is not None:
        house_name = active_house if isinstance(active_house, str) else active_house.name
        if territory.owner == house_name.upper():
            return None
    return territory


def draw_hover(
    surface: pygame.Surface,
    fonts: dict[str, pygame.font.Font],
    pos: tuple[float, float] | None,
    game_map: Map | None = None,
    houses: list[House] | None = None,
    minimax_scores: dict[str | None, float] | None = None,
) -> None:
    """Render illuminated golden isometric boundary and medieval parchment tooltip on hover."""
    if pos is None or not MAP_RECT.collidepoint(pos):
        return
    cell = hex_at(pos)
    if cell is None:
        return
    col, row = cell
    center = center_of(col, row)
    cx, cy = round(center[0]), round(center[1])

    # Illuminated golden isometric highlight
    top_poly = hex_points(center)
    glow = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
    pygame.draw.polygon(glow, (*GOLD, 80), top_poly)
    surface.blit(glow, (0, 0))
    pygame.draw.polygon(surface, GOLD, top_poly, 2)

    # Tooltip Data
    house_by_name = {h.name: h for h in houses} if houses else {}
    territory = (game_map.by_coord.get(cell) or game_map.region_of(*cell)) if game_map is not None else None
    if territory is not None:
        owner_house = house_by_name.get(territory.owner) if territory.owner else None
        garrison_val = owner_house.armies if owner_house is not None else territory.armies
        title = territory.name
        res_val = territory.resource_value
        def_bonus = territory.defense_bonus
        owner = territory.owner
    else:
        landmark = LANDMARKS.get(cell)
        title = landmark[0] if landmark else "Open Plains"
        garrison_val = landmark[2] if landmark else 3
        res_val = 3
        def_bonus = 2
        owner = landmark[3] if landmark else None

    # Check whether Minimax has evaluated this territory as a candidate attack move
    mm_score = minimax_scores.get(title) if (minimax_scores and title in minimax_scores) else None
    mm_hold = minimax_scores.get(None) if minimax_scores else None
    mm_best_key = (
        max(minimax_scores, key=lambda k: (minimax_scores[k], k is not None))
        if minimax_scores
        else None
    )

    # Medieval Tooltip Card
    is_throne = title == "KING'S LANDING"
    extra_h = 44 if mm_score is not None else 0
    card_h = (132 if is_throne else 110) + extra_h
    card_w = max(240 if is_throne else 218, 250 if mm_score is not None else 210)
    tip = pygame.Rect(int(pos[0]) + 16, int(pos[1]) - 30, card_w, card_h)
    if tip.right > MAP_RECT.right - 10:
        tip.x = int(pos[0]) - tip.width - 16
    if tip.bottom > MAP_RECT.bottom - 10:
        tip.y = int(pos[1]) - tip.height - 10

    accent = GOLD if is_throne else (HOUSE_COLORS.get(owner, GOLD) if owner else GOLD)
    draw_glass_panel(surface, tip, (24, 22, 16) if is_throne else (18, 28, 32), accent, 8)

    if is_throne:
        crown_spr = get_sprite("assets/ui/crown.png", (18, 18))
        if crown_spr:
            surface.blit(crown_spr, (tip.x + 10, tip.y + 8))
        write(surface, "KING'S LANDING", (tip.x + 32, tip.y + 8), fonts["cardtitle"], GOLD)
        owner_str = f"Ruler: House {owner.title()}" if owner else "Neutral Capital (Royal Garrison)"
        write(surface, owner_str, (tip.x + 12, tip.y + 28), fonts["tiny"], (255, 235, 170))
        write(surface, "OBJECTIVE: Capture to Win the Game!", (tip.x + 12, tip.y + 46), fonts["micro"], GOLD)
        pygame.draw.line(surface, (110, 95, 60), (tip.x + 12, tip.y + 64), (tip.right - 12, tip.y + 64), 1)
        write(surface, f"Royal Garrison: {garrison_val} Armies", (tip.x + 12, tip.y + 70), fonts["micro"], IVORY)
        write(surface, f"Imperial Tribute: +{res_val} Gold / turn", (tip.x + 12, tip.y + 88), fonts["micro"], GOLD)
        write(surface, f"Fortifications: +{def_bonus} Defense", (tip.x + 12, tip.y + 106), fonts["tiny"], MUTED)
        mm_y = tip.y + 126
    else:
        write(surface, title, (tip.x + 12, tip.y + 8), fonts["cardtitle"], IVORY)
        owner_str = f"Ruler: House {owner.title()}" if owner else "Neutral Seat"
        write(surface, owner_str, (tip.x + 12, tip.y + 28), fonts["tiny"], accent)

        pygame.draw.line(surface, (60, 78, 75), (tip.x + 12, tip.y + 46), (tip.right - 12, tip.y + 46), 1)
        write(surface, f"Garrison Armies: {garrison_val}", (tip.x + 12, tip.y + 52), fonts["micro"], IVORY)
        write(surface, f"Tribute / Income: +{res_val} Gold", (tip.x + 12, tip.y + 70), fonts["micro"], GOLD)
        write(surface, f"Defense Fortification: +{def_bonus}", (tip.x + 12, tip.y + 88), fonts["tiny"], MUTED)
        mm_y = tip.y + 106

    if mm_score is not None:
        pygame.draw.line(surface, (70, 88, 85), (tip.x + 12, mm_y), (tip.right - 12, mm_y), 1)
        is_best = mm_best_key == title
        mm_label = f"Minimax: {mm_score:+.1f}" + (" · BEST" if is_best else "")
        mm_col = (130, 228, 165) if is_best else GOLD
        write(surface, mm_label, (tip.x + 12, mm_y + 6), fonts["micro"], mm_col)
        if mm_hold is not None:
            delta = mm_score - mm_hold
            delta_col = (130, 228, 165) if delta > 0 else ((238, 140, 120) if delta < 0 else MUTED)
            write(surface, f"vs Hold: {mm_hold:+.1f} ({delta:+.1f})", (tip.x + 12, mm_y + 23), fonts["tiny"], delta_col)


def _draw_button(
    surface: pygame.Surface,
    rect: pygame.Rect,
    label: str,
    font: pygame.font.Font,
    active: bool = True,
    hovered: bool = False,
    accent: tuple[int, int, int] = GOLD,
) -> None:
    """Render a beveled medieval button with subtle top highlight and shadowed text."""
    fill = mix(accent, (18, 28, 33), 0.72 if not hovered else 0.48)
    border = accent if (hovered or active) else mix(accent, (100, 120, 115), 0.45)
    pygame.draw.rect(surface, (6, 10, 14), rect.move(0, 2), border_radius=7)
    pygame.draw.rect(surface, fill, rect, border_radius=7)
    pygame.draw.line(
        surface,
        mix(fill, (255, 250, 220), 0.25 if hovered else 0.14),
        (rect.x + 5, rect.y + 2),
        (rect.right - 5, rect.y + 2),
        1,
    )
    pygame.draw.rect(surface, border, rect, 2 if hovered else 1, border_radius=7)
    if label:
        col = (255, 252, 232) if hovered else IVORY
        sh = font.render(label, True, (8, 12, 16))
        txt = font.render(label, True, col)
        tx = rect.centerx - txt.get_width() // 2
        ty = rect.centery - txt.get_height() // 2
        surface.blit(sh, (tx + 1, ty + 1))
        surface.blit(txt, (tx, ty))


def draw_startup_menu(
    surface: pygame.Surface,
    fonts: dict[str, pygame.font.Font],
    selected_mode: str = "AI vs AI",
    selected_house: str = "STARK",
    mouse: tuple[float, float] | None = None,
) -> dict[str, pygame.Rect]:
    """Render the realm entry menu."""
    buttons: dict[str, pygame.Rect] = {}
    overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
    overlay.fill((6, 12, 16, 215))
    surface.blit(overlay, (0, 0))

    panel = pygame.Rect(0, 0, 580, 480)
    panel.center = (WIDTH // 2, HEIGHT // 2)
    draw_glass_panel(surface, panel, (20, 30, 34), GOLD, 12)

    crown_icon = get_sprite("assets/ui/crown.png", (42, 42))
    if crown_icon:
        surface.blit(crown_icon, (panel.centerx - 21, panel.y + 20))
    title_text = "GAME OF THRONES"
    title_w, _ = fonts["hero"].size(title_text)
    write(surface, title_text, (panel.centerx - title_w // 2, panel.y + 70), fonts["hero"], GOLD)
    sub_text = "AI CONQUEST · ISOMETRIC RTS EDITION"
    sub_w, _ = fonts["small"].size(sub_text)
    write(surface, sub_text, (panel.centerx - sub_w // 2, panel.y + 114), fonts["small"], IVORY)

    pygame.draw.line(surface, (70, 88, 85), (panel.x + 40, panel.y + 144), (panel.right - 40, panel.y + 144), 1)

    # Game Mode Selection
    write(surface, "SELECT CONQUEST MODE", (panel.x + 40, panel.y + 158), fonts["micro"], MUTED)
    for idx, (m_key, m_label) in enumerate((("mode_ai", "AI vs AI (Observer Mode)"), ("mode_human", "Human vs AI (Player Command)"))):
        btn = pygame.Rect(panel.x + 40 + idx * 255, panel.y + 180, 245, 42)
        buttons[m_key] = btn
        is_sel = (m_key == "mode_ai" and selected_mode == "AI vs AI") or (m_key == "mode_human" and selected_mode == "Human vs AI")
        _draw_button(surface, btn, m_label, fonts["micro"], active=is_sel, hovered=bool(mouse and btn.collidepoint(mouse)), accent=GOLD if is_sel else (100, 120, 115))

    # House Selection
    write(surface, "CHOOSE YOUR GREAT HOUSE", (panel.x + 40, panel.y + 242), fonts["micro"], MUTED)
    for idx, h_name in enumerate(("STARK", "LANNISTER", "TARGARYEN")):
        btn = pygame.Rect(panel.x + 40 + idx * 168, panel.y + 266, 160, 68)
        buttons[f"house_{h_name}"] = btn
        is_sel = selected_house == h_name
        accent = HOUSE_COLORS[h_name]
        _draw_button(surface, btn, "", fonts["small"], active=is_sel, hovered=bool(mouse and btn.collidepoint(mouse)), accent=accent if is_sel else (100, 120, 115))
        draw_crest(surface, (btn.x + 26, btn.centery), h_name, 15)
        write(surface, h_name, (btn.x + 49, btn.centery - 9), fonts["small"], accent if is_sel else IVORY)

    # Enter realm button
    start_btn = pygame.Rect(panel.x + 40, panel.bottom - 74, panel.width - 80, 48)
    buttons["start"] = start_btn
    hovered = bool(mouse and start_btn.collidepoint(mouse))
    fill_top = (232, 188, 92) if hovered else (210, 162, 72)
    fill_bot = (182, 134, 48) if hovered else (162, 114, 38)
    pygame.draw.rect(surface, fill_bot, start_btn, border_radius=9)
    top_half = pygame.Rect(start_btn.x + 1, start_btn.y + 1, start_btn.width - 2, start_btn.height // 2)
    pygame.draw.rect(surface, fill_top, top_half, border_top_left_radius=8, border_top_right_radius=8)
    pygame.draw.rect(surface, (245, 212, 132), start_btn, 1, border_radius=9)
    lbl = fonts["subhead"].render("ENTER THE REALM", True, (18, 25, 29))
    surface.blit(lbl, (start_btn.centerx - lbl.get_width() // 2, start_btn.centery - lbl.get_height() // 2))
    return buttons


def draw_human_prompt(
    surface: pygame.Surface,
    fonts: dict[str, pygame.font.Font],
    house: House,
    diplomacy: Diplomacy,
    mouse: tuple[float, float] | None = None,
) -> dict[str, pygame.Rect]:
    """Render interactive player command bar during human turns."""
    buttons: dict[str, pygame.Rect] = {}
    proposal = house.get_pending_proposal()
    if proposal is not None:
        sender_key = str(proposal.get("from", "")).upper()
        sender_house = diplomacy.houses.get(sender_key)
        if sender_house is not None and sender_house.is_eliminated():
            house.clear_inbox()
            proposal = None
    bar_w = min(780, MAP_RECT.width - 560)
    bar = pygame.Rect(MAP_RECT.centerx - bar_w // 2, MAP_RECT.y + 12, bar_w, 48)
    draw_glass_panel(surface, bar, (22, 34, 40), HOUSE_COLORS[house.name], 8)

    if proposal is not None:
        sender = str(proposal.get("from", "")).title()
        write(surface, f"RAVEN FROM HOUSE {sender.upper()}: ALLIANCE OFFER", (bar.x + 14, bar.y + 8), fonts["small"], GOLD)
        write(surface, "Accept the diplomatic pact or reject it before marching.", (bar.x + 14, bar.y + 26), fonts["tiny"], MUTED)
        for idx, (key, label, col) in enumerate((("accept", "ACCEPT", STARK), ("reject", "REJECT", TARGARYEN))):
            btn = pygame.Rect(bar.right - 200 + idx * 96, bar.y + 9, 88, 30)
            buttons[key] = btn
            _draw_button(surface, btn, label, fonts["micro"], hovered=bool(mouse and btn.collidepoint(mouse)), accent=col)
    else:
        write(surface, f"YOUR TURN · HOUSE {house.name}", (bar.x + 14, bar.y + 8), fonts["small"], HOUSE_COLORS[house.name])
        write(surface, "Select an adjacent enemy hold to attack, or issue orders.", (bar.x + 14, bar.y + 26), fonts["tiny"], MUTED)
        ally = house.allied_with
        ally_house = diplomacy.houses.get(ally) if ally else None
        if ally and (ally_house is None or not ally_house.is_eliminated()):
            btn = pygame.Rect(bar.right - 210, bar.y + 9, 108, 30)
            buttons["betray"] = btn
            _draw_button(surface, btn, f"BETRAY {ally[:4]}", fonts["tiny"], hovered=bool(mouse and btn.collidepoint(mouse)), accent=TARGARYEN)
        else:
            alive_others = [
                n for n in ("STARK", "LANNISTER", "TARGARYEN")
                if n != house.name and (n not in diplomacy.houses or not diplomacy.houses[n].is_eliminated())
            ]
            if len(alive_others) >= 2:
                for idx, other in enumerate(alive_others):
                    btn = pygame.Rect(bar.right - 300 + idx * 102, bar.y + 9, 94, 30)
                    buttons[f"ally_{other}"] = btn
                    _draw_button(surface, btn, f"ALLY {other[:5]}", fonts["tiny"], hovered=bool(mouse and btn.collidepoint(mouse)), accent=HOUSE_COLORS[other])
        pass_btn = pygame.Rect(bar.right - 92, bar.y + 9, 84, 30)
        buttons["hold"] = pass_btn
        _draw_button(surface, pass_btn, "HOLD TURN", fonts["tiny"], hovered=bool(mouse and pass_btn.collidepoint(mouse)), accent=GOLD)
    return buttons


def draw_ai_prompt(
    surface: pygame.Surface,
    fonts: dict[str, pygame.font.Font],
    turn: int,
    mouse: tuple[float, float] | None = None,
    battle_status: str | None = None,
) -> dict[str, pygame.Rect]:
    """Render the Advance Turn button or live Battle-in-Progress banner."""
    bar_w = min(780, MAP_RECT.width - 560)
    bar = pygame.Rect(MAP_RECT.centerx - bar_w // 2, MAP_RECT.y + 12, bar_w, 48)
    if battle_status:
        paused_mode = battle_status.startswith("GAME PAUSED")
        accent = GOLD if paused_mode else (235, 130, 75)
        bg = (22, 32, 38) if paused_mode else (28, 24, 24)
        sub_txt = (
            "Inspect the map, AI Brain [H], or Raven Log [L] while paused."
            if paused_mode
            else "War in progress — turn will finish once the battle concludes."
        )
        badge_txt = "PAUSED" if paused_mode else "FIGHTING..."
        draw_glass_panel(surface, bar, bg, accent, 8)
        write(surface, battle_status, (bar.x + 14, bar.y + 8), fonts["small"], GOLD)
        write(surface, sub_txt, (bar.x + 14, bar.y + 26), fonts["tiny"], MUTED)
        badge = pygame.Rect(bar.right - 138, bar.y + 9, 126, 30)
        _draw_button(surface, badge, badge_txt, fonts["micro"], active=paused_mode, hovered=False, accent=accent)
        return {}

    draw_glass_panel(surface, bar, (22, 34, 40), GOLD, 8)
    write(surface, f"AI CONQUEST · AWAITING VIEWER PERMISSION (TURN {turn:02d})", (bar.x + 14, bar.y + 8), fonts["small"], GOLD)
    write(surface, "Click 'ADVANCE TURN' or press SPACE / ENTER to step forward.", (bar.x + 14, bar.y + 26), fonts["tiny"], MUTED)

    next_btn = pygame.Rect(bar.right - 150, bar.y + 8, 140, 32)
    hovered = bool(mouse and next_btn.collidepoint(mouse))

    # Gleaming medieval advance button
    _draw_button(surface, next_btn, "ADVANCE TURN >>", fonts["micro"], active=True, hovered=hovered, accent=GOLD)
    return {"next_turn": next_btn}


def draw_game_over_banner(
    surface: pygame.Surface,
    fonts: dict[str, pygame.font.Font],
    winner: House,
    mouse: tuple[float, float] | None = None,
) -> dict[str, pygame.Rect]:
    """Render top control banner after dismissing the win popup to inspect the final realm."""
    buttons: dict[str, pygame.Rect] = {}
    bar_w = min(840, MAP_RECT.width - 560)
    bar = pygame.Rect(MAP_RECT.centerx - bar_w // 2, MAP_RECT.y + 12, bar_w, 48)
    accent = HOUSE_COLORS.get(winner.name, GOLD)
    draw_glass_panel(surface, bar, (22, 34, 40), accent, 8)

    write(
        surface,
        f"CONQUEST CONCLUDED · HOUSE {winner.name} RULES WESTEROS",
        (bar.x + 14, bar.y + 8),
        fonts["small"],
        accent,
    )
    write(
        surface,
        "Reviewing final realm state. Click territories to inspect garrisons and the Raven's Log.",
        (bar.x + 14, bar.y + 26),
        fonts["tiny"],
        MUTED,
    )

    summary_btn = pygame.Rect(bar.right - 268, bar.y + 8, 144, 32)
    buttons["view_summary"] = summary_btn
    hovered_sum = bool(mouse and summary_btn.collidepoint(mouse))
    _draw_button(
        surface,
        summary_btn,
        "VICTORY SUMMARY",
        fonts["micro"],
        active=True,
        hovered=hovered_sum,
        accent=accent,
    )

    new_btn = pygame.Rect(bar.right - 114, bar.y + 8, 104, 32)
    buttons["play_again"] = new_btn
    hovered_new = bool(mouse and new_btn.collidepoint(mouse))
    _draw_button(
        surface,
        new_btn,
        "NEW GAME",
        fonts["micro"],
        active=True,
        hovered=hovered_new,
        accent=GOLD,
    )
    return buttons


def draw_win_screen(
    surface: pygame.Surface,
    fonts: dict[str, pygame.font.Font],
    winner: House,
    mouse: tuple[float, float] | None = None,
) -> dict[str, pygame.Rect]:
    """Render the Iron Throne victory ceremony with Review Board and New Game options."""
    buttons: dict[str, pygame.Rect] = {}
    overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
    overlay.fill((6, 12, 16, 215))
    surface.blit(overlay, (0, 0))

    accent = HOUSE_COLORS.get(winner.name, GOLD)
    panel = pygame.Rect(0, 0, 560, 350)
    panel.center = (WIDTH // 2, HEIGHT // 2)
    draw_glass_panel(surface, panel, (20, 30, 36), accent, 12)

    # Top-right [X] close button
    close_btn = pygame.Rect(panel.right - 36, panel.y + 12, 24, 24)
    buttons["close"] = close_btn
    hovered_close = bool(mouse and close_btn.collidepoint(mouse))
    pygame.draw.rect(
        surface,
        (40, 50, 55) if not hovered_close else (80, 40, 40),
        close_btn,
        border_radius=4,
    )
    pygame.draw.rect(surface, accent if not hovered_close else GOLD, close_btn, 1, border_radius=4)
    x_lbl = fonts["micro"].render("X", True, IVORY if not hovered_close else GOLD)
    surface.blit(
        x_lbl,
        (
            close_btn.centerx - x_lbl.get_width() // 2,
            close_btn.centery - x_lbl.get_height() // 2,
        ),
    )

    draw_crest(surface, (panel.centerx, panel.y + 54), winner.name, 28)
    title_s = fonts["hero"].render(f"HOUSE {winner.name}", True, accent)
    surface.blit(title_s, (panel.centerx - title_s.get_width() // 2, panel.y + 96))
    sub_s = fonts["subhead"].render("CLAIMS THE IRON THRONE & RULES WESTEROS", True, IVORY)
    surface.blit(sub_s, (panel.centerx - sub_s.get_width() // 2, panel.y + 138))

    pygame.draw.line(surface, (75, 95, 90), (panel.x + 40, panel.y + 172), (panel.right - 40, panel.y + 172), 1)
    stats = [
        ("HOLDS", str(len(winner.territories)), IVORY),
        ("GOLD", str(winner.gold), GOLD),
        ("ARMIES", str(winner.armies), IVORY),
    ]
    for idx, (label, val, col) in enumerate(stats):
        sx = panel.x + 60 + idx * 156
        write(surface, label, (sx, panel.y + 186), fonts["tiny"], MUTED)
        write(surface, val, (sx, panel.y + 206), fonts["turn"], col)

    # Two bottom action buttons: Review Board vs New Game
    review_btn = pygame.Rect(panel.x + 40, panel.bottom - 68, 225, 44)
    buttons["review_board"] = review_btn
    hovered_rev = bool(mouse and review_btn.collidepoint(mouse))
    _draw_button(
        surface,
        review_btn,
        "REVIEW REALM / BOARD",
        fonts["micro"],
        active=True,
        hovered=hovered_rev,
        accent=IVORY,
    )

    again_btn = pygame.Rect(panel.right - 265, panel.bottom - 68, 225, 44)
    buttons["play_again"] = again_btn
    hovered_again = bool(mouse and again_btn.collidepoint(mouse))
    pygame.draw.rect(
        surface,
        accent if hovered_again else mix(accent, (25, 35, 40), 0.3),
        again_btn,
        border_radius=9,
    )
    pygame.draw.rect(surface, GOLD, again_btn, 1, border_radius=9)
    lbl = fonts["subhead"].render("NEW CONQUEST", True, (18, 25, 29) if hovered_again else IVORY)
    surface.blit(lbl, (again_btn.centerx - lbl.get_width() // 2, again_btn.centery - lbl.get_height() // 2))

    return buttons


def draw(
    screen: pygame.Surface,
    game_map: Map | None = None,
    houses: list[House] | None = None,
    diplomacy: Diplomacy | None = None,
    turn_log: list[dict[str, str | int]] | None = None,
    mode: str = "AI vs AI",
    fonts: dict[str, pygame.font.Font] | None = None,
    mouse: tuple[float, float] | None = None,
    turn: int = 1,
    animations: list[dict[str, object]] | None = None,
    show_houses: bool = False,
    show_log: bool = False,
    selected_fuzzy_house: str | None = None,
    minimax_scores: dict[str | None, float] | None = None,
    brain_tab: str = "trace",
    acting_house: str | None = None,
) -> dict[str, pygame.Rect]:
    """Render the complete full-screen Game of Thrones: AI Conquest interface."""
    active_fonts = _get_fonts(fonts)
    draw_backdrop(screen)
    draw_top_bar(screen, active_fonts, houses=houses, turn=turn, mode=mode)
    draw_glass_panel(screen, MAP_RECT, (18, 30, 36), GOLD, 10)
    draw_world(
        screen,
        active_fonts,
        MAP_RECT.inflate(-4, -4),
        game_map=game_map,
        houses=houses,
        turn=turn,
        animations=animations,
    )
    pygame.draw.rect(screen, GOLD, MAP_RECT, 1, border_radius=10)
    draw_hover(screen, active_fonts, mouse, game_map=game_map, houses=houses, minimax_scores=minimax_scores)
    return draw_sidebar(
        screen,
        active_fonts,
        houses=houses,
        diplomacy=diplomacy,
        turn_log=turn_log,
        show_houses=show_houses,
        show_log=show_log,
        selected_fuzzy_house=selected_fuzzy_house,
        mouse=mouse,
        brain_tab=brain_tab,
        acting_house=acting_house,
    )


def draw_screen(
    screen: pygame.Surface,
    fonts: dict[str, pygame.font.Font] | None = None,
    mouse: tuple[float, float] | None = None,
) -> None:
    """Backwards-compatible entry point for rendering."""
    draw(screen, fonts=fonts, mouse=mouse)
