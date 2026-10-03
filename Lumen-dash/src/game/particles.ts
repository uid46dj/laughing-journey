import * as THREE from 'three';

const MAX = 160;

/** Cheap additive burst particles (mote pickups, landings, hits). */
export class Particles {
  readonly points: THREE.Points;
  private pos = new Float32Array(MAX * 3);
  private col = new Float32Array(MAX * 3);
  private vel = new Float32Array(MAX * 3);
  private life = new Float32Array(MAX);
  private next = 0;
  private c = new THREE.Color();
  density = 1;

  constructor(scene: THREE.Scene) {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(this.pos, 3));
    g.setAttribute('color', new THREE.BufferAttribute(this.col, 3));
    this.points = new THREE.Points(
      g,
      new THREE.PointsMaterial({
        size: 0.22,
        vertexColors: true,
        transparent: true,
        blending: THREE.NormalBlending,
        depthWrite: false,
      }),
    );
    this.points.frustumCulled = false;
    this.pos.fill(-999);
    scene.add(this.points);
  }

  burst(x: number, y: number, z: number, color: string, count: number, speed: number) {
    this.c.set(color);
    const n = Math.max(1, Math.floor(count * this.density));
    for (let i = 0; i < n; i++) {
      const k = this.next;
      this.next = (this.next + 1) % MAX;
      this.pos[k * 3] = x;
      this.pos[k * 3 + 1] = y;
      this.pos[k * 3 + 2] = z;
      const a = Math.random() * Math.PI * 2;
      const up = Math.random();
      this.vel[k * 3] = Math.cos(a) * speed * (0.4 + Math.random() * 0.6);
      this.vel[k * 3 + 1] = (0.3 + up) * speed;
      this.vel[k * 3 + 2] = Math.sin(a) * speed * 0.6;
      this.col[k * 3] = this.c.r;
      this.col[k * 3 + 1] = this.c.g;
      this.col[k * 3 + 2] = this.c.b;
      this.life[k] = 0.5 + Math.random() * 0.4;
    }
  }

  reset() {
    this.life.fill(0);
    this.pos.fill(-999);
    this.col.fill(0);
  }

  update(dt: number, worldSpeed: number) {
    for (let i = 0; i < MAX; i++) {
      if (this.life[i] <= 0) continue;
      this.life[i] -= dt;
      if (this.life[i] <= 0) {
        this.pos[i * 3 + 1] = -999;
        continue;
      }
      this.vel[i * 3 + 1] -= 9 * dt;
      this.pos[i * 3] += this.vel[i * 3] * dt;
      this.pos[i * 3 + 1] += this.vel[i * 3 + 1] * dt;
      this.pos[i * 3 + 2] += (this.vel[i * 3 + 2] + worldSpeed) * dt;
      const f = Math.min(1, this.life[i] * 2.5);
      this.col[i * 3] *= f > 0.99 ? 1 : 0.94;
      this.col[i * 3 + 1] *= f > 0.99 ? 1 : 0.94;
      this.col[i * 3 + 2] *= f > 0.99 ? 1 : 0.94;
    }
    this.points.geometry.attributes.position.needsUpdate = true;
    this.points.geometry.attributes.color.needsUpdate = true;
  }
}
