/** Normalized image-space landmark (0..1). `x` is in the RAW (un-mirrored) camera image. */
export interface Landmark {
  x: number;
  y: number;
  z: number;
  visibility: number;
}

export interface PoseFrame {
  /** performance.now() at the moment inference started for this frame (ms). */
  t: number;
  landmarks: Landmark[];
  /** video width / height, needed to convert y to width-units. */
  aspect: number;
}

export interface PoseMetrics {
  fps: number;
  inferenceMs: number;
  delegate: 'GPU' | 'CPU' | 'unknown';
  source: 'local' | 'cdn' | 'unknown';
}

/** MediaPipe BlazePose landmark indices (only the ones we use). */
export const LM = {
  NOSE: 0,
  L_SHOULDER: 11,
  R_SHOULDER: 12,
  L_ELBOW: 13,
  R_ELBOW: 14,
  L_WRIST: 15,
  R_WRIST: 16,
  L_HIP: 23,
  R_HIP: 24,
} as const;

export const SKELETON_EDGES: ReadonlyArray<readonly [number, number]> = [
  [11, 12],
  [11, 13],
  [13, 15],
  [12, 14],
  [14, 16],
  [11, 23],
  [12, 24],
  [23, 24],
];
