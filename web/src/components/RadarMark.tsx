// The wordmark's glyph: two range rings and a show picked up at two o'clock.
export default function RadarMark({ className = "h-6 w-6" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
      <circle cx="12" cy="12" r="10.5" stroke="currentColor" strokeWidth="1.5" opacity="0.35" />
      <circle cx="12" cy="12" r="6" stroke="currentColor" strokeWidth="1.5" opacity="0.6" />
      <circle cx="12" cy="12" r="2" fill="currentColor" />
      <circle cx="17.2" cy="7.6" r="2.4" className="fill-pink" />
    </svg>
  );
}
