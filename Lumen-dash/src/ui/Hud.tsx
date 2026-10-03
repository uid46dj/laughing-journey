import { controller } from '../app/Controller';
import { gestureStore, hudStore, settingsStore, uiStore, useStore } from '../app/store';
import { Btn, PreviewCanvas } from './common';

/** The Hollow's proximity — how close the monster is to catching you. */
function MonsterBar({ closeness }: { closeness: number }) {
  const near = closeness > 0.7;
  return (
    <div className="flex items-center gap-2" aria-label={`monster ${Math.round(closeness * 100)} percent close`}>
      <span className={`text-lg ${near ? 'animate-pulse' : ''}`} title="The Hollow — keep jogging to keep it back">
        👹
      </span>
      <div className="h-2.5 w-24 overflow-hidden rounded-full bg-white/10">
        <div
          className={`h-full rounded-full transition-[width] duration-200 ${
            near ? 'bg-rose-500 shadow-[0_0_10px_#f43f5e]' : 'bg-gradient-to-r from-amber-400 to-rose-500'
          }`}
          style={{ width: `${Math.round(closeness * 100)}%` }}
        />
      </div>
    </div>
  );
}

/** Live leg-cadence from the second phone. Target 2.5 steps/s, fast ≥ 3. */
function CadenceMeter({ cadence }: { cadence: number }) {
  const pct = Math.min(100, (cadence / 5) * 100);
  const fast = cadence >= 3;
  const ok = cadence >= 2;
  return (
    <div className="flex items-center gap-2 rounded-xl bg-black/40 p-2" title="Jog cadence — faster jog = faster run">
      <span className="text-lg">🏃</span>
      <div className="relative h-2.5 w-24 overflow-hidden rounded-full bg-white/10">
        <div className="absolute inset-y-0 left-1/2 w-0.5 bg-amber-300/80" />
        <div className="absolute inset-y-0 right-0 w-[40%] bg-emerald-400/15" />
        <div
          className={`h-full rounded-full transition-[width] duration-150 ${
            fast ? 'bg-emerald-400 shadow-[0_0_8px_#34d399]' : ok ? 'bg-amber-300' : 'bg-rose-400'
          }`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="w-12 text-right font-bold tabular-nums text-sm">{cadence.toFixed(1)}/s</span>
    </div>
  );
}

function GestureIndicator() {
  const g = useStore(gestureStore);
  return (
    <div className="flex items-center gap-2 rounded-xl bg-black/40 p-2">
      <div className="flex w-24 gap-1">
        {([-1, 0, 1] as const).map((z) => (
          <div key={z} className={`h-3 flex-1 rounded-full transition ${g.zone === z ? 'bg-amber-300 shadow-[0_0_10px_#fcd34d]' : 'bg-white/15'}`} />
        ))}
      </div>
      <div key={`j${g.jumpAt}`} className={`text-xl ${g.jumpAt ? 'flash' : ''}`} title="Jump">
        ⬆
      </div>
      <div key={`c${g.crouchAt}`} className={`text-xl ${g.crouchAt ? 'flash' : ''} ${g.posture === 'crouching' ? 'text-cyan-300' : 'opacity-50'}`} title="Crouch">
        ⬇
      </div>
    </div>
  );
}

function HandsRing() {
  const g = useStore(gestureStore);
  if (g.handsUp <= 0.02) return null;
  const r = 38;
  const c = 2 * Math.PI * r;
  return (
    <div className="pointer-events-none absolute bottom-24 left-1/2 -translate-x-1/2 text-center">
      <svg width="100" height="100" viewBox="0 0 100 100">
        <circle cx="50" cy="50" r={r} stroke="rgba(255,255,255,0.15)" strokeWidth="8" fill="none" />
        <circle
          cx="50"
          cy="50"
          r={r}
          stroke="#fcd34d"
          strokeWidth="8"
          fill="none"
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={c * (1 - g.handsUp)}
          transform="rotate(-90 50 50)"
        />
        <text x="50" y="58" textAnchor="middle" fontSize="28">
          🙌
        </text>
      </svg>
    </div>
  );
}

export function Hud() {
  const h = useStore(hudStore);
  const ui = useStore(uiStore);
  const st = useStore(settingsStore);
  const g = useStore(gestureStore);
  const set = settingsStore.set;
  const cam = ui.mode === 'camera';
  const playing = h.state === 'playing' || h.state === 'dying' || h.state === 'countdown';
  const fadeOver = h.state === 'gameover';

  return (
    <div className="pointer-events-none absolute inset-0">
      {/* Hollow vignette */}
      <div
        className="absolute inset-0 transition-opacity duration-300"
        style={{
          opacity: Math.min(1, h.closeness * 1.15),
          background: 'radial-gradient(ellipse at center, transparent 40%, rgba(120,10,110,0.55) 80%, rgba(10,0,20,0.9) 100%)',
        }}
      />

      {(playing || h.state === 'paused' || fadeOver) && (
        <>
          <div className="absolute left-0 right-0 top-0 flex items-start justify-between p-4 sm:p-6">
            <div className="space-y-2 rounded-2xl bg-black/35 px-4 py-3 backdrop-blur-sm">
              <div className="text-xs font-bold uppercase tracking-widest text-violet-200/70">Distance</div>
              <div className="text-2xl font-black tabular-nums">{h.distance} m</div>
              <div className="flex items-center gap-3">
                <span className="text-amber-300">◆</span>
                <span className="text-lg font-bold tabular-nums">{h.motes}</span>
                {h.streak >= 3 && (
                  <span className="rounded-md bg-amber-300 px-1.5 py-0.5 text-xs font-black text-slate-900">
                    ×{h.mult} · {h.streak}
                  </span>
                )}
              </div>
              <MonsterBar closeness={h.closeness} />
              <div className="text-xs font-semibold text-cyan-200/80">
                {h.biome} · Tier {h.tier} · {Math.round(h.speed * 3.6)} km/h
                {h.jogCadence != null && Math.abs(h.jogMult - 1) > 0.02 && (
                  <span className={h.jogMult > 1 ? 'text-emerald-300' : 'text-rose-300'}>
                    {' '}
                    ×{h.jogMult.toFixed(2)}
                  </span>
                )}
              </div>
            </div>

            <div className="text-center">
              <div className="text-xs font-bold uppercase tracking-[0.3em] text-violet-200/70">Score</div>
              <div className="text-5xl font-black tabular-nums drop-shadow-[0_0_14px_rgba(251,191,36,0.6)] sm:text-6xl">{h.score.toLocaleString()}</div>
            </div>

            <div className="flex flex-col items-end gap-2">
              {cam && st.showPip && (
                <div
                  className={`overflow-hidden rounded-xl border-4 ${g.tracking === 'ok' ? 'border-emerald-400' : g.tracking === 'degraded' ? 'border-amber-400' : 'border-rose-500'}`}
                >
                  <PreviewCanvas className="h-[150px] w-[200px]" />
                </div>
              )}
              {cam && <GestureIndicator />}
              {cam && h.jogCadence != null && <CadenceMeter cadence={h.jogCadence} />}
              {cam && (
                <button
                  className="pointer-events-auto rounded-lg bg-black/40 px-3 py-1.5 text-sm font-semibold text-violet-100 hover:bg-black/60"
                  title="Flip the camera preview upside down (V)"
                  onClick={() => set({ flipVertical: !st.flipVertical })}
                >
                  {st.flipVertical ? 'Flip ON' : 'Flip'}
                </button>
              )}

              <button
                className="pointer-events-auto rounded-lg bg-black/40 px-3 py-1.5 text-sm font-semibold text-violet-100 hover:bg-black/60"
                onClick={() => controller.game.pause('manual')}
              >
                ⏸ Pause
              </button>
            </div>
          </div>
          {cam && <HandsRing />}
        </>
      )}

      {h.state === 'countdown' && (
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <div key={h.countdown} className="pop glow-text text-[10rem] font-black italic leading-none">
            {h.countdown}
          </div>
          {h.jogCadence != null && (
            <div className="pop mt-4 rounded-full bg-black/50 px-5 py-2 text-sm font-bold text-amber-200">
              Jog in place — faster jog = faster run!
            </div>
          )}
        </div>
      )}

      {h.state === 'paused' && <PauseOverlay />}
      {fadeOver && <GameOver />}
    </div>
  );
}

function PauseOverlay() {
  const h = useStore(hudStore);
  const ui = useStore(uiStore);
  const cam = ui.mode === 'camera';
  if (ui.settingsOpen) return null;
  const lost = h.pauseReason === 'tracking';
  return (
    <div className="pointer-events-auto absolute inset-0 flex items-center justify-center bg-[#1b1510]/70 p-4">
      <div className="glass w-full max-w-sm space-y-5 rounded-3xl p-8 text-center">
        {lost ? (
          <>
            <div className="text-5xl">🫥</div>
            <h2 className="text-3xl font-black text-rose-300">We lost you</h2>
            <p className="text-violet-100/90">Step back into the frame. The game continues automatically once we see you again.</p>
            <div className="mx-auto w-48 overflow-hidden rounded-xl border-4 border-rose-500">
              <PreviewCanvas className="aspect-[4/3] w-full" />
            </div>
          </>
        ) : (
          <>
            <h2 className="glow-text text-4xl font-black italic">Paused</h2>
            <p className="text-sm text-violet-200/70">{h.pauseReason === 'hidden' ? 'The tab was hidden.' : 'Take a breath.'}</p>
          </>
        )}
        <div className="flex flex-col gap-3">
          <Btn onClick={() => controller.game.resume()}>▶ Resume</Btn>
          {cam && (
            <Btn variant="cyan" onClick={() => controller.recalibrate()}>
              Recalibrate (R)
            </Btn>
          )}
          <Btn variant="ghost" onClick={() => uiStore.set({ settingsOpen: true })}>
            Settings
          </Btn>
          <Btn variant="ghost" onClick={() => controller.quitToMenu()}>
            Quit to Menu
          </Btn>
        </div>
        {cam && !lost && <p className="text-xs text-violet-300/60">Hold both hands above your head to resume.</p>}
      </div>
    </div>
  );
}

function GameOver() {
  const h = useStore(hudStore);
  const ui = useStore(uiStore);
  const cam = ui.mode === 'camera';
  return (
    <div className="pointer-events-auto absolute inset-0 flex items-center justify-center bg-[#1b1510]/65 p-4">
      <div className="glass w-full max-w-md space-y-5 rounded-3xl p-8 text-center">
        <h2 className="text-4xl font-black italic text-rose-300">The Hollow caught you</h2>
        {h.newBest && <div className="pop inline-block rounded-full bg-gradient-to-r from-amber-300 to-fuchsia-400 px-4 py-1 font-black text-slate-900">★ NEW BEST!</div>}
        <div>
          <div className="text-xs font-bold uppercase tracking-[0.3em] text-violet-200/70">Score</div>
          <div className="glow-text text-6xl font-black tabular-nums">{h.score.toLocaleString()}</div>
        </div>
        <div className="grid grid-cols-3 gap-2 text-sm">
          <Stat label="Distance" value={`${h.distance} m`} />
          <Stat label="Motes" value={String(h.motes)} />
          <Stat label="Best" value={h.best.toLocaleString()} />
        </div>
        <div className="flex flex-col gap-3">
          <Btn onClick={() => controller.startRun()}>↻ Run Again</Btn>
          <Btn variant="ghost" onClick={() => controller.quitToMenu()}>
            Menu
          </Btn>
        </div>
        <p className="text-xs text-violet-300/60">{cam ? 'Hold both hands above your head for 1 second to run again.' : 'Press Enter to run again.'}</p>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-white/5 p-2">
      <div className="text-[10px] font-bold uppercase tracking-widest text-violet-300/70">{label}</div>
      <div className="text-lg font-black tabular-nums">{value}</div>
    </div>
  );
}
