# Implementation Brief: LUMEN DASH — a Webcam-Controlled 3D Endless Runner

You are a senior game/web engineer. Build a complete, polished, **single-player 3D endless runner controlled by the player's body through a laptop webcam**. Everything runs locally in the browser. No LLM, no cloud AI, no paid API, and **no network access during gameplay**.

The game is *inspired by the structure* of Temple Run and Subway Surfers (auto-forward running, three lanes, jump/slide/dodge, coins, escalating speed). Its **identity, characters, names, art, level themes and mechanics must be fully original**. Do not reproduce any existing game's characters, obstacle designs, UI or naming.

Work milestone by milestone (Section 14). After each milestone the project must build and run. Do not leave stubs for anything in the MVP scope.

---

## 1. Product Goals (in priority order)

1. **Responsiveness.** A real jump must make the runner jump within ~150 ms end to end.
2. **Intuitiveness.** Movements are big, obvious, physically natural. No analog precision is needed.
3. **Forgiveness.** False negatives and false positives are both costly. Prefer slightly lenient detection plus generous game-side input buffering.
4. **Coherent identity.** It should look and sound like a real game, not a tech demo, even with only procedural assets.
5. **Reusable gesture layer.** The pose and gesture system is a standalone module that knows nothing about this game.

**Out of scope:** multiplayer, accounts, shops, online leaderboards, voice control, LLM or any AI "assistant", mobile layouts, and multi-person tracking.

---

## 2. Tech Stack (decided, do not substitute without a written reason)

| Concern | Choice |
|---|---|
| Build / UI shell | Vite + React + TypeScript (strict) + Tailwind CSS |
| 3D | **Plain three.js**, used imperatively. No react-three-fiber. The game loop must not depend on React renders. |
| Pose estimation | **MediaPipe Tasks Vision `PoseLandmarker`** (`@mediapipe/tasks-vision`), *lite* model, single pose, GPU delegate with automatic CPU fallback |
| State (UI only) | Small store (zustand or equivalent) bridging game state to React HUD and menus |
| Audio | Web Audio API, **procedurally synthesized** SFX and music. No audio files. |
| Tests | Vitest for gesture engine, track generator and collision logic |
| Persistence | `localStorage` (high score, settings, calibration profile) |

**Offline requirement (important).** Do not load the WASM runtime or the `.task` model from a CDN. Vendor them:
- Copy `node_modules/@mediapipe/tasks-vision/wasm/*` to `public/mediapipe/wasm/` (add a script that does this on `postinstall`).
- Commit `pose_landmarker_lite.task` to `public/models/`. Download it once at development time and document the source in the README.
- Load both from relative URLs. The game must work after the first page load with the network disabled. Optionally add a simple service worker that caches the app shell.

Note: `getUserMedia` requires `localhost` or HTTPS. Document this in the README.

---

## 3. Architecture

### 3.1 Pipeline

```
Webcam <video>
  → CameraSource            (getUserMedia, device selection, mirrored)
  → PoseEstimator           (MediaPipe, ~30 Hz, requestVideoFrameCallback)
  → LandmarkFilter          (One-Euro smoothing, visibility gating)
  → GestureEngine           (calibration + deterministic detectors)   ← reusable, game-agnostic
  → ControlSnapshot + GestureEvents
  → InputAdapter (runner)   (maps gestures → RunnerCommands)          ← the ONLY bridge
  → Game core               (fixed-timestep simulation + three.js renderer)
```

### 3.2 Hard module boundaries

