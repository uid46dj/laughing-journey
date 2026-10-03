import { Game } from '../game/Game';
import type { HudState } from '../game/Game';
import { DefaultGestureEngine } from '../cam/GestureEngine';
import { assessFraming } from '../cam/framing';
import { GESTURE_CONFIG } from '../cam/gestureConfig';
import type { GestureEvent } from '../cam/gestureTypes';
import { CompositeInputSource } from '../game/InputSource';
import { GestureInputSource } from '../cam/GestureInputSource';
import { KeyboardInputSource } from '../game/KeyboardInputSource';
import { CameraError, CameraSource } from '../cam/CameraSource';
import { LandmarkFilter } from '../cam/LandmarkFilter';
import { PhoneCamera } from '../cam/PhoneCamera';
import { PoseEstimator } from '../cam/PoseEstimator';
import type { PoseFrame } from '../cam/poseTypes';
import { drawPreview } from '../cam/drawPreview';
import { debugStore, gestureStore, hudStore, settingsStore, uiStore } from './store';

const TUTORIAL_STEPS = 4;

/**
 * Wires the independent layers together:
 *   camera -> pose -> filter -> gesture engine -> GestureInputSource -> Game
 * It is the only module that knows about all of them.
 */
export class Controller {
  game!: Game;
  readonly camera = new CameraSource();
  /** Optional: use a phone's camera as the webcam (see tools/phonecam-server.mjs). */
  readonly phoneCam = new PhoneCamera();
  private estimator = new PoseEstimator();
  private filter = new LandmarkFilter();
  private engine = new DefaultGestureEngine();
  private gestureInput = new GestureInputSource();
  private keyboard = new KeyboardInputSource();
  private previews = new Set<HTMLCanvasElement>();
  private calibBuf: PoseFrame[] = [];
  private calibStart: number | null = null;
  private lastUiPush = 0;
  private log: string[] = [];
  private tutorialAdvance: number | null = null;
  private flowId = 0;

  init(container: HTMLElement) {
    this.game = new Game(container);
    this.game.onHud = (h: HudState) => hudStore.set(h);
    this.game.onQualityDrop = (q) => {
      settingsStore.set({ quality: q });
      this.toast(`Frame rate was low — graphics set to ${q}.`);
    };
    this.keyboard.attach();
    this.game.setInput(this.keyboard);
    this.applySettings();
    settingsStore.subscribe(() => this.applySettings());
    this.camera.onEnded = () => {
      this.game.pause('tracking');
      this.toast('Camera disconnected.');
      this.stopCamera();
      uiStore.set({ mode: 'keyboard' });
      this.game.setInput(this.keyboard);
    };
    window.addEventListener('keydown', this.onKey);
  }

  dispose() {
    window.removeEventListener('keydown', this.onKey);
    this.keyboard.detach();
    this.stopCamera();
    this.phoneCam.stop();
    this.estimator.dispose();
    this.game.dispose();
  }

  /**
   * Switch the camera source to the phone.
   * Must be called BEFORE the camera flow starts, because PhoneCamera patches
   * `getUserMedia` — which is exactly what CameraSource.start() calls.
   */
  async usePhoneCamera(): Promise<boolean> {
    const probe = await this.phoneCam.probe();
    if (!probe.ok || !probe.streaming) {
      this.toast(probe.message);
      return false;
    }
    await this.phoneCam.start();
    this.toast(`Phone camera active — ${probe.message}`);
    return true;
  }

  usePcCamera() {
    this.phoneCam.stop();
    this.toast('Switched back to the PC camera.');
  }

  private onKey = (e: KeyboardEvent) => {
    if (e.code === 'F3') {
      e.preventDefault();
      settingsStore.set((s) => ({ showDebug: !s.showDebug }));
    }
    if (e.code === 'KeyR' && this.game.state === 'paused' && uiStore.get().mode === 'camera') this.recalibrate();
    if ((e.code === 'Enter' || e.code === 'Space') && this.game.state === 'gameover') this.startRun();
  };

  private applySettings() {
    const s = settingsStore.get();
    this.engine.setSensitivity(s.sensitivity);
    this.game.applySettings({ reducedMotion: s.reducedMotion, quality: s.quality, volume: s.volume, music: s.music, sfx: s.sfx });
  }

