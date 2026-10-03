import * as THREE from 'three';
import { clothTexture } from './textures';

export interface RunnerPoseInput {
  speed: number;
  grounded: boolean;
  sliding: boolean;
  stumbling: boolean;
  dead: boolean;
  lateralVel: number;
  time: number;
  idle: boolean;
}

const damp = (cur: number, target: number, k: number, dt: number) => cur + (target - cur) * (1 - Math.exp(-k * dt));

/**
 * The Lumen Courier — built from primitives, procedurally animated.
 * Faces -Z. A glowing lantern pack on the back faces the chase camera.
 */
export class RunnerModel {
  readonly object = new THREE.Group();
  private body = new THREE.Group();
  private torso: THREE.Group;
  private legL: THREE.Group;
  private legR: THREE.Group;
  private armL: THREE.Group;
  private armR: THREE.Group;
  private scarf: THREE.Group[] = [];
  private lantern: THREE.Mesh;
  private shadow: THREE.Mesh;
  private phase = 0;
  private cur = { lean: 0, legL: 0, legR: 0, armL: 0, armR: 0, y: 0 };

  constructor() {
    const suit = new THREE.MeshStandardMaterial({ color: '#ded3bd', map: clothTexture(), flatShading: true, roughness: 0.95 });
    const dark = new THREE.MeshStandardMaterial({ color: '#5b4b3a', flatShading: true, roughness: 1 });
    const amber = new THREE.MeshStandardMaterial({ color: '#b5762a', flatShading: true, roughness: 0.85 });
    const glow = new THREE.MeshStandardMaterial({ color: '#e8c98a', emissive: '#d9a441', emissiveIntensity: 0.25, flatShading: true, roughness: 0.5 });
    const visorMat = new THREE.MeshStandardMaterial({ color: '#8fa79a', flatShading: true, roughness: 0.3, metalness: 0.6 });

    this.torso = new THREE.Group();
    const chest = new THREE.Mesh(new THREE.CapsuleGeometry(0.22, 0.42, 4, 8), suit);
    chest.position.y = 1.08;
    const belt = new THREE.Mesh(new THREE.CylinderGeometry(0.24, 0.24, 0.08, 8), amber);
    belt.position.y = 0.9;
    const head = new THREE.Mesh(new THREE.SphereGeometry(0.2, 12, 10), suit);
    head.position.y = 1.58;
    const hood = new THREE.Mesh(new THREE.SphereGeometry(0.22, 10, 8, 0, Math.PI * 2, 0, Math.PI * 0.62), dark);
    hood.position.y = 1.6;
    hood.rotation.x = 0.25;
    const visor = new THREE.Mesh(new THREE.BoxGeometry(0.26, 0.07, 0.06), visorMat);
    visor.position.set(0, 1.58, -0.18);
    const pack = new THREE.Mesh(new THREE.BoxGeometry(0.32, 0.4, 0.16), dark);
    pack.position.set(0, 1.1, 0.26);
    this.lantern = new THREE.Mesh(new THREE.OctahedronGeometry(0.15), glow);
    this.lantern.position.set(0, 1.12, 0.38);
    this.torso.add(chest, belt, head, hood, visor, pack, this.lantern);

    const limb = (len: number, r: number, mat: THREE.Material, x: number, y: number) => {
      const pivot = new THREE.Group();
      pivot.position.set(x, y, 0);
      const m = new THREE.Mesh(new THREE.CapsuleGeometry(r, len, 4, 6), mat);
      m.position.y = -(len / 2 + r);
      pivot.add(m);
      return pivot;
    };
    this.legL = limb(0.5, 0.1, dark, -0.13, 0.82);
    this.legR = limb(0.5, 0.1, dark, 0.13, 0.82);
    this.armL = limb(0.4, 0.075, suit, -0.31, 1.35);
    this.armR = limb(0.4, 0.075, suit, 0.31, 1.35);

    // scarf: chained segments trailing behind
    let parent: THREE.Object3D = this.torso;
    for (let i = 0; i < 4; i++) {
      const seg = new THREE.Group();
      const m = new THREE.Mesh(new THREE.BoxGeometry(0.16 - i * 0.02, 0.04, 0.3), amber);
      m.position.z = 0.15;
      seg.add(m);
      seg.position.set(0, i === 0 ? 1.4 : 0, i === 0 ? 0.12 : 0.3);
      parent.add(seg);
      this.scarf.push(seg);
      parent = seg;
    }

    this.body.add(this.torso, this.legL, this.legR, this.armL, this.armR);
    this.object.add(this.body);

    this.shadow = new THREE.Mesh(
      new THREE.CircleGeometry(0.55, 16),
      new THREE.MeshBasicMaterial({ color: '#241a10', transparent: true, opacity: 0.32, depthWrite: false }),
    );
    this.shadow.rotation.x = -Math.PI / 2;
    this.shadow.position.y = 0.04;
    this.object.add(this.shadow);

    // gentle warm fill so the runner reads against dark ruins (no neon halo)
    const light = new THREE.PointLight('#ffe0b0', 1.6, 7);
    light.position.set(0, 1.4, 0.8);
    this.object.add(light);
  }

