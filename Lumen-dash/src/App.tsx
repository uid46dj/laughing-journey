import { useEffect, useRef } from 'react';
import { controller } from './app/Controller';
import { settingsStore, uiStore, useStore } from './app/store';
import { Debug } from './ui/Debug';
import { Hud } from './ui/Hud';
import { HowTo, Menu } from './ui/Menu';
import { Settings } from './ui/Settings';
import { Setup } from './ui/Setup';

export default function App() {
  const host = useRef<HTMLDivElement>(null);
  const ui = useStore(uiStore);
  const st = useStore(settingsStore);

  useEffect(() => {
    if (!host.current) return;
    controller.init(host.current);
    const onLost = () => uiStore.set({ contextLost: true });
    window.addEventListener('lumen-contextlost', onLost);
    const unlock = () => controller.unlockAudio();
    window.addEventListener('pointerdown', unlock, { once: true });
    return () => {
      window.removeEventListener('lumen-contextlost', onLost);
      controller.dispose();
    };
  }, []);

  return (
    <div className="fixed inset-0 overflow-hidden bg-[#1b1510]">
      <div ref={host} className="absolute inset-0" />

      <div className="pointer-events-none absolute inset-0">
        {ui.screen === 'menu' && <Menu />}
        {ui.screen === 'howto' && <HowTo />}
        {ui.screen === 'setup' && <Setup />}
        {ui.screen === 'game' && <Hud />}
        {ui.settingsOpen && <Settings />}
        {st.showDebug && <Debug />}

        {ui.toast && (
          <div key={ui.toast} className="toast absolute left-1/2 top-4 z-40 -translate-x-1/2 rounded-xl bg-black/80 px-4 py-2 text-sm font-semibold text-amber-200">
            {ui.toast}
          </div>
        )}

        {ui.contextLost && (
          <div className="pointer-events-auto absolute inset-0 z-50 flex items-center justify-center bg-black/90 text-center">
            <div className="space-y-4">
              <h2 className="text-2xl font-black text-rose-300">Graphics context lost</h2>
              <p className="text-violet-100/80">Your browser dropped the GPU context.</p>
              <button className="rounded-xl bg-amber-300 px-6 py-3 font-bold text-slate-900" onClick={() => location.reload()}>
                Reload
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
