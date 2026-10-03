import type { ControlSnapshot, GestureEvent } from './gestureTypes';
import type { InputSource, RunnerInput } from '../game/InputSource';

/** Adapts gesture-engine output to the game's RunnerInput. */
export class GestureInputSource implements InputSource {
  private snapshot: ControlSnapshot | null = null;
  private jumpT: number | null = null;
  private pause = false;
  /** Latency samples (ms): pose-frame start -> game applies the jump. */
  latencies: number[] = [];

  push(snapshot: ControlSnapshot, events: GestureEvent[]) {
    this.snapshot = snapshot;
    for (const e of events) {
      if (e.type === 'jump') this.jumpT = e.t;
      else if (e.type === 'handsUpHold') this.pause = true;
    }
  }

  get medianLatency(): number {
    if (!this.latencies.length) return 0;
    const s = [...this.latencies].sort((a, b) => a - b);
    return s[s.length >> 1];
  }

  clear() {
    this.snapshot = null;
    this.jumpT = null;
    this.pause = false;
  }

  poll(now: number): RunnerInput {
    const s = this.snapshot;
    const usable = !!s && s.calibrated && s.tracking !== 'lost';
    let jump = false;
    if (this.jumpT !== null) {
      jump = true;
      this.latencies.push(Math.max(0, now - this.jumpT));
      if (this.latencies.length > 15) this.latencies.shift();
      this.jumpT = null;
    }
    const pause = this.pause;
    this.pause = false;
    return {
      targetLane: usable ? s!.zoneX : null,
      laneStep: 0,
      jumpPressed: jump && usable,
      slideHeld: usable && s!.posture === 'crouching',
      pausePressed: pause,
      trackingState: s ? (s.calibrated ? s.tracking : 'n/a') : 'lost',
    };
  }
}
