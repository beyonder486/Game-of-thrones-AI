"""Build the complete game-mechanics report as a PDF.

Run from the project root:  py presentation/make_game_report.py
Output: presentation/Game_of_Thrones_AI_Conquest_Report.pdf
"""
import os

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Cambria (ships with Windows) has every symbol used below: ⌊ ⌋ Σ √ → ⇔ ≥ ∈ −
pdfmetrics.registerFont(TTFont("Body", "C:/Windows/Fonts/cambria.ttc", subfontIndex=0))
pdfmetrics.registerFont(TTFont("BodyBold", "C:/Windows/Fonts/cambriab.ttf"))
pdfmetrics.registerFont(TTFont("BodyItalic", "C:/Windows/Fonts/cambriai.ttf"))
pdfmetrics.registerFontFamily("Body", normal="Body", bold="BodyBold", italic="BodyItalic", boldItalic="BodyBold")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOTS = os.path.join(ROOT, "presentation", "screenshots")
OUT = os.path.join(ROOT, "presentation", "Game_of_Thrones_AI_Conquest_Report.pdf")

NAVY, GOLD, EMBER, INK, SOFT = (colors.HexColor(c) for c in ("#0E2B42", "#B8892E", "#C2562F", "#1E2329", "#55606B"))
ss = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=ss["Heading1"], fontName="BodyBold", fontSize=18, textColor=NAVY, spaceBefore=6, spaceAfter=8)
H2 = ParagraphStyle("H2", parent=ss["Heading2"], fontName="BodyBold", fontSize=13, textColor=EMBER, spaceBefore=10, spaceAfter=4)
P = ParagraphStyle("P", parent=ss["BodyText"], fontName="Body", fontSize=10, leading=14.5, textColor=INK, spaceAfter=5)
B = ParagraphStyle("B", parent=P, leftIndent=12, bulletIndent=2, spaceAfter=2)
F = ParagraphStyle("F", parent=P, fontName="BodyBold", fontSize=9.5, leading=13, textColor=NAVY, backColor=colors.HexColor("#EEF2F5"),
                   borderPadding=(5, 6, 5, 6), leftIndent=6, rightIndent=6, spaceBefore=4, spaceAfter=8)
CAP = ParagraphStyle("CAP", parent=P, fontSize=8.5, textColor=SOFT, alignment=TA_CENTER, spaceAfter=10)
NOTE = ParagraphStyle("NOTE", parent=P, backColor=colors.HexColor("#FBF4E4"), borderPadding=(5, 6, 5, 6), leftIndent=6, rightIndent=6, spaceBefore=4, spaceAfter=8)
CELL = ParagraphStyle("CELL", parent=P, fontSize=8.8, leading=11.5, spaceAfter=0)
CELLB = ParagraphStyle("CELLB", parent=CELL, fontName="BodyBold", textColor=colors.white)

story = []
def h1(t): story.append(Paragraph(t, H1))
def h2(t): story.append(Paragraph(t, H2))
def p(t): story.append(Paragraph(t, P))
def bl(*items):
    for t in items: story.append(Paragraph(t, B, bulletText="•"))
def f(t): story.append(Paragraph(t, F))
def note(t): story.append(Paragraph(t, NOTE))
def table(rows, widths):
    data = [[Paragraph(str(c), CELLB if i == 0 else CELL) for c in r] for i, r in enumerate(rows)]
    t = Table(data, colWidths=[w * cm for w in widths], repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), NAVY), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F3F5F7")]),
                           ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#C9D1D8")),
                           ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    story.append(t); story.append(Spacer(1, 8))
def img(name, caption, w=16.5):
    path = os.path.join(SHOTS, name)
    if not os.path.exists(path): return
    from PIL import Image as PI
    iw, ih = PI.open(path).size
    story.append(KeepTogether([Image(path, width=w * cm, height=w * cm * ih / iw), Paragraph(caption, CAP)]))

