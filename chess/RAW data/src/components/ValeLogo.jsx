export function ValeMark({ className = '' }) {
  return (
    <svg
      className={`vale-mark ${className}`.trim()}
      viewBox="0 0 48 48"
      role="img"
      aria-label="Valé mark"
      focusable="false"
    >
      <path className="vale-mark-outline" d="M24 2.75 44.5 14.6v18.8L24 45.25 3.5 33.4V14.6Z" />
      <path className="vale-mark-v" d="m10.5 15.2 13.5 22 13.5-22" />
      <path className="vale-mark-cut" d="m17.25 15.3 6.75 10.9 6.75-10.9" />
      <circle className="vale-mark-point" cx="24" cy="27.8" r="1.75" />
    </svg>
  );
}
