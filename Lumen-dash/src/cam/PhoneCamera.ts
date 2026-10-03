/**
 * PhoneCamera — use a phone's camera as the PC's webcam, with no app and no driver.
 *
 * How it fits into the game:
 *   `CameraSource.start()` is the only place the game touches a real camera, and it calls
 *   `navigator.mediaDevices.getUserMedia()`. We patch that one function to return a
 *   MediaStream backed by a <canvas> that we repaint with the newest frame arriving from
 *   the phone. Everything downstream — PoseEstimator, LandmarkFilter, GestureEngine — is
 *   untouched, so the phone behaves exactly like a built-in webcam.
 *
 * Latency notes:
 *   - The relay server keeps only the NEWEST frame, so a slow consumer can never build a
 *     backlog. The PC always draws the most recent image rather than a stale queue.
 *   - `canvas.captureStream(0)` + manual `track.requestFrame()` gives frame-accurate
 *     control: no implicit buffering, and we only emit when a frame really arrived.
 *   - Over `adb reverse` (USB) the transport is the dominant cost and is well under a frame.
 */

export interface PhoneCamOptions {
  /** Base URL of the relay server on the PC. */
  baseUrl?: string;
  /** Frame size of the synthesized camera stream. */
  width?: number;
  height?: number;
}

export interface PhoneCamStats {
  active: boolean;
  frames: number;
  fps: number;
  latencyMs: number;
  sourceWidth: number;
  sourceHeight: number;
}

const DEFAULTS: Required<PhoneCamOptions> = { baseUrl: 'http://127.0.0.1:8080', width: 640, height: 480 };

/** Shape of the internal MediaStreamTrack method used to push frames. */
interface RequestFrameTrack extends MediaStreamTrack {
  requestFrame?: () => void;
}

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

export class PhoneCamera {
  private baseUrl: string;
  private width: number;
  private height: number;

  private canvas: HTMLCanvasElement | null = null;
  private ctx: CanvasRenderingContext2D | null = null;
  private stream: MediaStream | null = null;
  private track: RequestFrameTrack | null = null;
  private running = false;
  private since = 0;
  private originalGum: typeof navigator.mediaDevices.getUserMedia | null = null;

  private frames = 0;
  private lastFpsAt = 0;
  private fps = 0;
  private latencyMs = 0;

  constructor(opts: PhoneCamOptions = {}) {
    const o = { ...DEFAULTS, ...opts };
    this.baseUrl = o.baseUrl.replace(/\/$/, '');
    this.width = o.width;
    this.height = o.height;
  }

  get active() {
    return this.running;
  }

  get stats(): PhoneCamStats {
    return {
      active: this.running,
      frames: this.frames,
      fps: this.fps,
      latencyMs: this.latencyMs,
      sourceWidth: this.canvas?.width ?? 0,
      sourceHeight: this.canvas?.height ?? 0,
    };
  }

  /** True when the relay server is up and a phone has sent at least one frame. */
  async probe(timeoutMs = 1200): Promise<{ ok: boolean; streaming: boolean; message: string }> {
    try {
      const ctl = new AbortController();
      const timer = setTimeout(() => ctl.abort(), timeoutMs);
      const res = await fetch(`${this.baseUrl}/health`, { signal: ctl.signal, cache: 'no-store' });
      clearTimeout(timer);
      if (!res.ok) return { ok: false, streaming: false, message: `Relay server replied ${res.status}.` };
      const j = (await res.json()) as { streaming?: boolean; avgFps?: number };
      return {
        ok: true,
        streaming: !!j.streaming,
        message: j.streaming
          ? `Phone is streaming at ~${j.avgFps ?? 0} fps.`
          : 'Relay server is up, but no phone frames yet — open the phone page and press Start.',
      };
    } catch {
      return {
        ok: false,
        streaming: false,
        message: `Cannot reach the relay server at ${this.baseUrl}. Start it with "npm run phonecam".`,
      };
    }
  }

  /**
   * Patches `navigator.mediaDevices.getUserMedia` so the game's CameraSource receives the
   * phone feed instead of the PC's built-in webcam, then starts pulling frames.
   */
  async start(): Promise<boolean> {
    if (this.running) return true;

    this.canvas = document.createElement('canvas');
    this.canvas.width = this.width;
    this.canvas.height = this.height;
    this.ctx = this.canvas.getContext('2d', { alpha: false, desynchronized: true });

    // 0 = only emit on explicit requestFrame(); the PoseEstimator then sees exactly the
    // frames that arrived, with no extra buffering.
    this.stream = this.canvas.captureStream(0);
    this.track = (this.stream.getVideoTracks()[0] as RequestFrameTrack | undefined) ?? null;

    this.originalGum = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
    const stream = this.stream;
    navigator.mediaDevices.getUserMedia = (async (constraints?: MediaStreamConstraints) => {
      if (!constraints?.video) return this.originalGum!(constraints);
      // Answer with a clone so the game owns (and can stop) its own track.
      const track = stream.getVideoTracks()[0];
      return new MediaStream(track ? [track.clone()] : []);
    }) as typeof navigator.mediaDevices.getUserMedia;

    this.running = true;
    this.frames = 0;
    this.since = 0;
    this.lastFpsAt = performance.now();
    void this.pump();
    return true;
  }

  /** Long-polls the relay for the newest frame and paints it. */
  private async pump(): Promise<void> {
    while (this.running) {
      try {
        const res = await fetch(`${this.baseUrl}/latest?since=${this.since}`, { cache: 'no-store' });
        if (res.status === 204) continue;
        if (!res.ok) {
          await sleep(300);
          continue;
        }
        const blob = await res.blob();
        const seq = Number(res.headers.get('X-Seq') || 0);
        const lag = Number(res.headers.get('X-Lag-Ms') || -1);
        if (seq > this.since) this.since = seq;
        if (lag >= 0) this.latencyMs = Math.round(lag);

        const bmp = await createImageBitmap(blob);
        await this.paint(bmp);
      } catch {
        if (this.running) await sleep(200);
      }
    }
  }

  private async paint(bmp: ImageBitmap): Promise<void> {
    const { ctx, canvas } = this;
    if (!ctx || !canvas) return;

    // Match the stream resolution to the phone's, but keep it even-sized.
    const w = Math.max(2, Math.round(bmp.width / 2) * 2);
    const h = Math.max(2, Math.round(bmp.height / 2) * 2);
    if (canvas.width !== w || canvas.height !== h) {
      canvas.width = w;
      canvas.height = h;
    }
    ctx.drawImage(bmp, 0, 0, w, h);
    bmp.close?.();

    // Push the frame to consumers (the game's hidden <video>).
    this.track?.requestFrame?.();

    this.frames++;
    const now = performance.now();
    if (now - this.lastFpsAt >= 1000) {
      this.fps = Math.round((this.frames * 1000) / (now - this.lastFpsAt));
      this.frames = 0;
      this.lastFpsAt = now;
    }
  }

  /** Restores the real `getUserMedia` and releases everything. */
  stop(): void {
    if (!this.running) return;
    this.running = false;
    if (this.originalGum) navigator.mediaDevices.getUserMedia = this.originalGum;
    this.originalGum = null;
    this.stream?.getTracks().forEach((t) => t.stop());
    this.stream = null;
    this.track = null;
    this.canvas = null;
    this.ctx = null;
  }
}