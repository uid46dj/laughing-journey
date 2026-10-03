# Lumen Dash — Jog-speed (2nd phone) + chasing monster

## Context

Lumen Dash is a 3D endless runner (three.js, fixed 120 Hz sim) controlled by body pose
via webcam/MediaPipe. Speed today is deterministic: `speedAt(distance)` (src/game/config.ts:8),
and `TrackGenerator` plans obstacle spacing from that exact curve (src/game/TrackGenerator.ts:95,169).
"The Hollow" exists as a `closeness` value (0..1): hits raise it, it creeps in as two
screen-edge lobes (Game.ts `buildHollow`), lethal on a second hit while close.

Phone-as-webcam already exists: `tools/phonecam-server.mjs` (relay, port 8080) +
`tools/phonecam-phone.html` posts JPEG frames; `src/cam/PhoneCamera.ts` patches
`getUserMedia` globally — so a second video stream would conflict. The input contract is
`RunnerInput` (src/game/InputSource.ts), merged by `CompositeInputSource`.

## Locked decisions

1. **Leg phone computes cadence itself** (frame-differencing motion detection on the lower
   half of its camera frame — no ML) and sends only the number to the existing relay over
   USB (`adb reverse`). Both phones on USB, same relay port, different paths.
2. **Bounded speed multiplier**: jog cadence scales speed within `[minMult, maxMult]`
   around the auto curve. Track generator plans spacing for the worst case (maxMult) so
   jump/slide timing stays fair at any cadence.
3. **Monster unifies with the Hollow**: gains when jogging slower than target cadence AND
   on obstacle hits; falls back when jogging faster. Caught (closeness ≥ 1) = game over.
   The 3D monster replaces the old screen-edge lobes; the CSS vignette stays.
4. **Keyboard mode / no leg phone**: unchanged — auto-speed, neutral multiplier, monster
   gains only from hits.
5. **UI**: live cadence meter, monster-proximity bar (replaces the 2 diamond pips),
   live cadence bar on the leg phone page, How-to/Menu updates, countdown hint.

## Implementation tasks (ordered)

### 1. Relay: cadence endpoint + leg phone page
- `tools/phonecam-server.mjs`:
  - `POST /cadence` — store newest `{c, v, ts}` (cadence steps/s, legs-visible flag).
  - `GET /cadence` — long-poll, same waiter/notify pattern as `/latest`, JSON response.
  - Serve `GET /legs` → new `tools/legcam-phone.html`.
- `tools/legcam-phone.html` (new, styled like phonecam-phone.html):
  - `getUserMedia` (rear cam), `requestVideoFrameCallback` loop.
  - Per frame: draw to 160×120 canvas → grayscale → mean abs diff vs previous frame,
    **lower 60% of frame only** → motion energy. EMA (α≈0.4).
  - Adaptive threshold ≈ 1.8× slow-EMA baseline (τ≈3 s); peak = energy above threshold
    with ≥250 ms refractory. Cadence = peaks in trailing 1 s window.
  - `visible` = recent energy above noise floor (distinguishes "standing still" from
    "camera blocked / no legs").
  - POST `{c, v}` to `/cadence` every 200 ms. Live cadence bar with target marker
    (2.5 steps/s) and green "fast" zone (≥3.0). Start/Stop, camera selector, flip-vertical.

### 2. PC-side jog source
- `src/cam/JogSource.ts` (new): long-polls `GET /cadence` from the relay base URL
  (default `http://127.0.0.1:8080`, same as PhoneCamera). EMA on cadence (α≈0.35).
  Implements `InputSource`: `poll()` returns `{...NEUTRAL_INPUT, jogCadence}` where
  `jogCadence` is `null` when disabled / no update for 1.5 s / legs not visible.
  Unreachable relay → silently neutral (plain `npm run dev` has no relay).
- `src/game/InputSource.ts`: add `jogCadence: number | null` to `RunnerInput`,
  `NEUTRAL_INPUT`, and `CompositeInputSource` (last non-null wins, like `targetLane`).

### 3. Game: speed multiplier + monster dynamics
- `src/game/config.ts` — new tunables:
  ```ts
  export const JOG = {
    target: 2.5,        // steps/sec at neutral (1.0×)
    sensitivity: 0.35,  // Δmult per step/sec off target
    minMult: 0.8, maxMult: 1.3,
    gainRate: 0.30,     // closeness/s at full-slow (standing still catches in ~17 s)
    recoverRate: 0.45,  // closeness/s at full-fast (recovers in ~7 s)
    signalTimeoutMs: 1500,
  };
  export const planSpeedAt = (d: number) => speedAt(d) * JOG.maxMult;
  ```
  Multiplier: `mult = clamp(1 + (cadence − target) × sensitivity, minMult, maxMult)`,
  EMA-smoothed in-game (damp k≈4).
