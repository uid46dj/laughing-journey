export type TrackingInfo = 'ok' | 'degraded' | 'lost' | 'n/a';

/** The ONLY thing the game knows about player input. */
export interface RunnerInput {
  /** Absolute lane the player is standing/leaning in (webcam). Applied when it CHANGES. */
  targetLane: -1 | 0 | 1 | null;
  /** Relative one-lane step (keyboard). */
  laneStep: -1 | 0 | 1;
  /** Edge-triggered, consumed by poll(). */
  jumpPressed: boolean;
  /** Level-triggered. */
  slideHeld: boolean;
  /** Edge-triggered. */
  pausePressed: boolean;
  /**
   * Leg-cadence in steps/sec from the second phone (jog speed), or null when
   * no leg phone is connected / its legs are not visible. Null => neutral speed.
   */
  jogCadence: number | null;
  trackingState: TrackingInfo;
}

export interface InputSource {
  poll(now: number): RunnerInput;
}

export const NEUTRAL_INPUT: RunnerInput = {
  targetLane: null,
  laneStep: 0,
  jumpPressed: false,
  slideHeld: false,
  pausePressed: false,
  jogCadence: null,
  trackingState: 'n/a',
};

/** Merges several sources (e.g. webcam + jog phone + keyboard). */
export class CompositeInputSource implements InputSource {
  constructor(private sources: InputSource[]) {}

  poll(now: number): RunnerInput {
    const out: RunnerInput = { ...NEUTRAL_INPUT };
    let step = 0;
    for (const s of this.sources) {
      const i = s.poll(now);
      if (i.targetLane !== null) out.targetLane = i.targetLane;
      step += i.laneStep;
      out.jumpPressed ||= i.jumpPressed;
      out.slideHeld ||= i.slideHeld;
      out.pausePressed ||= i.pausePressed;
      if (i.jogCadence !== null) out.jogCadence = i.jogCadence;
      if (i.trackingState !== 'n/a') out.trackingState = i.trackingState;
    }
    out.laneStep = step > 0 ? 1 : step < 0 ? -1 : 0;
    return out;
  }
}
