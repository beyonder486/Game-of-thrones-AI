# Presentation Analysis

A review of the current 12-slide deck against the whole of `README.md` (500 lines).

## Folder layout

| Folder | Purpose |
| :--- | :--- |
| `gameplay/` | Put the gameplay video(s) here |
| `screenshots/` | Frames pulled from the video, plus in-game screenshots |
| `slides/` | Source files of the current deck (`deck.json`, `deck.css`, `slides/*.html`) |

## Slide-by-slide review

| # | Slide | Matches README? | Gaps / issues |
| :-: | :--- | :--- | :--- |
| 1 | Cover | Yes | Team names are a placeholder. No game image yet. |
| 2 | Overview | Yes (19 holds, 21×8 map, 2 win paths, 2 modes) | No screenshot of the map. |
| 3 | Starting stats | Yes, the table is exact | It doesn't mention that the 15 neutral holds have 2–4 troops and 1–3 defense; that's only in the speaker notes. |
| 4 | Economy | Yes, the formulas are correct | Worked example missing (Stark earns 10 + 9 = 19 in Round 1). |
| 5 | Combat | Yes | The 31 armies ≈ 50% vs 46 armies = 100% comparison is shortened. |
| 6 | Diplomacy | Yes | The five alliance effects are compressed into one line. |
| 7 | 7 algorithms | Yes | Good overview slide. |
| 8 | Fuzzy Logic | Yes | Shows 4 of the 6 rules. Contexts A and B are only in the notes. A chart of the membership curves would help. |
| 9 | Minimax | Yes, formula is exact | Alpha-beta pruning itself isn't explained. The King's Landing guard (armies ≥ 30) is missing. |
| 10 | MCTS | Yes | Action sets for Contexts A and B are only in the notes. |
| 11 | Turn flow | Yes | The inbox branch (answer an offer first) is only in the notes. |
| 12 | Closing | — | Fine. |

No factual errors were found; every number and formula on the slides matches the README.

## README topics not yet in the deck

1. **Visuals and presentation layer:** 3 animated house dragons (Frost, Golden, Valyrian Red), ground army sprites, 2.5D isometric map.
2. **HUD:** top status bar, the FUZZY [H] drawer, RAVEN LOG [L] drawer, Minimax hover preview.
3. **Audio:** battle sound effects and background music that gets quieter during battles.
4. **Controls** table.
5. **Verification:** `test_algorithms.py` and its 9 automated checks, including an 8-game headless AI vs AI simulation.
6. **Known AI approximations** (3 honest limitations, which evaluators usually like to see).
7. **Tech stack and file map:** Python 3.10+, pygame, numpy, Pillow; the module structure.
8. **Glossary terms** such as Voronoi regions, an asynchronous inbox and unilateral betrayal.

## Planned additions once the gameplay video arrives

| New slide | Content | Source |
| :--- | :--- | :--- |
| Gameplay hero (cover/overview) | Full-map screenshot | Video frame |
| The world | Map with houses and King's Landing | Video frame |
| A battle | Dragons + armies clash | Video frame |
| Diplomacy in action | Alliance offer / Raven Log | Video frame |
| AI made visible | FUZZY drawer + Minimax hover | Video frame |
| Victory | Iron Throne / elimination screen | Video frame |
| Verification | 9 checks and simulation results | `test_algorithms.py` output |
| Limitations and future work | 3 approximations | README |
| Tech stack and architecture | Modules diagram | README file map |
| How to run / demo | Controls + `python main.py` | README |

Target length: about 20 slides.

## Tools needed

- **Frame extraction:** `ffmpeg` is **not installed** on this machine. Options: install it (`choco install ffmpeg`), or use Python with `opencv-python`.
- Timestamps of key moments in the video would make frame selection much more accurate.

## Changes merged from main (commit ccef193, "Modified UI")

| Change | Effect on the deck |
| :--- | :--- |
| Minimax stops at an Iron Throne capture: ±50 per remaining ply, so faster wins score higher | Added to the Minimax slide's notes |
| Minimax never overrides **Hold** when Hold beats every attack | Minimax slide updated |
| MCTS now records a trace: visits, average Q and fuzzy bias for each option | New screenshot/slide: **AI BRAIN [H]** panel |
| **AI BRAIN [H]** drawer (replaces FUZZY [H]) with *Live All-Algorithm Trace* and *Pairwise Fuzzy* tabs | Use in the "AI made visible" slide |
| **PAUSE / RESUME [P]** and **Restart [R]** keys | Add to the controls slide |

Note: README.md has not been updated for these UI changes yet (it still says FUZZY [H]).
