import * as THREE from 'three';
import { BIOMES, BIOME_LEN, CHUNK_LEN, DRAW_DIST, LANE_W, QUALITY } from './config';
import type { Quality } from './config';
import { pathTexture, rockTexture } from './textures';

const smooth = (a: number, b: number, x: number) => {
  const t = Math.min(1, Math.max(0, (x - a) / (b - a)));
  return t * t * (3 - 2 * t);
};

const CHUNK_COUNT = Math.ceil((DRAW_DIST + 40) / CHUNK_LEN) + 2;

const tmpA = new THREE.Color();
const tmpB = new THREE.Color();

export class Environment {
  readonly group = new THREE.Group();
  readonly fog: THREE.FogExp2;
  private sky: THREE.Mesh;
  private skyUniforms: { top: { value: THREE.Color }; bottom: { value: THREE.Color } };
  private hemi: THREE.HemisphereLight;
  private sun: THREE.DirectionalLight;
  private chunks: THREE.Group[] = [];
  private pathMat = new THREE.MeshStandardMaterial({ color: '#b8ac93', map: pathTexture([1, 4]), flatShading: true, roughness: 1 });
  private edgeMat = new THREE.MeshStandardMaterial({ color: '#d9c9a3', flatShading: true, roughness: 0.9 });
  private lineMat = new THREE.MeshBasicMaterial({ color: '#6b5f47', transparent: true, opacity: 0.5 });
  private cliffMat = new THREE.MeshStandardMaterial({ color: '#7a6a52', map: rockTexture([1, 2]), flatShading: true, roughness: 1 });
  private crystalMat = new THREE.MeshStandardMaterial({ color: '#8fa79a', flatShading: true, roughness: 0.45, metalness: 0.5 });
  private dust: THREE.Points;
  private dustPos: Float32Array;
  private dustCount = 200;
  biomeName = BIOMES[0].name;

  constructor(scene: THREE.Scene) {
    this.fog = new THREE.FogExp2('#c8a071', QUALITY.medium.fog);
    scene.fog = this.fog;

    this.skyUniforms = { top: { value: new THREE.Color() }, bottom: { value: new THREE.Color() } };
    this.sky = new THREE.Mesh(
      new THREE.SphereGeometry(420, 24, 16),
      new THREE.ShaderMaterial({
        side: THREE.BackSide,
        depthWrite: false,
        fog: false,
        uniforms: this.skyUniforms,
        vertexShader: 'varying float vY; void main(){ vY = normalize(position).y; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }',
        fragmentShader: [
          'uniform vec3 top; uniform vec3 bottom; varying float vY;',
          'void main(){',
          '  float t = smoothstep(-0.02, 0.55, vY);',
          '  gl_FragColor = vec4(mix(bottom, top, t), 1.0);',
          '  #include <colorspace_fragment>',
          '}',
        ].join('\n'),
      }),
    );
    this.sky.renderOrder = -10;
    this.sky.frustumCulled = false;
    scene.add(this.sky);

    // low dusk sun disc, parented to the sky so it stays at the horizon
    const sunDisc = new THREE.Mesh(
      new THREE.CircleGeometry(38, 40),
      new THREE.MeshBasicMaterial({ color: '#fff0cd', transparent: true, opacity: 0.75, fog: false, depthWrite: false }),
    );
    sunDisc.position.set(0, 60, -380);
    this.sky.add(sunDisc);

    this.hemi = new THREE.HemisphereLight('#bcd2e8', '#6b5a42', 1.1);
    this.sun = new THREE.DirectionalLight('#ffe3b0', 1.9);
    this.sun.position.set(-6, 10, 8);
    this.sun.target.position.set(0, 0, -20);
    scene.add(this.hemi, this.sun, this.sun.target);

    this.group.name = 'environment';
    for (let i = 0; i < CHUNK_COUNT; i++) {
      const c = this.buildChunk();
      c.userData.index = i - 2;
      this.chunks.push(c);
      this.group.add(c);
    }
    scene.add(this.group);

    // drifting dust motes around the camera
    this.dustPos = new Float32Array(this.dustCount * 3);
    for (let i = 0; i < this.dustCount; i++) this.resetDust(i, true);
    const dg = new THREE.BufferGeometry();
    dg.setAttribute('position', new THREE.BufferAttribute(this.dustPos, 3));
    this.dust = new THREE.Points(
      dg,
      new THREE.PointsMaterial({ color: '#e8dcc0', size: 0.14, transparent: true, opacity: 0.4, depthWrite: false, sizeAttenuation: true }),
    );
    this.dust.frustumCulled = false;
    scene.add(this.dust);
  }

  private resetDust(i: number, anywhere: boolean) {
    this.dustPos[i * 3] = (Math.random() - 0.5) * 26;
    this.dustPos[i * 3 + 1] = 0.4 + Math.random() * 8;
    this.dustPos[i * 3 + 2] = anywhere ? -Math.random() * 90 + 6 : -90;
  }

