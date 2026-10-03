/** Fully procedural audio (Web Audio). No files. Starts only after a user gesture via unlock(). */
export class GameAudio {
  private ctx: AudioContext | null = null;
  private master!: GainNode;
  private sfxGain!: GainNode;
  private musicGain!: GainNode;
  private noiseBuf: AudioBuffer | null = null;
  private musicTimer: number | null = null;
  private step = 0;
  private intensity = 0;
  private volume = 0.7;
  private sfxOn = true;
  private musicOn = true;
  private pad: { o: OscillatorNode[]; g: GainNode } | null = null;

  unlock() {
    if (!this.ctx) {
      const AC = window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      if (!AC) return;
      this.ctx = new AC();
      this.master = this.ctx.createGain();
      this.sfxGain = this.ctx.createGain();
      this.musicGain = this.ctx.createGain();
      this.sfxGain.connect(this.master);
      this.musicGain.connect(this.master);
      this.master.connect(this.ctx.destination);
      const len = this.ctx.sampleRate;
      this.noiseBuf = this.ctx.createBuffer(1, len, this.ctx.sampleRate);
      const d = this.noiseBuf.getChannelData(0);
      for (let i = 0; i < len; i++) d[i] = Math.random() * 2 - 1;
      this.applyLevels();
    }
    if (this.ctx.state === 'suspended') void this.ctx.resume();
  }

  configure(volume: number, music: boolean, sfx: boolean) {
    this.volume = volume;
    this.musicOn = music;
    this.sfxOn = sfx;
    this.applyLevels();
  }

  private applyLevels() {
    if (!this.ctx) return;
    this.master.gain.value = this.volume;
    this.sfxGain.gain.value = this.sfxOn ? 0.9 : 0;
    this.musicGain.gain.value = this.musicOn ? 0.5 : 0;
  }

  private tone(freq: number, dur: number, type: OscillatorType, vol: number, to?: number, delay = 0, dest?: AudioNode) {
    const c = this.ctx;
    if (!c) return;
    const t = c.currentTime + delay;
    const o = c.createOscillator();
    const g = c.createGain();
    o.type = type;
    o.frequency.setValueAtTime(freq, t);
    if (to) o.frequency.exponentialRampToValueAtTime(to, t + dur);
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(vol, t + 0.01);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    o.connect(g).connect(dest ?? this.sfxGain);
    o.start(t);
    o.stop(t + dur + 0.05);
  }

  private noise(dur: number, vol: number, freq: number, type: BiquadFilterType = 'bandpass', dest?: AudioNode, sweepTo?: number) {
    const c = this.ctx;
    if (!c || !this.noiseBuf) return;
    const t = c.currentTime;
    const s = c.createBufferSource();
    s.buffer = this.noiseBuf;
    const f = c.createBiquadFilter();
    f.type = type;
    f.frequency.setValueAtTime(freq, t);
    if (sweepTo) f.frequency.exponentialRampToValueAtTime(sweepTo, t + dur);
    const g = c.createGain();
    g.gain.setValueAtTime(vol, t);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    s.connect(f).connect(g).connect(dest ?? this.sfxGain);
    s.start(t);
    s.stop(t + dur + 0.05);
  }

  jump() {
    this.noise(0.25, 0.25, 500, 'bandpass', undefined, 1800);
    this.tone(300, 0.2, 'sine', 0.12, 620);
  }
  slide() {
    this.noise(0.4, 0.22, 3000, 'highpass');
  }
  land() {
    this.tone(90, 0.12, 'sine', 0.25, 45);
  }
  mote(streak: number) {
    const f = 660 * Math.pow(2, Math.min(streak, 12) / 12);
    this.tone(f, 0.18, 'triangle', 0.16);
    this.tone(f * 1.5, 0.22, 'sine', 0.07, undefined, 0.04);
  }
  prism() {
    [880, 1109, 1319].forEach((f, i) => this.tone(f, 0.4, 'triangle', 0.14, undefined, i * 0.07));
  }
  hit() {
    this.tone(120, 0.3, 'sawtooth', 0.28, 40);
    this.noise(0.3, 0.4, 600, 'lowpass');
  }
  gameOver() {
    [392, 330, 262, 196].forEach((f, i) => this.tone(f, 0.5, 'triangle', 0.2, f * 0.97, i * 0.18));
  }
  blip() {
    this.tone(720, 0.07, 'square', 0.06);
  }
  tick() {
    this.tone(1000, 0.06, 'square', 0.07);
  }
  go() {
    this.tone(660, 0.3, 'triangle', 0.18, 1320);
  }
  tierUp() {
    [523, 659, 784].forEach((f, i) => this.tone(f, 0.25, 'triangle', 0.14, undefined, i * 0.08));
  }

  setIntensity(x: number) {
    this.intensity = Math.min(1, Math.max(0, x));
    if (this.pad && this.ctx) this.pad.g.gain.setTargetAtTime(0.05 + 0.04 * this.intensity, this.ctx.currentTime, 0.5);
  }

  startMusic() {
    const c = this.ctx;
    if (!c || this.musicTimer !== null) return;
    const g = c.createGain();
    g.gain.value = 0.06;
    const lp = c.createBiquadFilter();
    lp.type = 'lowpass';
    lp.frequency.value = 520;
    g.connect(lp).connect(this.musicGain);
    const o = [c.createOscillator(), c.createOscillator(), c.createOscillator()];
    o.forEach((osc, i) => {
      osc.type = 'sawtooth';
      osc.frequency.value = 110;
      osc.detune.value = (i - 1) * 9;
      osc.connect(g);
      osc.start();
    });
    this.pad = { o, g };
    this.step = 0;
    const roots = [110, 87.31, 130.81, 98];
    const scale = [0, 3, 7, 10, 12, 15];
    const tick = () => {
      if (!this.ctx || !this.pad) return;
      const bpm = 92 + this.intensity * 44;
      const bar = Math.floor(this.step / 16) % 4;
      const root = roots[bar];
      if (this.step % 16 === 0) this.pad.o.forEach((osc) => osc.frequency.setTargetAtTime(root, this.ctx!.currentTime, 0.4));
      if (this.step % 4 === 0) this.tone(130, 0.14, 'sine', 0.35, 42, 0, this.musicGain);
      if (this.step % 4 === 2) this.noise(0.05, 0.1, 7000, 'highpass', this.musicGain);
      if (this.step % 2 === 0) {
        const n = scale[(this.step * 3 + bar) % scale.length];
        this.tone(root * 4 * Math.pow(2, n / 12), 0.2, 'triangle', 0.05 + 0.03 * this.intensity, undefined, 0, this.musicGain);
      }
      this.step++;
      this.musicTimer = window.setTimeout(tick, (60 / bpm / 4) * 1000);
    };
    this.musicTimer = window.setTimeout(tick, 100);
  }

  stopMusic() {
    if (this.musicTimer !== null) clearTimeout(this.musicTimer);
    this.musicTimer = null;
    if (this.pad) {
      this.pad.o.forEach((o) => {
        try {
          o.stop();
        } catch {
          /* already stopped */
        }
      });
      this.pad = null;
    }
  }
}