def footer(c, d):
    c.saveState(); c.setFont("Body", 8); c.setFillColor(SOFT)
    c.drawString(2 * cm, 1.2 * cm, "Game of Thrones: AI Conquest — Complete Game Report")
    c.drawRightString(A4[0] - 2 * cm, 1.2 * cm, f"Page {d.page}"); c.restoreState()

# ── Title ───────────────────────────────────────────────
story += [Spacer(1, 3 * cm), Paragraph("Game of Thrones: AI Conquest", ParagraphStyle("T", parent=H1, fontSize=28, alignment=TA_CENTER, leading=34)),
          Paragraph("Complete Game Report: Rules, Mechanics and the Seven AI Algorithms", ParagraphStyle("ST", parent=P, fontSize=13, alignment=TA_CENTER, textColor=EMBER)),
          Spacer(1, 0.6 * cm), Paragraph("KUET · Artificial Intelligence Project · [Team member names]", ParagraphStyle("A", parent=P, alignment=TA_CENTER, textColor=SOFT)),
          Spacer(1, 1 * cm)]
img("03_start_map.jpg", "The opening board: 19 holds on a 21 × 8 hex map, three Great Houses at their capitals.")
story.append(PageBreak())

h1("Contents")
for i, t in enumerate(["The game at a glance", "Map, houses and starting stats", "Turn structure", "Economy and recruitment",
                       "Combat", "Diplomacy, trust and betrayal", "How the AI is organised", "BFS and DFS: scouting",
                       "Greedy search", "A* pathfinding", "Mamdani Fuzzy Logic", "Minimax with alpha-beta pruning",
                       "Monte Carlo Tree Search (MCTS)", "One complete turn, step by step", "Modes, screens and controls", "Glossary"], 1):
    story.append(Paragraph(f"{i}.  {t}", P))
story.append(PageBreak())

# ── 1 ───────────────────────────────────────────────────
h1("1. The game at a glance")
p("Game of Thrones: AI Conquest is a turn-based 2.5D strategy game. Three Great Houses (Stark, Lannister and Targaryen) "
  "compete for the Iron Throne by conquering territory, managing gold and armies, and forming or breaking alliances. "
  "Every decision an AI house makes comes from classic AI algorithms working together.")
table([["Element", "Value"],
       ["Map", "19 named holds on a 21 × 8 hex grid; two holds are neighbours when their coloured regions touch"],
       ["Players", "3 Great Houses; turn order is shuffled at the start of every game"],
       ["Moves", "One military move per turn: attack one hold, betray and strike, or hold"],
       ["Win 1: Iron Throne", "Hold King’s Landing when the round ends"],
       ["Win 2: Elimination", "Be the last house that still owns land"],
       ["Modes", "AI vs AI (watch) and Human vs AI (play one house against two AIs)"]], [4, 12.5])
note("<b>Key rule:</b> the winner is checked only after every house has acted in the round. A house that takes "
     "King’s Landing mid-round can still lose it to a rival acting later in the same round. Allies never share gold or armies.")

# ── 2 ───────────────────────────────────────────────────
h1("2. Map, houses and starting stats")
table([["House", "Capital", "Gold", "Armies", "Income", "Defense"],
       ["Stark", "Winterfell", "60", "14", "+9", "3"], ["Lannister", "Casterly Rock", "65", "14", "+9", "2"],
       ["Targaryen", "Dragonstone", "60", "14", "+8", "4"],
       ["Iron Throne (neutral)", "King’s Landing", "—", "11 garrison", "+15", "3"]], [4, 3.5, 1.8, 2.5, 2, 2])
bl("The other 15 holds start neutral with 2–4 garrison troops and a defense bonus of 1–3.",
   "Every pair of houses starts with trust 50 (out of 100).",
   "King’s Landing’s effective defense is 11 × 3 = <b>33</b>, more than a 1-hold house can ever field (supply cap 14), so the throne is a mid-to-late-game goal.")

