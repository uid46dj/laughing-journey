import { RUN, speedAt, tierAt } from './config';
import type { ObstacleKind } from './config';
import { Rng } from './rng';
import { PATTERNS } from './patterns';

export type Lane = -1 | 0 | 1;

export type SpawnItem =
  | { kind: 'obstacle'; type: ObstacleKind; s: number; lane: Lane }
  | { kind: 'mote'; s: number; lane: Lane; y: number }
  | { kind: 'prism'; s: number; lane: Lane; y: number };

type Action = 'none' | 'jump' | 'slide' | 'block';

const CELL_TYPE: Record<string, ObstacleKind> = { B: 'barrier', G: 'gate', M: 'monolith', C: 'crack', L: 'lantern' };

export const actionOf = (c: string): Action =>
  c === '.' ? 'none' : c === 'B' || c === 'C' ? 'jump' : c === 'G' || c === 'L' ? 'slide' : 'block';

/** Time a human needs to shift `d` lanes. */
const changeTime = (d: number) => (d === 0 ? 0 : d === 1 ? 0.55 : 1.0);

/** Time needed between two consecutive actions (jump->slide etc. must be generous: bodies are slow). */
const transitionTime = (a: Action, b: Action) => {
  if (a === 'none' || b === 'none') return 0;
  if ((a === 'jump' && b === 'slide') || (a === 'slide' && b === 'jump')) return 0.9;
  if (a === 'jump') return 0.8;
  return 0.6;
};

/** Minimum gap (s) between consecutive action requirements for a tier. 1.4s at tier 1 -> 0.8s at tier 5. */
export const baseGap = (tier: number) => Math.max(1.4 - 0.15 * (tier - 1), 0.8);

export const pairCost = (base: number, prevCell: string, cell: string, fromLane: number, toLane: number) =>
  Math.max(base, changeTime(Math.abs(fromLane - toLane)), transitionTime(actionOf(prevCell), actionOf(cell)));

export class TrackGenerator {
  private rng: Rng;
  cursor: number;
  private reachable = [true, true, true];
  private prevRow: string | null = null;
  private patternCount = 0;
  /** Menu attract mode: only motes. */
  restOnly = false;

  constructor(seed: number, restOnly = false) {
    this.rng = new Rng(seed);
    this.restOnly = restOnly;
    this.cursor = 12;
    this.prevRow = null;
    this.firstRest = true;
  }
  private firstRest: boolean;

  generateUntil(limit: number): SpawnItem[] {
    const out: SpawnItem[] = [];
    while (this.cursor < limit) this.nextPattern(out);
    return out;
  }

  private nextPattern(out: SpawnItem[]) {
    if (this.restOnly) {
      this.rest(out, 1.6, 2.4);
      return;
    }
    if (this.firstRest) {
      this.firstRest = false;
      this.rest(out, 0, 0, RUN.introClear);
      return;
    }
    const tier = tierAt(this.cursor);
    const pool = PATTERNS.filter((p) => p.tier <= tier);
    const weights = pool.map((p) => (p.tier === tier ? 3 : p.tier === tier - 1 ? 2 : 1));
    let r = this.rng.next() * weights.reduce((a, b) => a + b, 0);
    let pat = pool[0];
    for (let i = 0; i < pool.length; i++) {
      r -= weights[i];
      if (r <= 0) {
        pat = pool[i];
        break;
      }
    }
    const mirror = this.rng.chance(0.5);
    const rows = pat.rows.map((row) => (mirror ? [...row].reverse().join('') : row));
    const base = baseGap(tier);

    rows.forEach((row, idx) => {
      if (idx === 0) {
        // first row follows a rest gap that was already added to the cursor.
        this.prevRow = null;
      } else {
        const gap = this.rowGap(this.prevRow!, row, base);
        const prev = this.prevRow!;
        const prevS = this.cursor;
        this.cursor += gap * speedAt(this.cursor) * 1.05;
        this.placeMotesBetween(out, prev, row, prevS, this.cursor);
        this.updateReachable(prev, row, base, gap);
      }
      this.placeRow(out, row);
      this.prevRow = row;
    });
    this.patternCount++;
    // breathing room: motes only, any lane becomes reachable again
    this.rest(out, 1.5, 2.6);
  }

