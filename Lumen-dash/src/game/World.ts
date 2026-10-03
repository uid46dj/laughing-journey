import * as THREE from 'three';
import { DRAW_DIST, LANE_W } from './config';
import type { ObstacleKind } from './config';
import { TrackGenerator } from './TrackGenerator';
import type { Lane } from './TrackGenerator';
import { buildMote, buildObstacle, buildPrism } from './objects';

export type EntityKind = ObstacleKind | 'mote' | 'prism';

export interface Entity {
  kind: EntityKind;
  object: THREE.Object3D;
  s: number;
  lane: Lane;
  y: number;
  phase: number;
  hit: boolean;
}

/** Owns active obstacles/collectibles (pooled) and feeds them from the generator. */
export class World {
  readonly group = new THREE.Group();
  readonly active: Entity[] = [];
  private pools = new Map<EntityKind, THREE.Object3D[]>();
  private generator: TrackGenerator;

  constructor(
    scene: THREE.Scene,
    seed: number,
    restOnly: boolean,
  ) {
    scene.add(this.group);
    this.generator = new TrackGenerator(seed, restOnly);
  }

  reset(seed: number, restOnly: boolean) {
    for (const e of this.active) this.release(e.object, e.kind);
    this.active.length = 0;
    this.generator = new TrackGenerator(seed, restOnly);
  }

  private acquire(kind: EntityKind): THREE.Object3D {
    const pool = this.pools.get(kind);
    const obj = pool?.pop() ?? this.build(kind);
    obj.visible = true;
    this.group.add(obj);
    return obj;
  }

  private build(kind: EntityKind): THREE.Object3D {
    if (kind === 'mote') return buildMote();
    if (kind === 'prism') return buildPrism();
    return buildObstacle(kind);
  }

  release(obj: THREE.Object3D, kind: EntityKind) {
    obj.visible = false;
    this.group.remove(obj);
    let pool = this.pools.get(kind);
    if (!pool) this.pools.set(kind, (pool = []));
    pool.push(obj);
  }

  remove(e: Entity) {
    const i = this.active.indexOf(e);
    if (i >= 0) this.active.splice(i, 1);
    this.release(e.object, e.kind);
  }

  /** Obstacle centre x in world space (lanterns swing). */
  static entityX(e: Entity): number {
    let x = e.lane * LANE_W;
    if (e.kind === 'lantern') x += Math.sin(e.phase) * 2.6 * 0.34;
    return x;
  }

  update(distance: number, timeSec: number) {
    for (const item of this.generator.generateUntil(distance + DRAW_DIST)) {
      const kind: EntityKind = item.kind === 'obstacle' ? item.type : item.kind;
      const object = this.acquire(kind);
      this.active.push({
        kind,
        object,
        s: item.s,
        lane: item.lane,
        y: item.kind === 'obstacle' ? 0 : item.y,
        phase: (item.s * 1.7) % (Math.PI * 2),
        hit: false,
      });
    }
    for (let i = this.active.length - 1; i >= 0; i--) {
      const e = this.active[i];
      if (e.s < distance - 14) {
        this.active.splice(i, 1);
        this.release(e.object, e.kind);
        continue;
      }
      const o = e.object;
      if (e.kind === 'lantern') {
        e.phase = (e.s * 1.7 + timeSec * 2.2) % (Math.PI * 2);
        const pivot = o.getObjectByName('pivot');
        if (pivot) pivot.rotation.z = Math.sin(e.phase) * 0.34;
      }
      o.position.set(e.lane * LANE_W, e.kind === 'mote' || e.kind === 'prism' ? e.y + Math.sin(timeSec * 3 + e.s) * 0.08 : 0, -(e.s - distance));
      if (e.kind === 'mote' || e.kind === 'prism') o.rotation.y = timeSec * 2 + e.s;
    }
  }
}
