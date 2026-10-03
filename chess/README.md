# chess

Two **unrelated** desktop chess applications. They share nothing but this folder and
the virtualenv — different codebases, different authors' approaches, different
dependencies. Pick one.

| Folder | App | Entrypoint | Dependencies |
|---|---|---|---|
| [`chess 1/`](chess%201/) | **Nexus Chess** | `chess_game.py` | `python-chess` + Tkinter |
| [`chess 2/`](chess%202/) | **Chess Arena** | `chess_arena.py` | **none** — standard library only |

Both are single-file Python apps and both need a graphical display (`Xvfb` is fine
for testing). Neither uses the network.

## Setup

A virtualenv is already configured at `.venv` (Python 3.14, `python-chess` 1.11.2,
working `tkinter`). Only **chess 1** needs it:

```bash
.venv/bin/python -m pip install "python-chess>=1.999,<2"   # if you ever need to rebuild it
```

> Both folder names contain a space — **always quote the path**:
> `.venv/bin/python "chess 1/chess_game.py"`.

---

## chess 1 — Nexus Chess

A chess studio built **on top of `python-chess`**, so the rules, move generation and
PGN handling come from a well-tested library and the file concentrates on the app:
UI, search, persistence and analysis.

**Features** — legal-move highlighting, promotions, undo, pause, hints, board
rotation, PGN import/export, history/replay, and bounded cancellable match analysis.
Three modes (Human vs AI, AI vs AI, Human vs Human) at Easy / Balanced / Strong.

**Storage** — SQLite at `~/.nexus_chess/chess.sqlite3` holds unfinished games,
settings, completed games and a result-weighted opening memory. Override the
location with `--data-dir PATH`.

```bash
.venv/bin/python "chess 1/chess_game.py"              # launch the GUI
.venv/bin/python "chess 1/chess_game.py" --self-test  # headless checks (15 tests)
.venv/bin/python "chess 1/chess_game.py" --gui-test   # real Tk smoke test
```

`--self-test` covers rules, perft, the engine, persistence, PGN and analysis without
touching your real database.

> The built-in AI and the review scores are **practice-level heuristics**. They are
> not Stockfish, not an Elo rating, and not calibrated accuracy. Games are untimed.

---

## chess 2 — Chess Arena

The same game idea written **from scratch against the standard library** — no
`python-chess`, no third-party packages at all.

**Engine** — 0x88 mailbox board with Zobrist hashing; iterative-deepening PVS
alpha-beta with a transposition table, quiescence search, null-move pruning,
late-move reductions, check extensions, killer/history move ordering and MVV-LVA.
Seven playing styles (balanced, positional, tactical, aggressive, defensive,
endgame, wild) on top of a tapered evaluation with pawn-structure, king-safety and
mobility terms.

**Also included** — a records/analysis layer (centipawn-loss and accuracy grading,
blunder and missed-mate detection, coaching hints, annotated PGN and JSON export)
and a dependency-free Tk GUI.

### Building

`chess_arena.py` is **generated**. The real sources are the ordered fragments in
`.build/`:

```bash
cd "chess 2"
./build.sh      # cat .build/p*.py > chess_arena.py, then py_compile it
```

> **Never edit `chess_arena.py` by hand** — the next `./build.sh` overwrites it.
> Edit `.build/p01…p11` instead.

### Tests

```bash
python3 .build/test_rules.py --quick        # perft / movegen   -> prints RULES-OK
python3 -m unittest discover -s .build -p 'test_records.py'
python3 .build/dbg_search.py                # search smoke test with printed PVs
```

`test_rules.py` uses `python-chess` as an optional oracle when it is importable, but
the app itself does not require it.

### Known gaps

Two things are unfinished, and neither is caused by the folder layout:

1. **No CLI entry point.** The file has no `if __name__ == "__main__"` block, so
   running `python3 chess_arena.py --selftest` does nothing and the flags in the
   module docstring (`--selftest`, `--sim`, `--analyze`) are not wired up. Launch the
   GUI from Python instead:

   ```bash
   python3 -c "import chess_arena; chess_arena.launch_gui()"
   ```

2. **`TimeManager` has no attribute `time`** — a real bug in the search code that
   breaks anything driving a search through a `TimeManager` subclass. Current test
   status: `test_rules.py` passes (`RULES-OK`), `test_records.py` runs 28 tests with
   **1 error** (the analysis smoke test), `test_engine.py` runs 15 with **5 errors**,
   all the same `AttributeError`.

Engine data is written to `~/.chess_arena/` at runtime.