# ── 3 ───────────────────────────────────────────────────
h1("3. Turn structure")
p("A round gives every surviving house one turn, in the shuffled order. Each house’s turn follows this pipeline:")
table([["Step", "If an alliance offer is waiting in the inbox", "If the inbox is empty"],
       ["1", "Fuzzy Logic (Context B): rate the offer", "BFS + DFS: scout reachable holds and corridors"],
       ["2", "MCTS: accept or reject", "Fuzzy Logic (Context A): rate own situation"],
       ["3", "Alliance forms, or the offer is cleared", "MCTS: propose an alliance, betray an ally, or stay solo"],
       ["4", "Minimax: pick a hold to attack, or Hold", "Minimax: pick a hold to attack, or Hold"],
       ["5", "A*: route to the target’s first border step", "A*: route to the target’s first border step"],
       ["6", "Combat, then elimination check", "Combat, then elimination check"]], [1.3, 7.6, 7.6])
p("<b>End of round:</b> collect income → recruit troops → +5 trust for each surviving alliance → refresh fuzzy scores → check for a winner → next turn.")

# ── 4 ───────────────────────────────────────────────────
h1("4. Economy and recruitment")
f("Income(h) = 10 + Σ resource_value(t)   for every hold t owned by house h")
f("SupplyCap(h) = 10 + 4 × |holds|")
f("Recruits = min( 3 ,  ⌊(Gold − 15) / 5⌋ ,  SupplyCap − Armies )")
table([["Rule", "Value", "Why"], ["Army cost", "5 gold", "gold pays for troops"], ["Reserve", "15 gold always kept", "a house is never left broke"],
       ["Max recruits", "3 per round", "no sudden giant armies"], ["Supply cap", "10 + 4 per hold", "stops ‘camp on one castle and hoard troops’"]], [4, 4.5, 8])
h2("Worked example")
bl("Stark, round 1: 60 gold + income (10 + 9) = 79 gold. Cap with 1 hold = 14 = current armies → <b>0 recruits</b>. Gold alone cannot grow an army.",
   "After taking one more hold: cap 18 → 3 recruits for 15 gold.",
   "To beat King’s Landing (33) a house needs a cap of at least 34, i.e. <b>6 holds</b>. Land unlocks troops; gold pays for them.")
p("Gold also matters elsewhere: it is worth +0.5 per gold in Minimax’s board score, and the whole treasury of an eliminated house goes to the house that took its last hold.")

# ── 5 ───────────────────────────────────────────────────
h1("5. Combat")
h2("5.1 Defense strength")
f("Neutral hold:   EffectiveDefense = garrison × defense_bonus")
f("Rival house:    EffectiveDefense = armies × (1 + 0.05 × defense_bonus)")
p("Garrisons are small (2–11 troops), so the full bonus makes castles tough. A house defends with its whole army pool (14–40), "
  "so it gets only +5% per level; otherwise wars between houses would never happen. The bonus comes from the hold being attacked.")
h2("5.2 Battle roll")
f("AttackPower = attacker_armies × luck_A        DefensePower = EffectiveDefense × luck_D        luck ∈ [0.80, 1.20]")
p("Each side rolls its own luck. The attacker wins only if AttackPower is strictly greater; a tie goes to the defender.")
h2("5.3 When is a win possible?")
f("Favoured: armies > defense         Guaranteed: 0.8 × armies > 1.2 × defense  ⇔  armies > 1.5 × defense")
table([["Battle", "Effective defense", "Win chance"], ["14 vs neutral 3 (bonus 2)", "6", "100%"], ["14 vs neutral 4 (bonus 3)", "12", "81%"],
       ["22 vs house 20 (bonus 2)", "22", "50%"], ["20 vs house 20 (bonus 3)", "23", "21%"], ["34 vs King’s Landing", "33", "57%"],
       ["40 vs King’s Landing", "33", "87%"], ["50 vs King’s Landing", "33", "100%"]], [7, 4.5, 4])
