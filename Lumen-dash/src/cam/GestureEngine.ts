import { LM } from './poseTypes';
import type { PoseFrame } from './poseTypes';
import { GESTURE_CONFIG as C } from './gestureConfig';
import type {
  CalibrationProfile,
  CalibrationResult,
  ControlSnapshot,
  GestureEngine,
  GestureEvent,
  Posture,
  TrackingState,
  ZoneX,
} from './gestureTypes';

interface Signals {
  /** mirrored shoulder-midpoint x (0..1) — negative lateral = player's left */
  mx: number;
  /** vertical signal in width-units, up = positive */
  u: number;
  sw: number;
}

const median = (a: number[]) => {
  const s = [...a].sort((x, y) => x - y);
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};

export class DefaultGestureEngine implements GestureEngine {
  private sens = 1;
  private profile: CalibrationProfile | null = null;
  private events: GestureEvent[] = [];

  private zone: ZoneX = 0;
  private zoneCand: ZoneX = 0;
  private zoneCount = 0;

  private posture: Posture = 'standing';
  private crouchCount = 0;

  private hist: { t: number; v: number }[] = [];
  private lastJumpT = -1e9;
  private lastCrouchEndT = -1e9;

  private tracking: TrackingState = 'lost';
  private lastValidT = -1e9;
  private lastT: number | null = null;

  private handsStart: number | null = null;
  private handsFired = false;
  private handsProgress = 0;

  private lateral = 0;
  private vertical = 0;

  setSensitivity(s: number) {
    this.sens = Math.min(1.6, Math.max(0.5, s));
  }

  reset() {
    this.events = [];
    this.zone = 0;
    this.zoneCand = 0;
    this.zoneCount = 0;
    this.posture = 'standing';
    this.crouchCount = 0;
    this.hist = [];
    this.lastJumpT = -1e9;
    this.lastCrouchEndT = -1e9;
    this.tracking = 'lost';
    this.lastValidT = -1e9;
    this.lastT = null;
    this.handsStart = null;
    this.handsFired = false;
    this.handsProgress = 0;
    this.lateral = 0;
    this.vertical = 0;
    this.profile = null;
  }

  drainEvents(): GestureEvent[] {
    const e = this.events;
    this.events = [];
    return e;
  }

  private read(frame: PoseFrame): Signals | null {
    const nose = frame.landmarks[LM.NOSE];
    const ls = frame.landmarks[LM.L_SHOULDER];
    const rs = frame.landmarks[LM.R_SHOULDER];
    if (!nose || !ls || !rs) return null;
    if (nose.visibility < C.minVisibility || ls.visibility < C.minVisibility || rs.visibility < C.minVisibility) return null;
    const sw = Math.abs(ls.x - rs.x);
    if (sw < 0.02) return null;
    const midX = (ls.x + rs.x) / 2;
    const yShoulders = (ls.y + rs.y) / 2;
    const y = yShoulders * (1 - C.noseWeight) + nose.y * C.noseWeight;
    return { mx: 1 - midX, u: -y / frame.aspect, sw };
  }

  calibrate(frames: PoseFrame[]): CalibrationResult {
    const sigs = frames.map((f) => this.read(f)).filter((s): s is Signals => s !== null);
    if (sigs.length < C.calibration.minFrames) {
      return { ok: false, reasons: ['We could not see you clearly. Try better lighting.'] };
    }
    const profile: CalibrationProfile = {
      mx0: median(sigs.map((s) => s.mx)),
      u0: median(sigs.map((s) => s.u)),
      sw0: median(sigs.map((s) => s.sw)),
    };
    const reasons: string[] = [];
    if (profile.sw0 < C.calibration.minShoulderWidth) reasons.push('Move closer.');
    if (profile.sw0 > C.calibration.maxShoulderWidth) reasons.push('Move back.');
    if (Math.abs(profile.mx0 - 0.5) > C.calibration.maxCenterOffset) reasons.push('Step to the middle.');
    if (reasons.length) return { ok: false, reasons };

    const keepEvents = this.events;
    this.reset();
    this.events = keepEvents;
    this.profile = profile;
    this.events.push({ type: 'calibrationChanged', t: frames[frames.length - 1].t });
    return { ok: true, reasons: [], profile };
  }

  process(frame: PoseFrame | null, now: number): ControlSnapshot {
    const t = frame ? frame.t : now;
    const sig = frame ? this.read(frame) : null;

    if (sig) {
      if (this.tracking === 'lost') this.onRecovered();
      this.tracking = 'ok';
      this.lastValidT = t;
    } else if (t - this.lastValidT > C.lostAfterMs) {
      if (this.tracking !== 'lost') this.onLost();
      this.tracking = 'lost';
    } else {
      this.tracking = 'degraded';
    }

    if (frame && sig) this.updateHands(frame, t);
    else this.resetHands();

    if (sig && this.profile) this.update(sig, this.profile, t);
    return this.snapshot(t);
  }

  private onLost() {
    this.resetHands();
    this.hist = [];
  }

  private onRecovered() {
    this.hist = [];
    this.zoneCount = 0;
    this.crouchCount = 0;
    this.lastT = null;
  }

