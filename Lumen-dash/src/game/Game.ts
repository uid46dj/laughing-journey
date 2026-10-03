import * as THREE from 'three';
import type { InputSource, RunnerInput } from './InputSource';
import { JOG, LANE_W, OBSTACLE_BOX, PLAYER, QUALITY, RUN, SIM_DT, jogMultFor, speedAt, tierAt, SPEED } from './config';
import type { Quality } from './config';
import { RunnerModel } from './RunnerModel';
import { Monster } from './Monster';
import { GameAudio } from './audio';
import { Particles } from './particles';
import { Environment } from './Environment';
import { World } from './World';
import type { Entity } from './World';

export type GameState = 'menu' | 'countdown' | 'playing' | 'paused' | 'dying' | 'gameover';
export type PauseReason = 'manual' | 'tracking' | 'hidden';

export interface HudState {
  state: GameState;
  pauseReason: PauseReason;
  countdown: number;
  score: number;
  distance: number;
  motes: number;
  streak: number;
  mult: number;
  tier: number;
  speed: number;
  pips: number;
  closeness: number;
  /** Leg-cadence in steps/sec from the second phone, or null when absent. */
  jogCadence: number | null;
  /** Current jog speed multiplier (1 = neutral). */
  jogMult: number;
  best: number;
  newBest: boolean;
  biome: string;
  fps: number;
  trackingLost: boolean;
}

export interface GameSettings {
  reducedMotion: boolean;
  quality: Quality;
  volume: number;
  music: boolean;
  sfx: boolean;
}

type Events = {
  mote: { streak: number; mult: number };
  prism: undefined;
  hit: undefined;
  jump: undefined;
  slide: undefined;
  land: undefined;
  gameOver: undefined;
  tierUp: { tier: number };
  tick: undefined;
  go: undefined;
};

class Emitter<E extends Record<string, unknown>> {
  private map = new Map<keyof E, Array<(p: never) => void>>();
  on<K extends keyof E>(k: K, fn: (p: E[K]) => void) {
    const a = this.map.get(k) ?? [];
    a.push(fn as (p: never) => void);
    this.map.set(k, a);
  }
  emit<K extends keyof E>(k: K, p?: E[K]) {
    this.map.get(k)?.forEach((fn) => (fn as (p: E[K] | undefined) => void)(p));
  }
}

const BEST_KEY = 'lumen-dash-best';
const clamp01 = (x: number) => Math.min(1, Math.max(0, x));
const damp = (k: number, dt: number) => 1 - Math.exp(-k * dt);

export class Game {
  onHud: (h: HudState) => void = () => {};
  onQualityDrop: (q: Quality) => void = () => {};
  readonly audio = new GameAudio();
  private events = new Emitter<Events>();

  private renderer: THREE.WebGLRenderer;
  private scene = new THREE.Scene();
  private camera = new THREE.PerspectiveCamera(62, 1, 0.1, 520);
  private env: Environment;
  private world: World;
  private runner = new RunnerModel();
  private particles: Particles;
  private monster = new Monster();
  private ro: ResizeObserver;
  private raf = 0;
  private lastNow = 0;
  private acc = 0;
  private input: InputSource | null = null;
  private seed: number;

  state: GameState = 'menu';
  private pauseReason: PauseReason = 'manual';
  private countdownT = 0;
  private dyingT = 0;
  private timeScale = 1;

  // sim
  private distance = 0;
  private simTime = 0;
  private realTime = 0;
  private speed = SPEED.start;
  private slowT = 0;
  private x = 0;
  private prevX = 0;
  private y = 0;
  private vy = 0;
  private grav = 30;
  private grounded = true;
  private laneFrom = 0;
  private laneTo = 0;
  private laneT = 1;
  private desiredLane = 0;
  private lastTarget: number | null = null;
  private sliding = false;
  private slideTimer = 0;
  private slideLatched = false;
  private slideHeld = false;
  private prevSlideHeld = false;
  private fastFall = false;
  private jumpBuf = 0;
  private slideBuf = 0;
  private invuln = 0;
  private closeness = 0;
  /** Raw cadence from the leg phone (steps/sec), null when absent. */
  private jogCadence: number | null = null;
  /** Smoothed jog speed multiplier. */
  private jogMult = 1;
  private bonus = 0;
  private motes = 0;
  private streak = 0;
  private lastMoteT = -99;
  private tier = 1;
  private best = 0;
  private newBest = false;
  private dead = false;