  setVisible(v: boolean) {
    this.body.visible = v;
  }

  /** y = height of feet above ground. */
  animate(dt: number, x: number, y: number, p: RunnerPoseInput) {
    this.object.position.x = x;
    this.phase += dt * p.speed * 0.75;
    const sw = Math.sin(this.phase);
    const c = this.cur;
    let lean = -0.14;
    let legL = sw * 0.95;
    let legR = -sw * 0.95;
    let armL = -sw * 0.9;
    let armR = sw * 0.9;
    let bob = Math.abs(Math.sin(this.phase)) * 0.07;
    let rootY = 0;

    if (p.idle) {
      legL = legR = armL = armR = 0;
      lean = 0;
      bob = Math.sin(p.time * 2) * 0.01;
    } else if (p.dead) {
      lean = -1.1;
      legL = 0.4;
      legR = -0.3;
      armL = 1.6;
      armR = 1.2;
      bob = 0;
    } else if (p.sliding) {
      lean = 1.25;
      legL = 0.15;
      legR = 0.25;
      armL = -1.0;
      armR = -1.2;
      rootY = 0.38;
      bob = 0;
    } else if (!p.grounded) {
      lean = -0.1;
      legL = 1.1;
      legR = 0.4;
      armL = 2.5;
      armR = 2.3;
      bob = 0;
    } else if (p.stumbling) {
      lean = -0.4 + Math.sin(p.time * 30) * 0.08;
      armL = 1.2;
      armR = 0.8;
    }

    const k = 22;
    c.lean = damp(c.lean, lean, k, dt);
    c.legL = damp(c.legL, legL, k, dt);
    c.legR = damp(c.legR, legR, k, dt);
    c.armL = damp(c.armL, armL, k, dt);
    c.armR = damp(c.armR, armR, k, dt);
    c.y = damp(c.y, rootY, k, dt);

    this.body.rotation.x = c.lean;
    this.body.position.y = y + c.y + bob;
    this.legL.rotation.x = c.legL;
    this.legR.rotation.x = c.legR;
    this.armL.rotation.x = c.armL;
    this.armR.rotation.x = c.armR;

    // scarf ripples with speed & lateral motion
    const wave = Math.min(1, p.speed / 28);
    this.scarf.forEach((s, i) => {
      s.rotation.x = -0.35 * wave + Math.sin(p.time * 9 - i * 0.9) * 0.18 * (0.4 + wave);
      s.rotation.y = Math.sin(p.time * 7 - i) * 0.1 + p.lateralVel * 0.025;
    });
    this.lantern.rotation.y = p.time * 2;
    const s = 1 - Math.min(0.6, y / 3);
    this.shadow.scale.setScalar(Math.max(0.4, s));
    (this.shadow.material as THREE.MeshBasicMaterial).opacity = 0.35 * Math.max(0.3, s);
  }
}
