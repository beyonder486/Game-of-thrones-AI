"""Build animated WebPs for the slides from the game's own sprite sheets and renderer.

Run from the project root:  py presentation/make_animations.py
Outputs go to presentation/animations/.
"""
from __future__ import annotations

import os
import random
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "presentation", "animations")
os.makedirs(OUT, exist_ok=True)
A = os.path.join(ROOT, "assets")


def strip(path: str, n: int, cols: int | None = None, rows: int = 1, row: int = 0) -> list[Image.Image]:
    sheet = Image.open(path).convert("RGBA")
    cols = cols or n
    w, h = sheet.width // cols, sheet.height // rows
    return [sheet.crop((i * w, row * h, (i + 1) * w, (row + 1) * h)) for i in range(n)]


def trim(frames: list[Image.Image]) -> list[Image.Image]:
    """Crop all frames to the union of their non-transparent boxes (keeps alignment)."""
    box = None
    for f in frames:
        b = f.getbbox()
        if b:
            box = b if box is None else (min(box[0], b[0]), min(box[1], b[1]), max(box[2], b[2]), max(box[3], b[3]))
    return [f.crop(box) for f in frames] if box else frames


def save(frames: list[Image.Image], name: str, ms: int, scale: float = 1.0) -> None:
    if scale != 1.0:
        frames = [f.resize((round(f.width * scale), round(f.height * scale)), Image.LANCZOS) for f in frames]
    p = os.path.join(OUT, name)
    frames[0].save(p, save_all=True, append_images=frames[1:], duration=ms, loop=0, lossless=False, quality=88, method=6)
    print(f"{name}: {len(frames)} frames, {frames[0].size}, {os.path.getsize(p) // 1024} KB")


# 1. House dragons (8-frame wing-flap strips, right-facing)
save(trim(strip(f"{A}/units/dragon_stark_flap.png", 8)), "dragon_stark.webp", 95, 1.3)
save(trim(strip(f"{A}/units/dragon_lannister_flap.png", 8)), "dragon_lannister.webp", 95, 1.2)
# Targaryen red dragon: right-facing sheet, 4x4 grid = 16 frames
red = []
for r in range(4):
    red += strip(f"{A}/ui/reddragonfly.png", 4, cols=4, rows=4, row=r)
save(trim(red), "dragon_targaryen.webp", 70, 1.6)

# 2. Ground troops
save(trim(strip(f"{A}/ui/Medieval Warrior Pack/Run.png", 8)), "warrior_run.webp", 85, 2.0)
save(trim(strip(f"{A}/ui/Medieval Warrior Pack/Attack1.png", 4) + strip(f"{A}/ui/Medieval Warrior Pack/Attack2.png", 4)), "warrior_attack.webp", 110, 2.0)
save(trim(strip(f"{A}/ui/EVil Wizard 2/Sprites/Attack1.png", 8)), "wizard_attack.webp", 95, 1.3)

# 3. A real battle captured from the game renderer (dragon swoop + fire breath)
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
sys.path.insert(0, ROOT)
os.chdir(ROOT)
import pygame  # noqa: E402

import main  # noqa: E402
from constants import HEIGHT, WIDTH  # noqa: E402
from renderer import MAP_RECT, draw, hex_at, make_fonts  # noqa: E402

pygame.init()
pygame.display.set_mode((1, 1))
canvas = pygame.Surface((WIDTH, HEIGHT))
fonts = make_fonts()


def centre(col: int, row: int) -> tuple[int, int]:
    for xx in range(MAP_RECT.left, MAP_RECT.right, 4):
        for yy in range(MAP_RECT.top, MAP_RECT.bottom, 4):
            if hex_at((xx, yy)) == (col, row):
                return xx, yy
    return MAP_RECT.center


random.seed(7)
c = main.GameController("AI vs AI")
captured = 0
for _ in range(60):
    if captured >= 2 or c.winner:
        break
    for h in list(c.houses):
        if h.is_eliminated() or c.winner or captured >= 2:
            continue
        c.step_house_turn(h)
        march = next((a for a in c.animations if a.get("type") == "march"), None)
        if march is not None and (captured == 0 or march["defender"] != "NEUTRAL"):
            cx, cy = centre(*march["to_coord"])
            fx, fy = centre(*march["from_coord"])
            mx, my = (cx + fx) // 2, (cy + fy) // 2
            box = (max(0, mx - 380), max(0, my - 270), 0, 0)
            box = (box[0], box[1], min(WIDTH, box[0] + 760), min(HEIGHT, box[1] + 540))
            frames = []
            steps = int(march["duration"] * 15)
            for _ in range(steps):
                draw(canvas, game_map=c.map, houses=c.houses, diplomacy=c.diplomacy, turn_log=c.diplomacy.event_log,
                     mode=c.mode, fonts=fonts, mouse=None, turn=c.turn, animations=c.animations,
                     show_houses=False, show_log=False, selected_fuzzy_house=h.name, minimax_scores=None,
                     brain_tab="trace", acting_house=h.name)
                raw = pygame.image.tostring(canvas, "RGB")
                frames.append(Image.frombytes("RGB", (WIDTH, HEIGHT), raw).crop(box))
                c.update_animations(1 / 15)
            kind = "neutral" if march["defender"] == "NEUTRAL" else "house"
            save(frames, f"battle_{kind}.webp", 66)
            print("   ", march["house"], "vs", march["defender"], "at", march["target_name"])
            captured += 1
        for _ in range(400):
            if not c.has_blocking_animation():
                break
            c.update_animations(1 / 30)
        c.animations.clear()
    if not c.winner:
        c._end_of_round()