p("Win chances come from 200,000 simulated rolls each with the game’s own effective_defense(). The AI never attacks King’s Landing with fewer armies than its effective defense.")
h2("5.4 Casualties")
table([["Result", "Attacker loses", "Defender loses"], ["Attacker wins", "⌊0.5 × D⌋", "⌊0.8 × D⌋"], ["Defender holds", "⌊0.6 × A⌋", "⌊0.2 × min(A, D)⌋"]], [5, 5.5, 6])
bl("A = attacker’s armies, D = defender’s armies. Nobody drops below 1 army.",
   "On a win the hold changes owner. A house left with 0 holds is eliminated: its gold goes to the winner and its alliances and offers are erased.",
   "Example: 22 Lannister beat 20 Stark → Lannister loses 10, Stark loses 16.",
   "Why min(A, D): a raid of 6 into 20 can only kill 1 defender, so suicide attacks cannot trade 3-for-4.")
img("06_battle_house.jpg", "A battle in progress: Lannister’s dragon attacks Stark at Moat Cailin.")

# ── 6 ───────────────────────────────────────────────────
h1("6. Diplomacy, trust and betrayal")
bl("<b>Trust</b> runs from 0 to 100 for every pair of houses; it starts at 50.",
   "<b>+5 trust</b> for each round an alliance survives; <b>−30 trust</b> for every betrayal.",
   "<b>Two-turn handshake:</b> the proposer sends a raven to the target’s inbox and still makes its military move; the target answers on its own next turn.",
   "<b>An alliance gives:</b> no attacks between allies, both focus on the third house, and every house switches Minimax to Paranoid mode. Allies never share gold or armies.",
   "<b>Betrayal happens three ways:</b> MCTS chooses to betray; a house attacks its ally’s hold; or a house accepts a new ally while already allied.",
   "<b>Guards:</b> offers are auto-rejected when only two houses remain or the sender is eliminated; an eliminated house’s pacts and offers are purged.")
img("09_alliance_formed.jpg", "Stark allied with Lannister (turn 4): the panel shows pairwise alliance and betrayal scores and Paranoid mode.")

# ── 7 ───────────────────────────────────────────────────
h1("7. How the AI is organised")
p("Seven algorithms work together, each with one job. No algorithm both scores and decides.")
table([["Stage", "Algorithm", "Job", "Decides?"], ["Scout", "BFS + DFS", "Holds within 3 marches; expansion corridors (shown as scouting info)", "No"],
       ["Feel", "Fuzzy Logic", "Turn threat, weakness and trust into alliance / betrayal / solo scores (0–1)", "No, scores only"],
       ["Diplomacy", "MCTS (+ Greedy inside)", "500 simulated futures choose propose / betray / solo / accept / reject", "Yes"],
       ["War", "Minimax + alpha-beta", "Look 3 moves ahead; attack one hold or Hold", "Yes"],
       ["Route", "A*", "Safest road to King’s Landing; first step toward a distant click", "Yes"]], [2.3, 3.6, 8.2, 2.4])
img("07_ai_brain_trace.jpg", "The in-game AI Brain panel (press H) shows each house’s Fuzzy scores, MCTS visits, Minimax scores and A* corridor.")

# ── 8 ───────────────────────────────────────────────────
h1("8. BFS and DFS: scouting")
h2("Breadth-First Search")
bl("<b>Takes:</b> the map, the capital, n_steps = 3. <b>Calculates:</b> visits holds ring by ring with a queue, never twice. <b>Returns:</b> the set of reachable holds.",
   "From Winterfell: 1 step → 5 holds, 2 steps → 12 (King’s Landing enters), 3 steps → 15.",
   "Why: finds everything within a fixed number of steps in the fewest operations; O(V + E).")
h2("Depth-First Search")
bl("<b>Takes:</b> the map, the capital, depth_limit = 3. <b>Calculates:</b> follows one path as deep as allowed, then backtracks; no hold twice on a path. <b>Returns:</b> every path ending in a neutral or weak hold (defense &lt; 2).",
   "From Winterfell, DFS finds 64 cycle-free expansion corridors.",
   "Why: lists whole multi-step routes with very little memory (O(depth)).")
note("BFS and DFS are scouting information shown in the AI Brain panel; they do not change Minimax or MCTS scores.")

