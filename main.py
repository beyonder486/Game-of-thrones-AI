"""Main entry point and turn controller for Game of Thrones: AI Conquest."""

from __future__ import annotations

import ctypes
import sys

import pygame

from algorithms.astar import get_path
from algorithms.bfs import get_reachable
from algorithms.dfs import get_expansion_paths
from algorithms.fuzzy_diplomacy import evaluate_diplomacy
from algorithms.mcts import get_diplomacy_decision, get_proposal_response
from algorithms.minimax import get_best_move
from combat import Combat
from constants import ARMY_COST, FPS, HEIGHT, MAX_RECRUITS_PER_TURN, WIDTH
from diplomacy import Diplomacy
from house import House, create_initial_houses
from map import Map, Territory
from renderer import (
    draw,
    draw_ai_prompt,
    draw_game_over_banner,
    draw_human_prompt,
    draw_screen,
    draw_startup_menu,
    draw_win_screen,
    handle_click,
    make_fonts,
)


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
        self.by_name: dict[str, House] = {h.name: h for h in self.houses}
        for h in self.houses:
            h.is_human = self.mode == "Human vs AI" and h.name == self.human_house_name
        self.diplomacy = Diplomacy(self.houses)
        self.turn = 1
        self.active_index = 0
        self.winner: House | None = None

        # Precompute initial Fuzzy Context A scores so the HUD bars start populated.
        for h in self.houses:
            self._update_context_a_fuzzy(h)

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
        sender_strength = _scale_military(proposer.get_military_strength())
        own_weakness = max(0.0, min(100.0, 100.0 - _scale_military(house.get_military_strength())))
        trust = self.diplomacy.get_trust(house, proposer)
        scores = evaluate_diplomacy(sender_strength, own_weakness, trust)
        house.fuzzy_scores = scores
        return scores

    def _execute_attack(self, house: House, target_territory: Territory) -> None:
        if not house.territories or target_territory.owner == house.name:
            return
        # Route troop movement from the nearest owned territory via A*
        best_route: list[Territory] = []
        for origin in house.territories:
            candidate = get_path(self.map, origin, target_territory)
            if not best_route or len(candidate) < len(best_route):
                best_route = candidate
        step_target = best_route[1] if len(best_route) > 1 else target_territory
        if step_target.owner == house.name:
            return

        # Unilateral betrayal if attacking an active ally's territory
        if step_target.owner and self.diplomacy.are_allied(house, step_target.owner):
            ally_name = step_target.owner
            self.diplomacy.break_alliance(house, ally_name)
            self.diplomacy.log_diplomacy(self.turn, house, f"betrayed {ally_name.title()}")

        defender = self.by_name.get(step_target.owner) if step_target.owner else None
        result = Combat.resolve_combat(house, defender, step_target, self.map)
        outcome = "captured" if result["territory_transferred"] else "repelled at"
        target_label = step_target.name.title().replace("'S", "'s")
        self.diplomacy.log_event(self.turn, house, "Minimax/A*", f"{outcome} {target_label}")

        # If a third house was just eliminated, dissolve any orphaned alliance cleanly
        if defender is not None and defender.is_eliminated() and defender.allied_with:
            self.diplomacy.dissolve_alliance(defender, defender.allied_with)

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
                _reachable = get_reachable(self.map, capital, n_steps=3)
                _expansion = get_expansion_paths(self.map, capital, depth_limit=3)

            # 2. Fuzzy Logic — evaluate diplomatic landscape (Context A)
            fuzzy_scores = self._update_context_a_fuzzy(house)

            # 3. MCTS — decide: propose_alliance / betray / solo
            decision, target_house = get_diplomacy_decision(
                house, self.houses, self.map, fuzzy_scores, self.diplomacy
            )

            # 4. If propose: queue proposal in target's inbox; if betray: break alliance
            if decision == "propose_alliance" and target_house is not None:
                self.diplomacy.queue_proposal(house, target_house, self.turn)
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
            house.collect_income()
            # 9. recruit_armies() based on available gold (capped per turn to prevent instant snowball)
            recruits = min(MAX_RECRUITS_PER_TURN, max(0, (house.gold - 15) // ARMY_COST))
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
        """Advance one full turn across all non-eliminated houses."""
        if self.winner is not None:
            return
        for house in self.houses:
            if not house.is_eliminated():
                self.step_house_turn(house)
                if self.winner is not None:
                    return
        self._end_of_round()

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
                self._update_context_a_fuzzy(house)
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
            if proposer is not None:
                self.diplomacy.resolve_proposal(proposer, house, accepted=(action == "accept"), turn=self.turn)
            else:
                house.clear_inbox()
            return False

        # One action per turn for the human house
        if action == "attack" and target_territory is not None:
            if target_territory.owner == house.name:
                return False
            self._execute_attack(house, target_territory)
        elif action.startswith("ally_"):
            partner_name = action.split("_", 1)[1].upper()
            partner = self.by_name.get(partner_name)
            if partner is not None and not partner.is_eliminated():
                self.diplomacy.queue_proposal(house, partner, self.turn)
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

        self.winner = self.check_winner()
        if self.winner is not None:
            return True
        self.active_index += 1
        self.advance_until_human_or_end()
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
    in_menu = True
    show_win_modal = True
    controller = GameController(mode=selected_mode, human_house=selected_house)
    menu_buttons: dict[str, pygame.Rect] = {}
    human_buttons: dict[str, pygame.Rect] = {}
    ai_buttons: dict[str, pygame.Rect] = {}
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
                screen = pygame.display.set_mode(event.size, pygame.RESIZABLE)
            elif (
                event.type == pygame.KEYDOWN
                and event.key in (pygame.K_SPACE, pygame.K_RETURN, pygame.K_RIGHT)
                and not in_menu
            ):
                if controller.winner is not None and show_win_modal:
                    show_win_modal = False
                elif controller.winner is None and controller.mode == "AI vs AI":
                    controller.advance_turn()
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and mouse is not None:
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
                        in_menu = False
                        show_win_modal = True
                        if controller.mode == "Human vs AI":
                            controller.advance_until_human_or_end()
                elif controller.winner is not None:
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
                elif controller.mode == "AI vs AI":
                    if "next_turn" in ai_buttons and ai_buttons["next_turn"].collidepoint(mouse):
                        controller.advance_turn()
                elif controller.mode == "Human vs AI" and controller.active_house().is_human:
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

        draw(
            canvas,
            game_map=controller.map,
            houses=controller.houses,
            diplomacy=controller.diplomacy,
            turn_log=controller.diplomacy.event_log,
            mode=controller.mode,
            fonts=fonts,
            mouse=None if (in_menu or (controller.winner is not None and show_win_modal)) else mouse,
            turn=controller.turn,
        )
        human_buttons = {}
        ai_buttons = {}
        game_over_buttons = {}
        if not in_menu and controller.winner is None:
            if controller.mode == "Human vs AI" and controller.active_house().is_human:
                human_buttons = draw_human_prompt(
                    canvas, fonts, controller.active_house(), controller.diplomacy, mouse=mouse
                )
            elif controller.mode == "AI vs AI":
                ai_buttons = draw_ai_prompt(canvas, fonts, controller.turn, mouse=mouse)
        if in_menu:
            menu_buttons = draw_startup_menu(
                canvas, fonts, selected_mode=selected_mode, selected_house=selected_house, mouse=mouse
            )
        elif controller.winner is not None:
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
        clock.tick(FPS)

    pygame.quit()


if __name__ == "__main__":
    main()