  private resetHands() {
    this.handsStart = null;
    this.handsFired = false;
    this.handsProgress = 0;
  }

  private updateHands(frame: PoseFrame, t: number) {
    const nose = frame.landmarks[LM.NOSE];
    const lw = frame.landmarks[LM.L_WRIST];
    const rw = frame.landmarks[LM.R_WRIST];
    const up =
      lw && rw && lw.visibility >= C.wristVisibility && rw.visibility >= C.wristVisibility && lw.y < nose.y && rw.y < nose.y;
    if (up) {
      if (this.handsStart === null) this.handsStart = t;
      this.handsProgress = Math.min(1, (t - this.handsStart) / C.handsUpHoldMs);
      if (this.handsProgress >= 1 && !this.handsFired) {
        this.handsFired = true;
        this.events.push({ type: 'handsUpHold', t });
      }
    } else {
      this.resetHands();
    }
  }

  private update(sig: Signals, p: CalibrationProfile, t: number) {
    const dtMs = this.lastT === null ? 33 : Math.min(t - this.lastT, 200);
    this.lastT = t;
    const s = this.sens;

    const lateral = (sig.mx - p.mx0) / p.sw0;
    const v = (sig.u - p.u0) / p.sw0;
    this.lateral = lateral;
    this.vertical = v;

    this.hist.push({ t, v });
    while (this.hist.length && t - this.hist[0].t > 350) this.hist.shift();

    // ---- crouch (state with hysteresis) ----
    const crouchEnter = C.crouchEnter / s;
    const crouchExit = C.crouchExit / s;
    if (this.posture === 'standing') {
      if (v < crouchEnter && t - this.lastJumpT > C.postJumpCrouchLockoutMs) this.crouchCount++;
      else this.crouchCount = 0;
      if (this.crouchCount >= C.crouchStableFrames) {
        this.posture = 'crouching';
        this.crouchCount = 0;
        this.events.push({ type: 'crouchStart', t });
      }
    } else {
      if (v > crouchExit) this.crouchCount++;
      else this.crouchCount = 0;
      if (this.crouchCount >= C.crouchStableFrames) {
        this.posture = 'standing';
        this.crouchCount = 0;
        this.lastCrouchEndT = t;
        this.events.push({ type: 'crouchEnd', t });
      }
    }

    // ---- jump (fires on rising edge) ----
    if (
      this.posture === 'standing' &&
      t - this.lastJumpT > C.jumpRefractoryMs &&
      t - this.lastCrouchEndT > C.postCrouchJumpLockoutMs &&
      v > C.jumpDisplacement / s
    ) {
      let maxVel = 0;
      for (const h of this.hist) {
        const dt = t - h.t;
        if (dt >= C.jumpVelocityMinDtMs && dt <= C.jumpVelocityWindowMs) {
          maxVel = Math.max(maxVel, ((v - h.v) / dt) * 1000);
        }
      }
      if (maxVel > C.jumpVelocity / s) {
        this.lastJumpT = t;
        this.events.push({ type: 'jump', t, strength: v });
      }
    }

    // ---- lateral zone with hysteresis + frame stability ----
    const enter = C.lateralEnter / s;
    const exit = C.lateralExit / s;
    let cand: ZoneX = this.zone;
    if (this.zone === 0) {
      if (lateral < -enter) cand = -1;
      else if (lateral > enter) cand = 1;
    } else if (this.zone === -1) {
      if (lateral > -exit) cand = lateral > enter ? 1 : 0;
    } else if (lateral < exit) {
      cand = lateral < -enter ? -1 : 0;
    }
    if (cand !== this.zone) {
      if (cand === this.zoneCand) this.zoneCount++;
      else {
        this.zoneCand = cand;
        this.zoneCount = 1;
      }
      if (this.zoneCount >= C.zoneStableFrames) {
        this.events.push({ type: 'zoneChange', t, from: this.zone, to: cand });
        this.zone = cand;
        this.zoneCount = 0;
      }
    } else {
      this.zoneCand = this.zone;
      this.zoneCount = 0;
    }

    // ---- slow drift correction (only while clearly idle) ----
    const first = this.hist[0];
    const stationary = first && Math.abs(v - first.v) < 0.08;
    if (
      this.zone === 0 &&
      this.posture === 'standing' &&
      Math.abs(lateral) < 0.2 &&
      Math.abs(v) < 0.12 &&
      stationary &&
      t - this.lastJumpT > 600 &&
      t - this.lastCrouchEndT > 600
    ) {
      const a = 1 - Math.exp(-dtMs / C.driftTauMs);
      p.mx0 += (sig.mx - p.mx0) * a;
      p.u0 += (sig.u - p.u0) * a;
    }
  }

  private snapshot(t: number): ControlSnapshot {
    return {
      t,
      calibrated: this.profile !== null,
      tracking: this.tracking,
      zoneX: this.zone,
      lateral: this.lateral,
      posture: this.posture,
      verticalOffset: this.vertical,
      handsUpProgress: this.handsProgress,
    };
  }
}
