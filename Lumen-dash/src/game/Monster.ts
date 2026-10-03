import * as THREE from 'three';

/**
 * The Hollow — the monster that hunts the runner from behind.
 * Built from primitives (no external assets), like the runner.
 *
 * `closeness` (0..1) drives everything: the monster rises out of the frame
 * below and to the side, then converges on the runner's back. At 1.0 it is
 * right behind the player — caught.
 */
export class Monster {
  readonly object = new THREE.Group();
  private body = new THREE.Group();
  private spikes: THREE.Group;
  private eyes: THREE.Mesh[] = [];
  private shell: THREE.Mesh;
  private lungeT = 0;
  private lungeFrom = 0;

  constructor() {
    const dark = new THREE.MeshStandardMaterial({
      color: '#0a0618',
      flatShading: true,
      roughness: 0.9,
    });
    const eyeMat = new THREE.MeshStandardMaterial({
      color: '#f0abfc',
      emissive: '#d946ef',
      emissiveIntensity: 2.2,
      flatShading: true,
    });

    const core = new THREE.Mesh(new THREE.IcosahedronGeometry(0.85, 1), dark);
    core.position.y = 1.25;
    this.body.add(core);

    // maw: a dark open mouth facing the runner (and the camera behind it)
    const maw = new THREE.Mesh(new THREE.ConeGeometry(0.42, 0.55, 6), dark);
    maw.position.set(0, 0.95, 0.55);
    maw.rotation.x = Math.PI / 2.4;
    this.body.add(maw);

    // eyes on the camera-facing side (+Z)
    for (const side of [-1, 1]) {
      const eye = new THREE.Mesh(new THREE.SphereGeometry(0.11, 8, 8), eyeMat);
      eye.position.set(side * 0.32, 1.45, 0.62);
      this.eyes.push(eye);
      this.body.add(eye);
    }

    // spikes radiating from the core
    this.spikes = new THREE.Group();
    const spikeMat = new THREE.MeshStandardMaterial({
      color: '#1a1030',
      flatShading: true,
      roughness: 1,
    });
    const dirs: Array<[number, number, number]> = [
      [0, 1, 0],
      [0.8, 0.5, 0.3],
      [-0.8, 0.5, 0.3],
      [0.7, -0.4, -0.5],
      [-0.7, -0.4, -0.5],
      [0, 0.3, -1],
      [0.9, -0.2, 0.6],
      [-0.9, -0.2, 0.6],
    ];
    for (const [dx, dy, dz] of dirs) {
      const spike = new THREE.Mesh(new THREE.ConeGeometry(0.15, 0.75, 5), spikeMat);
      const dir = new THREE.Vector3(dx, dy, dz).normalize();
      spike.position.copy(dir).multiplyScalar(0.95).add(new THREE.Vector3(0, 1.25, 0));
      spike.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir);
      this.spikes.add(spike);
    }
    this.body.add(this.spikes);

    // additive magenta aura, like the old Hollow lobes
    this.shell = new THREE.Mesh(
      new THREE.IcosahedronGeometry(1.25, 1),
      new THREE.MeshBasicMaterial({
        color: '#c026d3',
        transparent: true,
        opacity: 0.35,
        side: THREE.BackSide,
        blending: THREE.AdditiveBlending,
        fog: false,
      }),
    );
    this.shell.position.y = 1.25;
    this.body.add(this.shell);

    this.object.add(this.body);
    this.object.visible = false;
  }

  /** Catch animation: lunge onto the player. */
  lunge() {
    this.lungeT = 0.45;
    this.lungeFrom = this.object.position.z;
  }

  /**
   * @param x runner x (the monster tracks the player's lane)
   * @param closeness 0..1 — how close the monster is
   */
  update(dt: number, x: number, closeness: number, time: number) {
    // catch lunge: ease from the current position onto the player's back
    let z: number;
    if (this.lungeT > 0) {
      this.lungeT = Math.max(0, this.lungeT - dt);
      const k = 1 - this.lungeT / 0.45;
      const e = k * k * (3 - 2 * k);
      z = this.lungeFrom + (0.7 - this.lungeFrom) * e;
    } else {
      z = 5.2 - 3.7 * closeness;
    }
    const y = -0.9 + 2.0 * closeness;
    const side = (1 - closeness) * 1.9 * (closeness > 0.5 ? -1 : 1);
    this.object.position.set(x * 0.8 + side, y, z);

    const s = 0.7 + 0.5 * closeness;
    const pulse = 1 + Math.sin(time * 3.2) * 0.05;
    this.object.scale.setScalar(s * pulse);

    this.body.rotation.z = Math.sin(time * 1.7) * 0.12;
    this.body.rotation.y = Math.sin(time * 0.9) * 0.35;
    this.spikes.rotation.y += dt * 0.8;
    this.spikes.rotation.x = Math.sin(time * 1.3) * 0.15;

    // eyes flare as it gets close; snap to a stare during the lunge
    const flare = this.lungeT > 0 ? 4 : 2.2 + closeness * 1.5 + Math.sin(time * 5) * 0.4;
    for (const eye of this.eyes) {
      (eye.material as THREE.MeshStandardMaterial).emissiveIntensity = flare;
    }
    (this.shell.material as THREE.MeshBasicMaterial).opacity = 0.12 + closeness * 0.3;

    // when nearly on top of the player, it bobs forward hungrily
    if (closeness > 0.75 && this.lungeT <= 0) {
      const hunger = ((closeness - 0.75) / 0.25) * Math.max(0, Math.sin(time * 9)) * 0.45;
      this.object.position.z -= hunger;
    }
  }
}