- `src/game/TrackGenerator.ts`: use `planSpeedAt` instead of `speedAt` for the two
  distance-gap computations (lines 95, 169) so timing rules hold at any multiplier.
  Side effect (accepted, tunable via `maxMult`): default pacing gets ~maxMult× more
  time per obstacle at neutral speed.
- `src/game/Game.ts`:
  - `stepPlaying`: `this.speed = speedAt(distance) × jogMult × stumbleMult` (stumbleSlow
    composes as today).
  - Jog pressure (only in `playing`, after countdown): `mult < 1` →
    `closeness += (1−mult) × gainRate × dt`; `mult > 1` →
    `closeness −= (mult−1) × recoverRate × dt`; clamp [0, 1]. `cadence == null` → no
    pressure, mult drifts to 1.
  - Death: continuous check `closeness ≥ 1` → `die()` ("caught"). Keep existing
    two-hit lethality in `onHit` (second hit while `closeness ≥ hollowLethal`).
  - Replace `buildHollow` lobes with the Monster (task 4). Keep CSS vignette.
  - `HudState` += `jogCadence: number | null`, `jogMult: number`.

### 4. Monster model
- `src/game/Monster.ts` (new, primitives only — consistent with RunnerModel/objects.ts):
  dark icosahedron core, cone spikes, two glowing eyes, maw, additive magenta shell.
  Animation: bob/sway/breathing; lunge oscillation when `closeness > 0.8`; `lunge()`
  on catch (z → 0.9 over 0.3 s).
  Position: visible when `closeness > 0.05`; `z = 4.6 − 3.0 × closeness` (looms from
  near-camera to right behind the runner), `x = runner.x × 0.8`, scale grows with closeness.
- `Game.ts`: instantiate, update in `render()`, `visible` tied to closeness/state.

### 5. Wiring
- `src/app/Controller.ts`: create `JogSource`; include it in the `CompositeInputSource`
  for camera mode (`[gestureInput, jog, keyboard]`). Start/stop polling with the new
  `jogPhone` setting. After calibration, toast leg-phone status (non-blocking).
- `src/app/store.ts`: `Settings.jogPhone: boolean` (default **true** — silent neutral
  fallback when absent); `hudStore` += `jogCadence`, `jogMult`.
- `src/ui/Settings.tsx`: toggle "Second phone as jog sensor".

### 6. UI
- `src/ui/Hud.tsx`:
  - `CadenceMeter` (only when `h.jogCadence != null`): live steps/s + bar with target
    band, red→amber→green.
  - `MonsterBar` replaces `Pips`: proximity bar with monster glyph, amber→red, pulses
    when `closeness > 0.7`.
  - Countdown hint: "Jog in place — faster jog = faster run!" when jogPhone enabled.
- `src/ui/Menu.tsx` (HowTo + tagline): new cards for "Jog in place" and "The Hollow
  monster"; leg-phone setup steps (open `http://localhost:8080/legs` on the 2nd phone);
  update the one-hit text to describe monster pressure.
- `tools/dev-with-phonecam.mjs`: run `adb reverse` for **every** connected device (loop
  `adb devices`), keep watching for new devices; banner prints both URLs
  (`/` body cam, `/legs` cadence).
- `README.md`: two-phone setup section.

## Risks
- **False cadence** from other motion in frame → lower-region-only analysis + adaptive
  threshold; the phone page's live meter lets the user verify before playing.
- **Pacing side-effect** from worst-case track planning → tunable via `JOG.maxMult`
  (lower = closer to today's pacing, less headroom).
- **"No legs visible" vs "standing still"** → `visible` flag from motion-energy noise
  floor; invisible ⇒ neutral (no unfair monster pressure).
- Two phones on one relay port need per-device `adb reverse` (handled in task 6).

## Validation
1. `npm run typecheck`.
2. `npm run dev` — keyboard mode: speed curve, monster-from-hits, and game-over flow
   unchanged; no relay errors in console.
3. `npm run dev:cam`, two phones: body phone opens `/`, leg phone opens `/legs`.
   - Cadence meter moves when jogging; speed (km/h in HUD) scales with cadence.
   - Stand still → monster approaches (~15 s to catch); jog fast → it falls back.
   - Obstacle hit → monster jumps closer; second hit while close → caught → game over.
4. Without a leg phone: `curl -X POST :8080/cadence` test values to verify PC polling;
   game stays neutral when `/cadence` is silent.
5. Fixed `?seed=` run: confirm obstacle gaps remain fair at max multiplier
   (jump↔slide transitions ≥ planned seconds at `planSpeedAt`).

## Open questions
None — all five design decisions resolved with the user.