  toast(msg: string) {
    uiStore.set({ toast: msg });
    window.setTimeout(() => {
      if (uiStore.get().toast === msg) uiStore.set({ toast: null });
    }, 4000);
  }

  registerPreview(c: HTMLCanvasElement) {
    this.previews.add(c);
    return () => {
      this.previews.delete(c);
    };
  }

  // ---------------- flows ----------------
  unlockAudio() {
    this.game.audio.unlock();
  }

  startKeyboardRun() {
    this.unlockAudio();
    this.stopCamera();
    uiStore.set({ mode: 'keyboard', screen: 'game' });
    this.game.setInput(this.keyboard);
    this.startRun();
  }

  startRun() {
    this.gestureInput.clear();
    this.game.startRun();
  }

  async startCameraFlow(returnToGame = false) {
    this.unlockAudio();
    const id = ++this.flowId;
    this.setSetup({ phase: 'starting', message: 'Requesting camera…', progress: 0, returnToGame, framingOk: false });
    uiStore.set({ screen: 'setup', mode: 'camera' });
    try {
      await this.camera.start(settingsStore.get().deviceId || undefined);
    } catch (e) {
      if (id !== this.flowId) return;
      this.camera.stop();
      this.setSetup({ phase: 'error', message: e instanceof CameraError ? e.message : 'Could not start the camera.' });
      return;
    }
    try {
      await this.estimator.init((m) => id === this.flowId && this.setSetup({ message: m }));
    } catch (e) {
      if (id !== this.flowId) return;
      this.camera.stop();
      const msg = e instanceof Error ? e.message : String(e);
      this.setSetup({
        phase: 'error',
        message: `The pose model could not be loaded (${msg}). It needs a one-time download unless the files are bundled in /public. You can play with the keyboard.`,
      });
      return;
    }
    if (id !== this.flowId) return;
    this.engine.reset();
    this.applySettings();
    this.filter.reset();
    this.game.setInput(new CompositeInputSource([this.gestureInput, this.keyboard]));
    this.gestureInput.clear();
    this.estimator.start(this.camera.video, this.onPoseFrame);
    this.beginCalibration();
  }

  recalibrate() {
    if (!this.camera.active) {
      void this.startCameraFlow(true);
      return;
    }
    uiStore.set({ screen: 'setup' });
    this.setSetup({ returnToGame: true });
    this.beginCalibration();
  }

  private beginCalibration() {
    this.calibBuf = [];
    this.calibStart = null;
    this.setSetup({ phase: 'calibrating', message: 'Stand where your whole upper body is visible.', progress: 0, framingOk: false });
  }

  private setSetup(p: Partial<ReturnType<typeof uiStore.get>['setup']>) {
    uiStore.set((s) => ({ setup: { ...s.setup, ...p } }));
  }

  stopCamera() {
    this.flowId++;
    this.estimator.stop();
    this.camera.stop();
    this.gestureInput.clear();
  }

  cancelSetup() {
    this.stopCamera();
    this.game.setInput(this.keyboard);
    uiStore.set({ screen: 'menu', mode: 'keyboard' });
  }

  quitToMenu() {
    this.stopCamera();
    this.game.setInput(this.keyboard);
    this.game.quitToMenu();
    uiStore.set({ screen: 'menu', mode: 'keyboard', settingsOpen: false });
  }

  skipTutorial() {
    settingsStore.set({ tutorialDone: true });
    this.finishSetup();
  }

  private finishSetup() {
    const returning = uiStore.get().setup.returnToGame;
    uiStore.set({ screen: 'game' });
    if (returning && this.game.state === 'paused') this.game.resume();
    else this.startRun();
  }

