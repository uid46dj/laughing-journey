import { FilesetResolver, PoseLandmarker } from '@mediapipe/tasks-vision';
import type { Landmark, PoseFrame, PoseMetrics } from './poseTypes';

const MP_VERSION = '1.0.1';
const BASE = import.meta.env.BASE_URL ?? '/';

/**
 * Asset sources, tried in order. Drop `pose_landmarker_lite.task` into `public/models/` and the
 * contents of `node_modules/@mediapipe/tasks-vision/wasm` into `public/mediapipe/wasm/`
 * to make the game fully offline. Otherwise the CDN is used on first load.
 */
const WASM_SOURCES = [
  { base: `${BASE}mediapipe/wasm`, probe: 'vision_wasm_internal.wasm', source: 'local' as const },
  { base: `https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@${MP_VERSION}/wasm`, probe: '', source: 'cdn' as const },
  { base: `https://unpkg.com/@mediapipe/tasks-vision@${MP_VERSION}/wasm`, probe: '', source: 'cdn' as const },
];
const MODEL_SOURCES = [
  `${BASE}models/pose_landmarker_lite.task`,
  'https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task',
];

async function reachable(url: string): Promise<boolean> {
  try {
    const res = await fetch(url, { method: 'HEAD' });
    const type = res.headers.get('content-type') ?? '';
    return res.ok && !type.includes('text/html');
  } catch {
    return false;
  }
}

export class PoseEstimator {
  private landmarker: PoseLandmarker | null = null;
  private running = false;
  private video: HTMLVideoElement | null = null;
  private lastVideoTime = -1;
  private onFrame: ((f: PoseFrame | null) => void) | null = null;
  private completions: number[] = [];
  metrics: PoseMetrics = { fps: 0, inferenceMs: 0, delegate: 'unknown', source: 'unknown' };

  get ready() {
    return this.landmarker !== null;
  }

  async init(onProgress?: (msg: string) => void): Promise<void> {
    if (this.landmarker) return;
    onProgress?.('Locating pose engine…');
    let wasmBase = WASM_SOURCES[1].base;
    let source: PoseMetrics['source'] = 'cdn';
    for (const s of WASM_SOURCES) {
      if (s.source === 'local') {
        if (await reachable(`${s.base}/${s.probe}`)) {
          wasmBase = s.base;
          source = 'local';
          break;
        }
      } else {
        wasmBase = s.base;
        source = 'cdn';
        if (await reachable(`${s.base}/vision_wasm_internal.js`)) break;
      }
    }
    let modelUrl = MODEL_SOURCES[1];
    if (await reachable(MODEL_SOURCES[0])) modelUrl = MODEL_SOURCES[0];
    else source = 'cdn';

    onProgress?.('Loading pose model…');
    const fileset = await FilesetResolver.forVisionTasks(wasmBase);
    const create = (delegate: 'GPU' | 'CPU') =>
      PoseLandmarker.createFromOptions(fileset, {
        baseOptions: { modelAssetPath: modelUrl, delegate },
        runningMode: 'VIDEO',
        numPoses: 1,
        minPoseDetectionConfidence: 0.5,
        minPosePresenceConfidence: 0.5,
        minTrackingConfidence: 0.5,
      });
    try {
      this.landmarker = await create('GPU');
      this.metrics.delegate = 'GPU';
    } catch {
      onProgress?.('GPU unavailable, using CPU…');
      this.landmarker = await create('CPU');
      this.metrics.delegate = 'CPU';
    }
    this.metrics.source = source;
  }

  start(video: HTMLVideoElement, onFrame: (f: PoseFrame | null) => void) {
    this.video = video;
    this.onFrame = onFrame;
    this.lastVideoTime = -1;
    this.running = true;
    // a new loop id invalidates any callback still pending from a previous loop
    this.loopId++;
    this.schedule(this.loopId);
  }

  stop() {
    this.running = false;
    this.loopId++;
    this.onFrame = null;
  }

  dispose() {
    this.stop();
    this.landmarker?.close();
    this.landmarker = null;
  }

  private loopId = 0;

  private schedule(id: number) {
    const v = this.video as HTMLVideoElement & {
      requestVideoFrameCallback?: (cb: () => void) => number;
    };
    if (!this.running || !v) return;
    const cb = () => this.tick(id);
    if (v.requestVideoFrameCallback) v.requestVideoFrameCallback(cb);
    else requestAnimationFrame(cb);
  }

  private tick(id: number) {
    const v = this.video;
    if (id !== this.loopId || !this.running || !v || !this.landmarker) return;
    if (v.readyState >= 2 && v.currentTime !== this.lastVideoTime && v.videoWidth > 0) {
      this.lastVideoTime = v.currentTime;
      const t0 = performance.now();
      let frame: PoseFrame | null = null;
      try {
        const res = this.landmarker.detectForVideo(v, t0);
        const lm = res.landmarks[0];
        if (lm) {
          const landmarks: Landmark[] = lm.map((p) => ({
            x: p.x,
            y: p.y,
            z: p.z,
            visibility: p.visibility ?? 0,
          }));
          frame = { t: t0, landmarks, aspect: v.videoWidth / v.videoHeight };
        }
      } catch {
        frame = null;
      }
      const t1 = performance.now();
      this.metrics.inferenceMs = this.metrics.inferenceMs * 0.8 + (t1 - t0) * 0.2;
      this.completions.push(t1);
      while (this.completions.length && t1 - this.completions[0] > 1000) this.completions.shift();
      this.metrics.fps = this.completions.length;
      this.onFrame?.(frame);
    }
    this.schedule(id);
  }
}