# ── 9 ───────────────────────────────────────────────────
h1("9. Greedy search")
f("t* = argmax over adjacent candidates of ( resource_value(t) − defense_bonus(t) )   — ties go to King’s Landing")
table([["Stark, turn 1: adjacent hold", "r", "b", "r − b"], ["Riverrun (Greedy’s pick)", "5", "2", "3"], ["Pyke", "4", "2", "2"],
       ["The Twins (Minimax’s pick)", "5", "3", "2"], ["The Wall", "4", "3", "1"]], [7.5, 2, 2, 2.5])
p("Greedy has no look-ahead, so it is not the war decision. It is used because it is instant: it plays every house inside MCTS’s 500 simulated futures.")

# ── 10 ──────────────────────────────────────────────────
h1("10. A* pathfinding")
f("f(n) = g(n) + h(n)      g = Σ defense bonuses crossed so far      h = hex distance left to the goal")
table([["House", "Safest route to King’s Landing", "Cost", "Minimax bonus"],
       ["Stark", "Winterfell → The Twins → King’s Landing", "6", "9"],
       ["Lannister", "Casterly Rock → Oldtown → Highgarden → King’s Landing", "7", "7.5"],
       ["Targaryen", "Dragonstone → Storm’s End → Harrenhal → King’s Landing", "6", "9"]], [2.5, 8.5, 1.5, 3])
f("Throne-corridor bonus (inside Minimax) = 1.5 × max(0, 12 − A* cost)")
bl("Step by step for Stark: expand Winterfell (g 0 + h 5 = 5) → neighbours Pyke f11, Riverrun f8, The Wall f7, The Twins f6 → expand The Twins (3 + 3 = 6) → King’s Landing f6 → route found, cost 6.",
   "Owning The Twins cuts the cost to 3, raising the bonus to 13.5. That is a main reason Stark attacks The Twins on turn 1.",
   "Second use: when a human clicks a distant hold, A* marches one step along the safest route toward it.")
note("<b>Technical note:</b> A* is guaranteed optimal only when h never overestimates. Here one move can span several hexes for little defense, so h can overestimate; "
     "every route <i>to King’s Landing</i> is still optimal, so the AI’s war choices are unaffected.")

# ── 11 ──────────────────────────────────────────────────
h1("11. Mamdani Fuzzy Logic")
p("Fuzzy Logic turns three numbers into three smooth scores, with no brittle cut-offs such as ‘weak if armies &lt; 10’.")
f("Strength = (armies + Σ defense) × 2.5, capped at 100       Weakness = 100 − own strength       Trust = 0–100")
f("Low = (0, 0, 60)      Medium = (20, 50, 80)      High = (40, 100, 100)    (triangles, same for every input and output)")
table([["#", "IF", "THEN"], ["1", "Enemy HIGH and Weakness HIGH", "Alliance HIGH"], ["2", "Trust LOW and Enemy MEDIUM", "Alliance LOW"],
       ["3", "Weakness LOW and Enemy LOW", "Betrayal HIGH"], ["4", "Weakness LOW and Trust HIGH", "Solo HIGH"],
       ["5", "Enemy HIGH and Trust HIGH", "Alliance MEDIUM"], ["6", "Trust LOW", "Betrayal MEDIUM"]], [1, 9, 6.5])
p("<b>Four stages:</b> fuzzify each input → fire the 6 rules (AND = min) → aggregate the clipped outputs (max) → take the centroid → three scores in 0.00–1.00, passed to MCTS as a bias. "
  "<b>Context A</b> (own diplomacy) uses both rivals combined as the enemy; <b>Context B</b> (an incoming offer) uses the third house as the enemy and trust toward the sender.")
table([["Situation", "Enemy", "Weak", "Trust", "Alliance", "Betrayal", "Solo"], ["Weak house vs a giant", "100", "80", "50", "0.73", "0.50", "0.00"],
       ["Weak, trusted partner", "100", "80", "80", "0.65", "0.00", "0.00"], ["Dominant, low trust", "30", "10", "20", "0.25", "0.62", "0.00"],
       ["Balanced, high trust", "60", "40", "90", "0.50", "0.00", "0.75"]], [5, 1.6, 1.6, 1.6, 2.2, 2.2, 1.8])
