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


def _draw_patrol_dragon(
    surface: pygame.Surface,
    game_map: Map | None,
    houses: list[House] | None,
    animations: list[dict[str, object]] | None,
) -> None:
    """Render an ambient flying Targaryen dragon circling Dragonstone/capital."""
    if animations and any(
        a.get("type") == "march" and a.get("house") == "TARGARYEN" for a in animations
    ):
        return
    if houses:
        targ = next((h for h in houses if h.name == "TARGARYEN"), None)
        if targ is not None and targ.is_eliminated():
            return
        anchor = targ.territories[0] if targ and targ.territories else None
    else:
        anchor = None
    if anchor is None and game_map is not None:
        owned = game_map.get_owned_by("TARGARYEN")
        anchor = owned[0] if owned else None
    col, row = (anchor.col, anchor.row) if anchor is not None else DRAGONSTONE_COORD
    cx, cy = center_of(col, row)

    theta = pygame.time.get_ticks() * 0.00055
    rx, ry = 36.0, 20.0
    px = cx + math.cos(theta) * rx
    py = cy + math.sin(theta) * ry
    dx = -math.sin(theta) * rx
    dy = math.cos(theta) * ry
    direction = _dragon_direction(dx, dy)
    frames = _get_dragon_frames(direction, "fly", DRAGON_PATROL_SIZE)
    if not frames:
        return
    frame = frames[(pygame.time.get_ticks() // 135) % len(frames)]

    shadow = pygame.Surface((42, 16), pygame.SRCALPHA)
    pygame.draw.ellipse(shadow, (8, 12, 16, 105), (0, 0, 42, 16))
    surface.blit(shadow, (round(px - 21), round(py + 6)))
    surface.blit(frame, (round(px - frame.get_width() / 2), round(py - 28 - frame.get_height() / 2)))


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


_WARRIOR_FRAME_CACHE: dict[tuple[str, tuple[int, int]], list[pygame.Surface]] = {}
_WARRIOR_SHEETS: dict[str, str] = {
    "run": "assets/ui/Medieval Warrior Pack/Run.png",
    "attack1": "assets/ui/Medieval Warrior Pack/Attack1.png",
    "attack2": "assets/ui/Medieval Warrior Pack/Attack2.png",
    "idle": "assets/ui/Medieval Warrior Pack/Idle.png",
    "hit": "assets/ui/Medieval Warrior Pack/Hit.png",
    "death": "assets/ui/Medieval Warrior Pack/Death.png",
}


def _get_warrior_frames(
    kind: str = "run",
    size: tuple[int, int] = (54, 54),
) -> list[pygame.Surface]:
    """Slice and cache Medieval Warrior Pack horizontal sprite-sheet frames (184x137 cells)."""
    key = (kind, size)
    if key in _WARRIOR_FRAME_CACHE:
        return _WARRIOR_FRAME_CACHE[key]
    path = _WARRIOR_SHEETS.get(kind, _WARRIOR_SHEETS["run"])
    sheet = get_sprite(path)
    if sheet is None:
        _WARRIOR_FRAME_CACHE[key] = []
        return []
    cell_w = 184
    cell_h = sheet.get_height()
    count = max(1, sheet.get_width() // cell_w)
    # Consistent crop inside each 184x137 cell so feet stay pixel-locked across all actions
    crop_x, crop_y = 38, 22
    crop_w, crop_h = min(108, cell_w - crop_x), min(108, cell_h - crop_y)
    frames: list[pygame.Surface] = []
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
    """Render animated running Medieval Warriors patrolling between owned holds."""
    if game_map is None or not houses:
        return
    ticks_ms = pygame.time.get_ticks()
    ticks = ticks_ms * 0.00032
    run_frames = _get_warrior_frames("run", (48, 48))
    fallback = get_sprite("assets/units/knights.png", (34, 38)) if not run_frames else None
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

            run_frames = _get_warrior_frames("run", (62, 62))
            idle_frames = _get_warrior_frames("idle", (62, 62))
            atk1_frames = _get_warrior_frames("attack1", (66, 66))
            atk2_frames = _get_warrior_frames("attack2", (66, 66))
            hit_frames = _get_warrior_frames("hit", (62, 62))
            death_frames = _get_warrior_frames("death", (62, 62))

            att_slots = ((-10, -14, 0), (0, 0, 2), (-8, 14, 4))
            def_slots = ((10, -14, 1), (0, 0, 3), (8, 14, 5))

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

                # Defending castle's warriors running out to meet the invasion
                for fx, fy, foff in def_slots:
                    _draw_warrior_unit(
                        surface, dpx + fx, dpy + fy, run_frames, int(elapsed * 11) + foff, def_flip, def_color
                    )

                # Attacking house (Targaryen dragon OR Stark/Lannister warrior squad)
                if house == "TARGARYEN":
                    frames = _get_dragon_frames(_dragon_direction(dx, dy), "fly", DRAGON_BATTLE_SIZE)
                    if frames:
                        frame = frames[int(elapsed * 8) % len(frames)]
                        shadow = pygame.Surface((48, 18), pygame.SRCALPHA)
                        pygame.draw.ellipse(shadow, (8, 12, 16, 120), (0, 0, 48, 18))
                        surface.blit(shadow, (round(apx - 24), round(apy + 6)))
                        arc = math.sin(mt * math.pi) * 14
                        surface.blit(frame, (round(apx - frame.get_width() / 2), round(apy - 28 - arc - frame.get_height() / 2)))
                else:
                    for fx, fy, foff in att_slots:
                        _draw_warrior_unit(
                            surface, apx + fx, apy + fy, run_frames, int(elapsed * 11) + foff, att_flip, accent
                        )

            elif t < 0.78:
                # Phase 2: Extended face-to-face sword fight / dragonfire clash!
                ct = (t - 0.34) / 0.44
                clash_cycle = int(elapsed * 3.5)

                # Defenders fighting back (alternating sword swings & taking hits)
                for idx_w, (fx, fy, foff) in enumerate(def_slots):
                    taking_hit = ((clash_cycle + idx_w) % 3 == 0)
                    if taking_hit and hit_frames:
                        fset = hit_frames
                        fidx = int(elapsed * 9 + foff) % len(fset)
                    else:
                        fset = atk1_frames if (idx_w % 2 == 0) else atk2_frames
                        fidx = int(elapsed * 9 + foff) % max(1, len(fset))
                    lunge = (-4 if def_flip else 4) * math.sin(elapsed * 12 + idx_w)
                    _draw_warrior_unit(
                        surface, def_meet_x + fx + lunge, def_meet_y + fy, fset, fidx, def_flip, def_color
                    )

                if house == "TARGARYEN":
                    frames = _get_dragon_frames(_dragon_direction(dx, dy), "attack", DRAGON_BATTLE_SIZE)
                    if frames:
                        frame = frames[int(elapsed * 7) % len(frames)]
                        shadow = pygame.Surface((48, 18), pygame.SRCALPHA)
                        pygame.draw.ellipse(shadow, (8, 12, 16, 120), (0, 0, 48, 18))
                        surface.blit(shadow, (round(att_meet_x - 24), round(att_meet_y + 8)))
                        surface.blit(frame, (round(att_meet_x - frame.get_width() / 2), round(att_meet_y - 26 - frame.get_height() / 2)))
                    # Streaming dragonfire & embers onto defending warriors
                    for i in range(10):
                        p = (elapsed * 2.4 + i * 0.1) % 1.0
                        ex = round(att_meet_x + (def_meet_x - att_meet_x) * p + math.sin(i * 2.1 + elapsed * 9) * 8)
                        ey = round(att_meet_y - 18 + (def_meet_y - att_meet_y + 12) * p + math.cos(i * 1.7 + elapsed * 9) * 6)
                        col = (255, 205, 76) if i % 2 == 0 else (242, 86, 34)
                        pygame.draw.circle(surface, col, (ex, ey), max(2, round(6 * (1.0 - p * 0.5))))
                else:
                    # Attacking warriors trading sword swings & hits face-to-face
                    for idx_w, (fx, fy, foff) in enumerate(att_slots):
                        taking_hit = ((clash_cycle + idx_w + 1) % 3 == 0)
                        if taking_hit and hit_frames:
                            fset = hit_frames
                            fidx = int(elapsed * 9 + foff) % len(fset)
                        else:
                            fset = atk1_frames if (idx_w % 2 == 0) else atk2_frames
                            fidx = int(elapsed * 9 + foff) % max(1, len(fset))
                        lunge = (-4 if att_flip else 4) * math.sin(elapsed * 12 + idx_w + 1.5)
                        _draw_warrior_unit(
                            surface, att_meet_x + fx + lunge, att_meet_y + fy, fset, fidx, att_flip, accent
                        )

                # Live steel clash sparks flying between the two squads
                for i in range(7):
                    sp_p = (elapsed * 3.2 + i * 0.17) % 1.0
                    ang = i * (math.tau / 7) + elapsed * 3.0
                    rad = 4 + sp_p * 22
                    sx = round(mid_x + math.cos(ang) * rad)
                    sy = round(mid_y - 12 + math.sin(ang) * rad * 0.6)
                    pygame.draw.circle(surface, GOLD if i % 2 == 0 else IVORY, (sx, sy), max(1, round(3.5 * (1.0 - sp_p))))

                # Battle progress label above the clash
                clash_lbl = "CLASHING!"
                write(surface, clash_lbl, (round(mid_x - fonts["micro"].size(clash_lbl)[0] / 2), round(mid_y - 54)), fonts["micro"], GOLD)

            else:
                # Phase 3: Defeated warriors fall (Death.png), victors hold the field
                it = (t - 0.78) / 0.22
                death_idx = min(max(0, len(death_frames) - 1), int(it * len(death_frames)))

                if captured:
                    # Defenders collapse; attackers stand victorious
                    for fx, fy, _ in def_slots:
                        _draw_warrior_unit(
                            surface, def_meet_x + fx, def_meet_y + fy, death_frames, death_idx, def_flip, def_color, show_ring=False
                        )
                    if house == "TARGARYEN":
                        frames = _get_dragon_frames(_dragon_direction(dx, dy), "fly", DRAGON_BATTLE_SIZE)
                        if frames:
                            frame = frames[int(elapsed * 8) % len(frames)]
                            surface.blit(frame, (round(bx - frame.get_width() / 2), round(by - 32 - frame.get_height() / 2)))
                    else:
                        for fx, fy, foff in att_slots:
                            _draw_warrior_unit(
                                surface, att_meet_x + fx, att_meet_y + fy, idle_frames, int(elapsed * 8) + foff, att_flip, accent
                            )
                else:
                    # Attackers collapse (or dragon retreats); defenders stand triumphant
                    if house == "TARGARYEN":
                        frames = _get_dragon_frames(_dragon_direction(-dx, -dy), "fly", DRAGON_BATTLE_SIZE)
                        if frames:
                            rx = att_meet_x - ux * 26 * it
                            ry = att_meet_y - uy * 26 * it
                            frame = frames[int(elapsed * 8) % len(frames)]
                            surface.blit(frame, (round(rx - frame.get_width() / 2), round(ry - 28 - frame.get_height() / 2)))
                    else:
                        for fx, fy, _ in att_slots:
                            _draw_warrior_unit(
                                surface, att_meet_x + fx, att_meet_y + fy, death_frames, death_idx, att_flip, accent, show_ring=False
                            )
                    for fx, fy, foff in def_slots:
                        _draw_warrior_unit(
                            surface, def_meet_x + fx, def_meet_y + fy, idle_frames, int(elapsed * 8) + foff, def_flip, def_color
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
    mouse: tuple[float, float] | None = None,
) -> dict[str, pygame.Rect]:
    """Render top-right collapsible drawer toggle pills on the full-screen map."""
    buttons: dict[str, pygame.Rect] = {}
    houses_btn = pygame.Rect(MAP_RECT.right - 274, MAP_RECT.y + 14, 126, 40)
    log_btn = pygame.Rect(MAP_RECT.right - 140, MAP_RECT.y + 14, 126, 40)
    buttons["toggle_houses"] = houses_btn
    buttons["toggle_log"] = log_btn
    _draw_button(
        surface,
        houses_btn,
        "HOUSES [H]",
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


def draw_sidebar(
    surface: pygame.Surface,
    fonts: dict[str, pygame.font.Font],
    houses: list[House] | None = None,
    diplomacy: Diplomacy | None = None,
    turn_log: list[dict[str, str | int]] | None = None,
    show_houses: bool = False,
    show_log: bool = False,
) -> None:
    """Render collapsible floating House Intelligence & Raven's Log drawers over the map."""
    if not show_houses and not show_log:
        return

    drawer_y = MAP_RECT.y + 66
    drawer_h = MAP_RECT.height - 114
    log_w = 436
    house_w = 418

    if show_houses:
        hx = MAP_RECT.right - house_w - (log_w + 26 if show_log else 14)
        rect = pygame.Rect(hx, drawer_y, house_w, drawer_h)
        draw_glass_panel(surface, rect, (16, 25, 30), GOLD, 10)
        write(surface, "REALM OVERVIEW", (rect.x + 16, rect.y + 12), fonts["subhead"], IVORY)
        write_right(surface, "HOUSE INTELLIGENCE", rect.right - 16, rect.y + 14, fonts["micro"], MUTED)
        pygame.draw.line(surface, GOLD, (rect.x + 16, rect.y + 36), (rect.x + 82, rect.y + 36), 2)

        active_pacts = []
        if diplomacy is not None:
            seen_pairs: set[tuple[str, str]] = set()
            for h1, h2 in diplomacy.alliances.items():
                if h2 and tuple(sorted((h1, h2))) not in seen_pairs:
                    seen_pairs.add(tuple(sorted((h1, h2))))
                    active_pacts.append(f"{h1.title()} & {h2.title()}")
        pact_line = f"Active alliance: {', '.join(active_pacts)}" if active_pacts else "No active alliances across the realm."
        write(surface, pact_line, (rect.x + 16, rect.y + 44), fonts["tiny"], GOLD if active_pacts else MUTED)

        if houses:
            total_strength = max(1.0, sum(h.get_military_strength() for h in houses if not h.is_eliminated()))
            cards: list[dict[str, object]] = []
            for h in houses:
                status = "ELIMINATED" if h.is_eliminated() else (f"ALLY: {h.allied_with}" if h.allied_with else ("YOUR POV" if h.is_human else "SOLO"))
                income = 0 if h.is_eliminated() else (10 + sum(t.resource_value for t in h.territories))
                share = 0.0 if h.is_eliminated() else (h.get_military_strength() / total_strength)
                cards.append(
                    {
                        "name": h.name,
                        "motto": h.motto,
                        "gold": str(h.gold),
                        "armies": str(h.armies),
                        "lands": str(len(h.territories)),
                        "status": status,
                        "mode": h.mode,
                        "pending": h.get_pending_proposal() is not None,
                        "fuzzy": h.fuzzy_scores,
                        "income": income,
                        "power_share": share,
                    }
                )
            pov_house = next((h for h in houses if h.is_human), houses[0])
            fuzzy_scores = pov_house.fuzzy_scores
            perspective = pov_house.name
        else:
            cards = [
                {"name": "STARK", "motto": "WINTER IS COMING", "gold": "60", "armies": "14", "lands": "1", "status": "YOUR POV", "mode": "DECOMPOSED", "pending": False, "income": 19, "power_share": 0.35},
                {"name": "LANNISTER", "motto": "HEAR ME ROAR", "gold": "65", "armies": "14", "lands": "1", "status": "SOLO", "mode": "DECOMPOSED", "pending": False, "income": 19, "power_share": 0.33},
                {"name": "TARGARYEN", "motto": "FIRE AND BLOOD", "gold": "45", "armies": "12", "lands": "1", "status": "SOLO", "mode": "DECOMPOSED", "pending": False, "income": 16, "power_share": 0.32},
            ]
            fuzzy_scores = None
            perspective = "STARK"

        for index, card in enumerate(cards):
            draw_house_stat_card(
                surface,
                pygame.Rect(rect.x + 12, rect.y + 66 + index * 154, rect.width - 24, 144),
                card,
                fonts,
            )

        draw_diplomacy_panel(
            surface,
            pygame.Rect(rect.x + 12, rect.bottom - 166, rect.width - 24, 154),
            fonts,
            fuzzy_scores,
            perspective_house=perspective,
        )

    if show_log:
        log_entries = turn_log if turn_log is not None else (diplomacy.event_log if diplomacy is not None else None)
        raven_rect = pygame.Rect(MAP_RECT.right - log_w - 14, drawer_y, log_w, drawer_h)
        draw_raven_panel(surface, raven_rect, fonts, log_entries)


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
    territory = game_map.by_coord.get(cell) if game_map is not None else None
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

    # Medieval Tooltip Card
    is_throne = title == "KING'S LANDING"
    card_h = 132 if is_throne else 110
    tip = pygame.Rect(int(pos[0]) + 16, int(pos[1]) - 30, 240 if is_throne else 210, card_h)
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
    else:
        write(surface, title, (tip.x + 12, tip.y + 8), fonts["cardtitle"], IVORY)
        owner_str = f"Ruler: House {owner.title()}" if owner else "Neutral Seat"
        write(surface, owner_str, (tip.x + 12, tip.y + 28), fonts["tiny"], accent)

        pygame.draw.line(surface, (60, 78, 75), (tip.x + 12, tip.y + 46), (tip.right - 12, tip.y + 46), 1)
        write(surface, f"Garrison Armies: {garrison_val}", (tip.x + 12, tip.y + 52), fonts["micro"], IVORY)
        write(surface, f"Tribute / Income: +{res_val} Gold", (tip.x + 12, tip.y + 70), fonts["micro"], GOLD)
        write(surface, f"Defense Fortification: +{def_bonus}", (tip.x + 12, tip.y + 88), fonts["tiny"], MUTED)


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
        if ally:
            btn = pygame.Rect(bar.right - 210, bar.y + 9, 108, 30)
            buttons["betray"] = btn
            _draw_button(surface, btn, f"BETRAY {ally[:4]}", fonts["tiny"], hovered=bool(mouse and btn.collidepoint(mouse)), accent=TARGARYEN)
        else:
            others = [n for n in ("STARK", "LANNISTER", "TARGARYEN") if n != house.name]
            for idx, other in enumerate(others):
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
        draw_glass_panel(surface, bar, (28, 24, 24), (235, 130, 75), 8)
        write(surface, battle_status, (bar.x + 14, bar.y + 8), fonts["small"], GOLD)
        write(surface, "War in progress — turn will finish once the battle concludes.", (bar.x + 14, bar.y + 26), fonts["tiny"], MUTED)
        badge = pygame.Rect(bar.right - 138, bar.y + 9, 126, 30)
        _draw_button(surface, badge, "FIGHTING...", fonts["micro"], active=False, hovered=False, accent=(235, 130, 75))
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
) -> None:
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
    draw_hover(screen, active_fonts, mouse, game_map=game_map, houses=houses)
    draw_sidebar(
        screen,
        active_fonts,
        houses=houses,
        diplomacy=diplomacy,
        turn_log=turn_log,
        show_houses=show_houses,
        show_log=show_log,
    )


def draw_screen(
    screen: pygame.Surface,
    fonts: dict[str, pygame.font.Font] | None = None,
    mouse: tuple[float, float] | None = None,
) -> None:
    """Backwards-compatible entry point for rendering."""
    draw(screen, fonts=fonts, mouse=mouse)
