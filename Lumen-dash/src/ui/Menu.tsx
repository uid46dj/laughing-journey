import { controller } from '../app/Controller';
import { hudStore, uiStore, useStore } from '../app/store';
import { Btn, Logo } from './common';

export function Menu() {
  const hud = useStore(hudStore);
  return (
    <div className="pointer-events-none absolute inset-0 flex items-center bg-gradient-to-r from-[#1b1510]/90 via-[#1b1510]/45 to-transparent px-8 sm:px-16">
      <div className="max-w-md space-y-8">
        <Logo />
        <p className="max-w-sm text-lg leading-snug text-violet-100/90">
          Run the glass causeway. <span className="text-amber-300">Lean</span>, <span className="text-amber-300">jump</span> and{' '}
          <span className="text-amber-300">duck</span> — with your actual body. The Hollow is close behind.
        </p>
        <div className="flex flex-col gap-3">
          <Btn onClick={() => void controller.startCameraFlow()}>📷 Play with Camera</Btn>
          <Btn variant="cyan" onClick={() => controller.startKeyboardRun()}>
            ⌨ Play with Keyboard
          </Btn>
          <div className="flex gap-3">
            <Btn variant="ghost" className="flex-1" onClick={() => uiStore.set({ screen: 'howto' })}>
              How to Play
            </Btn>
            <Btn variant="ghost" className="flex-1" onClick={() => uiStore.set({ settingsOpen: true })}>
              Settings
            </Btn>
          </div>
        </div>
        <div className="flex items-center gap-3 text-sm text-violet-200/80">
          <span className="rounded-md bg-white/10 px-2 py-1 font-semibold text-amber-200">BEST</span>
          <span className="text-xl font-bold tabular-nums">{hud.best.toLocaleString()}</span>
        </div>
        <p className="max-w-xs text-xs text-violet-300/60">
          Your camera video is processed on this device only and never leaves it.
        </p>
      </div>
    </div>
  );
}

const MOVES = [
  { icon: '⬅', title: 'Step or lean left', text: 'Move to your left — the runner takes the left lane.', anim: 'nudge-l' },
  { icon: '➡', title: 'Step or lean right', text: 'Move to your right — the runner takes the right lane.', anim: 'nudge-r' },
  { icon: '⬆', title: 'Jump', text: 'A real hop. Clears low amber barriers and cracks.', anim: 'hop' },
  { icon: '⬇', title: 'Crouch', text: 'Drop your shoulders. Slide under cyan gates. Stay low to keep sliding.', anim: 'squat' },
];

export function HowTo() {
  return (
    <div className="absolute inset-0 flex items-center justify-center overflow-y-auto bg-[#1b1510]/80 p-4">
      <div className="glass pointer-events-auto my-auto w-full max-w-3xl space-y-6 rounded-3xl p-6 sm:p-8">
        <div className="flex items-center justify-between">
          <h2 className="glow-text text-3xl font-black italic">How to Play</h2>
          <Btn variant="ghost" onClick={() => uiStore.set({ screen: 'menu' })}>
            Back
          </Btn>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          {MOVES.map((m) => (
            <div key={m.title} className="flex items-center gap-4 rounded-2xl bg-white/5 p-4">
              <div className={`text-4xl ${m.anim}`}>{m.icon}</div>
              <div>
                <div className="font-bold text-amber-200">{m.title}</div>
                <div className="text-sm text-violet-100/80">{m.text}</div>
              </div>
            </div>
          ))}
        </div>
        <div className="grid gap-3 text-sm sm:grid-cols-3">
          <div className="rounded-2xl border border-amber-300/40 bg-amber-300/10 p-3">
            <b className="text-amber-300">▁ Amber, low</b>
            <br />
            Barriers & cracks → <b>jump</b>
          </div>
          <div className="rounded-2xl border border-cyan-300/40 bg-cyan-300/10 p-3">
            <b className="text-cyan-300">▔ Cyan, overhead</b>
            <br />
            Gates & lanterns → <b>crouch</b>
          </div>
          <div className="rounded-2xl border border-fuchsia-300/40 bg-fuchsia-300/10 p-3">
            <b className="text-fuchsia-300">█ Magenta, tall</b>
            <br />
            Monoliths → <b>change lane</b>
          </div>
        </div>
        <div className="grid gap-4 text-sm text-violet-100/80 sm:grid-cols-2">
          <div>
            <div className="mb-1 font-bold text-white">Good camera setup</div>
            <ul className="list-disc space-y-1 pl-5">
              <li>Stand 1.5–2 m back so head and shoulders fit with room above to jump.</li>
              <li>Face a window or lamp; avoid strong light behind you.</li>
              <li>Plain background and a contrasting top help tracking.</li>
              <li>Hold both hands above your head for 1 second to pause.</li>
            </ul>
          </div>
          <div>
            <div className="mb-1 font-bold text-white">Keyboard</div>
            <ul className="list-disc space-y-1 pl-5">
              <li>← → / A D: change lane</li>
              <li>↑ / W / Space: jump</li>
              <li>↓ / S / Ctrl: crouch & slide</li>
              <li>Esc / P: pause · F3: debug overlay</li>
            </ul>
            <p className="mt-2 text-xs text-violet-300/70">Collect motes in a row to build a ×4 multiplier. One hit lets the Hollow close in; a second hit while it is close ends the run.</p>
          </div>
        </div>
      </div>
    </div>
  );
}
