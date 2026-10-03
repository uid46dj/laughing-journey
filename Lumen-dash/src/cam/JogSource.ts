import type { InputSource, RunnerInput } from '../game/InputSource';
import { NEUTRAL_INPUT } from '../game/InputSource';

/**
 * JogSource — reads leg-cadence from the second phone via the relay server.
 *
 * The phone page (tools/legcam-phone.html, served at /legs) analyses its own
 * camera feed and POSTs a tiny JSON payload ({c, v}) to the relay's
 * /cadence endpoint. This class long-polls that endpoint — no video is
 * streamed to the PC, so there is no conflict with PhoneCamera's
 * getUserMedia patch and the payload is a few bytes over USB.
 *
 * Mirrors JOG.signalTimeoutMs in game/config (kept local: src/cam must not
 * import from src/game except game/InputSource).
 */
const SIGNAL_TIMEOUT_MS = 1500;
const EMA_ALPHA = 0.35;

export interface JogSourceOptions {
  /** Base URL of the relay server on the PC. */
  baseUrl?: string;
}

export interface JogProbe {
  ok: boolean;
  streaming: boolean;
  message: string;
}

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

interface CadenceUpdate {
  c?: number;
  v?: boolean;
  seq?: number;
}

export class JogSource implements InputSource {
  private baseUrl: string;
  private running = false;
  private since = 0;

  /** Smoothed cadence in steps/sec. */
  private cadence = 0;
  /** Whether the phone currently sees legs (vs. blocked/pointed away). */
  private visible = false;
  private lastUpdate = 0;

  constructor(opts: JogSourceOptions = {}) {
    this.baseUrl = (opts.baseUrl ?? 'http://127.0.0.1:8080').replace(/\/$/, '');
  }

  get active() {
    return this.running;
  }

  /** True when the relay is up and a leg phone has sent cadence. */
  async probe(timeoutMs = 1200): Promise<JogProbe> {
    try {
      const ctl = new AbortController();
      const timer = setTimeout(() => ctl.abort(), timeoutMs);
      const res = await fetch(`${this.baseUrl}/health`, { signal: ctl.signal, cache: 'no-store' });
      clearTimeout(timer);
      if (!res.ok) return { ok: false, streaming: false, message: `Relay server replied ${res.status}.` };
      const j = (await res.json()) as { cadence?: { streaming?: boolean; cadence?: number } };
      const streaming = !!j.cadence?.streaming;
      return {
        ok: true,
        streaming,
        message: streaming
          ? `Leg phone connected — jogging at ~${Math.round(j.cadence!.cadence ?? 0)} steps/s.`
          : 'Relay is up, but no leg phone yet — open the /legs page on the second phone.',
      };
    } catch {
      return {
        ok: false,
        streaming: false,
        message: `Cannot reach the relay server at ${this.baseUrl}. Start it with "npm run phonecam".`,
      };
    }
  }

  start() {
    if (this.running) return;
    this.running = true;
    this.since = 0;
    this.lastUpdate = 0;
    void this.pump();
  }

  stop() {
    this.running = false;
    this.visible = false;
    this.lastUpdate = 0;
  }

  /** Long-polls the relay for the newest cadence reading. */
  private async pump(): Promise<void> {
    while (this.running) {
      try {
        const res = await fetch(`${this.baseUrl}/cadence?since=${this.since}`, { cache: 'no-store' });
        if (!res.ok) {
          await sleep(300);
          continue;
        }
        const j = (await res.json()) as CadenceUpdate;
        if (j.seq && j.seq > this.since) this.since = j.seq;
        const raw = typeof j.c === 'number' ? j.c : 0;
        this.cadence = this.lastUpdate === 0 ? raw : this.cadence + (raw - this.cadence) * EMA_ALPHA;
        this.visible = !!j.v;
        this.lastUpdate = performance.now();
      } catch {
        if (this.running) await sleep(200);
      }
    }
  }

  poll(now: number): RunnerInput {
    const fresh = this.visible && now - this.lastUpdate < SIGNAL_TIMEOUT_MS;
    return {
      ...NEUTRAL_INPUT,
      jogCadence: fresh ? this.cadence : null,
    };
  }
}
