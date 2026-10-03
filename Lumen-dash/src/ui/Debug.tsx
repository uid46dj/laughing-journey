import { debugStore, gestureStore, settingsStore, useStore } from '../app/store';
import { GESTURE_CONFIG as C } from '../cam/gestureConfig';

function Bar({ label, value, min, max, marks }: { label: string; value: number; min: number; max: number; marks: number[] }) {
  const pos = (v: number) => `${((Math.min(max, Math.max(min, v)) - min) / (max - min)) * 100}%`;
  return (
    <div className="mt-1">
      <div className="flex justify-between">
        <span>{label}</span>
        <span className="tabular-nums">{value.toFixed(2)}</span>
      </div>
      <div className="relative h-3 rounded bg-white/10">
        {marks.map((m) => (
          <div key={m} className="absolute top-0 h-3 w-px bg-amber-300/80" style={{ left: pos(m) }} />
        ))}
        <div className="absolute top-0 h-3 w-1.5 -translate-x-1/2 rounded bg-cyan-300" style={{ left: pos(value) }} />
      </div>
    </div>
  );
}

export function Debug() {
  const d = useStore(debugStore);
  const g = useStore(gestureStore);
  const s = useStore(settingsStore);
  const k = s.sensitivity;
  return (
    <div className="pointer-events-none absolute bottom-3 left-3 z-20 w-64 rounded-xl bg-black/70 p-3 font-mono text-[11px] leading-4 text-emerald-100">
      <div className="font-bold text-amber-200">DEBUG</div>
      <div>
        pose {d.poseFps} fps · {d.inferenceMs} ms · {d.delegate}/{d.source}
      </div>
      <div>latency (median, frame→game): {d.latency} ms</div>
      <div>
        tracking: {g.tracking} · calibrated: {String(g.calibrated)} · {g.posture}
      </div>
      <Bar label="lateral (SW)" value={d.lateral} min={-1.2} max={1.2} marks={[-C.lateralEnter / k, -C.lateralExit / k, C.lateralExit / k, C.lateralEnter / k]} />
      <Bar label="vertical (SW)" value={d.vertical} min={-0.8} max={0.8} marks={[C.crouchEnter / k, C.crouchExit / k, C.jumpDisplacement / k]} />
      <div className="mt-2 text-violet-200/80">events</div>
      {d.log.map((l, i) => (
        <div key={i + l}>{l}</div>
      ))}
    </div>
  );
}
