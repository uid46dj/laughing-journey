import type { PoseFrame } from './poseTypes';

/** -1 = player's left, 0 = center, 1 = player's right (already un-mirrored). */
export type ZoneX = -1 | 0 | 1;
export type Posture = 'standing' | 'crouching';
export type TrackingState = 'ok' | 'degraded' | 'lost';

export interface ControlSnapshot {
  t: number;
  calibrated: boolean;
  tracking: TrackingState;
  zoneX: ZoneX;
  /** offset from neutral in shoulder-widths (negative = left). */
  lateral: number;
  posture: Posture;
  /** vertical offset from neutral in shoulder-widths (positive = up). */
  verticalOffset: number;
  /** 0..1 progress of the hands-up hold. */
  handsUpProgress: number;
}

export type GestureEvent =
  | { type: 'jump'; t: number; strength: number }
  | { type: 'crouchStart'; t: number }
  | { type: 'crouchEnd'; t: number }
  | { type: 'zoneChange'; t: number; from: ZoneX; to: ZoneX }
  | { type: 'handsUpHold'; t: number }
  | { type: 'calibrationChanged'; t: number };

export interface CalibrationProfile {
  mx0: number;
  u0: number;
  sw0: number;
}

export interface CalibrationResult {
  ok: boolean;
  reasons: string[];
  profile?: CalibrationProfile;
}

export interface GestureEngine {
  /** Pure & deterministic: time comes from `frame.t` (or `now` when there is no frame). */
  process(frame: PoseFrame | null, now: number): ControlSnapshot;
  drainEvents(): GestureEvent[];
  calibrate(frames: PoseFrame[]): CalibrationResult;
  setSensitivity(s: number): void;
  reset(): void;
}

export interface FramingAssessment {
  status: 'ok' | 'no-pose' | 'too-far' | 'too-close' | 'off-center' | 'head-high' | 'low-shoulders';
  message: string;
}