  private rowGap(prev: string, row: string, base: number): number {
    let best = Infinity;
    for (let a = 0; a < 3; a++) {
      if (!this.reachable[a] || prev[a] === 'M') continue;
      for (let b = 0; b < 3; b++) {
        if (row[b] === 'M') continue;
        best = Math.min(best, pairCost(base, prev[a], row[b], a, b));
      }
    }
    return Number.isFinite(best) ? best : Math.max(base, 1.0);
  }

  private updateReachable(prev: string, row: string, base: number, gap: number) {
    const next = [false, false, false];
    for (let b = 0; b < 3; b++) {
      if (row[b] === 'M') continue;
      for (let a = 0; a < 3; a++) {
        if (!this.reachable[a] || prev[a] === 'M') continue;
        if (pairCost(base, prev[a], row[b], a, b) <= gap + 1e-6) next[b] = true;
      }
    }
    this.reachable = next;
  }

  /** Public so tests can check what the player must be able to do. */
  getReachable() {
    return [...this.reachable];
  }

  private placeRow(out: SpawnItem[], row: string) {
    for (let i = 0; i < 3; i++) {
      const c = row[i];
      if (c === '.') continue;
      const lane = (i - 1) as Lane;
      out.push({ kind: 'obstacle', type: CELL_TYPE[c], s: this.cursor, lane });
      if ((c === 'B' || c === 'C') && this.rng.chance(0.7)) {
        // reward arc: collecting means you jumped
        for (let k = -2; k <= 2; k++) {
          const o = k * 1.5;
          out.push({ kind: 'mote', s: this.cursor + o, lane, y: 0.7 + 1.5 * (1 - (o / 3.4) ** 2) });
        }
      } else if (c === 'G' && this.rng.chance(0.6)) {
        for (let k = -2; k <= 2; k++) out.push({ kind: 'mote', s: this.cursor + k * 1.5, lane, y: 0.5 });
      }
    }
  }

  private placeMotesBetween(out: SpawnItem[], prev: string, row: string, s1: number, s2: number) {
    const d = s2 - s1;
    const n = Math.min(6, Math.floor((d - 4) / 1.8));
    if (n < 2) return;
    const candidates: Lane[] = [];
    for (let l = 0; l < 3; l++) {
      if (this.reachable[l] && prev[l] === '.' && row[l] === '.') candidates.push((l - 1) as Lane);
    }
    if (!candidates.length) return;
    const lane = candidates[this.rng.int(0, candidates.length - 1)];
    const start = s1 + (d - (n - 1) * 1.8) / 2;
    for (let i = 0; i < n; i++) out.push({ kind: 'mote', s: start + i * 1.8, lane, y: 0.7 });
  }

  private rest(out: SpawnItem[], minSec: number, maxSec: number, fixedDist?: number) {
    const dist = fixedDist ?? this.rng.range(minSec, maxSec) * speedAt(this.cursor) * 1.05;
    const lane = this.rng.int(-1, 1) as Lane;
    const n = Math.min(12, Math.floor((dist - 4) / 1.8));
    const start = this.cursor + 3;
    for (let i = 0; i < n; i++) {
      const sinuous = this.restOnly ? 0 : 0;
      out.push({ kind: 'mote', s: start + i * 1.8, lane, y: 0.7 + sinuous });
    }
    if (!this.restOnly && n > 4 && this.rng.chance(0.14)) {
      const pl = (((lane + 2) % 3) - 1) as Lane;
      out.push({ kind: 'prism', s: start + (n / 2) * 1.8, lane: pl, y: 1.0 });
    }
    this.cursor += dist;
    this.reachable = [true, true, true];
    this.prevRow = null;
  }
}
