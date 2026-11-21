"""Main entry point and turn controller for Game of Thrones: AI Conquest."""

from __future__ import annotations

import ctypes
import os
import random
import sys

import pygame

from algorithms.astar import get_path
from algorithms.bfs import get_reachable
from algorithms.dfs import get_expansion_paths
from algorithms.fuzzy_diplomacy import evaluate_diplomacy
from algorithms.mcts import get_diplomacy_decision, get_proposal_response
from algorithms.minimax import get_best_move, get_move_scores
from combat import Combat
from constants import ARMY_COST, FPS, HEIGHT, MAX_RECRUITS_PER_TURN, WIDTH
from diplomacy import Diplomacy
from house import House, create_initial_houses
from map import Map, Territory
from renderer import (
    draw,
    draw_ai_prompt,
    draw_game_over_banner,
    draw_hud_toggles,
    draw_human_prompt,
    draw_screen,
    draw_startup_menu,
    draw_win_screen,
    handle_click,
    make_fonts,
)


SWORD_FIGHT_SOUND_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "assets",
    "sounds",
    "dragon-studio-sword-fight-393849.mp3",
)
FIRE_BREATH_SOUND_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "assets",
    "sounds",
    "floraphonic-fireball-whoosh-5-179129.mp3",
)
BGM_SOUND_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "assets",
    "sounds",
    "Lament of the War - MP3 Preview.mp3",
)
BGM_NORMAL_VOL: float = 0.42
BGM_DUCKED_VOL: float = 0.12
_SWORD_FIGHT_SFX: pygame.mixer.Sound | None = None
_FIRE_BREATH_SFX: pygame.mixer.Sound | None = None
_SWORD_FIGHT_CHANNEL: pygame.mixer.Channel | None = None
_FIRE_BREATH_CHANNEL: pygame.mixer.Channel | None = None
_BGM_STARTED: bool = False
_BGM_CURRENT_VOL: float = 0.0
_SFX_LOADED: bool = False
_BGM_ENABLED: bool = False  # Background music off by default; battle SFX always active


def _start_bgm() -> bool:
    """Start looping background music when enabled."""
    global _BGM_STARTED, _BGM_CURRENT_VOL
    if _BGM_STARTED or not pygame.mixer.get_init() or not os.path.isfile(BGM_SOUND_PATH):
        return _BGM_STARTED
    try:
        pygame.mixer.music.load(BGM_SOUND_PATH)
        _BGM_CURRENT_VOL = BGM_DUCKED_VOL if _is_battle_sfx_playing() else BGM_NORMAL_VOL
        pygame.mixer.music.set_volume(_BGM_CURRENT_VOL if _BGM_ENABLED else 0.0)
        pygame.mixer.music.play(loops=-1, fade_ms=700)
        _BGM_STARTED = True
    except pygame.error:
        _BGM_STARTED = False
    return _BGM_STARTED


def _toggle_bgm() -> bool:
    """Toggle background music ON/OFF without ever disabling sword or dragon battle SFX."""
    global _BGM_ENABLED, _BGM_CURRENT_VOL
    _BGM_ENABLED = not _BGM_ENABLED
    if not pygame.mixer.get_init():
        return _BGM_ENABLED
    if _BGM_ENABLED:
        if not _BGM_STARTED:
            _start_bgm()
        else:
            try:
                pygame.mixer.music.unpause()
            except pygame.error:
                pass
    else:
        _BGM_CURRENT_VOL = 0.0
        if _BGM_STARTED:
            try:
                pygame.mixer.music.set_volume(0.0)
                pygame.mixer.music.pause()
            except pygame.error:
                pass
    return _BGM_ENABLED


def _is_battle_sfx_playing() -> bool:
    for ch in (_SWORD_FIGHT_CHANNEL, _FIRE_BREATH_CHANNEL):
        if ch is not None:
            try:
                if ch.get_busy():
                    return True
            except pygame.error:
                pass
    return False


