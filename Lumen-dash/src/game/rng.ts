/** mulberry32 — small deterministic PRNG. All track generation goes through this. */
export class Rng {
  private a: number;
  constructor(seed: number) {
    this.a = seed >>> 0;
  }
  next(): number {
    this.a = (this.a + 0x6d2b79f5) >>> 0;
    let t = this.a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  }
  range(min: number, max: number) {
    return min + this.next() * (max - min);
  }
  int(min: number, maxInclusive: number) {
    return Math.floor(this.range(min, maxInclusive + 1));
  }
  chance(p: number) {
    return this.next() < p;
  }
}