p("Solo has only rule 4, so its score is either 0 or about 0.70–0.80, never in between.")

# ── 12 ──────────────────────────────────────────────────
h1("12. Minimax with alpha-beta pruning")
p("Minimax decides war. It looks three moves ahead (my move → the enemy’s best reply → my move) and scores each resulting board with V, assuming average combat luck.")
f("V = 2·Σ(r + b) + 1.5·Armies + 0.5·Gold + 500·[own King’s Landing] + 1.5·max(0, 12 − A* cost) − Σ enemies (Σ r + 1.5·Armies)")
bl("<b>Decomposed mode</b> (no alliance on the board): one 1-vs-1 search per rival, combined by each rival’s strength.",
   "<b>Paranoid mode</b> (any alliance exists): rivals act as one team that always picks the reply hurting me most.",
   "<b>Filters:</b> never attack an ally; need 5+ armies to attack a house; only attack King’s Landing with armies ≥ its effective defense; taking the throne ends the search with +50 per remaining ply, so a sooner win scores higher.",
   "<b>Pick rule:</b> if Hold beats every attack → Hold. Otherwise pick at random among attacks within 2 points of the best and not below Hold.")
h2("Real example: Stark, turn 1 (search against Lannister)")
table([["Move", "Hold", "Pyke", "Riverrun", "The Wall", "The Twins"], ["Score", "68.5", "79", "41.5", "81", "81.5 (best)"]], [2.5, 2.4, 2.4, 2.4, 2.6, 3.2])
bl("Inside The Twins, Lannister’s most damaging reply is Oldtown (81.5); Stark’s best follow-up is Highgarden.",
   "V for that line = land 56 + armies 16.5 + gold 30 + throne path 13.5 − enemy 34.5 = <b>81.5</b>.",
   "The full search visits 143 positions, scores 104 leaves and prunes 13 branches. Alpha-beta gives the same answer as plain Minimax, faster.")
img("12_human_minimax_hover.jpg", "Human mode: hovering The Twins shows its Minimax score (+82.8, combining both rival searches) against Hold (+69.0).")
img("tree_visualizer_end.jpg", "The tree visualizer (tree_visualizer.html) after the full turn-1 search: the winning line in green, pruned branches in red.")

# ── 13 ──────────────────────────────────────────────────
h1("13. Monte Carlo Tree Search (MCTS)")
p("MCTS decides diplomacy. For each option it plays out simulated 10-turn futures in which every house moves greedily with real ±20% combat luck, then keeps the option that was visited most.")
f("UCT(a) = Q(a)/N(a)  +  1.414 · √( ln N_parent / N(a) )  +  FuzzyBias(a)")
bl("<b>Exploit</b> Q/N: the average reward so far. <b>Explore</b>: tries options that have been tested less. <b>Instinct</b>: the Fuzzy score for that option.",
   "<b>Options:</b> Context A = propose / betray / solo; Context B = accept / reject. Proposals go to the most-trusted rival (ties to the weaker one), so weaker houses team up against the leader.",
   "<b>500 iterations</b> per decision; the most-visited option wins.")
table([["Outcome of a simulated future", "Reward"], ["I take the throne", "10"], ["I am eliminated", "0"],
       ["Otherwise", "(0.5·land + 0.3·military + 0.2·income − 0.4·risk) ÷ 100"], ["A rival takes the throne", "the above, halved"]], [8, 8.5])
p("<b>Risk:</b> an alliance breaks each simulated turn with p = 0.25 × (1 − trust/100), adding +10 risk (12.5% per turn at trust 50); betraying first adds +30.")
table([["Situation", "Options (bias, avg Q → visits)", "Decision"],
       ["Targaryen, turn 2, no ally", "Solo (0.73, 0.03 → 393) · Propose (0.54, 0.05 → 107)", "Solo: close outcomes, the fuzzy bias tipped it"],
       ["Lannister, turn 4, offer from Stark", "Accept (0.50, 2.07 → 496) · Reject (0.76, 0.00 → 4)", "Accept: simulations overruled the bias"],
       ["Stark, allied with Targaryen, trust 22", "Keep (0.00, 2.81 → 489) · Betray (0.64, 0.90 → 11)", "Keep: Fuzzy said betray, MCTS disagreed"]], [4.4, 7.3, 4.8])
