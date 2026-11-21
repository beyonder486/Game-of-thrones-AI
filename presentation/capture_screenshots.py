"""Headless screenshot capture for the presentation.

Runs the real game code with no window and saves PNG frames of key moments
into presentation/screenshots/. Run from the project root:  py presentation/capture_screenshots.py
"""
from __future__ import annotations

import os
import random
import sys

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import pygame  # noqa: E402

import main  # noqa: E402
from constants import HEIGHT, WIDTH  # noqa: E402
from renderer import (  # noqa: E402
    MAP_RECT, draw, draw_ai_prompt, draw_hud_toggles, draw_human_prompt,
    draw_startup_menu, draw_win_screen, hex_at, make_fonts,
)

OUT = os.path.join(ROOT, "presentation", "screenshots")
os.makedirs(OUT, exist_ok=True)

pygame.init()
pygame.display.set_mode((1, 1))
canvas = pygame.Surface((WIDTH, HEIGHT))
fonts = make_fonts()


def render(c, name, *, menu=False, brain=False, log=False, tab="trace", house=None,
           mouse=None, minimax=None, win=False, label=None, human=False, sel_mode="AI vs AI"):
    draw(canvas, game_map=c.map, houses=c.houses, diplomacy=c.diplomacy,
         turn_log=c.diplomacy.event_log, mode=c.mode, fonts=fonts, mouse=mouse,
         turn=c.turn, animations=c.animations, show_houses=brain, show_log=log,
         selected_fuzzy_house=house or c.houses[0].name, minimax_scores=minimax,
         brain_tab=tab, acting_house=c.active_trace_house if label else None)
    if menu:
        draw_startup_menu(canvas, fonts, selected_mode=sel_mode, selected_house="STARK", mouse=None)
    elif win:
        draw_win_screen(canvas, fonts, c.winner, mouse=None)
    else:
        draw_hud_toggles(canvas, fonts, show_houses=brain, show_log=log, music_enabled=False,
                         is_paused=False, mouse=None)
        if human:
            draw_human_prompt(canvas, fonts, c.active_house(), c.diplomacy, mouse=None)
        else:
            draw_ai_prompt(canvas, fonts, c.turn, mouse=None, battle_status=label)
    path = os.path.join(OUT, name + ".png")
    pygame.image.save(canvas, path)
    print("saved", name)


def tick(c, seconds):
    for _ in range(int(seconds * 30)):
        c.update_animations(1 / 30)


def finish(c):
    for _ in range(600):
        if not c.has_blocking_animation() and not any(c.animations):
            break
        c.update_animations(1 / 30)
    c.animations.clear()


def pixel_of(territory):
    for x in range(MAP_RECT.left, MAP_RECT.right, 6):
        for y in range(MAP_RECT.top, MAP_RECT.bottom, 6):
            if hex_at((x, y)) == (territory.col, territory.row):
                return (x, y)
    return None


# ── 1. Menus ───────────────────────────────────────────────
random.seed(7)
c = main.GameController("AI vs AI")
render(c, "01_menu_ai_vs_ai", menu=True)
render(c, "02_menu_human_vs_ai", menu=True, sel_mode="Human vs AI")
render(c, "03_start_map")

# ── 2. AI vs AI game: battles, ravens, brain, log, win ─────
got = set()
for _ in range(120):
    if c.winner:
        break
    for h in list(c.houses):
        if h.is_eliminated() or c.winner:
            continue
        c.step_house_turn(h)
        kinds = {a.get("type") for a in c.animations}
        if "raven" in kinds and "raven" not in got:
            tick(c, 0.35)
            render(c, "05_raven_proposal", label=f"HOUSE {h.name} SENDS A RAVEN")
            got.add("raven")
        if "march" in kinds:
            march = next(a for a in c.animations if a.get("type") == "march")
            key = "battle_house" if march["defender"] != "NEUTRAL" else "battle_neutral"
            if key not in got:
                tick(c, 2.6)
                render(c, f"06_{key}", label=c._active_battle_label)
                got.add(key)
        if "brain_a" not in got and h.last_trace and c.turn >= 2:
            render(c, "07_ai_brain_trace", brain=True, tab="trace", house=h.name)
            render(c, "08_ai_brain_fuzzy", brain=True, tab="fuzzy", house=h.name)
            got.add("brain_a")
        if any(c.diplomacy.alliances.values()) and "ally" not in got:
            finish(c)
            render(c, "09_alliance_formed", brain=True, tab="fuzzy", house=h.name)
            render(c, "10_raven_log", log=True)
            got.add("ally")
        finish(c)
    if c.turn == 6 and "mid" not in got:
        render(c, "04_midgame_map")
        got.add("mid")
    if c.winner is None:
        c._end_of_round()
if "ally" not in got:
    render(c, "10_raven_log", log=True)
if c.winner:
    render(c, "11_victory", win=True)
print("AI game ended turn", c.turn, "winner", c.winner.name if c.winner else None)

# ── 3. Human vs AI: Minimax hover preview ──────────────────
random.seed(11)
h = main.GameController("Human vs AI", human_house="STARK")
h.start_animated_turn()
for _ in range(40):
    if h.active_house().is_human and not h.is_turn_busy():
        break
    h.update_animations(1 / 30)
    h._pump_animated_turn() if h._round_in_progress else h.start_animated_turn()
me = h.active_house()
scores = h.human_minimax_scores or {}
best = max((k for k in scores if k), key=lambda k: scores[k], default=None)
if best:
    pos = pixel_of(h.map.by_name[best])
    render(h, "12_human_minimax_hover", mouse=pos, minimax=scores, human=True)
    print("hover scores", {k: round(v, 1) for k, v in scores.items()})
render(h, "13_human_turn", human=True)
