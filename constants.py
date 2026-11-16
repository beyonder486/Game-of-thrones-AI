"""Shared constants and visual palette for Game of Thrones: AI Conquest."""

from __future__ import annotations

import math

# Window & Grid Dimensions
WIDTH, HEIGHT = 1860, 900
FPS = 30
MAP_RECT_BOUNDS = (22, 101, 930, 756)
HEX_R = min(
    (MAP_RECT_BOUNDS[2] - 36) / (1.5 * 14 + 2),
    (MAP_RECT_BOUNDS[3] - 112) / (math.sqrt(3) * 8.5),
)
HEX_H = math.sqrt(3) * HEX_R
X_STEP = HEX_R * 1.5
Y_STEP = HEX_H

# Color Palette
INK = (20, 27, 33)
INK_GLASS = (24, 34, 40)
IVORY = (246, 235, 210)
MUTED = (195, 199, 188)
GOLD = (236, 185, 94)
STARK = (73, 167, 191)
LANNISTER = (232, 131, 53)
TARGARYEN = (154, 105, 220)
SEA = (29, 100, 121)

HOUSE_NAMES = ("STARK", "LANNISTER", "TARGARYEN")

HOUSE_COLORS: dict[str, tuple[int, int, int]] = {
    "STARK": STARK,
    "LANNISTER": LANNISTER,
    "TARGARYEN": TARGARYEN,
    # Case-insensitive aliases for convenience
    "Stark": STARK,
    "Lannister": LANNISTER,
    "Targaryen": TARGARYEN,
}

# AI & Economy Constants
MINIMAX_DEPTH = 3
MCTS_ITER = 500
MCTS_ROLLOUT_DEPTH = 10
UCT_C = 1.414
BASE_INCOME = 10
ARMY_COST = 5
MIN_ATTACK_ARMIES = 5
MAX_RECRUITS_PER_TURN = 3
BETRAYAL_PENALTY = -30
ALLY_BONUS = 5

# Starting values per house
STARTING_VALUES: dict[str, dict[str, int]] = {
    "STARK": {"gold": 50, "armies": 10},
    "LANNISTER": {"gold": 70, "armies": 15},
    "TARGARYEN": {"gold": 40, "armies": 12},
}
STARTING_TERRITORIES: dict[str, str] = {
    "STARK": "WINTERFELL",
    "LANNISTER": "CASTERLY ROCK",
    "TARGARYEN": "DRAGONSTONE",
}
HOUSE_MOTTOS: dict[str, str] = {
    "STARK": "WINTER IS COMING",
    "LANNISTER": "HEAR ME ROAR",
    "TARGARYEN": "FIRE AND BLOOD",
}

# Iron Throne
IRON_THRONE = "KING'S LANDING"
THRONE_BONUS = 500

# Pacing (AI-vs-AI auto-advance: one full turn per second)
AI_TURN_DELAY_MS = 1000

# MCTS Reward Weights
REWARD_THRONE = 1000
REWARD_TERRITORY = 0.5
REWARD_MILITARY = 0.3
REWARD_RESOURCE = 0.2
REWARD_ALLIANCE_RISK = -0.4
