# laughing-journey

A personal monorepo holding three independent projects, each self-contained with its
own toolchain and its own README:

| Project | What it is | Stack | Docs |
|---|---|---|---|
| [`Lumen-dash/`](Lumen-dash/) | **Lumen Dash** — a 3D endless runner played with your body via webcam | React 19, TypeScript, Vite 7, three.js, Tailwind 4, MediaPipe | [Lumen-dash/README.md](Lumen-dash/README.md) |
| [`VALE/`](VALE/) | **VALÉ — Obsidian No. 01** — product landing page for a luxury writing instrument | React 19, Vite 8, GSAP | [VALE/README.md](VALE/README.md) |
| [`chess/`](chess/) | Two self-contained desktop chess apps | Python 3.10+, Tkinter | [chess/README.md](chess/README.md) |

```
laughing-journey/
├── Lumen-dash/          # webcam endless runner (TypeScript)
├── VALE/                # product landing page (JavaScript)
└── chess/               # Python only
    ├── chess 1/         # Nexus Chess   — chess_game.py   (python-chess)
    ├── chess 2/         # Chess Arena   — chess_arena.py  (stdlib only)
    └── .venv/           # shared virtualenv for both chess apps
```

The projects share nothing but this repository: different languages, different
dependency trees, separate `node_modules`, separate virtualenv. Run, build and test
each one from its own directory.

---

## Quick start

```bash
# --- Webcam runner -------------------------------------------------
cd Lumen-dash
npm install
npm run dev        # http://localhost:5173

# --- Product site --------------------------------------------------
cd ../VALE
npm install
npm run dev

# --- Desktop chess -------------------------------------------------
cd ../chess
.venv/bin/python "chess 1/chess_game.py"        # Nexus Chess
```

Requirements: **Node 18+** for the two web projects, **Python 3.10+** for the chess
apps. A shared virtualenv lives at `chess/.venv` with `python-chess` 1.11.2 and a
working `tkinter`.

> The camera needs `localhost` or HTTPS — browsers block `getUserMedia` on plain LAN
> IPs. Keyboard mode needs no camera and no network.

---

## Lumen Dash

A single-player 3D endless runner controlled by body movement through the webcam.
Pose estimation runs **entirely locally** (MediaPipe `PoseLandmarker`, lite model)
and gestures are matched by a deterministic rule engine — no LLM, no cloud AI.

```bash
cd Lumen-dash
npm install
npm run dev        # keyboard + camera play
npm run build      # production bundle (single-file via vite-plugin-singlefile)
npm run typecheck  # tsc --noEmit
```

Play with **Camera** (calibration → tutorial → run) or with the **Keyboard**
(`← →`/`A D` to change lane, `↑`/`W`/`Space` jump, `↓`/`S`/`Ctrl` slide,
`Esc`/`P` pause, `F3` debug overlay).

### Scripts

| Script | What it does |
|---|---|
| `npm run dev` | Vite dev server |
| `npm run build` | Production build |
| `npm run preview` | Serve the production build |
| `npm run typecheck` | TypeScript check |
| `npm run dev:cam` | Everything: phone-camera relay + Vite + `adb` tunnel |
| `npm run phonecam` | Just the phone-camera relay server |
| `npm run phone-port` | Open/close a port *on the phone* via `adb shell` |

### Phone as camera (no app)

No webcam on the PC? `npm run dev:cam` turns the **phone's browser** into a webcam
over USB: the phone streams JPEG frames, the PC paints them to a `<canvas>`, and
`PhoneCamera` overrides `navigator.mediaDevices.getUserMedia` to return that canvas
as a `MediaStream`. The game itself is untouched — everything downstream (pose,
filter, gesture engine) is the normal path.

```bash
npm run dev:cam          # relay + Vite + adb reverse (use this one)
# phone:  open http://localhost:8080/ → tap "Start streaming" → allow camera
# PC:     open http://localhost:5173  → Settings → "Use phone as camera" → Play with Camera
```

`adb reverse` is what makes this work: the phone reaches the PC on `localhost`, which
browsers count as a secure context.

### Fully offline

Drop these two assets into `public/` and the game needs no network at all:

```
public/models/pose_landmarker_lite.task
public/mediapipe/wasm/*      # copy from node_modules/@mediapipe/tasks-vision/wasm
```

Without them the app falls back to a CDN on first load. Keyboard mode never needs
either.

### Layout

```
src/cam     camera → pose → One-Euro filter → gesture engine   (game-agnostic)
src/game    world, runner, collisions, audio, input sources     (zero camera code)
src/app     Controller — wires everything, owns the store
src/ui      React screens and HUD
src/prompt  the original implementation brief
tools/      phone-camera relay + adb helpers
docs/       GESTURE_ENGINE.md — reusing the pose/gesture modules elsewhere
```

`src/game` never imports `src/cam`, and `src/cam` may import only `game/InputSource`.
That is what lets keyboard mode run with no camera code in the bundle at all.

Tuning: gesture thresholds live in `src/cam/gestureConfig.ts` (units are
shoulder-widths, so they are distance-independent), gameplay constants in
`src/game/config.ts`, obstacle patterns in `src/game/patterns.ts`. Append
`?seed=123` to the URL for a fixed track.

