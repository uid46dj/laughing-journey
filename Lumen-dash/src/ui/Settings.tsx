import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { controller } from '../app/Controller';
import { settingsStore, uiStore, useStore } from '../app/store';
import type { Quality } from '../game/config';
import { Btn } from './common';

function Row({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-white/10 py-3">
      <div>
        <div className="font-semibold">{label}</div>
        {hint && <div className="text-xs text-violet-300/70">{hint}</div>}
      </div>
      {children}
    </div>
  );
}

function Toggle({ on, onChange }: { on: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      role="switch"
      aria-checked={on}
      onClick={() => onChange(!on)}
      className={`relative h-7 w-12 shrink-0 rounded-full transition ${on ? 'bg-gradient-to-r from-amber-300 to-fuchsia-400' : 'bg-white/15'}`}
    >
      <span className={`absolute top-1 h-5 w-5 rounded-full bg-white transition-all ${on ? 'left-6' : 'left-1'}`} />
    </button>
  );
}

/** Phone-as-webcam: relay server status + switch. Needs tools/phonecam-server.mjs running. */
function PhoneCamRow() {
  const [status, setStatus] = useState<string>('checking...');
  const [ok, setOk] = useState(false);
  const on = controller.phoneCam.active;

  const poll = async () => {
    const r = await controller.phoneCam.probe(800);
    setOk(r.ok);
    setStatus(r.message);
  };
  useEffect(() => {
    void poll();
    const id = window.setInterval(poll, 2500);
    return () => window.clearInterval(id);
  }, []);

  return (
    <>
      <Row label="Use phone as camera" hint={status}>
        <Toggle
          on={on}
          onChange={async (v) => {
            if (v) await controller.usePhoneCamera();
            else controller.usePcCamera();
            setTimeout(poll, 400);
          }}
        />
      </Row>
      {on && (
        <div className="pt-3 text-xs font-semibold text-emerald-200">
          Streaming from the phone &mdash; {controller.phoneCam.stats.fps} fps &middot;{' '}
          {controller.phoneCam.stats.latencyMs} ms lag
        </div>
      )}
      {!ok && (
        <div className="pt-3 text-xs text-amber-200/90">
          Relay server not detected. Run <code>npm run phonecam</code>, then open the printed URL on the phone.
        </div>
      )}
    </>
  );
}

export function Settings() {
  const s = useStore(settingsStore);
  const ui = useStore(uiStore);
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const set = settingsStore.set;

  useEffect(() => {
    void controller.camera.listDevices().then(setDevices).catch(() => setDevices([]));
  }, []);

  return (
    <div className="pointer-events-auto absolute inset-0 z-30 flex items-center justify-center overflow-y-auto bg-[#1b1510]/80 p-4">
      <div className="glass my-auto w-full max-w-lg rounded-3xl p-6">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="glow-text text-3xl font-black italic">Settings</h2>
          <Btn variant="ghost" onClick={() => uiStore.set({ settingsOpen: false })}>
            Close
          </Btn>
        </div>

        <Row label="Gesture sensitivity" hint="Higher = smaller movements trigger actions">
          <div className="flex items-center gap-2">
            <input type="range" min={0.7} max={1.4} step={0.05} value={s.sensitivity} onChange={(e) => set({ sensitivity: Number(e.target.value) })} />
            <span className="w-10 text-right tabular-nums">{s.sensitivity.toFixed(2)}</span>
          </div>
        </Row>
        <PhoneCamRow />
        <Row label="Camera">
          <select
            className="max-w-[12rem] rounded-lg border border-white/20 bg-[#1a1240] px-2 py-1 text-sm"
            value={s.deviceId}
            onChange={(e) => set({ deviceId: e.target.value })}
          >
            <option value="">Default</option>
            {devices.map((d, i) => (
              <option key={d.deviceId || i} value={d.deviceId}>
                {d.label || `Camera ${i + 1}`}
              </option>
            ))}
          </select>
        </Row>
        <Row label="Mirror preview">
          <Toggle on={s.mirror} onChange={(v) => set({ mirror: v })} />
        </Row>

        <Row label="Flip camera upside down">
          <Toggle on={s.flipVertical} onChange={(v) => set({ flipVertical: v })} />
        </Row>
        <Row label="Show camera picture-in-picture">
          <Toggle on={s.showPip} onChange={(v) => set({ showPip: v })} />
        </Row>
        <Row label="Debug overlay (F3)">
          <Toggle on={s.showDebug} onChange={(v) => set({ showDebug: v })} />
        </Row>
        <Row label="Master volume">
          <input type="range" min={0} max={1} step={0.05} value={s.volume} onChange={(e) => set({ volume: Number(e.target.value) })} />
        </Row>
        <Row label="Music">
          <Toggle on={s.music} onChange={(v) => set({ music: v })} />
        </Row>
        <Row label="Sound effects">
          <Toggle on={s.sfx} onChange={(v) => set({ sfx: v })} />
        </Row>
        <Row label="Reduced motion" hint="No camera shake, roll or FOV zoom">
          <Toggle on={s.reducedMotion} onChange={(v) => set({ reducedMotion: v })} />
        </Row>
        <Row label="Graphics quality">
          <select
            className="rounded-lg border border-white/20 bg-[#1a1240] px-2 py-1 text-sm"
            value={s.quality}
            onChange={(e) => set({ quality: e.target.value as Quality })}
          >
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
          </select>
        </Row>
        <div className="flex flex-wrap gap-3 pt-4">
          {ui.mode === 'camera' && (
            <Btn
              variant="cyan"
              onClick={() => {
                uiStore.set({ settingsOpen: false });
                controller.recalibrate();
              }}
            >
              Recalibrate
            </Btn>
          )}
          <Btn variant="ghost" onClick={() => set({ tutorialDone: false })}>
            Replay tutorial next time
          </Btn>
        </div>
      </div>
    </div>
  );
}