  // tracking / pause
  private lostFor = 0;
  private okFor = 0;
  private trackingState: RunnerInput['trackingState'] = 'n/a';

  // camera
  private camPos = new THREE.Vector3(2.6, 2.2, 4.6);
  private camLook = new THREE.Vector3(-1.2, 1.1, -3);
  private shake = 0;
  private reducedMotion = false;
  private quality: Quality = 'medium';
  private frameAvg = 16;
  private slowFrames = 0;
  private hudTimer = 0;
  private fpsAvg = 60;

  constructor(private container: HTMLElement) {
    const q = new URLSearchParams(location.search).get('seed');
    this.seed = q ? Number(q) || 1 : Math.floor(Math.random() * 1e9);
    try {
      this.best = Number(localStorage.getItem(BEST_KEY)) || 0;
    } catch {
      this.best = 0;
    }

    this.renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
    this.renderer.setClearColor('#150f4d');
    this.renderer.domElement.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;display:block;';
    container.appendChild(this.renderer.domElement);
    this.renderer.domElement.addEventListener('webglcontextlost', (e) => {
      e.preventDefault();
      cancelAnimationFrame(this.raf);
      window.dispatchEvent(new CustomEvent('lumen-contextlost'));
    });

    this.env = new Environment(this.scene);
    this.world = new World(this.scene, this.seed, true);
    this.particles = new Particles(this.scene);
    this.scene.add(this.runner.object);
    this.scene.add(this.monster.object);

    this.applyQuality('medium');
    this.ro = new ResizeObserver(() => this.resize());
    this.ro.observe(container);
    this.resize();
    this.wireSystems();
    document.addEventListener('visibilitychange', this.onVisibility);
    this.lastNow = performance.now();
    this.raf = requestAnimationFrame(this.frame);
  }

  // ---------- public API ----------
  setInput(src: InputSource | null) {
    this.input = src;
  }

  applySettings(s: GameSettings) {
    this.reducedMotion = s.reducedMotion;
    this.audio.configure(s.volume, s.music, s.sfx);
    if (s.quality !== this.quality) this.applyQuality(s.quality);
  }

  startRun() {
    this.audio.unlock();
    this.distance = 0;
    this.simTime = 0;
    this.speed = SPEED.start;
    this.slowT = 0;
    this.x = this.prevX = 0;
    this.y = 0;
    this.vy = 0;
    this.grounded = true;
    this.laneFrom = this.laneTo = this.desiredLane = 0;
    this.laneT = 1;
    this.lastTarget = null;
    this.sliding = false;
    this.slideLatched = false;
    this.jumpBuf = this.slideBuf = 0;
    this.invuln = 0;
    this.closeness = 0;
    this.jogCadence = null;
    this.jogMult = 1;
    this.bonus = 0;
    this.motes = 0;
    this.streak = 0;
    this.lastMoteT = -99;
    this.tier = 1;
    this.newBest = false;
    this.dead = false;
    this.dyingT = 0;
    this.timeScale = 1;
    this.shake = 0;
    this.lostFor = 0;
    this.okFor = 0;
    this.seed = (this.seed * 1664525 + 1013904223) >>> 0;
    const url = new URLSearchParams(location.search).get('seed');
    this.world.reset(url ? Number(url) || 1 : this.seed, false);
    this.env.reset();
    this.particles.reset();
    this.runner.setVisible(true);
    this.beginCountdown(3);
    this.audio.startMusic();
  }

  pause(reason: PauseReason = 'manual') {
    if (this.state !== 'playing' && this.state !== 'countdown') return;
    this.state = 'paused';
    this.pauseReason = reason;
    this.lostFor = 0;
    this.okFor = 0;
    this.pushHud();
  }

  /** Resume always goes through a 3s countdown so the player can get back into position. */
  resume() {
    if (this.state !== 'paused') return;
    this.beginCountdown(3);
  }

  quitToMenu() {
    this.state = 'menu';
    this.dead = false;
    this.timeScale = 1;
    this.distance = 0;
    this.x = 0;
    this.y = 0;
    this.grounded = true;
    this.sliding = false;
    this.closeness = 0;
    this.world.reset(this.seed, true);
    this.env.reset();
    this.particles.reset();
    this.audio.stopMusic();
    this.pushHud();
  }

  get isRunning() {
    return this.state !== 'menu';
  }