def _update_bgm_ducking(dt: float) -> None:
    """Smoothly dim background music while sword-fight or dragon-breath SFX play."""
    global _BGM_CURRENT_VOL
    if not _BGM_STARTED or not _BGM_ENABLED or not pygame.mixer.get_init():
        return
    if _is_battle_sfx_playing():
        target = BGM_DUCKED_VOL
        rate = 6.5  # fast duck down when battle SFX ignite
    else:
        target = BGM_NORMAL_VOL
        rate = 1.6  # smooth swell back up once clash ends
    if abs(_BGM_CURRENT_VOL - target) > 0.002:
        step = min(1.0, max(0.0, dt) * rate)
        _BGM_CURRENT_VOL += (target - _BGM_CURRENT_VOL) * step
        try:
            pygame.mixer.music.set_volume(max(0.0, min(1.0, _BGM_CURRENT_VOL)))
        except pygame.error:
            pass


def _load_battle_sfx() -> tuple[pygame.mixer.Sound | None, pygame.mixer.Sound | None]:
    global _SWORD_FIGHT_SFX, _FIRE_BREATH_SFX, _SFX_LOADED
    if _SFX_LOADED:
        return _SWORD_FIGHT_SFX, _FIRE_BREATH_SFX
    _SFX_LOADED = True
    if not pygame.mixer.get_init():
        return None, None
    for path, vol, target in (
        (SWORD_FIGHT_SOUND_PATH, 0.58, "sword"),
        (FIRE_BREATH_SOUND_PATH, 0.72, "fire"),
    ):
        if not os.path.isfile(path):
            continue
        try:
            sfx = pygame.mixer.Sound(path)
            sfx.set_volume(vol)
            if target == "sword":
                _SWORD_FIGHT_SFX = sfx
            else:
                _FIRE_BREATH_SFX = sfx
        except pygame.error:
            pass
    return _SWORD_FIGHT_SFX, _FIRE_BREATH_SFX


def _play_battle_sfx(maxtime_ms: int = 1850) -> None:
    global _SWORD_FIGHT_CHANNEL
    if not pygame.mixer.get_init():
        return
    sword_sfx, _ = _load_battle_sfx()
    if sword_sfx is None:
        return
    try:
        if _SWORD_FIGHT_CHANNEL is not None:
            _SWORD_FIGHT_CHANNEL.stop()
        _SWORD_FIGHT_CHANNEL = sword_sfx.play(maxtime=maxtime_ms, fade_ms=80)
    except pygame.error:
        pass


def _play_fire_breath_sfx(maxtime_ms: int = 1750) -> None:
    global _FIRE_BREATH_CHANNEL
    if not pygame.mixer.get_init():
        return
    _, fire_sfx = _load_battle_sfx()
    if fire_sfx is None:
        return
    try:
        if _FIRE_BREATH_CHANNEL is not None:
            _FIRE_BREATH_CHANNEL.stop()
        _FIRE_BREATH_CHANNEL = fire_sfx.play(maxtime=maxtime_ms, fade_ms=40)
    except pygame.error:
        pass


def _fadeout_battle_sfx(ms: int = 240) -> None:
    global _SWORD_FIGHT_CHANNEL, _FIRE_BREATH_CHANNEL
    for ch in (_SWORD_FIGHT_CHANNEL, _FIRE_BREATH_CHANNEL):
        if ch is not None:
            try:
                ch.fadeout(ms)
            except pygame.error:
                pass
    _SWORD_FIGHT_CHANNEL = None
    _FIRE_BREATH_CHANNEL = None


def _scale_military(strength: float) -> float:
    return max(0.0, min(100.0, strength * 2.5))