```
src/
  pose/                 # Webcam + landmark acquisition. No gesture or game knowledge.
    CameraSource.ts
    PoseEstimator.ts    # wraps MediaPipe; emits PoseFrame
    OneEuroFilter.ts
    landmarks.ts        # index constants (NOSE=0, L_SHOULDER=11, R_SHOULDER=12, L_HIP=23 ...)
    types.ts            # PoseFrame, Landmark
  gestures/             # Game-agnostic. Imports ONLY from pose/types.
    GestureEngine.ts
    Calibration.ts
    detectors/
      LateralZoneDetector.ts
      JumpDetector.ts
      CrouchDetector.ts
      HandsUpHoldDetector.ts   # used for "pause" by the runner
    config.ts           # all thresholds, documented
    types.ts
    replay/             # record/replay of PoseFrame sequences for tests
  input/                # The bridge layer.
    InputSource.ts      # interface the game consumes
    GestureInputSource.ts
    KeyboardInputSource.ts   # arrows/WASD/space/ctrl: dev + accessibility fallback
    CompositeInputSource.ts
  game/                 # Pure game. Imports input/InputSource only. NO import from pose/ or gestures/.
    core/ (Game.ts, loop.ts, state machine, events)
    world/ (TrackGenerator, Chunk, patterns, Obstacle, Collectible, Environment)
    player/ (PlayerController, RunnerModel, animation)
    systems/ (collision, difficulty, scoring, camera rig, particles, audio)
    config.ts
  ui/                   # React: screens, HUD, calibration, debug overlay, settings
  store/
  main.tsx, App.tsx
```

Enforce the boundaries with an ESLint `no-restricted-imports` rule (or an equivalent check) so `game/` can't import `pose/` or `gestures/`, and `gestures/` can't import `game/`. Document the rule in the README.

### 3.3 Core contracts (implement these shapes)

```ts
// pose/types.ts
export interface Landmark { x: number; y: number; z: number; visibility: number } // normalized 0..1, image space
export interface PoseFrame { t: number /* ms, performance.now() */; landmarks: Landmark[]; worldLandmarks?: Landmark[] }

// gestures/types.ts
export type ZoneX = -1 | 0 | 1;                       // left, center, right (already un-mirrored: -1 is the player's left)
export interface ControlSnapshot {
  t: number;
  tracking: 'ok' | 'degraded' | 'lost';
  zoneX: ZoneX;               // continuous state, hysteresis applied
  lateral: number;            // normalized offset in shoulder-widths (for debug / UI)
  posture: 'standing' | 'crouching';
  verticalOffset: number;     // normalized, for debug / UI
}
export type GestureEvent =
  | { type: 'jump'; t: number; strength: number }
  | { type: 'crouchStart'; t: number } | { type: 'crouchEnd'; t: number }
  | { type: 'zoneChange'; t: number; from: ZoneX; to: ZoneX }
  | { type: 'handsUpHold'; t: number }
  | { type: 'calibrationChanged'; t: number };

export interface GestureEngine {
  process(frame: PoseFrame | null): ControlSnapshot;   // pure, deterministic, no timers
  drainEvents(): GestureEvent[];
  calibrate(frames: PoseFrame[]): CalibrationResult;
  reset(): void;
}

// input/InputSource.ts  (the only thing the game sees)
export interface RunnerInput {
  targetLane: -1 | 0 | 1 | null;  // desired lane (null = no preference)
  jumpPressed: boolean;           // edge-triggered; consumed by the game
  slideHeld: boolean;             // level-triggered
  pausePressed: boolean;
  trackingState: 'ok' | 'degraded' | 'lost' | 'n/a';
}
export interface InputSource { poll(now: number): RunnerInput }
```

The gesture engine must be **deterministic and pure given a sequence of `PoseFrame`s** (inject time through `frame.t`, never `Date.now()` inside detectors). This is what makes it unit-testable and reusable.

---

## 4. Pose Estimation Layer

- Request `getUserMedia({ video: { width: 640, height: 480, frameRate: { ideal: 30 } } })`. Use 640×480 or lower, because more resolution only adds latency.
- Drive inference from `video.requestVideoFrameCallback` (fall back to `requestAnimationFrame`). Never queue inference. If a frame is still being processed, drop the new one.
- Run `PoseLandmarker` in `VIDEO` mode with `numPoses: 1`, delegate `GPU` with fallback to `CPU`.
- Target ≥ 24 pose updates per second on an average laptop. Show the measured pose FPS and inference ms in the debug overlay.
- Run inference on the main thread first (simplest, most robust). Isolate it behind `PoseEstimator` so a Worker version can be swapped in later without touching other layers.
- Apply a **One-Euro filter** per landmark coordinate (low `minCutoff` for jitter at rest, `beta` high enough to follow fast jumps). Expose its parameters in `gestures/config.ts` or `pose/config.ts`.
- Ignore landmarks with `visibility < 0.5`. If the nose or either shoulder is invisible for > 400 ms, set tracking to `lost`. A single missed frame must not drop the state.
- **Upper-body first.** Laptop cameras often cut the player off at the waist or chest. The *required* landmarks are **nose, left and right shoulders**. Hips, knees and wrists are optional extras that improve confidence but must never be required for the core controls.

