/**
 * Obstacle patterns. A pattern is a list of ROWS; each row is 3 characters (left, middle, right lane).
 *   .  empty        B  barrier (jump)     G  gate (slide)
 *   M  monolith (change lane)             C  crack (jump)       L  swinging lantern (slide)
 * RULE: every row must keep at least one passable lane (any char except M). Spacing between rows is
 * computed by the generator from the fairness rules, not stored here.
 */
export interface Pattern {
  tier: number;
  rows: string[];
}

export const PATTERNS: Pattern[] = [
  // Tier 1 — jump and lane change basics
  { tier: 1, rows: ['BBB'] },
  { tier: 1, rows: ['.B.'] },
  { tier: 1, rows: ['M..'] },
  { tier: 1, rows: ['MM.'] },
  { tier: 1, rows: ['.M.', 'M.M'] },
  { tier: 1, rows: ['B..', '..B'] },
  // Tier 2 — slide gates arrive
  { tier: 2, rows: ['GGG'] },
  { tier: 2, rows: ['.G.'] },
  { tier: 2, rows: ['G..', '.G.', '..G'] },
  { tier: 2, rows: ['MM.', '.MM'] },
  { tier: 2, rows: ['BBB', '.M.'] },
  // Tier 3 — cracks and mixed rows
  { tier: 3, rows: ['.C.'] },
  { tier: 3, rows: ['C.C'] },
  { tier: 3, rows: ['BBB', 'GGG'] },
  { tier: 3, rows: ['MM.', 'GGG'] },
  { tier: 3, rows: ['MM.', '.MM', 'MM.'] },
  { tier: 3, rows: ['CCC'] },
  // Tier 4 — swinging lanterns
  { tier: 4, rows: ['.L.'] },
  { tier: 4, rows: ['L.L', '.M.'] },
  { tier: 4, rows: ['LLL', 'BBB'] },
  { tier: 4, rows: ['B.G', '.M.'] },
  { tier: 4, rows: ['GBG'] },
  // Tier 5 — chains
  { tier: 5, rows: ['BBB', 'GGG', 'BBB'] },
  { tier: 5, rows: ['M.M', '.M.', 'M.M'] },
  { tier: 5, rows: ['CBC', '.M.', 'GLG'] },
  { tier: 5, rows: ['C.C', 'BGB'] },
  { tier: 5, rows: ['MM.', 'CCC', '.MM'] },
];