---

## VALE

**VALÉ — Obsidian No. 01**: a Vite + React landing page for a premium writing
instrument. The pen is drawn in CSS with a subtle 3D pointer inspection; GSAP +
ScrollTrigger drive entrance and scroll animations. Cormorant Garamond + Manrope,
self-hosted in `public/fonts/`.

```bash
cd VALE
npm install
npm run dev
npm run build
npm run preview
npm test           # Playwright: responsive sweep 320→2560px, anchors, axe a11y
npm run test:ui
```

`tests/site.spec.js` checks every section destination at ten viewport widths,
asserts zero horizontal overflow and zero console errors, and runs axe-core
accessibility checks.

```
src/            landing page (components, hooks, styles)
tests/          Playwright suite
public/         self-hosted fonts, favicon, social image
index.html      document head (SEO / OG / Twitter metadata)
CLINE/          working copy of the site; the only place to make changes
"RAW data"/     pristine snapshot of the original starting files — never edit
```

> **`CLINE/` vs `"RAW data/"`:** all edits go in `CLINE/`. `"RAW data/"` is a
> restore point and must not be modified. Earlier versions are also recoverable
> from git history (`fbf01c3` — README only, `7b4c39b` — first full Vite + React
> scaffold). If you ever re-sync `CLINE/` from the project root with
> `rsync --delete`, add `--exclude 'README-CLINE.md'` so that note survives.

---

## chess

Python only. Two unrelated desktop chess apps, each in its own folder, sharing just
the virtualenv in `.venv/`.

| Folder | App | Entrypoint | Dependencies |
|---|---|---|---|
| [`chess 1/`](chess/chess%201/) | Nexus Chess | `chess_game.py` | `python-chess` + Tkinter |
| [`chess 2/`](chess/chess%202/) | Chess Arena | `chess_arena.py` | **none** — standard library only |

Both need a display (or `Xvfb` for the GUI tests).

### chess 1 — Nexus Chess

A single-file desktop chess studio built **on top of `python-chess`**. Legal-move
highlighting, promotions, undo, pause, hints, board rotation, PGN import/export,
history/replay and bounded cancellable match analysis. SQLite (at
`~/.nexus_chess/chess.sqlite3`, override with `--data-dir`) stores unfinished games,
settings, completed games and a result-weighted opening memory.

```bash
cd chess
.venv/bin/python "chess 1/chess_game.py"              # GUI
.venv/bin/python "chess 1/chess_game.py" --self-test  # headless checks
.venv/bin/python "chess 1/chess_game.py" --gui-test   # Tk smoke test (needs a display)
```

Three modes: Human vs AI, AI vs AI, Human vs Human, at Easy / Balanced / Strong.
The built-in AI and the review scores are **practice-level heuristics** — not
Stockfish, not an Elo rating, not calibrated accuracy. Games are untimed.

> The folder name contains a space — quote the path in every shell command.

### chess 2 — Chess Arena

An **in-progress** single-file chess application with **zero third-party
dependencies** — the entire engine, rules and persistence are written against the
standard library (0x88 mailbox board, Zobrist hashing, iterative-deepening PVS
alpha-beta with a transposition table, quiescence, null-move pruning, LMR, check
extensions, killer/history ordering and MVV-LVA, seven playing styles on a tapered
evaluation).

The real sources are the fragments in `.build/`; `chess_arena.py` is **generated**
from them:

```bash
cd "chess/chess 2"
./build.sh                                   # cat .build/p*.py > chess_arena.py, then compile
python3 .build/test_rules.py --quick        # perft / movegen  -> prints RULES-OK
python3 -m unittest discover -s .build -p 'test_records.py'
```

> **Never edit `chess_arena.py` by hand** — the next `./build.sh` overwrites it.
> Edit the `p01…p11` parts under `.build/` instead.

> **Status: the CLI entry point is still missing.** The build now assembles all
> 3116 lines including the records store, the analysis layer and the Tk `ChessApp`,
> and the file imports cleanly. But there is still no `if __name__ == "__main__"`
> block, so `python3 chess_arena.py --selftest` silently does nothing and the flags
> in its own docstring are not wired up. Launch the GUI from Python for now:
> `python3 -c "import chess_arena; chess_arena.launch_gui()"`.
> Separately, the search code has a pre-existing bug — `TimeManager` has no
> attribute `time` — which fails the analysis and engine tests (1 and 5 errors
> respectively). `test_rules.py` passes. None of this is caused by the folder move;
> see [chess/README.md](chess/README.md) for detail.

---

## Repository notes

`VALE/.gitignore` covers `node_modules`, `dist`, `playwright-report/`,
`test-results/` and `.env`. `chess/` has no `.gitignore` of its own, so `chess/.venv`
and Python `__pycache__/` directories are currently unignored — add one before
staging that tree. `Lumen-dash/` likewise has no `.gitignore`.

Both web projects pin their dependencies with a committed `package-lock.json`, so
`npm ci` reproduces the exact tree the build was verified against.