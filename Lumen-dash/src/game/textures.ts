import * as THREE from 'three';

/**
 * Procedural surface textures. Everything is drawn on a canvas at load time, so the game
 * ships no image files and stays fully offline.
 *
 * The palette is deliberately dusty and desaturated: weathered sandstone and worn temple
 * masonry rather than glowing neon. Form reads from the texture (mortar lines, grain,
 * weathering) instead of from emissive colour.
 */

const cache = new Map<string, THREE.Texture>();

function canvasOf(size: number): { c: HTMLCanvasElement; ctx: CanvasRenderingContext2D } {
  const c = document.createElement('canvas');
  c.width = size;
  c.height = size;
  const ctx = c.getContext('2d');
  if (!ctx) throw new Error('2D canvas is unavailable — cannot build textures.');
  return { c, ctx };
}

/** Deterministic jitter without Math.random, so every reload looks identical. */
function rng(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function speckle(
  ctx: CanvasRenderingContext2D,
  size: number,
  count: number,
  seed: number,
  light: string,
  dark: string,
) {
  const r = rng(seed);
  for (let i = 0; i < count; i++) {
    const x = r() * size;
    const y = r() * size;
    const s = 1 + r() * 2.2;
    ctx.fillStyle = r() > 0.5 ? light : dark;
    ctx.globalAlpha = 0.06 + r() * 0.14;
    ctx.fillRect(x, y, s, s);
  }
  ctx.globalAlpha = 1;
}

/** Vertical weathering streaks — the thing that makes stone look old rather than printed. */
function streaks(ctx: CanvasRenderingContext2D, size: number, count: number, seed: number, color: string) {
  const r = rng(seed);
  for (let i = 0; i < count; i++) {
    const x = r() * size;
    const w = 2 + r() * 9;
    const y = r() * size * 0.4;
    const h = size * (0.25 + r() * 0.7);
    const g = ctx.createLinearGradient(0, y, 0, y + h);
    g.addColorStop(0, 'rgba(0,0,0,0)');
    g.addColorStop(0.25, color);
    g.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.globalAlpha = 0.05 + r() * 0.1;
    ctx.fillStyle = g;
    ctx.fillRect(x, y, w, h);
  }
  ctx.globalAlpha = 1;
}

export interface MasonryOpts {
  size?: number;
  /** mortar / background colour, fills the whole canvas first */
  mortar: string;
  /** candidate block colours, picked at random per block */
  blocks: string[];
  /** number of block courses top to bottom */
  rows: number;
  /** 0..1 — per-block lightness variation */
  jitter?: number;
  /** extra speckle density */
  grain?: number;
  seed?: number;
}

/** Coursed masonry: offset blocks, recessed mortar, per-block tone variation, weathering. */
function drawMasonry(ctx: CanvasRenderingContext2D, size: number, o: MasonryOpts) {
  const r = rng(o.seed ?? 7);
  const jitter = o.jitter ?? 0.12;
  const gap = Math.max(2, Math.round(size / 190));

  ctx.fillStyle = o.mortar;
  ctx.fillRect(0, 0, size, size);

  const rowH = size / o.rows;
  const blockW = rowH * (1.7 + r() * 0.5);
  const bevel = Math.max(1, gap * 0.6);

  for (let row = 0; row < o.rows; row++) {
    const y = row * rowH;
    // alternate courses slide by half a block so vertical joints never line up
    const offset = (row % 2) * (blockW / 2) + (r() - 0.5) * blockW * 0.15;
    for (let x = -blockW; x < size + blockW; x += blockW) {
      const bx = x + offset;
      const tone = (r() - 0.5) * 2 * jitter;
      ctx.save();
      ctx.globalAlpha = Math.min(1, 1 + tone * 0.5);
      ctx.fillStyle = o.blocks[Math.floor(r() * o.blocks.length)];
      ctx.fillRect(bx + gap, y + gap, blockW - gap * 2, rowH - gap * 2);
      // bevelled edge: light on top, shadow at the bottom
      ctx.globalAlpha = 0.16;
      ctx.fillStyle = '#ffffff';
      ctx.fillRect(bx + gap, y + gap, blockW - gap * 2, bevel);
      ctx.fillStyle = '#000000';
      ctx.fillRect(bx + gap, y + rowH - gap - bevel, blockW - gap * 2, bevel);
      // chips broken out of the block edges
      if (r() > 0.82) {
        ctx.globalAlpha = 0.3;
        ctx.fillStyle = o.mortar;
        const cw = 2 + r() * (blockW * 0.22);
        ctx.fillRect(r() > 0.5 ? bx + gap : bx + blockW - cw - gap, y + gap, cw, bevel);
      }
      ctx.restore();
    }
  }

  speckle(ctx, size, Math.round(size * (o.grain ?? 0.9)), (o.seed ?? 7) + 991, '#ffffff', '#000000');
  streaks(ctx, size, Math.round(size / 14), (o.seed ?? 7) + 5501, '#2a2118');
}

/** Irregular rock face: horizontal strata plus heavy grain, for cliffs and canyon walls. */
function drawRock(ctx: CanvasRenderingContext2D, size: number, seed: number) {
  const r = rng(seed);
  ctx.fillStyle = '#6b5b46';
  ctx.fillRect(0, 0, size, size);
  const bands = 9 + Math.floor(r() * 5);
  for (let i = 0; i < bands; i++) {
    const y = (i / bands) * size + (r() - 0.5) * 6;
    const h = (size / bands) * (0.5 + r() * 0.9);
    const l = 0.55 + r() * 0.45;
    ctx.globalAlpha = 0.28 + r() * 0.3;
    ctx.fillStyle = `rgb(${Math.round(122 * l)},${Math.round(101 * l)},${Math.round(74 * l)})`;
    ctx.fillRect(0, y, size, h);
  }
  ctx.globalAlpha = 1;
  speckle(ctx, size, Math.round(size * 2.4), seed + 17, '#c9b48c', '#241c12');
  streaks(ctx, size, Math.round(size / 9), seed + 33, '#1d1710');
}

/** Hammered, slightly pitted metal for collectibles — reads as "gold", not as a light bulb. */
function drawMetal(ctx: CanvasRenderingContext2D, size: number, seed: number, base: string, hi: string) {
  const r = rng(seed);
  ctx.fillStyle = base;
  ctx.fillRect(0, 0, size, size);
  for (let i = 0; i < size / 3; i++) {
    ctx.globalAlpha = 0.06 + r() * 0.12;
    ctx.fillStyle = hi;
    ctx.beginPath();
    ctx.ellipse(r() * size, r() * size, 2 + r() * 7, 1 + r() * 4, r() * 3.14, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.globalAlpha = 1;
  speckle(ctx, size, Math.round(size * 0.7), seed + 71, '#fff6d8', '#3a2a12');
}

function finish(c: HTMLCanvasElement, repeat: [number, number]): THREE.Texture {
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.wrapS = THREE.RepeatWrapping;
  t.wrapT = THREE.RepeatWrapping;
  t.repeat.set(repeat[0], repeat[1]);
  t.anisotropy = 4;
  return t;
}

function memo(key: string, make: () => THREE.Texture): THREE.Texture {
  const hit = cache.get(key);
  if (hit) return hit;
  const t = make();
  cache.set(key, t);
  return t;
}

/** Weathered sandstone blocks — the default surface for walls and obstacles. */
export const stoneTexture = (repeat: [number, number] = [2, 2]): THREE.Texture =>
  memo(`stone-${repeat}`, () => {
    const size = 256;
    const { c, ctx } = canvasOf(size);
    drawMasonry(ctx, size, {
      mortar: '#4a3f30',
      blocks: ['#a89474', '#9d8a6c', '#b3a081', '#8e7c60', '#ab9778'],
      rows: 6,
      jitter: 0.14,
      seed: 7,
    });
    return finish(c, repeat);
  });

/** Bigger, paler slabs for the causeway deck — worn smooth by feet, so fewer joints. */
export const pathTexture = (repeat: [number, number] = [1, 4]): THREE.Texture =>
  memo(`path-${repeat}`, () => {
    const size = 256;
    const { c, ctx } = canvasOf(size);
    drawMasonry(ctx, size, {
      mortar: '#5c5245',
      blocks: ['#c3b79d', '#b6aa91', '#cfc4ab', '#a99d84'],
      rows: 4,
      jitter: 0.09,
      grain: 1.3,
      seed: 23,
    });
    return finish(c, repeat);
  });

/** Canyon rock for the cliffs, supports and scenery spines. */
export const rockTexture = (repeat: [number, number] = [2, 2]): THREE.Texture =>
  memo(`rock-${repeat}`, () => {
    const size = 256;
    const { c, ctx } = canvasOf(size);
    drawRock(ctx, size, 41);
    return finish(c, repeat);
  });

/** Hammered gold for motes. */
export const goldTexture = (repeat: [number, number] = [1, 1]): THREE.Texture =>
  memo(`gold-${repeat}`, () => {
    const size = 128;
    const { c, ctx } = canvasOf(size);
    drawMetal(ctx, size, 61, '#b08a3c', '#f2d98a');
    return finish(c, repeat);
  });

/** Oxidised bronze for prisms — greenish and aged, not neon. */
export const bronzeTexture = (repeat: [number, number] = [1, 1]): THREE.Texture =>
  memo(`bronze-${repeat}`, () => {
    const size = 128;
    const { c, ctx } = canvasOf(size);
    drawMetal(ctx, size, 89, '#6d8a76', '#b9cfb4');
    return finish(c, repeat);
  });

/** Coarse weave for the runner's suit — keeps the character readable without any shine. */
export const clothTexture = (repeat: [number, number] = [2, 2]): THREE.Texture =>
  memo(`cloth-${repeat}`, () => {
    const size = 128;
    const { c, ctx } = canvasOf(size);
    const r = rng(137);
    ctx.fillStyle = '#ded3bd';
    ctx.fillRect(0, 0, size, size);
    for (let i = 0; i < size; i += 3) {
      ctx.globalAlpha = 0.06 + r() * 0.05;
      ctx.fillStyle = i % 6 === 0 ? '#8a7d63' : '#ffffff';
      ctx.fillRect(i, 0, 1.5, size);
      ctx.fillRect(0, i, size, 1.5);
    }
    ctx.globalAlpha = 1;
    speckle(ctx, size, Math.round(size * 0.5), 137, '#ffffff', '#6b5f47');
    return finish(c, repeat);
  });

/** Called on teardown so the GPU copies are released. */
export function disposeTextures() {
  for (const t of cache.values()) t.dispose();
  cache.clear();
}