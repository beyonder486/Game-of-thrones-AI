# GUIDE — Project Documentation

All design and reference documentation for **Game of Thrones: AI Conquest**.
The project [`README.md`](../README.md) stays at the repository root.

| Document | What it is | Read it when |
|---|---|---|
| [`instructions.md`](instructions.md) | **The specification.** The original design brief — what was to be built, algorithm by algorithm. | You need the authoritative requirement for a feature. |
| [`instruction 2.md`](instruction%202.md) | **Mechanics reference.** Every rule, formula and constant as actually implemented, each with a `file:line` citation — combat casualty arithmetic, the economy, all seven algorithms, worked examples. | You need to know exactly how something behaves, or where a number is defined. |
| [`CODE_MAP.md`](CODE_MAP.md) | **Per-file API reference.** Every Python file and function: parameters, return value, how it works, and where the call flow comes from and goes to. Includes Mermaid architecture, turn-pipeline and call-graph diagrams. | You are navigating the codebase or tracing a call path. |
| [`TO_IMPLEMENT.md`](TO_IMPLEMENT.md) | **Gap audit.** Where the code and the spec disagree, undocumented behaviour, UI defects, and genuine gaps — with a suggested order of work. | You are deciding what to fix next. |

## Suggested reading order

1. **`instructions.md`** — what the system is meant to do
2. **`CODE_MAP.md`** — how the files fit together
3. **`instruction 2.md`** — the exact mechanics
4. **`TO_IMPLEMENT.md`** — what is still outstanding

> Mermaid diagrams in `CODE_MAP.md` render natively on GitHub. In VS Code, install
> *Markdown Preview Mermaid Support* to view them in the preview pane.
