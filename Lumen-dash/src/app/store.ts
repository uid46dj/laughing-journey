import { useSyncExternalStore } from 'react';
import type { HudState } from '../game/Game';
import type { Quality } from '../game/config';
import type { Posture, TrackingState, ZoneX } from '../cam/gestureTypes';

export function createStore<T extends object>(initial: T) {
  let state = initial;
  const listeners = new Set<() => void>();
  return {
    get: () => state,
    set(patch: Partial<T> | ((s: T) => Partial<T>)) {
      const p = typeof patch === 'function' ? patch(state) : patch;
      state = { ...state, ...p };
      listeners.forEach((l) => l());
    },
    subscribe(l: () => void) {
      listeners.add(l);
      return () => listeners.delete(l);
    },
  };
}

type Store<T extends object> = ReturnType<typeof createStore<T>>;

export function useStore<T extends object>(store: Store<T>): T {
  return useSyncExternalStore(store.subscribe, store.get, store.get);
}

// ---------------- settings (persisted) ----------------
export interface Settings {
  sensitivity: number;
  volume: number;
  music: boolean;
  sfx: boolean;
  reducedMotion: boolean;
  quality: Quality;
  showPip: boolean;
  showDebug: boolean;
  mirror: boolean;
  /** Turn the preview upside down (rotated camera / phone in a case). */
  flipVertical: boolean;
  deviceId: string;
  tutorialDone: boolean;
}

const SETTINGS_KEY = 'lumen-dash-settings';
const defaults: Settings = {
  sensitivity: 1,
  volume: 0.7,
  music: true,
  sfx: true,
  reducedMotion: false,
  quality: 'medium',
  showPip: true,
  showDebug: false,
  mirror: true,
  flipVertical: false,
  deviceId: '',
  tutorialDone: false,
};

function loadSettings(): Settings {
  try {
    const raw = localStorage.getItem(SETTINGS_KEY);
    if (raw) return { ...defaults, ...JSON.parse(raw) };
  } catch {
    /* ignore */
  }
  return defaults;
}

export const settingsStore = createStore<Settings>(loadSettings());
settingsStore.subscribe(() => {
  try {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(settingsStore.get()));
  } catch {
    /* ignore */
  }
});

// ---------------- UI flow ----------------
export type Screen = 'menu' | 'howto' | 'setup' | 'game';
export type SetupPhase = 'starting' | 'error' | 'calibrating' | 'tutorial';

export interface UiState {
  screen: Screen;
  settingsOpen: boolean;
  mode: 'keyboard' | 'camera';
  setup: {
    phase: SetupPhase;
    message: string;
    framingOk: boolean;
    progress: number;
    tutorialStep: number;
    tutorialDone: boolean[];
    returnToGame: boolean;
  };
  contextLost: boolean;
  toast: string | null;
}

export const uiStore = createStore<UiState>({
  screen: 'menu',
  settingsOpen: false,
  mode: 'keyboard',
  setup: { phase: 'starting', message: '', framingOk: false, progress: 0, tutorialStep: 0, tutorialDone: [false, false, false, false], returnToGame: false },
  contextLost: false,
  toast: null,
});

// ---------------- game HUD ----------------
export const hudStore = createStore<HudState>({
  state: 'menu',
  pauseReason: 'manual',
  countdown: 3,
  score: 0,
  distance: 0,
  motes: 0,
  streak: 0,
  mult: 1,
  tier: 1,
  speed: 11,
  pips: 2,
  closeness: 0,
  best: 0,
  newBest: false,
  biome: 'Causeway',
  fps: 60,
  trackingLost: false,
});

// ---------------- gesture feedback & debug ----------------
export interface GestureHud {
  calibrated: boolean;
  tracking: TrackingState;
  zone: ZoneX;
  posture: Posture;
  handsUp: number;
  jumpAt: number;
  crouchAt: number;
}
export const gestureStore = createStore<GestureHud>({
  calibrated: false,
  tracking: 'lost',
  zone: 0,
  posture: 'standing',
  handsUp: 0,
  jumpAt: 0,
  crouchAt: 0,
});

export interface DebugInfo {
  poseFps: number;
  inferenceMs: number;
  delegate: string;
  source: string;
  latency: number;
  lateral: number;
  vertical: number;
  log: string[];
}
export const debugStore = createStore<DebugInfo>({
  poseFps: 0,
  inferenceMs: 0,
  delegate: '-',
  source: '-',
  latency: 0,
  lateral: 0,
  vertical: 0,
  log: [],
});