class GameController:
    """Coordinates game state, exact 11-step turn structure, and human/AI actions."""

    def __init__(self, mode: str = "AI vs AI", human_house: str = "STARK") -> None:
        self.mode = mode
        self.human_house_name = human_house.upper()
        self.reset(mode=mode, human_house=human_house)

    def reset(self, mode: str | None = None, human_house: str | None = None) -> None:
        if mode is not None:
            self.mode = mode
        if human_house is not None:
            self.human_house_name = human_house.upper()

        self.map = Map()
        self.houses = create_initial_houses(self.map)
        random.shuffle(self.houses)
        self.by_name: dict[str, House] = {h.name: h for h in self.houses}
        for h in self.houses:
            h.is_human = self.mode == "Human vs AI" and h.name == self.human_house_name
        self.diplomacy = Diplomacy(self.houses)
        self.turn = 1
        self.active_index = 0
        self.winner: House | None = None
        self.animations: list[dict[str, object]] = []
        self._round_in_progress: bool = False
        self._round_house_idx: int = 0
        self._active_battle_label: str | None = None
        self._human_proposed_this_turn: bool = False
        self.human_minimax_scores: dict[str | None, float] = {}

        # Precompute initial Fuzzy Context A scores so the HUD bars start populated.
        for h in self.houses:
            self._update_context_a_fuzzy(h)

    def _refresh_human_minimax_scores(self, house: House) -> None:
        if self.mode == "Human vs AI" and house.is_human and not house.is_eliminated() and self.winner is None:
            self.human_minimax_scores = get_move_scores(house, self.houses, self.map, self.diplomacy)
        else:
            self.human_minimax_scores = {}

    def _update_context_a_fuzzy(self, house: House) -> dict[str, float]:
        enemies = [h for h in self.houses if h.name != house.name and not h.is_eliminated()]
        enemy_strength = _scale_military(sum(e.get_military_strength() for e in enemies))
        own_weakness = max(0.0, min(100.0, 100.0 - _scale_military(house.get_military_strength())))
        avg_trust = (
            sum(self.diplomacy.get_trust(house, e) for e in enemies) / len(enemies)
            if enemies
            else 50.0
        )
        scores = evaluate_diplomacy(enemy_strength, own_weakness, avg_trust)
        house.fuzzy_scores = scores
        return scores

    def _update_context_b_fuzzy(self, house: House, proposer: House) -> dict[str, float]:
        # Evaluate alliance against the 3rd (common enemy) house's threat when alive
        third = next(
            (h for h in self.houses if h.name not in (house.name, proposer.name) and not h.is_eliminated()),
            None,
        )
        threat_source = third if third is not None else proposer
        common_threat = _scale_military(threat_source.get_military_strength())
        own_weakness = max(0.0, min(100.0, 100.0 - _scale_military(house.get_military_strength())))
        trust = self.diplomacy.get_trust(house, proposer)
        scores = evaluate_diplomacy(common_threat, own_weakness, trust)
        house.fuzzy_scores = scores
        return scores

    def _execute_attack(self, house: House, target_territory: Territory) -> None:
        if not house.territories or target_territory.owner == house.name:
            return
        owned_set = set(house.territories)
        # If target_territory is already directly adjacent to an owned territory, strike it directly;
        # otherwise route from the nearest owned territory via A* and attack the first border hop.
        origin_t: Territory | None = None
        if any(target_territory in t.neighbors for t in owned_set):
            step_target = target_territory
        else:
            best_route: list[Territory] = []
            for origin in house.territories:
                candidate = get_path(self.map, origin, target_territory)
                # Trim any leading owned territories so step_target is the first border crossing
                while len(candidate) > 1 and candidate[1] in owned_set:
                    candidate = candidate[1:]
                if len(candidate) > 1 and (not best_route or len(candidate) < len(best_route)):
                    best_route = candidate
            if len(best_route) < 2:
                return
            origin_t = best_route[0]
            step_target = best_route[1]
        if step_target.owner == house.name or not any(step_target in t.neighbors for t in owned_set):
            return
        if origin_t is None:
            origin_t = next((t for t in house.territories if step_target in t.neighbors), house.territories[0])

        # Unilateral betrayal if attacking an active ally's territory
        if step_target.owner and self.diplomacy.are_allied(house, step_target.owner):
            ally_name = step_target.owner
            self.diplomacy.break_alliance(house, ally_name)
            self.diplomacy.log_diplomacy(self.turn, house, f"betrayed {ally_name.title()}")

        defender = self.by_name.get(step_target.owner) if step_target.owner else None
        defender_name = defender.name if defender is not None else "NEUTRAL"
        result = Combat.resolve_combat(house, defender, step_target, self.map)
        outcome = "captured" if result["territory_transferred"] else "repelled at"
        target_label = step_target.name.title().replace("'S", "'s")
        self.diplomacy.log_event(self.turn, house, "Minimax/A*", f"{outcome} {target_label}")
        self._active_battle_label = f"BATTLE FOR {step_target.name} · HOUSE {house.name} VS {defender_name}"
        self.animations.append({
            "type": "march",
            "house": house.name,
            "defender": defender_name,
            "from_coord": (origin_t.col, origin_t.row),
            "to_coord": (step_target.col, step_target.row),
            "captured": bool(result["territory_transferred"]),
            "target_name": step_target.name,
            "elapsed": 0.0,
            "duration": 3.2,
        })

        # If a house was just eliminated, dissolve its pact and purge all pending proposals to/from it
        if defender is not None and defender.is_eliminated():
            self.diplomacy.purge_eliminated(defender)

    def step_house_turn(self, house: House) -> None:
        """Execute the exact turn pipeline for a single AI house."""
        if house.is_eliminated() or self.winner is not None:
            return

        pending = house.get_pending_proposal()
        betray_target: House | None = None

        if pending is not None:
            # IF house.inbox has a pending proposal:
            proposer_name = str(pending.get("from", "")).upper()
            proposer = self.by_name.get(proposer_name)
            if proposer is not None and not proposer.is_eliminated():
                # 1. Fuzzy Logic — evaluate proposal sender's state (Context B)
                fuzzy_scores = self._update_context_b_fuzzy(house, proposer)
                # 2. MCTS — simulate accept vs reject outcome
                response = get_proposal_response(
                    house, proposer, self.houses, self.map, fuzzy_scores, self.diplomacy
                )
                # 3. Send YES/NO — update diplomacy state
                self.diplomacy.resolve_proposal(
                    proposer, house, accepted=(response == "accept"), turn=self.turn
                )
            else:
                house.clear_inbox()

            # 4. Minimax — select combat/expansion move
            target_territory = get_best_move(house, self.houses, self.map, self.diplomacy)
            # 5. A* & 6. Combat — route troop movement and resolve attack
            if target_territory is not None:
                self._execute_attack(house, target_territory)
            else:
                self.diplomacy.log_event(self.turn, house, "Minimax", "held fortifications")
        else:
            # ELSE (no pending proposal):
            # 1. BFS/DFS — update reachability map and deep expansion scouting
            if house.territories:
                capital = house.territories[0]
                house.reachable_holds = get_reachable(self.map, capital, n_steps=3)
                house.expansion_paths = get_expansion_paths(self.map, capital, depth_limit=3)

            # 2. Fuzzy Logic — evaluate diplomatic landscape (Context A)
            fuzzy_scores = self._update_context_a_fuzzy(house)

            # 3. MCTS — decide: propose_alliance / betray / solo
            decision, target_house = get_diplomacy_decision(
                house, self.houses, self.map, fuzzy_scores, self.diplomacy
            )

            # 4. If propose: queue proposal in target's inbox; if betray: break alliance
            if decision == "propose_alliance" and target_house is not None:
                self.diplomacy.queue_proposal(house, target_house, self.turn)
                if house.territories and target_house.territories:
                    self.animations.append({
                        "type": "raven",
                        "house": house.name,
                        "from_coord": (house.territories[0].col, house.territories[0].row),
                        "to_coord": (target_house.territories[0].col, target_house.territories[0].row),
                        "elapsed": 0.0,
                        "duration": 0.75,
                    })
            elif decision == "betray" and target_house is not None:
                betray_target = target_house
                self.diplomacy.break_alliance(house, target_house)
                self.diplomacy.log_diplomacy(self.turn, house, f"betrayed {target_house.name.title()}")

            # 5. Minimax — select combat/expansion move
            target_territory = get_best_move(
                house, self.houses, self.map, self.diplomacy, betray_target=betray_target
            )
            # 6. A* & 7. Combat — route troop movement and resolve attack
            if target_territory is not None:
                self._execute_attack(house, target_territory)
            elif decision != "propose_alliance":
                self.diplomacy.log_event(self.turn, house, "Minimax", "held fortifications")

    def _end_of_round(self) -> None:
        """Steps 8–11 after every house acts."""
        for house in self.houses:
            if house.is_eliminated():
                continue
            # 8. collect_income() for all houses
            income = house.collect_income()
            if income > 0 and house.territories:
                self.animations.append({
                    "type": "gold",
                    "house": house.name,
                    "coord": (house.territories[0].col, house.territories[0].row),
                    "amount": income,
                    "elapsed": 0.0,
                    "duration": 1.05,
                })
            # 9. recruit_armies() based on available gold (capped per turn & by realm supply limit)
            supply_cap = 12 + 6 * len(house.territories)
            recruits = min(
                MAX_RECRUITS_PER_TURN,
                max(0, (house.gold - 15) // ARMY_COST),
                max(0, supply_cap - house.armies),
            )
            if recruits > 0:
                house.recruit_armies(recruits)
            # 10. Update trust history for surviving alliances
            if house.allied_with and self.diplomacy.are_allied(house, house.allied_with):
                self.diplomacy.update_trust(house, house.allied_with, "keep")
            self._update_context_a_fuzzy(house)

        # 11. Check win condition (evaluated after all houses have acted)
        self.winner = self.check_winner()
        if self.winner is None:
            self.turn += 1

    def advance_turn(self) -> None:
        """Advance one full turn synchronously across all non-eliminated houses."""
        if self.winner is not None:
            return
        for house in self.houses:
            if not house.is_eliminated():
                self.step_house_turn(house)
                if self.winner is not None:
                    return
        self._end_of_round()

    # ── Animated sequential battle-gated turn orchestration ─
    def has_blocking_animation(self) -> bool:
        """True while a battle/march animation is still playing out on screen."""
        return any(a.get("type") == "march" for a in self.animations)

    def is_turn_busy(self) -> bool:
        """True while a round or battle animation is actively in progress."""
        return self._round_in_progress or self.has_blocking_animation()

    def start_animated_turn(self) -> None:
        """Begin a turn where each house's war plays out sequentially until finished."""
        if self.winner is not None or self.is_turn_busy():
            return
        self._round_in_progress = True
        self._round_house_idx = 0
        self._pump_animated_turn()

    def _pump_animated_turn(self) -> None:
        """Advance to the next house only once the previous battle animation has finished."""
        while self._round_in_progress and not self.has_blocking_animation():
            if self.winner is not None:
                self._round_in_progress = False
                self._active_battle_label = None
                return
            if self._round_house_idx >= len(self.houses):
                self._end_of_round()
                self._round_house_idx = 0
                if self.mode == "AI vs AI" or self.winner is not None:
                    self._round_in_progress = False
                    self._active_battle_label = None
                    return
                continue
            house = self.houses[self._round_house_idx]
            self._round_house_idx += 1
            if house.is_eliminated():
                continue
            if self.mode == "Human vs AI" and house.is_human:
                self.active_index = self._round_house_idx - 1
                self._human_proposed_this_turn = False
                pending = house.get_pending_proposal()
                proposer = self.by_name.get(str(pending.get("from", "")).upper()) if pending else None
                if proposer is not None and not proposer.is_eliminated():
                    self._update_context_b_fuzzy(house, proposer)
                else:
                    self._update_context_a_fuzzy(house)
                self._refresh_human_minimax_scores(house)
                self._round_in_progress = False
                self._active_battle_label = None
                return
            self.step_house_turn(house)
            if self.has_blocking_animation():
                return

    def update_animations(self, dt: float) -> None:
        """Advance active animations and proceed to the next move only when battles finish."""
        for anim in self.animations:
            anim["elapsed"] = float(anim.get("elapsed", 0.0)) + dt
            if anim.get("type") == "march":
                dur = max(0.05, float(anim.get("duration", 3.2)))
                prog = float(anim["elapsed"]) / dur
                if prog >= 0.30 and not anim.get("sfx_started"):
                    anim["sfx_started"] = True
                    _play_battle_sfx(maxtime_ms=1900)
                if prog >= 0.34 and not anim.get("fire_sfx_started"):
                    anim["fire_sfx_started"] = True
                    _play_fire_breath_sfx(maxtime_ms=1750)
                elif prog >= 0.80 and not anim.get("sfx_faded"):
                    anim["sfx_faded"] = True
                    _fadeout_battle_sfx(240)
        self.animations = [
            a for a in self.animations if float(a.get("elapsed", 0.0)) < float(a.get("duration", 1.0))
        ]
        if not self.has_blocking_animation():
            self._active_battle_label = None
            if self._round_in_progress:
                self._pump_animated_turn()

    # ── Human-vs-AI turn orchestration ─────────────────────
    def active_house(self) -> House:
        return self.houses[self.active_index]

    def advance_until_human_or_end(self) -> None:
        """Run AI houses in order until a human house needs input or the round completes."""
        while self.winner is None:
            if self.active_index >= len(self.houses):
                self._end_of_round()
                self.active_index = 0
                if self.mode == "AI vs AI":
                    break
                continue
            house = self.houses[self.active_index]
            if house.is_eliminated():
                self.active_index += 1
                continue
            if house.is_human:
                self._human_proposed_this_turn = False
                pending = house.get_pending_proposal()
                proposer = self.by_name.get(str(pending.get("from", "")).upper()) if pending else None
                if proposer is not None and not proposer.is_eliminated():
                    self._update_context_b_fuzzy(house, proposer)
                else:
                    self._update_context_a_fuzzy(house)
                self._refresh_human_minimax_scores(house)
                break
            self.step_house_turn(house)
            if self.winner is not None:
                break
            self.active_index += 1

    def handle_human_action(self, action: str, target_territory: Territory | None = None) -> bool:
        """Process a human player's single turn action or inbox response."""
        house = self.active_house()
        if not house.is_human or self.winner is not None:
            return False

        pending = house.get_pending_proposal()
        if pending is not None and action in ("accept", "reject"):
            proposer = self.by_name.get(str(pending.get("from", "")).upper())
            if proposer is not None and not proposer.is_eliminated():
                self.diplomacy.resolve_proposal(proposer, house, accepted=(action == "accept"), turn=self.turn)
            else:
                house.clear_inbox()
            self._refresh_human_minimax_scores(house)
            return False

        # One action per turn for the human house
        if action == "attack" and target_territory is not None:
            if target_territory.owner == house.name:
                return False
            self._execute_attack(house, target_territory)
        elif action.startswith("ally_"):
            if self._human_proposed_this_turn:
                return False
            surviving = sum(1 for h in self.houses if not h.is_eliminated())
            partner_name = action.split("_", 1)[1].upper()
            partner = self.by_name.get(partner_name)
            if surviving >= 3 and partner is not None and not partner.is_eliminated():
                self.diplomacy.queue_proposal(house, partner, self.turn)
                self._human_proposed_this_turn = True
                if house.territories and partner.territories:
                    self.animations.append({
                        "type": "raven",
                        "house": house.name,
                        "from_coord": (house.territories[0].col, house.territories[0].row),
                        "to_coord": (partner.territories[0].col, partner.territories[0].row),
                        "elapsed": 0.0,
                        "duration": 0.75,
                    })
            # Per spec, proposing house still makes its military move this turn.
            return False
        elif action == "betray" and house.allied_with:
            ally = self.by_name.get(house.allied_with)
            if ally is not None:
                self.diplomacy.break_alliance(house, ally)
                self.diplomacy.log_diplomacy(self.turn, house, f"betrayed {ally.name.title()}")
                strike = get_best_move(house, self.houses, self.map, self.diplomacy, betray_target=ally)
                if strike is not None:
                    self._execute_attack(house, strike)
        elif action == "hold":
            self.diplomacy.log_event(self.turn, house, "Player", "held fortifications")
        else:
            return False

        self.human_minimax_scores = {}
        self.winner = self.check_winner()
        if self.winner is not None:
            return True
        self._round_in_progress = True
        self._round_house_idx = self.active_index + 1
        self._pump_animated_turn()
        return True

    def check_winner(self) -> House | None:
        """Return the winning house if the Iron Throne is captured or one house survives."""
        if self.map.iron_throne.owner is not None:
            holder = self.by_name.get(self.map.iron_throne.owner)
            if holder is not None:
                return holder
        surviving = [h for h in self.houses if not h.is_eliminated()]
        if len(surviving) == 1:
            return surviving[0]
        return None


def _enable_windows_dpi_awareness() -> None:
    """Prevent Windows DWM blurry bitmap stretching on high-DPI displays."""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def main() -> None:
    _enable_windows_dpi_awareness()
    pygame.init()
    try:
        if not pygame.mixer.get_init():
            pygame.mixer.init()
        _load_battle_sfx()
    except pygame.error:
        pass
    pygame.display.set_caption("Game of Thrones: AI Conquest — Realm Overview")
    display = pygame.display.Info()
    desktop_width = display.current_w or WIDTH
    desktop_height = display.current_h or HEIGHT
    if desktop_width >= WIDTH + 16 and desktop_height >= HEIGHT + 64:
        window_size = (WIDTH, HEIGHT)
    else:
        fit_scale = min((desktop_width - 24) / WIDTH, (desktop_height - 72) / HEIGHT)
        fit_scale = max(0.45, fit_scale)
        window_size = (round(WIDTH * fit_scale), round(HEIGHT * fit_scale))
    screen = pygame.display.set_mode(window_size, pygame.RESIZABLE)
    canvas = pygame.Surface((WIDTH, HEIGHT))
    clock = pygame.time.Clock()
    fonts = make_fonts()

    selected_mode = "AI vs AI"
    selected_house = "STARK"
    selected_fuzzy_house = selected_house
    in_menu = True
    show_win_modal = True
    show_houses = False
    show_log = False
    is_fullscreen = False
    controller = GameController(mode=selected_mode, human_house=selected_house)
    menu_buttons: dict[str, pygame.Rect] = {}
    human_buttons: dict[str, pygame.Rect] = {}
    ai_buttons: dict[str, pygame.Rect] = {}
    hud_buttons: dict[str, pygame.Rect] = {}
    sidebar_buttons: dict[str, pygame.Rect] = {}
    win_buttons: dict[str, pygame.Rect] = {}
    game_over_buttons: dict[str, pygame.Rect] = {}
    running = True

    while running:
        scale = min(screen.get_width() / WIDTH, screen.get_height() / HEIGHT)
        scaled_size = (round(WIDTH * scale), round(HEIGHT * scale))
        offset = (
            (screen.get_width() - scaled_size[0]) // 2,
            (screen.get_height() - scaled_size[1]) // 2,
        )
        mx, my = pygame.mouse.get_pos()
        mouse = (
            ((mx - offset[0]) / scale, (my - offset[1]) / scale)
            if pygame.mouse.get_focused()
            else None
        )

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                if controller.winner is not None and show_win_modal:
                    show_win_modal = False
                elif in_menu:
                    running = False
                else:
                    in_menu = True
            elif event.type == pygame.VIDEORESIZE:
                if not is_fullscreen:
                    screen = pygame.display.set_mode(event.size, pygame.RESIZABLE)
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_F11:
                is_fullscreen = not is_fullscreen
                if is_fullscreen:
                    screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
                else:
                    screen = pygame.display.set_mode(window_size, pygame.RESIZABLE)
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_h and not in_menu:
                show_houses = not show_houses
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_l and not in_menu:
                show_log = not show_log
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_m:
                _toggle_bgm()
            elif (
                event.type == pygame.KEYDOWN
                and event.key in (pygame.K_SPACE, pygame.K_RETURN, pygame.K_RIGHT)
                and not in_menu
            ):
                if controller.winner is not None and show_win_modal and not controller.has_blocking_animation():
                    show_win_modal = False
                elif controller.winner is None and controller.mode == "AI vs AI" and not controller.is_turn_busy():
                    controller.start_animated_turn()
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and mouse is not None:
                if not in_menu and not (controller.winner is not None and show_win_modal):
                    if "toggle_music" in hud_buttons and hud_buttons["toggle_music"].collidepoint(mouse):
                        _toggle_bgm()
                        continue
                    if "toggle_houses" in hud_buttons and hud_buttons["toggle_houses"].collidepoint(mouse):
                        show_houses = not show_houses
                        continue
                    if "toggle_log" in hud_buttons and hud_buttons["toggle_log"].collidepoint(mouse):
                        show_log = not show_log
                        continue
                    tab_clicked = False
                    for h_name in ("STARK", "LANNISTER", "TARGARYEN"):
                        tkey = f"fuzzy_tab_{h_name}"
                        if tkey in sidebar_buttons and sidebar_buttons[tkey].collidepoint(mouse):
                            selected_fuzzy_house = h_name
                            tab_clicked = True
                            break
                    if tab_clicked:
                        continue
                    if (
                        ("drawer_fuzzy" in sidebar_buttons and sidebar_buttons["drawer_fuzzy"].collidepoint(mouse))
                        or ("drawer_log" in sidebar_buttons and sidebar_buttons["drawer_log"].collidepoint(mouse))
                    ):
                        continue
                if in_menu:
                    if "mode_ai" in menu_buttons and menu_buttons["mode_ai"].collidepoint(mouse):
                        selected_mode = "AI vs AI"
                    elif "mode_human" in menu_buttons and menu_buttons["mode_human"].collidepoint(mouse):
                        selected_mode = "Human vs AI"
                    for h_name in ("STARK", "LANNISTER", "TARGARYEN"):
                        key = f"house_{h_name}"
                        if key in menu_buttons and menu_buttons[key].collidepoint(mouse):
                            selected_house = h_name
                    if "start" in menu_buttons and menu_buttons["start"].collidepoint(mouse):
                        controller.reset(mode=selected_mode, human_house=selected_house)
                        selected_fuzzy_house = selected_house
                        in_menu = False
                        show_win_modal = True
                        if controller.mode == "Human vs AI":
                            controller._round_in_progress = True
                            controller._round_house_idx = 0
                            controller._pump_animated_turn()
                elif controller.winner is not None and not controller.has_blocking_animation():
                    if show_win_modal:
                        if ("review_board" in win_buttons and win_buttons["review_board"].collidepoint(mouse)) or (
                            "close" in win_buttons and win_buttons["close"].collidepoint(mouse)
                        ):
                            show_win_modal = False
                        elif "play_again" in win_buttons and win_buttons["play_again"].collidepoint(mouse):
                            in_menu = True
                            show_win_modal = True
                    else:
                        if "view_summary" in game_over_buttons and game_over_buttons["view_summary"].collidepoint(mouse):
                            show_win_modal = True
                        elif "play_again" in game_over_buttons and game_over_buttons["play_again"].collidepoint(mouse):
                            in_menu = True
                            show_win_modal = True
                elif controller.mode == "AI vs AI" and not controller.is_turn_busy():
                    if "next_turn" in ai_buttons and ai_buttons["next_turn"].collidepoint(mouse):
                        controller.start_animated_turn()
                elif controller.mode == "Human vs AI" and not controller.is_turn_busy() and controller.active_house().is_human:
                    handled = False
                    for key, btn in human_buttons.items():
                        if btn.collidepoint(mouse):
                            controller.handle_human_action(key)
                            handled = True
                            break
                    if not handled and controller.active_house().get_pending_proposal() is None:
                        clicked = handle_click(mouse, controller.map, controller.active_house())
                        if clicked is not None:
                            controller.handle_human_action("attack", clicked)

        active_minimax_scores = (
            controller.human_minimax_scores
            if (
                not in_menu
                and controller.mode == "Human vs AI"
                and controller.winner is None
                and not controller.is_turn_busy()
                and controller.active_house().is_human
            )
            else None
        )
        sidebar_buttons = draw(
            canvas,
            game_map=controller.map,
            houses=controller.houses,
            diplomacy=controller.diplomacy,
            turn_log=controller.diplomacy.event_log,
            mode=controller.mode,
            fonts=fonts,
            mouse=None if (in_menu or (controller.winner is not None and show_win_modal)) else mouse,
            turn=controller.turn,
            animations=controller.animations,
            show_houses=show_houses,
            show_log=show_log,
            selected_fuzzy_house=selected_fuzzy_house,
            minimax_scores=active_minimax_scores,
        )
        human_buttons = {}
        ai_buttons = {}
        hud_buttons = {}
        game_over_buttons = {}
        if not in_menu and not (controller.winner is not None and show_win_modal and not controller.has_blocking_animation()):
            hud_buttons = draw_hud_toggles(
                canvas,
                fonts,
                show_houses=show_houses,
                show_log=show_log,
                music_enabled=_BGM_ENABLED,
                mouse=mouse,
            )
        if not in_menu and (controller.winner is None or controller.has_blocking_animation()):
            if controller.is_turn_busy():
                draw_ai_prompt(
                    canvas,
                    fonts,
                    controller.turn,
                    mouse=mouse,
                    battle_status=controller._active_battle_label or "WAR IN PROGRESS · RESOLVING MOVES...",
                )
            elif controller.mode == "Human vs AI" and controller.active_house().is_human:
                human_buttons = draw_human_prompt(
                    canvas, fonts, controller.active_house(), controller.diplomacy, mouse=mouse
                )
            elif controller.mode == "AI vs AI":
                ai_buttons = draw_ai_prompt(canvas, fonts, controller.turn, mouse=mouse)
        if in_menu:
            menu_buttons = draw_startup_menu(
                canvas, fonts, selected_mode=selected_mode, selected_house=selected_house, mouse=mouse
            )
        elif controller.winner is not None and not controller.has_blocking_animation():
            if show_win_modal:
                win_buttons = draw_win_screen(canvas, fonts, controller.winner, mouse=mouse)
            else:
                game_over_buttons = draw_game_over_banner(canvas, fonts, controller.winner, mouse=mouse)

        screen.fill((10, 17, 22))
        if scaled_size == (WIDTH, HEIGHT):
            screen.blit(canvas, offset)
        else:
            screen.blit(pygame.transform.smoothscale(canvas, scaled_size), offset)
        pygame.display.flip()
        dt = clock.tick(FPS) / 1000.0
        controller.update_animations(dt)
        _update_bgm_ducking(dt)

    pygame.quit()


if __name__ == "__main__":
    main()