note("<b>Key insight:</b> Fuzzy steers the search; MCTS has the final word once the simulated outcomes clearly differ.")

# ── 14 ──────────────────────────────────────────────────
h1("14. One complete turn, step by step")
for i, t in enumerate(["Round starts; houses act in the shuffled order.",
                       "Next house: is an alliance offer waiting? YES → Fuzzy Context B → MCTS accept/reject → form the pact or clear the offer.",
                       "NO → BFS + DFS scout → Fuzzy Context A → MCTS chooses: propose (raven to the target’s inbox), betray (−30 trust, strike the former ally) or stay solo.",
                       "War: Minimax picks a target or Hold. If attacking, A* gives the first border step, then combat is rolled.",
                       "Elimination check: plunder the gold and purge the alliances of any house left with no holds.",
                       "Repeat for every remaining house.",
                       "End of round: income → recruitment (cap, reserve, max 3) → +5 trust per pact → refresh Fuzzy → winner? If none, a new round starts."], 1):
    story.append(Paragraph(f"<b>{i}.</b> {t}", B))
p("Greedy is not a separate step: it runs inside every MCTS rollout as the model of how each house plays.")

# ── 15 ──────────────────────────────────────────────────
h1("15. Modes, screens and controls")
table([["Mode", "How it plays"], ["AI vs AI (Observer)", "All three houses are AI. ADVANCE TURN, Space or Enter steps one turn."],
       ["Human vs AI (Command)", "You lead one house: click a hold to attack (a distant hold marches one A* step), ALLY offers, BETRAY, HOLD TURN; hover a hold to see its Minimax score."]], [4.5, 12])
table([["Key", "Action", "Key", "Action"], ["P", "Pause / resume", "L", "Raven Log (every move and diplomacy event)"],
       ["R", "Restart", "M", "Music on/off (battle sounds stay)"], ["H", "AI Brain panel", "F11", "Fullscreen"]], [1.5, 6.5, 1.5, 7])
p("Visual layer: three animated house dragons (Stark frost dragon, Lannister golden dragon, Targaryen red dragon), sword-fighting armies and dragon fire in every battle, an animated sea, and an optional music track that quietens during battles.")
img("11_victory.jpg", "A finished game: House Targaryen wins after taking 18 holds.")

# ── 16 ──────────────────────────────────────────────────
h1("16. Glossary")
table([["Term", "Meaning"], ["Hold", "One of the 19 castles / regions on the map"], ["Garrison", "Neutral troops defending an unclaimed hold"],
       ["Defense bonus", "How fortified a hold is (1–4)"], ["Effective defense", "Defense after the bonus is applied (neutral or house formula)"],
       ["Supply cap", "Maximum armies a house may have: 10 + 4 per hold"], ["Trust", "0–100 relationship score between two houses"],
       ["Inbox", "Where alliance offers wait until the target’s next turn"], ["Decomposed / Paranoid", "Minimax modes without / with an alliance on the board"],
       ["Alpha-beta pruning", "Skipping search branches that cannot change the decision"], ["UCT", "MCTS formula balancing exploitation, exploration and fuzzy bias"],
       ["Rollout", "One simulated 10-turn future inside MCTS"], ["Centroid", "Fuzzy Logic’s final step: the balance point of the output shape"]], [4.5, 12])

doc = SimpleDocTemplate(OUT, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.8 * cm, bottomMargin=1.8 * cm,
                        title="Game of Thrones: AI Conquest — Complete Game Report", author="KUET AI Project")
doc.build(story, onFirstPage=footer, onLaterPages=footer)
print("written:", OUT)
