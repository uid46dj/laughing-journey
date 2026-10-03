export const LANE_W = 2.4;
export const CHUNK_LEN = 24;
export const DRAW_DIST = 170;
export const SIM_DT = 1 / 120;

export const SPEED = { start: 11, max: 28, tau: 2000 };
/** Speed is a deterministic function of distance so the generator can plan spacing exactly. */
export const speedAt = (d: number) => SPEED.max - (SPEED.max - SPEED.start) * Math.exp(-d / SPEED.tau);
export const tierAt = (s: number) => Math.min(5, 1 + Math.floor(s / 400));

/**
 * Jog-speed control (second phone pointed at the player's legs).
 * The phone measures leg-cadence in steps/sec and sends it to the relay;
 * the game maps it to a bounded multiplier around the auto speed curve.
 * The track generator plans spacing with planSpeedAt() (worst case) so
 * jump/slide timing stays fair at ANY multiplier within the range.
 */
export const JOG = {
  /** Cadence (steps/sec) that maps to a 1.0× multiplier. */
  target: 2.5,
  /** Multiplier change per step/sec off target. */
  sensitivity: 0.35,
  minMult: 0.8,
  maxMult: 1.3,
  /** Closeness gained per second at full-slow (standing still catches in ~17 s). */
  gainRate: 0.3,
  /** Closeness recovered per second at full-fast. */
  recoverRate: 0.45,
  /** No cadence update for this long => treat as "no leg phone" (neutral). */
  signalTimeoutMs: 1500,
} as const;

/** Multiplier for a measured cadence, clamped to the fair range. */
export const jogMultFor = (cadence: number) =>
  Math.min(JOG.maxMult, Math.max(JOG.minMult, 1 + (cadence - JOG.target) * JOG.sensitivity));

/** Worst-case speed the track is planned for — always sufficient at any multiplier. */
export const planSpeedAt = (d: number) => speedAt(d) * JOG.maxMult;

export const RUN = {
  laneTime: 0.14,
  jumpHeight: 1.9,
  slideMin: 0.45,
  slideMax: 1.4,
  jumpBuffer: 0.15,
  slideBuffer: 0.12,
  invulnerable: 1.5,
  hollowHit: 0.8,
  hollowLethal: 0.5,
  hollowRecover: 0.08,
  stumbleSlow: 0.6,
  introClear: 70,
  fastFall: -22,
};

export const PLAYER = { halfX: 0.38, halfZ: 0.35, standH: 1.55, slideH: 0.65, footGrace: 0.12 };

export type ObstacleKind = 'barrier' | 'gate' | 'monolith' | 'crack' | 'lantern';

/** AABB in (lane-local x half-width, y range, z half-depth). */
export const OBSTACLE_BOX: Record<ObstacleKind, { hx: number; y0: number; y1: number; hz: number }> = {
  barrier: { hx: 1.0, y0: 0, y1: 0.85, hz: 0.5 },
  gate: { hx: 1.1, y0: 1.15, y1: 2.6, hz: 0.4 },
  monolith: { hx: 0.95, y0: 0, y1: 3.6, hz: 0.7 },
  crack: { hx: 1.1, y0: -2, y1: 0.25, hz: 2.0 },
  lantern: { hx: 0.4, y0: 1.2, y1: 2.2, hz: 0.4 },
};

export interface Biome {
  name: string;
  top: string;
  bottom: string;
  accent: string;
  crystal: string;
  path: string;
}

export const BIOMES: Biome[] = [
  { name: 'Dawn Causeway', top: '#3f4a63', bottom: '#c8a071', accent: '#e0cfa4', crystal: '#9fb3a8', path: '#b8ac93' },
  { name: 'Mossy Gorge', top: '#2f3d38', bottom: '#8fa07a', accent: '#c3cba4', crystal: '#8aa38c', path: '#a8ab8e' },
  { name: 'Ember Canyon', top: '#4a2f24', bottom: '#c07a45', accent: '#e8bb87', crystal: '#b08a6a', path: '#c0a488' },
];
export const BIOME_LEN = 600;

export type Quality = 'low' | 'medium' | 'high';
export const QUALITY: Record<Quality, { pixelRatio: number; fog: number; particles: number }> = {
  low: { pixelRatio: 1, fog: 0.02, particles: 0.4 },
  medium: { pixelRatio: 1.5, fog: 0.015, particles: 0.8 },
  high: { pixelRatio: 2, fog: 0.012, particles: 1 },
};
