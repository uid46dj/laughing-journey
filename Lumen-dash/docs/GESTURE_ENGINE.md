# Reusing the pose + gesture layer

`src/cam` (the camera + pose + gesture stack) knows nothing about the game.

```ts
const camera = new CameraSource();            await camera.start();
const estimator = new PoseEstimator();        await estimator.init();
const filter = new LandmarkFilter();
const engine = new DefaultGestureEngine();

// 1. calibrate: collect ~1.5 s of frames while assessFraming(frame).status === 'ok'
engine.calibrate(frames);

// 2. per frame
estimator.start(camera.video, (raw) => {
  const frame = raw ? filter.apply(raw) : null;
  const snapshot = engine.process(frame, performance.now()); // zoneX, posture, lateral, verticalOffset, tracking
  for (const ev of engine.drainEvents()) { /* jump, crouchStart/End, zoneChange, handsUpHold */ }
});
```

* `process()` is pure and deterministic: time comes from `frame.t` (or `now` if there is no frame). Feed it a recorded `PoseFrame[]` to replay/test.
* Signals are normalised by calibrated shoulder width, so thresholds don't depend on camera distance.
* Only nose + both shoulders are required; wrists are optional (hands-up hold).
* To add a gesture: add thresholds to `gestureConfig.ts`, compute it in `GestureEngine.update()` (or split into a detector class), emit a new `GestureEvent` variant in `gestureTypes.ts`.
* A new game only needs its own `InputSource` adapter (see `src/cam/GestureInputSource.ts`).
