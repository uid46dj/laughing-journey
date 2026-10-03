import { controller } from '../app/Controller';
import { gestureStore, settingsStore, uiStore, useStore } from '../app/store';
import { Btn, PreviewCanvas } from './common';

const STEPS = [
  { icon: '⬅', title: 'Step or lean LEFT', hint: 'Move your shoulders to the left side of the screen', anim: 'nudge-l' },
  { icon: '➡', title: 'Step or lean RIGHT', hint: 'Move your shoulders to the right side of the screen', anim: 'nudge-r' },
  { icon: '⬆', title: 'JUMP', hint: 'A quick, real hop — both feet off the floor', anim: 'hop' },
  { icon: '⬇', title: 'CROUCH', hint: 'Bend your knees and drop your shoulders, then stand up', anim: 'squat' },
];

export function Setup() {
  const ui = useStore(uiStore);
  const g = useStore(gestureStore);
  const s = ui.setup;

  return (
    <div className="absolute inset-0 flex items-center justify-center overflow-y-auto bg-[#1b1510]/85 p-4">
      <div className="glass pointer-events-auto my-auto w-full max-w-4xl rounded-3xl p-6 sm:p-8">
        {s.phase === 'starting' && (
          <div className="flex flex-col items-center gap-5 py-10 text-center">
            <div className="h-14 w-14 animate-spin rounded-full border-4 border-fuchsia-300/30 border-t-amber-300" />
            <div className="text-xl font-bold">{s.message || 'Starting…'}</div>
            <p className="max-w-sm text-sm text-violet-200/70">Your video stays on this device. The first load downloads a small pose model (~5 MB).</p>
            <Btn variant="ghost" onClick={() => controller.cancelSetup()}>
              Cancel
            </Btn>
          </div>
        )}

        {s.phase === 'error' && (
          <div className="flex flex-col items-center gap-5 py-8 text-center">
            <div className="text-5xl">📷</div>
            <h2 className="text-2xl font-black text-rose-300">Camera unavailable</h2>
            <p className="max-w-md text-violet-100/90">{s.message}</p>
            <div className="flex flex-wrap justify-center gap-3">
              <Btn onClick={() => void controller.startCameraFlow(s.returnToGame)}>Retry</Btn>
              <Btn variant="cyan" onClick={() => controller.startKeyboardRun()}>
                Play with Keyboard
              </Btn>
              <Btn variant="ghost" onClick={() => controller.cancelSetup()}>
                Back
              </Btn>
            </div>
          </div>
        )}

        {s.phase === 'calibrating' && (
          <div className="grid items-center gap-6 md:grid-cols-[1.2fr_1fr]">
            <div
              className={`relative overflow-hidden rounded-2xl border-4 transition-colors ${s.framingOk ? 'border-emerald-400' : 'border-amber-400/70'}`}
            >
              <PreviewCanvas className="aspect-[4/3] w-full" />
              {/* framing guide: head + shoulders */}
              <svg viewBox="0 0 400 300" className="pointer-events-none absolute inset-0 h-full w-full">
                <g fill="none" stroke={s.framingOk ? '#34d399' : '#fde68a'} strokeWidth="3" strokeDasharray="10 8" opacity="0.85">
                  <circle cx="200" cy="105" r="36" />
                  <path d="M110 250 Q110 170 200 160 Q290 170 290 250" />
                  <rect x="60" y="30" width="280" height="240" rx="14" opacity="0.35" />
                </g>
              </svg>
            </div>
            <div className="space-y-5">
              <h2 className="glow-text text-3xl font-black italic">Stand here</h2>
              <p className="min-h-[3.5rem] text-xl font-semibold leading-snug text-white">{s.message}</p>
              <div className="h-3 overflow-hidden rounded-full bg-white/10">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-emerald-300 to-cyan-300 transition-[width] duration-100"
                  style={{ width: `${Math.round(s.progress * 100)}%` }}
                />
              </div>
              <ul className="space-y-1 text-sm text-violet-200/80">
                <li>• Fit your head and shoulders in the outline.</li>
                <li>• Leave room above your head to jump.</li>
                <li>• Stand in the middle and hold still for 1.5 s.</li>
              </ul>
              <Btn variant="ghost" onClick={() => (s.returnToGame ? uiStore.set({ screen: 'game' }) : controller.cancelSetup())}>
                {s.returnToGame ? 'Back to game' : 'Cancel'}
              </Btn>
            </div>
          </div>
        )}

        {s.phase === 'tutorial' && (
          <div className="grid items-start gap-6 md:grid-cols-[1fr_1.2fr]">
            <div className="space-y-3">
              <div className={`overflow-hidden rounded-2xl border-4 ${g.tracking === 'ok' ? 'border-emerald-400' : 'border-rose-400'}`}>
                <PreviewCanvas className="aspect-[4/3] w-full" />
              </div>
              <div className="flex gap-1">
                {([-1, 0, 1] as const).map((z) => (
                  <div key={z} className={`h-3 flex-1 rounded-full transition ${g.zone === z ? 'bg-amber-300 shadow-[0_0_12px_#fcd34d]' : 'bg-white/10'}`} />
                ))}
              </div>
              <p className="text-xs text-violet-300/70">Trouble? Add light in front of you, step back a little, and use a plain background.</p>
            </div>
            <div className="space-y-4">
              <h2 className="glow-text text-3xl font-black italic">Learn the moves</h2>
              {STEPS.map((st, i) => {
                const done = s.tutorialDone[i];
                const current = i === s.tutorialStep;
                return (
                  <div
                    key={st.title}
                    className={`flex items-center gap-4 rounded-2xl border p-4 transition ${
                      done ? 'border-emerald-400/60 bg-emerald-400/10' : current ? 'border-amber-300/70 bg-amber-300/10' : 'border-white/10 bg-white/5 opacity-50'
                    }`}
                  >
                    <div className={`text-4xl ${current && !done ? st.anim : ''}`}>{done ? '✅' : st.icon}</div>
                    <div>
                      <div className="font-black tracking-wide">{st.title}</div>
                      {current && !done && <div className="text-sm text-violet-100/80">{st.hint}</div>}
                    </div>
                  </div>
                );
              })}
              <Btn
                variant="ghost"
                onClick={() => {
                  settingsStore.set({ tutorialDone: true });
                  controller.skipTutorial();
                }}
              >
                Skip tutorial
              </Btn>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