---

## 5. Gesture Engine (deterministic, no ML beyond landmarks)

### 5.1 Normalization

All signals are expressed in **shoulder-width units** (`SW` = distance between shoulder landmarks at calibration, tracked continuously with slow smoothing). This makes thresholds independent of the player's distance to the camera and body size.

Primary signals:
- `cx` = x of the shoulder midpoint (mirrored so that moving to the player's left gives a negative value, matching the on-screen mirror preview).
- `cy` = y of the shoulder midpoint (up is positive after inversion).
- `head` = nose y (secondary confirmation).

### 5.2 Calibration ("Stand Here" step)

1. Show the live camera preview with a framing guide: head and shoulders inside a target box, and the player roughly centered.
2. Check conditions: required landmarks visible, shoulder width between 12% and 45% of frame width (not too far or close), player roughly centered. Give plain-language fixes ("Move back a little", "Step to the middle").
3. Hold still for 1.5 s. Take the **median** of `cx`, `cy`, `SW` over those frames as the neutral profile `{cx0, cy0, SW0}`.
4. Store the profile in memory. Persist the preferred sensitivity only, not the profile, because the position differs per session.
5. **Slow drift correction.** While the player is in the neutral zone and not moving, the engine nudges `cx0`/`cy0` toward the current value (time constant ≈ 8 s) so slow posture or camera drift never breaks controls. Never drift while a gesture is active.
6. A "Recalibrate" button is available in Pause and Settings. Also offer the shortcut `R` while paused.

### 5.3 Lateral control: three-zone absolute lane mapping

Lane control is a **position**, not a swipe. The player steps or leans to a side, and the runner goes to that lane.

- `lateral = (cx − cx0) / SW0`
- Zones with **hysteresis**: enter the left zone at `lateral < −0.55`, leave it back to center at `> −0.30`. The right zone mirrors this. Defaults are placeholders to be tuned, and a sensitivity setting scales them (0.7×–1.4×).
- The zone must be stable for **2 consecutive frames** (~65 ms) before it changes, to reject single-frame jitter.
- The game moves the runner **one lane at a time** toward `targetLane`, with each lane change taking ~140 ms. If the player is in the right zone and the runner is in the left lane, it passes through the center. This allows "quick double step" in a natural way.
- Leaning and side-stepping must both work, since both move the shoulder midpoint. Do not require the feet.

### 5.4 Jump detection

A jump is a **fast upward movement of the shoulders/head**. Detect both rising velocity and displacement:

- Maintain a rolling window of `cy` (last 300 ms).
- Fire `jump` when **all** hold:
  - `(cy − cy0) / SW0 > 0.22` (displacement above neutral; tune), **and**
  - upward velocity over the last ~120 ms > ~`1.6 SW/s`, **and**
  - posture is not `crouching`, **and**
  - not in the refractory period (**450 ms** after the last jump), **and**
  - not within **350 ms after `crouchEnd`**. Standing back up after a crouch must never be read as a jump.
- `strength` = peak displacement (reserved for future use; the runner ignores it).
- Standing on tiptoe or slowly rising must not trigger it, which is why velocity is required.
- Don't wait for the apex. Fire on the **rising edge** once thresholds are met, to minimize latency.

### 5.5 Crouch detection

- Crouching is `(cy − cy0) / SW0 < −0.35` (shoulders drop), held for 2 frames. Exit when `> −0.18` (hysteresis).
- It is a **state** (`crouching`), with `crouchStart`/`crouchEnd` events.
- A lateral lean and a crouch can coincide, and each channel is processed independently.
- Forward-lean tolerance: if the nose drops much more than the shoulders (head-down look), do not count it as a crouch.

### 5.6 Pause gesture (optional but implement it)

`HandsUpHoldDetector`: both wrists above the nose (visibility ≥ 0.6) held for **1.0 s** → `handsUpHold`. The runner maps it to pause. Show a radial progress ring while it charges. Skip silently if the wrists are not visible, because Esc/P and click always work.

### 5.7 Required engine properties

- Every threshold lives in `gestures/config.ts` with a comment explaining the unit, tuning direction, and default.
- Detectors are independent classes with `update(signals, t)` and `reset()`.
- A **replay harness**: `PoseFrame[]` JSON in → `GestureEvent[]` out. Write Vitest cases using synthetic generated sequences (sine-wave sway, a jump arc, a crouch, noise, dropouts, tiptoe, slow drift) asserting:
  - a jump arc fires exactly one `jump`
  - crouch → stand does not fire `jump`
  - Gaussian jitter at 1–2% of SW causes zero false events over 60 s
  - dropout of 5 frames doesn't change state
  - a 500 ms dropout does not produce `lost`, and a 600 ms dropout does

---

## 6. Input Adapter & Game-Side Forgiveness

`GestureInputSource` converts engine output to `RunnerInput`. The game adds:

- **Jump buffer:** a `jumpPressed` that arrives up to **150 ms** before the runner is able to jump (for example just before landing) is held and executed on landing.
- **Slide buffer:** the same for slides, **120 ms**.
- **Lane-change forgiveness:** if a lane change is requested while the runner is mid-jump, it is allowed (air control). If a lane is blocked by a wall *side-on*, the runner bumps back (see collisions).
- **Coyote time:** 80 ms of allowed jump after a run-off (not very relevant on a flat track, but it keeps the controller reusable).
- **Slide semantics:** a slide starts on `crouchStart`, and the slide **lasts at least 0.45 s** even if the player rises quickly (so the player can't cheat out of an overhead obstacle with a late stand-up, but also doesn't get hit when the real posture is brief). The runner stays low while `slideHeld` remains true, up to **1.4 s**, then auto-stands (the player must crouch again to slide again).
- **Jump and slide cancel:** crouching in mid-air makes the runner **fast-fall** and then slide (Subway-Surfers-like fluidity, implemented in your own way). A jump during a slide cancels the slide.
- **Keyboard fallback** (`KeyboardInputSource`): ←/→ or A/D set one-lane steps, ↑/W/Space jump, ↓/S/Ctrl slide, Esc/P pause. `CompositeInputSource` merges both so devs and accessibility users can play with no webcam. The menu includes "Play with keyboard (no camera)".

---

## 7. Game Design

### 7.1 Setting & identity — *LUMEN DASH*

**Fiction:** You are a *Lumen Courier*, sprinting along a ruined **causeway of glass and stone** suspended over a dusk-lit canyon of glowing crystal. Fragments of stored daylight ("**motes**") float along the path. A pursuing **Hollow**, a drifting shadow-storm, is always behind you.

**Visual direction (low-poly, flat shaded, atmospheric):**
- Palette: deep indigo → teal sky gradient, warm amber lights, magenta and cyan crystal accents, off-white path. Strong contrast between the path (readable) and the background (muted).
- Exponential fog matched to the sky color, so the track pops into view smoothly. Use no hard pop-in.
- Directional "sunset" light plus hemisphere ambient. Cheap fake shadows (blob shadow under the runner and obstacles). Real shadow maps are optional and must be off by default.
- Gentle bloom-like glow on motes and crystals through emissive materials and additive sprites (post-processing optional and only if 60 fps holds).
- Runner: stylized character built from primitives (capsule torso, sphere head, tapered limbs, a trailing scarf made from a few spring-simulated segments). Procedural animation for **run cycle, jump (tuck), slide (low glide), stumble, and idle**. Give it a distinctive silhouette and a glowing chest "lantern" in the accent color.
- Environment scrolls by with parallax canyon walls, floating crystal clusters, drifting dust particles, and hanging lanterns. Add 2–3 **biome segments** (Causeway, Crystal Gorge, Ember Bridge) that blend through palette and fog changes every ~600 m.
- Use no external 3D models or textures. If you need textures, generate them with a canvas at startup.

**Audio (procedural):** footstep ticks synced to the run cycle, mote chime with rising pitch on streaks, jump whoosh, slide hiss, hit thud, game-over sting, UI blips, and a soft evolving ambient pad plus a light percussive loop that intensifies with speed. A master volume and mute are in the settings. Audio starts only after a user gesture.

### 7.2 Track & lanes

- 3 lanes, lane width **2.4 units**, lane centers at x = −2.4, 0, +2.4.
- The track is built from **chunks** of 24 units each, spawned ahead to a draw distance of ~160 units and recycled behind the player (object pooling, no per-frame allocation, `InstancedMesh` for repeated geometry).
- Use a **floating origin** or periodic world re-centering so float precision doesn't degrade after long runs (the player stays near z=0 and the world moves toward the camera, or shift everything back every 1000 units).
- Optionally, the path gets gentle visual curves (cosmetic only, with no gameplay effect) and slight elevation rolls. Keep gameplay lanes straight.

### 7.3 Obstacles (original designs)

| Obstacle | Behavior | Counter |
|---|---|---|
| **Cairn / low barrier** (knee-high glowing stone arc) | Blocks a single lane, passable by jumping | Jump |
| **Fallen beam / overhead gate** (a hanging crystal lintel, a clearance of ~1.1 units above the ground) | Blocks a lane at head height | Slide |
| **Monolith** (full-height stone pillar) | Fully blocks a lane | Change lane |
| **Wide wall with a gap** | Blocks two lanes | Change lane |
| **Crack** (a gap in the causeway floor, 1 lane wide, ~4 units long) | Falling = stumble | Jump |
| **Swinging lantern** (pendulum at head height in a lane, cyclic timing) | Time-based | Slide or lane change |

Clearly telegraph each type by silhouette and color (jump = amber low shapes, slide = cyan overhead shapes, lane-change = magenta tall shapes). Colorblind-safe, because shape differences must be sufficient on their own.

### 7.4 Collectibles

- **Motes:** glowing orbs placed in lines of 5–10, arcs over jump obstacles (collecting means you jumped), and trails under slide gates. +10 points each.
- **Mote streak:** consecutive motes with no gap > 1.2 s build a **streak**. Every 10 in a streak raises the multiplier (×1 → ×4), and a hit resets it.
- **Prism (rare):** a large crystal worth 100 points, placed in risky lanes.
- **Stretch goal (only after everything else is done):** a **Magnet** and a **Shield** power-up, 8 s each, with a HUD timer.

### 7.5 Run rules, health and collisions

- The runner starts with a **2-hit buffer**: the first collision causes a **stumble** (speed ×0.6, a brief camera shake, 1.5 s of invulnerability with a blink, the Hollow visibly closes in). The Hollow retreats gradually over 10 s of clean running. A second hit while the Hollow is close ends the run.
- Hitting a **Crack** or a **head-on Monolith/Wall** while the Hollow is already close ends the run.
- **Side-clip:** if the runner clips an obstacle while changing lanes, it is bumped back to its original lane and takes a stumble, rather than dying.
- Collision uses simple **AABBs** in lane space, with the player's hitbox shrunk ~15% for forgiveness. Run the checks only against obstacles within ±6 units of the player.
- On a game over: slow-motion for 0.8 s, the camera pulls back, then the Game Over screen.

### 7.6 Movement tuning (constants in `game/config.ts`)

| Param | Value |
|---|---|
| Start speed | 11 u/s (the first 8 s are an easy ramp-in with only motes and single obstacles) |
| Max speed | 28 u/s, with an exponential-ish ramp reaching ~90% after ~4 min |
| Lane change time | 140 ms (eased) |
| Jump | apex 1.9 u, air time ~0.75 s (scales slightly with speed so clearance is constant in *distance*) |
| Slide | min 0.45 s, max 1.4 s |
| Gravity | tuned from jump height and time, not copied from defaults |

Simulation uses a **fixed timestep** (e.g. 120 Hz) with render interpolation, so the physics stays stable at 60 Hz or 144 Hz displays. The simulation is deterministic given a seed and an input log.

### 7.7 Difficulty & fair generation

- A **pattern-based generator**. Hand-author ~25–30 patterns (as small data structures: rows of lane cells with obstacle types and mote placement), grouped into **difficulty tiers 1–5**. Pick patterns with a **seeded RNG**, weighted by the current tier. Mirror patterns randomly for variety.
- Tier advances with distance (about every 400 m) and also unlocks the new obstacle types gradually. Obstacle types are introduced one at a time with a safe, obvious first encounter.
- **Fairness rules (enforce them as code, and test them):**
  1. **There is always a legal path.** Between consecutive rows, at least one lane is passable using only actions that are physically possible given the time between rows.
  2. **Reaction/action time budget.** The minimum time gap between consecutive *action requirements* is `max(1.4 s − 0.15 s · (tier − 1), 0.8 s)`, which is 1.4 s at tier 1 and 0.8 s from tier 5 onward. These values are generous because **a human body is slower than a button press**. The generator converts the time to a distance using the current speed.
  3. Never require a **jump → slide** or **slide → jump** transition in less than 0.9 s.
  4. Never require a lane change of **2 lanes** in less than 1.0 s.
  5. Never place two overhead and ground obstacles such that the player has no time to stand up in between.
  6. Rest chunks (motes only) appear periodically, so the player can breathe and re-center.
- Write a Vitest "fuzz" test: generate 10,000 chunks across seeds and tiers and verify that the fairness rules hold with a path-search over lane/time.

### 7.8 Scoring & HUD

- `score = floor(distance_m) + motes·10·multiplier + prisms·100`.
- High score is persisted. A "New best!" banner appears on the Game Over screen.
- **HUD (in-run, minimal and legible):** score (top center), distance m, mote count with streak/multiplier, a hit-buffer indicator (2 pips), the current speed tier, and a **small mirrored webcam picture-in-picture** (toggleable, corner, ~200 px) with a skeleton overlay and a colored border: green = tracking ok, amber = degraded, red = lost. Next to it is a minimal **gesture indicator**: a 3-segment lane bar (shows `zoneX`), and icons that flash on jump/crouch recognition. This feedback matters because it lets players *learn* the controls.
- Use a **CSS-based HUD overlay** above the canvas (React), and read the game state from the store at ≤ 15 Hz so React re-renders never touch the frame loop.

---

## 8. Camera (game camera)

- Third-person chase: behind and above (≈ 5 u back, 3.2 u up, looking 8 u ahead), with a FOV of 62° that widens with speed up to 72°.
- Smoothly follows the runner's lateral position at ~40% (so lane changes feel dynamic, but the lanes stay readable).
- Subtle roll into lane changes, a small bob on landing, shake on a stumble, and a pull-back on game over. Respect the `reducedMotion` setting by disabling shake, roll and FOV effects.

---

## 9. Screens & Flow

```
Boot/Loading → Menu → [Camera permission → Calibration → Gesture tutorial] → Countdown → Playing ⇄ Paused → Game Over → (Restart | Menu)
```

1. **Loading:** load the model and WASM, with a progress bar. Show a clear error with retry if the model fails.
2. **Main menu:** a game logo and title (original wordmark in the glow style), a slowly running demo of the runner on an idle track in the background, buttons: **Play with Camera**, **Play with Keyboard**, **How to Play**, **Settings**. Show the high score.
3. **Camera permission:** a friendly explanation that video **never leaves the device**. Handle denied, no device, device busy, and insecure context with specific messages and a keyboard-mode fallback.
4. **Calibration:** see Section 5.2, with big clear guidance text.
5. **Gesture tutorial (≈ 20 s, skippable and remembered):** four steps, each of which must be successfully performed once to advance, with an animated ghost silhouette that demonstrates the move: *step/lean left* → *step/lean right* → *jump* → *crouch*. Show a green check on success. Provide the "Having trouble?" tips (lighting, distance, plain background).
6. **Countdown:** 3-2-1-GO, during which the player can see themselves.
7. **Pause:** Esc / P / hands-up hold / tracking lost > 1.5 s / tab hidden (auto-pause). Options: Resume (with a 3-s countdown, so the player can get back into the position), Recalibrate, Settings, Quit to menu.
8. **Tracking-lost overlay:** "We lost you. Step back into the frame." The game pauses automatically and resumes with a countdown after tracking is `ok` for 1 s.
9. **Game over:** score, distance, motes, best score, "New best", **Run Again** (primary, gesture-friendly: make it also triggered by holding hands up for 1 s) and Menu.
10. **Settings:** camera device, mirror preview, show camera PiP, show debug overlay, gesture sensitivity (0.7–1.4), master volume, music/SFX toggles, reduced motion, graphics quality (Low/Med/High: pixel ratio, particles, fog distance), and "Reset calibration".

### Debug overlay (toggle with `F3` or in settings)
Pose FPS and inference ms, the end-to-end gesture latency estimate, landmarks and the skeleton drawn, `lateral` and `verticalOffset` as live bars with the threshold lines drawn, recent gesture events log, and the tracking state. This is essential for tuning, so build it early (Milestone 2).

---

## 10. Performance Budget

- The render loop holds **60 FPS** on integrated-GPU laptops at the default (Medium) quality, while the pose model also runs. Pose inference is never allowed to stall rendering.
- `renderer.setPixelRatio(Math.min(devicePixelRatio, 1.5))` by default.
- Zero allocations in the hot loop (reuse vectors/objects), pooled chunks/obstacles/motes, instanced repeated meshes, merged static geometry where possible, no per-frame `new`.
- Auto quality: if the frame time averages > 20 ms for 3 s, step the quality down one level and notify the user.
- Dispose geometries/materials/textures correctly on restart. Restarting 20 times must not grow memory.
- Gesture-to-pixel latency target: **< 150 ms median** (camera frame → on-screen runner reaction). Measure it in the debug overlay by timestamping `frame.t` and the render frame in which the resulting command is applied.

---

## 11. Quality, Accessibility & Robustness

- Keyboard-only play is fully supported.
- Sensitivity control and reduced-motion mode.
- Color is never the only signal (shapes and icons carry meaning too).
- Visible and readable HUD text at a minimum of 16 px, with high contrast.
- Handle: camera denied/unplugged mid-game (auto-pause and a message), tab backgrounded, window resized, a WebGL context loss (show a message and offer a reload), and the GPU delegate failing (silently use the CPU).
- The page shows no console errors in normal use.
- Include a short `README.md`: setup, offline asset steps, controls, tuning guide for `gestures/config.ts`, architecture diagram, and the module-boundary rules.
- Include `docs/GESTURE_ENGINE.md` which describes how to reuse the `pose/` + `gestures/` modules in another game (the public API, how to register a new detector, and the replay-testing workflow).

---

## 12. Coding Standards

- TypeScript `strict`, no `any` in `pose/`, `gestures/`, and `game/core`.
- Small files, single responsibility, named constants (no magic numbers outside `config.ts` files).
- Deterministic seeded RNG utility (mulberry32 or similar) used for all generation. Support a `?seed=123` URL parameter for reproducing a run.
- Use a typed event emitter for game events (`mote`, `hit`, `jump`, `slide`, `gameOver`, `tierUp`) which the audio, particle and HUD systems all subscribe to. Systems don't call each other directly.
- Commit-quality code: comments only where the intent isn't obvious, particularly for every non-obvious threshold.

---

## 13. Suggested Gesture Tuning Defaults (starting points; make them easy to tweak)

| Name | Default | Notes |
|---|---|---|
| Lateral enter / exit | ±0.55 / ±0.30 SW | × sensitivity |
| Zone stability | 2 frames | |
| Jump displacement | +0.22 SW | |
| Jump velocity | 1.6 SW/s over 120 ms | |
| Jump refractory | 450 ms | |
| Post-crouch jump lockout | 350 ms | |
| Crouch enter / exit | −0.35 / −0.18 SW | |
| Hands-up hold | 1000 ms | |
| Lost-tracking timeout | 400 ms (state) / 1500 ms (auto-pause) | |
| One-Euro | minCutoff 1.2, beta 0.02 (tune with the overlay) | |
| Drift time constant | 8 s | |

---

## 14. Milestones (each ends with a runnable build)

**M1 — Game core with keyboard.** Vite/React/TS/Tailwind setup, three.js scene, fixed-step loop, runner with run/jump/slide/lane-change, chunked track and pooling, all obstacle types, motes, collisions with the hit buffer, scoring, HUD, menu → play → pause → game over → restart. Keyboard input through `InputSource`. *Already fun and fair at this stage.*

**M2 — Pose pipeline + debug overlay.** `CameraSource`, `PoseEstimator`, vendored offline MediaPipe, One-Euro filter, skeleton drawing, FPS/latency metrics, permission and error UX.

**M3 — Gesture engine.** Calibration, lateral zones, jump, crouch, hands-up, drift correction, config, replay harness and unit tests. `GestureInputSource` wired to the game. Play with the body end to end.

**M4 — Flow and onboarding.** Calibration screen, gesture tutorial, countdowns, tracking-lost auto-pause, PiP and gesture indicator, settings, persistence.

**M5 — Fair generation & difficulty.** Pattern library, tiers, fairness rules + fuzz tests, speed ramp, rest chunks, biomes.

**M6 — Visual and audio polish.** Runner model and animation, the Hollow, environment dressing, fog/palette biomes, particles, procedural audio, camera effects, reduced-motion, quality auto-scaling.

**M7 — Hardening.** Memory-leak check across restarts, offline test, error paths, docs (`README.md`, `docs/GESTURE_ENGINE.md`), lint rule for the module boundaries, and final tuning.

---

## 15. Acceptance Criteria

**Functional**
- [ ] A new player can go from page load to running in < 60 s using only the on-screen instructions.
- [ ] Step/lean left and right reliably (≥ 95% in a manual 40-attempt test) switch lanes, with no "double-lane" misfires.
- [ ] A normal jump triggers exactly one jump (≥ 95%), and standing up from a crouch triggers **zero** jumps in 20 trials.
- [ ] Crouching triggers a slide within 150 ms median, and the slide is held while the player stays low.
- [ ] Standing still and breathing/fidgeting for 60 s produces zero spurious gesture events.
- [ ] The game is playable for 5+ minutes while speed and difficulty rise, with no impossible sections (fuzz tests pass).
- [ ] Pause, resume (with countdown), restart, and the game-over flow all work via both the webcam and the keyboard.
- [ ] Losing tracking (covering the camera, or leaving the frame) pauses the game with a clear overlay, and recovery resumes it.
- [ ] The high score and settings persist across reloads.

**Technical**
- [ ] After the first load, with the network disabled, the game fully works (verify in DevTools "Offline").
- [ ] There are zero network requests to third-party hosts during gameplay.
- [ ] 60 FPS at the default quality on a mid-range laptop with pose running. Pose ≥ 24 Hz.
- [ ] Median gesture-to-screen latency < 150 ms as shown by the overlay.
- [ ] 20 consecutive restarts show no memory growth trend.
- [ ] `pose/` and `gestures/` compile and test without importing anything from `game/`, `ui/` or `three`. `game/` doesn't import from `pose/` or `gestures/` (enforced by lint).
- [ ] `npm run build` and `npm test` both pass. The TypeScript strict mode has no errors.

**Experience**
- [ ] It has a recognizable, original visual identity (palette, runner, environment, logo, audio), and no assets or names are copied from any existing game.
- [ ] It feels like the body controls the runner. Controls are forgiving, and failures feel like the player's mistakes rather than the tracker's.

---

## 16. How to Report Back

At the end of each milestone, give a brief summary of what works, what you measured (pose FPS, latency, frame time), known issues, and the tuning values you changed from the defaults in this brief. If any requirement in this brief is impossible or has a clearly better alternative, state the reason, choose the alternative, and continue. Do not stop to ask.
