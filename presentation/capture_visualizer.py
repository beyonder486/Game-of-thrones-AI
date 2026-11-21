"""Capture real screens of tree_visualizer.html at chosen steps (headless Edge, temporary copies)."""
import os, subprocess
SRC = r"D:\Codes\KUET PROJECTS\3 2 AI\Game-of-thrones-AI\tree_visualizer.html"
OUT = os.path.dirname(os.path.abspath(__file__))
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
base = open(SRC, encoding="utf-8").read()
def mm(i, n): return f'switchTab("minimax");mmScenarioSel.value={i};mmLoadScenario({i});if(typeof mmStop=="function")mmStop();mmExpandedRootChild=null;mmStepIdx={n};mmRender();'
def mc(i, n): return f'switchTab("mcts");mctsScenarioSel.value={i};mctsLoadScenario({i});if(typeof mctsStop=="function")mctsStop();mctsIter={n};mctsRender();'
def ast(i, n): return f'switchTab("astar");astarRouteSel.value={i};astarLoadRoute({i});if(typeof astarStop=="function")astarStop();astarStepIdx={n};astarRender();'
def fz(i, s): return f'switchTab("fuzzy");fuzzyPresetSel.value={i};fuzzyLoadPreset({i});fuzzyStage={s};fuzzyRender();'
SHOTS = {"mm_p1": mm(2, 30), "mm_p2": mm(2, 90), "mm_p3": mm(2, 156),
         "mcts_1": mc(0, 1), "mcts_2": mc(0, 50), "mcts_3": mc(0, 500),
         "astar_s": ast(0, 3), "astar_l": ast(1, 5), "astar_t": ast(2, 4),
         "fz_1": fz(0, 1), "fz_2": fz(0, 2), "fz_3": fz(0, 3), "fz_4": fz(0, 4)}
for name, js in SHOTS.items():
    page = os.path.join(OUT, name + ".html")
    open(page, "w", encoding="utf-8").write(base + f'\n<script>window.addEventListener("load",()=>setTimeout(()=>{{{js}}},300));</script>\n')
    png = os.path.join(OUT, name + ".png")
    subprocess.run([EDGE, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--window-size=1920,1080",
                    "--virtual-time-budget=5000", f"--screenshot={png}", "file:///" + page.replace("\\", "/")],
                   capture_output=True, timeout=90)
    os.remove(page)
    print(name, os.path.getsize(png) if os.path.exists(png) else "MISSING")
