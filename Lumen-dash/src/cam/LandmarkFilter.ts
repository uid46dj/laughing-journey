import type { PoseFrame } from './poseTypes';

class LowPass {
  last: number | null = null;
  filter(x: number, alpha: number): number {
    this.last = this.last === null ? x : alpha * x + (1 - alpha) * this.last;
    return this.last;
  }
}

/**
 * One-Euro filter (Casiez et al.). Units here are normalized-image units per second,
 * so `beta` is much larger than the usual pixel-based defaults.
 */
export class OneEuroFilter {
  private x = new LowPass();
  private dx = new LowPass();
  private lastT: number | null = null;
  private lastRaw = 0;

  constructor(
    private minCutoff = 1.5,
    private beta = 10,
    private dCutoff = 1.0,
  ) {}

  private alpha(cutoff: number, dt: number) {
    const tau = 1 / (2 * Math.PI * cutoff);
    return 1 / (1 + tau / dt);
  }

  filter(value: number, tMs: number): number {
    if (this.lastT === null) {
      this.lastT = tMs;
      this.lastRaw = value;
      return this.x.filter(value, 1);
    }
    const dt = Math.max((tMs - this.lastT) / 1000, 1e-3);
    this.lastT = tMs;
    const dvalue = (value - this.lastRaw) / dt;
    this.lastRaw = value;
    const edx = this.dx.filter(dvalue, this.alpha(this.dCutoff, dt));
    const cutoff = this.minCutoff + this.beta * Math.abs(edx);
    return this.x.filter(value, this.alpha(cutoff, dt));
  }

  reset() {
    this.x = new LowPass();
    this.dx = new LowPass();
    this.lastT = null;
  }
}

/** Smooths every landmark's x/y with a One-Euro filter. Low-visibility points pass through raw. */
export class LandmarkFilter {
  private fx: OneEuroFilter[] = [];
  private fy: OneEuroFilter[] = [];

  constructor(
    private minCutoff = 1.5,
    private beta = 10,
  ) {}

  apply(frame: PoseFrame): PoseFrame {
    const out = frame.landmarks.map((lm, i) => {
      if (!this.fx[i]) {
        this.fx[i] = new OneEuroFilter(this.minCutoff, this.beta);
        this.fy[i] = new OneEuroFilter(this.minCutoff, this.beta);
      }
      if (lm.visibility < 0.5) {
        this.fx[i].reset();
        this.fy[i].reset();
        return lm;
      }
      return {
        x: this.fx[i].filter(lm.x, frame.t),
        y: this.fy[i].filter(lm.y, frame.t),
        z: lm.z,
        visibility: lm.visibility,
      };
    });
    return { t: frame.t, aspect: frame.aspect, landmarks: out };
  }

  reset() {
    this.fx.forEach((f) => f.reset());
    this.fy.forEach((f) => f.reset());
  }
}
