import * as THREE from 'three';
import type { ObstacleKind } from './config';
import { bronzeTexture, goldTexture, rockTexture, stoneTexture } from './textures';

/**
 * Colour language: ochre = jump, verdigris = slide, rust = change lane. Shapes differ
 * too (not colour-only). Painted weathered surfaces rather than glowing neon: the tint sits
 * over the shared stone texture so obstacles still read as carved temple work.
 */
const painted = (color: string, repeat: [number, number]) =>
  new THREE.MeshStandardMaterial({ color, map: stoneTexture(repeat), flatShading: true, roughness: 0.95, metalness: 0 });

export const MATS = {
  stone: new THREE.MeshStandardMaterial({
    color: '#8d7f68',
    map: rockTexture([1, 2]),
    flatShading: true,
    roughness: 1,
    metalness: 0,
  }),
  amber: painted('#c9852f', [1, 1]),
  cyan: painted('#4f8f86', [1, 1]),
  magenta: painted('#9c4a3c', [1, 1]),
  void: new THREE.MeshBasicMaterial({ color: '#171009' }),
  mote: new THREE.MeshStandardMaterial({
    color: '#e8c98a',
    map: goldTexture(),
    flatShading: true,
    roughness: 0.42,
    metalness: 0.65,
  }),
  prism: new THREE.MeshStandardMaterial({
    color: '#9cc4b4',
    map: bronzeTexture(),
    flatShading: true,
    roughness: 0.38,
    metalness: 0.7,
  }),
};
const box = (w: number, h: number, d: number, mat: THREE.Material, x = 0, y = 0, z = 0) => {
  const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat);
  m.position.set(x, y, z);
  return m;
};

export function buildObstacle(kind: ObstacleKind): THREE.Group {
  const g = new THREE.Group();
  switch (kind) {
    case 'barrier': {
      // low, wide, amber-topped cairn arc: "hop over me"
      g.add(box(0.4, 0.7, 0.55, MATS.stone, -0.85, 0.35));
      g.add(box(0.4, 0.7, 0.55, MATS.stone, 0.85, 0.35));
      g.add(box(2.2, 0.22, 0.5, MATS.amber, 0, 0.74));
      const spike = new THREE.Mesh(new THREE.ConeGeometry(0.2, 0.4, 4), MATS.amber);
      spike.position.set(0, 1.0, 0);
      g.add(spike);
      break;
    }
    case 'gate': {
      // cyan lintel hanging at head height: "duck under me"
      g.add(box(0.28, 2.6, 0.3, MATS.stone, -1.05, 1.3));
      g.add(box(0.28, 2.6, 0.3, MATS.stone, 1.05, 1.3));
      g.add(box(2.4, 0.5, 0.4, MATS.cyan, 0, 1.9));
      for (const x of [-0.6, 0, 0.6]) {
        const shard = new THREE.Mesh(new THREE.ConeGeometry(0.16, 0.45, 4), MATS.cyan);
        shard.rotation.x = Math.PI;
        shard.position.set(x, 1.45, 0);
        g.add(shard);
      }
      break;
    }
    case 'monolith': {
      // tall magenta-veined pillar: "go around me"
      g.add(box(1.8, 3.6, 1.1, MATS.stone, 0, 1.8));
      g.add(box(0.22, 3.0, 1.15, MATS.magenta, 0, 1.8));
      g.add(box(1.3, 0.25, 1.2, MATS.magenta, 0, 3.55));
      break;
    }
    case 'crack': {
      g.add(box(2.2, 0.04, 4.0, MATS.void, 0, 0.03));
      g.add(box(0.12, 0.08, 4.1, MATS.amber, -1.1, 0.05));
      g.add(box(0.12, 0.08, 4.1, MATS.amber, 1.1, 0.05));
      g.add(box(2.3, 0.08, 0.12, MATS.amber, 0, 0.05, -2.0));
      g.add(box(2.3, 0.08, 0.12, MATS.amber, 0, 0.05, 2.0));
      break;
    }
    case 'lantern': {
      // pendulum: pivot group is rotated each frame (see World.update)
      const pivot = new THREE.Group();
      pivot.name = 'pivot';
      pivot.position.y = 4.2;
      const chain = box(0.06, 2.6, 0.06, MATS.stone, 0, -1.3);
      const body = new THREE.Mesh(new THREE.OctahedronGeometry(0.5), MATS.cyan);
      body.position.y = -2.7;
      body.scale.set(1, 1.2, 1);
      pivot.add(chain, body);
      g.add(pivot);
      g.add(box(0.4, 0.3, 0.4, MATS.stone, 0, 4.2));
      break;
    }
  }
  return g;
}

const moteGeo = new THREE.OctahedronGeometry(0.24, 0);
const prismGeo = new THREE.OctahedronGeometry(0.5, 0);

export const buildMote = () => new THREE.Mesh(moteGeo, MATS.mote);
export const buildPrism = () => {
  const m = new THREE.Mesh(prismGeo, MATS.prism);
  m.scale.set(0.8, 1.4, 0.8);
  return m;
};