  dispose() {
    cancelAnimationFrame(this.raf);
    this.ro.disconnect();
    document.removeEventListener('visibilitychange', this.onVisibility);
    this.audio.stopMusic();
    this.renderer.dispose();
    this.renderer.domElement.remove();
  }

  // ---------- internals ----------
  private beginCountdown(sec: number) {
    this.state = 'countdown';
    this.countdownT = sec;
    this.lastTick = Math.ceil(sec) + 1;
    this.pushHud();
  }
  private lastTick = 0;

  private wireSystems() {
    const a = this.audio;
    const p = this.particles;
    this.events.on('jump', () => {
      a.jump();
      p.burst(this.x, 0.1, 0, '#fde68a', 8, 2);
    });
    this.events.on('slide', () => a.slide());
    this.events.on('land', () => {
      a.land();
      p.burst(this.x, 0.1, 0, '#c4b5fd', 10, 2.5);
    });
    this.events.on('mote', ({ streak, mult }) => {
      a.mote(streak);
      p.burst(this.x, this.y + 1, 0, '#fde047', 6, 3);
      if (streak > 0 && streak % 10 === 0) a.tierUp();
      void mult;
    });
    this.events.on('prism', () => {
      a.prism();
      p.burst(this.x, this.y + 1, 0, '#bcd0bd', 24, 4);
    });
    this.events.on('hit', () => {
      a.hit();
      p.burst(this.x, this.y + 1, 0, '#fb7185', 28, 4.5);
    });
    this.events.on('gameOver', () => a.gameOver());
    this.events.on('tierUp', () => a.tierUp());
    this.events.on('tick', () => a.tick());
    this.events.on('go', () => a.go());
  }

