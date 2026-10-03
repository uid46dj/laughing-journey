# LUMEN DASH

A single-player 3D endless runner you control with your body through the webcam. Original world, runner, audio and obstacles.
Pose estimation runs **locally** (MediaPipe `PoseLandmarker`, lite model); gestures are recognised by a deterministic rule engine. No LLM, no cloud AI.

## Run

```
npm install
npm run dev      # http://localhost:5173  (camera needs localhost or https)
npm run build
```

Play with **Camera** (calibration → 4-step tutorial → run) or with the **Keyboard** (← → / A D, ↑ / W / Space, ↓ / S / Ctrl, Esc / P, F3 = debug overlay).

## Making it fully offline

The pose model and WASM runtime are loaded from `public/` if present, otherwise from a CDN on first load (jsDelivr / Google storage):

```
public/models/pose_landmarker_lite.task
public/mediapipe/wasm/*      # copy from node_modules/@mediapipe/tasks-vision/wasm
```

With those files in place no network access is needed. Model source:
`https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task`.
Keyboard mode never needs the network.

## Using your phone as the camera (no app)

The PC has no webcam, or you want a better one. `npm run phonecam` turns the phone's **browser**
into a webcam over USB — no app, no driver, no cloud, nothing installed on the phone.

```
[phone Chrome]  getUserMedia(rear cam) → JPEG frames → USB → [PC] canvas.captureStream()
                                                          → patched getUserMedia → PoseEstimator
```

The game is **not modified to do this**: `CameraSource` calls `navigator.mediaDevices.getUserMedia()`,
and `PhoneCamera` overrides just that function to return a `MediaStream` backed by a `<canvas>` it
repaints with each incoming frame. Everything downstream (pose, filter, gesture engine) is untouched.

### Start

One command does everything:

```bash
npm run dev:cam
```

That single command starts the relay server, starts Vite, auto-detects your phone over USB and
sets up `adb reverse`, then prints the URLs. **You do not need to run `adb reverse` yourself.**
Just plug the phone in whenever you like — a background watcher notices it and wires up the tunnel.
Ctrl+C stops all three and removes the tunnel.

Then **on the phone**: open `http://localhost:8080/` → tap **Start streaming** → allow camera.
On the PC: open `http://localhost:5173` → **Settings → Use phone as camera** (on) → *Play with Camera*.

| Command | What it does |
|---|---|
| `npm run dev:cam` | **everything** — relay + Vite + adb tunnel (use this) |
| `npm run dev` | just Vite (plain game dev, no phone) |
| `npm run phonecam` | just the relay server (if the game is already running) |
| `npm run phone-port` | open a port **on the phone** via `adb shell` (no app) |
| `npm run typecheck` | TypeScript check |

`adb reverse` makes the camera work at all: the phone reaches your PC at `localhost`, which browsers
treat as a **secure context**, so `getUserMedia` is allowed. A LAN IP would be blocked.

### Notes

* **Latency** is shown live in Settings. The relay keeps only the *newest* frame and the PC
  long-polls for it, so a slow frame is dropped rather than queued — you always get the most
  recent image instead of a backlog. Over USB expect roughly one frame (~33–100 ms), which is far
  below what pose tracking can perceive.
* Phone quality/fps are adjustable **on the phone page**; lower quality = lower latency.
* `adb reverse` resets on unplug/reboot — re-run it after reconnecting.
* The game runs the pose model on the PC, so the phone only needs to send pixels.

## Opening a port ON the phone (`adb forward`)

The camera setup above uses `adb reverse` (PC listens → phone connects). The opposite direction
is also available and needs **no app at all**: every Android device ships `toybox`, whose `nc`
can open a listening port and run a shell script as the connection handler.

```bash
npm run phone-port serve     # open port 9096 on the phone
npm run phone-port check     # GET it from the PC, print the response
npm run phone-port stop      # close it
```

Then `http://localhost:9096/` is served *by the phone itself*, reached over `adb forward`.
Verified on a Redmi 8 / Android 10 with `toybox nc`:

```
$ curl -i http://localhost:9096/
HTTP/1.1 200 OK
Content-Type: text/plain
Content-Length: 34

phone-port OK — toybox nc, no app
```

Three non-obvious things this depends on, each found the hard way:

* **`-L`, not `-l`.** Capital `-L` accepts repeated connections (a server loop). Lowercase `-l`
  serves exactly one client and then exits.
* **`-4` is required.** Without it toybox binds `tcp6 :::PORT`, which `adb forward` cannot reach.
* **The handler must not read the request.** Through `adb forward` the socket is half-closed, so
  stdin never reports EOF and a `while read` loop blocks forever — the client just times out.
  The handler therefore answers without draining the request, bounded by a background `dd`.

Under the hood: `toybox nc -4 -L -p 9096 sh /data/local/tmp/phonecam/handler.sh`, launched with
`nohup … &` because `adb shell` kills its children when the session ends.

```
Webcam → cam/CameraSource → cam/PoseEstimator → cam/LandmarkFilter (One-Euro)
       → cam/GestureEngine (calibration + detectors)                ← game-agnostic
       → cam/GestureInputSource → RunnerInput                      ← the only bridge
       → game/Game (fixed 120 Hz sim + three.js renderer)
```

The project is split into two flat folders, `src/game` and `src/cam`:

| Folder | Role | May import |
|---|---|---|
| `src/cam` | camera, pose landmarks, gesture recognition, preview drawing | nothing from `src/game` except `game/InputSource` |
| `src/game` | world, runner, collisions, audio, input sources, HUD state | never `src/cam` |
| `src/app` | `Controller` wires everything, stores | everything |
| `src/ui` | React screens/HUD | `app` |

`src/game` is fully self-contained: it builds and runs with zero camera code, which is why
keyboard mode never touches the network or MediaPipe.

## Tuning controls

All thresholds are in `src/cam/gestureConfig.ts` (units: shoulder-widths, so distance-independent). Open the debug overlay (F3) to see
live `lateral` / `vertical` signals with the threshold lines drawn. The Settings sensitivity slider (0.7–1.4) scales every threshold.

Gameplay constants: `src/game/config.ts`. Obstacle patterns: `src/game/patterns.ts` (spacing between rows is computed by
`TrackGenerator` from the fairness rules: lane-change time, jump↔slide transition ≥ 0.9 s, base gap 1.4 s → 0.8 s by tier).

`?seed=123` in the URL fixes the track seed.