  private buildChunk(): THREE.Group {
    const g = new THREE.Group();
    const slab = new THREE.Mesh(new THREE.BoxGeometry(LANE_W * 3 + 0.6, 0.6, CHUNK_LEN), this.pathMat);
    slab.position.set(0, -0.3, -CHUNK_LEN / 2);
    g.add(slab);
    // supports so the causeway reads as floating over a canyon
    const support = new THREE.Mesh(new THREE.BoxGeometry(4.2, 14, 6), this.cliffMat);
    support.position.set(0, -7.5, -CHUNK_LEN / 2);
    g.add(support);
    for (const x of [-LANE_W / 2, LANE_W / 2]) {
      const line = new THREE.Mesh(new THREE.BoxGeometry(0.07, 0.02, CHUNK_LEN), this.lineMat);
      line.position.set(x, 0.011, -CHUNK_LEN / 2);
      g.add(line);
    }
    for (const x of [-1, 1]) {
      const edge = new THREE.Mesh(new THREE.BoxGeometry(0.2, 0.14, CHUNK_LEN), this.edgeMat);
      edge.position.set(x * (LANE_W * 1.5 + 0.2), 0.05, -CHUNK_LEN / 2);
      g.add(edge);
      const cliff = new THREE.Mesh(new THREE.BoxGeometry(8, 1, CHUNK_LEN), this.cliffMat);
      cliff.name = 'cliff';
      cliff.userData.side = x;
      g.add(cliff);
      for (let k = 0; k < 3; k++) {
        const cr = new THREE.Mesh(new THREE.ConeGeometry(0.7, 1, 5), this.crystalMat);
        cr.name = 'crystal';
        cr.userData.side = x;
        g.add(cr);
      }
    }
    this.randomizeChunk(g);
    return g;
  }

  private randomizeChunk(g: THREE.Group) {
    g.children.forEach((m) => {
      const side = m.userData.side as number | undefined;
      if (m.name === 'cliff') {
        const h = 8 + Math.random() * 14;
        m.scale.y = h;
        m.position.set(side! * (13 + Math.random() * 3), h / 2 - 14, -CHUNK_LEN / 2);
      } else if (m.name === 'crystal') {
        const h = 2 + Math.random() * 5;
        m.scale.set(0.8 + Math.random() * 1.2, h, 0.8 + Math.random() * 1.2);
        m.position.set(side! * (7 + Math.random() * 5), h / 2 - 0.4, -Math.random() * CHUNK_LEN);
        m.rotation.y = Math.random() * 3;
        m.rotation.z = (Math.random() - 0.5) * 0.3;
      }
    });
  }

  /** Re-seat chunks at the start of the track (distance returns to 0). */
  reset() {
    this.chunks.forEach((c, i) => {
      c.userData.index = i - 2;
      this.randomizeChunk(c);
    });
  }

  setQuality(q: Quality) {
    this.fog.density = QUALITY[q].fog;
    this.dust.geometry.setDrawRange(0, Math.floor(this.dustCount * QUALITY[q].particles));
  }

  /** distance = metres run so far; runner stays at z=0, world slides toward the camera. */
  update(distance: number, dt: number, speed: number, camera: THREE.Camera) {
    // recycle chunks that fell behind the camera
    for (const c of this.chunks) {
      if ((c.userData.index + 1) * CHUNK_LEN < distance - 20) {
        let maxIdx = -Infinity;
        for (const o of this.chunks) maxIdx = Math.max(maxIdx, o.userData.index);
        c.userData.index = maxIdx + 1;
        this.randomizeChunk(c);
      }
      c.position.z = -(c.userData.index * CHUNK_LEN - distance);
    }

    // biome blend
    const p = distance / BIOME_LEN;
    const i = Math.floor(p);
    const f = smooth(0.82, 1, p - i);
    const a = BIOMES[i % BIOMES.length];
    const b = BIOMES[(i + 1) % BIOMES.length];
    this.biomeName = f > 0.5 ? b.name : a.name;
    const mix = (ka: string, kb: string, out: THREE.Color) => out.set(ka).lerp(tmpB.set(kb), f);
    mix(a.top, b.top, this.skyUniforms.top.value);
    mix(a.bottom, b.bottom, this.skyUniforms.bottom.value);
    this.fog.color.copy(this.skyUniforms.bottom.value);
    this.edgeMat.color.copy(mix(a.accent, b.accent, tmpA));
    this.crystalMat.color.copy(mix(a.crystal, b.crystal, tmpA));
    this.pathMat.color.copy(mix(a.path, b.path, tmpA));
    this.hemi.color.copy(this.skyUniforms.top.value).lerp(tmpB.set('#ffffff'), 0.4);

    this.sky.position.copy(camera.position);

    // dust flows toward camera
    const arr = this.dustPos;
    for (let k = 0; k < this.dustCount; k++) {
      arr[k * 3 + 2] += speed * dt * 0.7;
      arr[k * 3 + 1] += Math.sin(distance * 0.05 + k) * dt * 0.1;
      if (arr[k * 3 + 2] > 8) this.resetDust(k, false);
    }
    this.dust.geometry.attributes.position.needsUpdate = true;
  }
}