  private applyQuality(q: Quality) {
    this.quality = q;
    const cfg = QUALITY[q];
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, cfg.pixelRatio));
    this.env.setQuality(q);
    this.particles.density = cfg.particles;
    this.resize();
  }

  private resize() {
    const w = this.container.clientWidth || window.innerWidth;
    const h = this.container.clientHeight || window.innerHeight;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
  }

  private onVisibility = () => {
    if (document.hidden) this.pause('hidden');
  };

  private frame = (now: number) => {
    this.raf = requestAnimationFrame(this.frame);
    const dtReal = Math.min((now - this.lastNow) / 1000, 0.1);
    this.lastNow = now;
    if (dtReal <= 0) return;
    this.realTime += dtReal;

    this.pollInput(now, dtReal);
    this.updateState(dtReal);

    if (this.state === 'menu' || this.state === 'playing' || this.state === 'dying') {
      this.acc += dtReal * this.timeScale;
      let guard = 0;
      while (this.acc >= SIM_DT && guard++ < 20) {
        if (this.state === 'menu') this.stepMenu(SIM_DT);
        else this.stepPlaying(SIM_DT);
        this.acc -= SIM_DT;
      }
    }

    this.render(dtReal);
    this.monitorPerf(dtReal);

    this.hudTimer += dtReal;
    if (this.hudTimer > 0.066) {
      this.hudTimer = 0;
      this.pushHud();
    }
  };

  private pollInput(now: number, dtReal: number) {
    const inp = this.input ? this.input.poll(now) : null;
    this.trackingState = inp?.trackingState ?? 'n/a';
    this.jogCadence = inp?.jogCadence ?? null;
    if (!inp) {
      this.slideHeld = false;
      return;
    }
    if (inp.trackingState === 'lost') {
      this.lostFor += dtReal;
      this.okFor = 0;
    } else if (inp.trackingState === 'ok') {
      this.okFor += dtReal;
      this.lostFor = 0;
    }
    if (this.state === 'playing' && this.lostFor > 1.5) this.pause('tracking');
    else if (this.state === 'paused' && this.pauseReason === 'tracking' && this.okFor > 1.0) this.resume();

    if (inp.pausePressed) {
      if (this.state === 'playing' || this.state === 'countdown') this.pause('manual');
      else if (this.state === 'paused') this.resume();
    }

    const live = this.state === 'playing' && !this.dead;
    if (!live) {
      this.slideHeld = false;
      this.prevSlideHeld = inp.slideHeld;
      return;
    }
    if (inp.laneStep !== 0) this.desiredLane = Math.max(-1, Math.min(1, this.desiredLane + inp.laneStep));
    if (inp.targetLane !== null && inp.targetLane !== this.lastTarget) this.desiredLane = inp.targetLane;
    this.lastTarget = inp.targetLane;
    if (inp.jumpPressed) this.jumpBuf = RUN.jumpBuffer;
    this.slideHeld = inp.slideHeld;
    if (inp.slideHeld && !this.prevSlideHeld) {
      this.slideBuf = RUN.slideBuffer;
      if (!this.grounded) this.fastFall = true;
    }
    this.prevSlideHeld = inp.slideHeld;
  }

  private updateState(dtReal: number) {
    if (this.state === 'countdown') {
      this.countdownT -= dtReal;
      const n = Math.ceil(this.countdownT);
      if (n < this.lastTick && n > 0) {
        this.lastTick = n;
        this.events.emit('tick');
      }
      if (this.countdownT <= 0) {
        this.state = 'playing';
        this.events.emit('go');
        this.pushHud();
      }
    } else if (this.state === 'dying') {
      this.dyingT += dtReal;
      if (this.dyingT > 0.9) {
        this.state = 'gameover';
        this.timeScale = 1;
        this.audio.stopMusic();
        this.pushHud();
      }
    }
  }

  private stepMenu(dt: number) {
    this.speed = SPEED.start;
    this.distance += this.speed * dt;
    this.simTime += dt;
    this.prevX = this.x;
    this.x = Math.sin(this.simTime * 0.6) * LANE_W * 0.9;
  }

  private stepPlaying(dt: number) {
    this.simTime += dt;
    this.slowT = Math.max(0, this.slowT - dt / 1.5);
    // jog speed: cadence -> bounded multiplier (fast attack, slower release)
    const targetMult = this.jogCadence !== null ? jogMultFor(this.jogCadence) : 1;
    const k = targetMult > this.jogMult ? 6 : 2.5;
    this.jogMult += (targetMult - this.jogMult) * damp(k, dt);
    let mult = 1 - (1 - RUN.stumbleSlow) * Math.min(1, this.slowT * 1.5);
    if (this.dead) mult *= Math.max(0.05, 1 - this.dyingT / 0.5);
    this.speed = speedAt(this.distance) * mult * this.jogMult;
    this.distance += this.speed * dt;

    this.invuln = Math.max(0, this.invuln - dt);
    this.jumpBuf -= dt;
    this.slideBuf -= dt;
    if (!this.dead) this.closeness = Math.max(0, this.closeness - RUN.hollowRecover * dt);

    // the monster gains when you jog slower than target, falls back when faster
    if (this.jogCadence !== null && !this.dead) {
      if (this.jogMult < 1) this.closeness += (1 - this.jogMult) * JOG.gainRate * dt;
      else if (this.jogMult > 1) this.closeness -= (this.jogMult - 1) * JOG.recoverRate * dt;
      this.closeness = Math.min(1, Math.max(0, this.closeness));
    }
    if (this.closeness >= 1 && !this.dead) this.die();

    // lanes
    this.prevX = this.x;
    if (this.laneT < 1) this.laneT = Math.min(1, this.laneT + dt / RUN.laneTime);
    if (this.laneT >= 1 && this.desiredLane !== this.laneTo) {
      this.laneFrom = this.laneTo;
      this.laneTo += Math.sign(this.desiredLane - this.laneTo);
      this.laneT = 0;
    }
    const e = this.laneT * this.laneT * (3 - 2 * this.laneT);
    this.x = (this.laneFrom + (this.laneTo - this.laneFrom) * e) * LANE_W;

    // slide state
    if (this.sliding) {
      this.slideTimer += dt;
      if ((this.slideTimer >= RUN.slideMin && !this.slideHeld) || this.slideTimer >= RUN.slideMax) {
        if (this.slideTimer >= RUN.slideMax && this.slideHeld) this.slideLatched = true;
        this.sliding = false;
      }
    }
    if (!this.slideHeld) this.slideLatched = false;

    // jump / slide / air
    if (this.grounded) {
      if (this.jumpBuf > 0 && !this.dead) this.startJump();
      else if (!this.sliding && ((this.slideHeld && !this.slideLatched) || this.slideBuf > 0) && !this.dead) {
        this.sliding = true;
        this.slideTimer = 0;
        this.slideBuf = 0;
        this.events.emit('slide');
      }
    } else {
      if (this.fastFall && this.y > 0.2) this.vy = Math.min(this.vy, RUN.fastFall);
      this.vy -= this.grav * dt;
      this.y += this.vy * dt;
      if (this.y <= 0) {
        this.y = 0;
        this.vy = 0;
        this.grounded = true;
        this.fastFall = false;
        this.events.emit('land');
      }
    }

    if (!this.dead) {
      this.collide();
      const tier = tierAt(this.distance);
      if (tier > this.tier) {
        this.tier = tier;
        this.events.emit('tierUp', { tier });
      }
    }
  }

  private startJump() {
    const T = 0.68 + 0.14 * clamp01((this.speed - SPEED.start) / (SPEED.max - SPEED.start));
    const h = RUN.jumpHeight;
    this.grav = (8 * h) / (T * T);
    this.vy = (4 * h) / T;
    this.grounded = false;
    this.sliding = false;
    this.slideLatched = this.slideHeld;
    this.fastFall = false;
    this.jumpBuf = 0;
    this.events.emit('jump');
  }

  private collide() {
    const pb = this.y + PLAYER.footGrace;
    const pt = this.y + (this.sliding ? PLAYER.slideH : PLAYER.standH);
    const list = this.world.active;
    for (let i = list.length - 1; i >= 0; i--) {
      const en = list[i];
      const ds = en.s - this.distance;
      if (ds > 8 || ds < -8) continue;
      if (en.kind === 'mote' || en.kind === 'prism') {
        if (Math.abs(ds) < 0.9 && Math.abs(en.lane * LANE_W - this.x) < 1.0 && en.y > pb - 0.45 && en.y < pt + 0.3) {
          this.collect(en);
        }
        continue;
      }
      if (en.hit) continue;
      const b = OBSTACLE_BOX[en.kind];
      if (Math.abs(ds) > b.hz + PLAYER.halfZ) continue;
      if (Math.abs(World.entityX(en) - this.x) > b.hx + PLAYER.halfX) continue;
      if (pt < b.y0 || pb > b.y1) continue;
      this.onHit(en);
      if (this.dead) return;
    }
  }

  private collect(en: Entity) {
    if (this.simTime - this.lastMoteT > 1.2) this.streak = 0;
    this.lastMoteT = this.simTime;
    this.streak++;
    const mult = Math.min(4, 1 + Math.floor(this.streak / 10));
    if (en.kind === 'prism') {
      this.bonus += 100;
      this.events.emit('prism');
    } else {
      this.bonus += 10 * mult;
      this.motes++;
      this.events.emit('mote', { streak: this.streak, mult });
    }
    this.world.remove(en);
  }

  private onHit(en: Entity) {
    if (this.invuln > 0) return;
    en.hit = true;
    this.streak = 0;
    // side-clip: bumped back to the lane we came from, non-lethal
    if (this.laneT < 1 && en.lane === this.laneTo && en.lane !== this.laneFrom && en.kind !== 'crack') {
      const f = this.laneFrom;
      this.laneFrom = this.laneTo;
      this.laneTo = f;
      this.laneT = 1 - this.laneT;
      this.desiredLane = f;
      this.invuln = 1.0;
      this.slowT = 0.8;
      this.closeness = Math.max(this.closeness, 0.55);
      this.shake = 0.35;
      this.events.emit('hit');
      return;
    }
    if (this.closeness >= RUN.hollowLethal) {
      this.die();
      return;
    }
    this.closeness = RUN.hollowHit;
    this.invuln = RUN.invulnerable;
    this.slowT = 1;
    this.shake = 0.6;
    this.events.emit('hit');
  }

  private die() {
    this.dead = true;
    this.state = 'dying';
    this.dyingT = 0;
    this.timeScale = 0.25;
    this.shake = 0.8;
    this.sliding = false;
    this.monster.lunge();
    const score = this.score;
    if (score > this.best) {
      this.best = score;
      this.newBest = true;
      try {
        localStorage.setItem(BEST_KEY, String(score));
      } catch {
        /* storage unavailable */
      }
    }
    this.events.emit('hit');
    this.events.emit('gameOver');
    this.pushHud();
  }

  private get score() {
    return Math.floor(this.distance) + this.bonus;
  }

  // ---------- rendering ----------
  private render(dt: number) {
    const menu = this.state === 'menu';
    const speed = this.speed;
    this.world.update(this.distance, this.realTime);
    this.env.update(this.distance, dt, this.state === 'countdown' || this.state === 'paused' || this.state === 'gameover' ? 0 : speed, this.camera);
    this.particles.update(dt, this.state === 'paused' ? 0 : speed);

    const lateralVel = (this.x - this.prevX) / SIM_DT;
    const idle = this.state === 'countdown';
    this.runner.animate(dt, this.x, this.y, {
      speed: Math.max(speed, 4),
      grounded: this.grounded,
      sliding: this.sliding,
      stumbling: this.invuln > 0 && !this.dead,
      dead: this.dead,
      lateralVel: this.reducedMotion ? 0 : lateralVel,
      time: this.realTime,
      idle,
    });
    // blink while invulnerable
    this.runner.setVisible(!(this.invuln > 0 && !this.dead && Math.floor(this.realTime * 14) % 2 === 0));

    // the Hollow monster hunts from behind
    this.monster.object.visible = this.closeness > 0.05 && !menu;
    if (this.monster.object.visible) {
      this.monster.update(dt, this.x, this.closeness, this.realTime);
    }

    // camera rig
    const sp01 = clamp01((speed - SPEED.start) / (SPEED.max - SPEED.start));
    const pull = this.state === 'dying' || this.state === 'gameover' ? Math.min(1, this.dyingT / 1.2) : 0;
    let tx: number, ty: number, tz: number, lx: number, ly: number, lz: number;
    if (menu) {
      tx = 2.4 + Math.sin(this.realTime * 0.25) * 0.8;
      ty = 2.0;
      tz = 4.2;
      lx = -0.9;
      ly = 1.1;
      lz = -3;
    } else {
      tx = this.x * 0.6;
      ty = 3.2 + pull * 2.2;
      tz = 5.5 + pull * 3.5;
      lx = this.x * 0.4;
      ly = 1.0;
      lz = -8;
    }
    const k = damp(menu || this.state === 'countdown' ? 3 : 10, dt);
    this.camPos.x += (tx - this.camPos.x) * k;
    this.camPos.y += (ty - this.camPos.y) * k;
    this.camPos.z += (tz - this.camPos.z) * k;
    this.camLook.x += (lx - this.camLook.x) * k;
    this.camLook.y += (ly - this.camLook.y) * k;
    this.camLook.z += (lz - this.camLook.z) * k;

    this.shake = Math.max(0, this.shake - dt * 1.6);
    const sh = this.reducedMotion ? 0 : this.shake;
    this.camera.position.set(
      this.camPos.x + (Math.random() - 0.5) * sh * 0.5,
      this.camPos.y + (Math.random() - 0.5) * sh * 0.5 + (this.reducedMotion || menu ? 0 : Math.sin(this.realTime * 11) * 0.02 * sp01),
      this.camPos.z,
    );
    this.camera.lookAt(this.camLook);
    if (!this.reducedMotion && !menu) this.camera.rotateZ(-lateralVel * 0.004);
    const fov = this.reducedMotion ? 62 : 62 + 10 * sp01;
    if (Math.abs(this.camera.fov - fov) > 0.05) {
      this.camera.fov += (fov - this.camera.fov) * damp(4, dt);
      this.camera.updateProjectionMatrix();
    }

    this.audio.setIntensity(sp01);
    this.renderer.render(this.scene, this.camera);
  }

  private monitorPerf(dt: number) {
    this.frameAvg = this.frameAvg * 0.95 + dt * 1000 * 0.05;
    this.fpsAvg = this.fpsAvg * 0.95 + (1 / dt) * 0.05;
    if (this.state !== 'playing') {
      this.slowFrames = 0;
      return;
    }
    if (this.frameAvg > 20) this.slowFrames += dt;
    else this.slowFrames = 0;
    if (this.slowFrames > 3 && this.quality !== 'low') {
      this.slowFrames = 0;
      const next: Quality = this.quality === 'high' ? 'medium' : 'low';
      this.applyQuality(next);
      this.onQualityDrop(next);
    }
  }

  private pushHud() {
    const streak = this.simTime - this.lastMoteT > 1.2 ? 0 : this.streak;
    this.onHud({
      state: this.state,
      pauseReason: this.pauseReason,
      countdown: Math.max(1, Math.ceil(this.countdownT)),
      score: this.score,
      distance: Math.floor(this.distance),
      motes: this.motes,
      streak,
      mult: Math.min(4, 1 + Math.floor(streak / 10)),
      tier: tierAt(this.distance),
      speed: this.speed,
      pips: this.closeness >= RUN.hollowLethal ? 1 : 2,
      closeness: this.closeness,
      jogCadence: this.jogCadence,
      jogMult: this.jogMult,
      best: this.best,
      newBest: this.newBest,
      biome: this.env.biomeName,
      fps: Math.round(this.fpsAvg),
      trackingLost: this.trackingState === 'lost',
    });
  }
}
