import { useEffect, useRef } from 'react';
import type { ReactNode } from 'react';
import { controller } from '../app/Controller';

export function Btn({
  children,
  onClick,
  variant = 'primary',
  className = '',
  disabled,
}: {
  children: ReactNode;
  onClick?: () => void;
  variant?: 'primary' | 'ghost' | 'cyan';
  className?: string;
  disabled?: boolean;
}) {
  const base =
    'pointer-events-auto rounded-xl px-6 py-3 text-base font-bold tracking-wide transition active:scale-95 disabled:opacity-40 focus:outline-none focus-visible:ring-2 focus-visible:ring-white';
  const styles = {
    primary: 'bg-gradient-to-r from-amber-300 via-orange-400 to-fuchsia-500 text-slate-950 shadow-[0_0_28px_rgba(251,146,60,0.45)] hover:brightness-110',
    cyan: 'bg-gradient-to-r from-cyan-300 to-sky-500 text-slate-950 shadow-[0_0_24px_rgba(34,211,238,0.35)] hover:brightness-110',
    ghost: 'border border-violet-300/30 bg-white/5 text-violet-100 hover:bg-white/10',
  }[variant];
  return (
    <button
      disabled={disabled}
      onClick={() => {
        controller.game?.audio.blip();
        onClick?.();
      }}
      className={`${base} ${styles} ${className}`}
    >
      {children}
    </button>
  );
}

export function Logo({ size = 'lg' }: { size?: 'lg' | 'sm' }) {
  return (
    <div className="leading-none">
      <div className={`glow-text font-black italic tracking-tight ${size === 'lg' ? 'text-6xl sm:text-7xl' : 'text-3xl'}`}>LUMEN</div>
      <div
        className={`font-black italic tracking-[0.35em] text-cyan-200 ${size === 'lg' ? 'mt-1 text-3xl sm:text-4xl' : 'text-lg'}`}
        style={{ textShadow: '0 0 18px rgba(103,232,249,0.7)' }}
      >
        DASH
      </div>
    </div>
  );
}

/** Canvas that receives the live (mirrored) camera preview + skeleton. */
export function PreviewCanvas({ className = '', borderColor }: { className?: string; borderColor?: string }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => (ref.current ? controller.registerPreview(ref.current) : undefined), []);
  return (
    <canvas
      ref={ref}
      width={480}
      height={360}
      className={`bg-black/60 object-cover ${className}`}
      style={borderColor ? { borderColor } : undefined}
    />
  );
}