  // ---------------- per pose-frame pipeline ----------------
  private onPoseFrame = (raw: PoseFrame | null) => {
    const now = performance.now();
    const frame = raw ? this.filter.apply(raw) : null;
    const snap = this.engine.process(frame, now);
    const events = this.engine.drainEvents();
    this.gestureInput.push(snap, events);

    const ui = uiStore.get();
    if (ui.screen === 'setup' && ui.setup.phase === 'calibrating') this.calibrationStep(frame, now);
    if (ui.screen === 'setup' && ui.setup.phase === 'tutorial') this.tutorialStep(events);
    for (const e of events) this.afterEvent(e);

    const color = snap.tracking === 'ok' ? '#34d399' : snap.tracking === 'degraded' ? '#fbbf24' : '#f87171';
    const { mirror, flipVertical } = settingsStore.get();
    this.previews.forEach((c) => drawPreview(c, this.camera.video, frame, mirror, color, flipVertical));

    if (now - this.lastUiPush > 66) {
      this.lastUiPush = now;
      const g = gestureStore.get();
      gestureStore.set({
        calibrated: snap.calibrated,
        tracking: snap.tracking,
        zone: snap.zoneX,
        posture: snap.posture,
        handsUp: snap.handsUpProgress,
        jumpAt: g.jumpAt,
        crouchAt: g.crouchAt,
      });
      const m = this.estimator.metrics;
      debugStore.set({
        poseFps: m.fps,
        inferenceMs: Math.round(m.inferenceMs),
        delegate: m.delegate,
        source: m.source,
        latency: Math.round(this.gestureInput.medianLatency),
        lateral: snap.lateral,
        vertical: snap.verticalOffset,
        log: this.log,
      });
    }
  };

  private afterEvent(e: GestureEvent) {
    if (e.type === 'jump') gestureStore.set({ jumpAt: e.t });
    else if (e.type === 'crouchStart') gestureStore.set({ crouchAt: e.t });
    if (e.type !== 'calibrationChanged') {
      const label =
        e.type === 'zoneChange' ? `zone ${e.from}→${e.to}` : e.type === 'handsUpHold' ? 'hands-up hold' : e.type;
      this.log = [`${(e.t / 1000).toFixed(1)}s ${label}`, ...this.log].slice(0, 8);
    }
    if (e.type === 'handsUpHold' && this.game.state === 'gameover') this.startRun();
  }

  private calibrationStep(frame: PoseFrame | null, now: number) {
    const a = assessFraming(frame);
    if (a.status !== 'ok' || !frame) {
      this.calibStart = null;
      this.calibBuf = [];
      this.setSetup({ message: a.message, progress: 0, framingOk: false });
      return;
    }
    if (this.calibStart === null) this.calibStart = now;
    this.calibBuf.push(frame);
    const progress = Math.min(1, (now - this.calibStart) / GESTURE_CONFIG.calibration.holdMs);
    this.setSetup({ message: a.message, progress, framingOk: true });
    if (progress >= 1) {
      const res = this.engine.calibrate(this.calibBuf);
      this.calibBuf = [];
      this.calibStart = null;
      if (!res.ok) {
        this.setSetup({ message: res.reasons.join(' '), progress: 0, framingOk: false });
        return;
      }
      this.engine.drainEvents();
      const s = uiStore.get().setup;
      if (settingsStore.get().tutorialDone || s.returnToGame) {
        this.finishSetup();
      } else {
        this.setSetup({ phase: 'tutorial', tutorialStep: 0, tutorialDone: [false, false, false, false], message: '' });
      }
    }
  }

  private tutorialStep(events: GestureEvent[]) {
    const s = uiStore.get().setup;
    if (this.tutorialAdvance !== null) return;
    const step = s.tutorialStep;
    const hit = events.some(
      (e) =>
        (step === 0 && e.type === 'zoneChange' && e.to === -1) ||
        (step === 1 && e.type === 'zoneChange' && e.to === 1) ||
        (step === 2 && e.type === 'jump') ||
        (step === 3 && e.type === 'crouchStart'),
    );
    if (!hit) return;
    this.game.audio.blip();
    const done = [...s.tutorialDone];
    done[step] = true;
    this.setSetup({ tutorialDone: done });
    this.tutorialAdvance = window.setTimeout(() => {
      this.tutorialAdvance = null;
      if (step + 1 >= TUTORIAL_STEPS) {
        settingsStore.set({ tutorialDone: true });
        this.finishSetup();
      } else {
        this.setSetup({ tutorialStep: step + 1 });
      }
    }, 900);
  }
}

export const controller = new Controller();
