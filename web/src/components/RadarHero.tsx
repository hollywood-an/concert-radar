// The sign-in page's picture of what the app does: rings at three travel distances, one
// slow sweep, and shows that light up as it passes. Yellow marks artists you follow.
// Purely illustrative, so it is hidden from assistive technology.

const CENTER = 200;
const RINGS = [
  { radius: 60, label: "10 mi" },
  { radius: 120, label: "25 mi" },
  { radius: 180, label: "50 mi" },
];

// Shows on the scope: angle in degrees clockwise from the top, distance from the centre.
const SHOWS = [
  { angle: 24, distance: 96, followed: false },
  { angle: 61, distance: 150, followed: true },
  { angle: 118, distance: 52, followed: false },
  { angle: 163, distance: 132, followed: false },
  { angle: 205, distance: 84, followed: true },
  { angle: 251, distance: 166, followed: false },
  { angle: 296, distance: 112, followed: false },
  { angle: 338, distance: 40, followed: false },
];

const SWEEP_SECONDS = 8;

export default function RadarHero() {
  return (
    <div className="relative mx-auto aspect-square w-full max-w-[30rem]" aria-hidden="true">
      {/* The sweep: bright at its leading edge, fading behind it. */}
      <div
        className="radar-sweep absolute inset-[5%] rounded-full"
        style={{
          background:
            "conic-gradient(from 0deg, rgb(227 18 107 / 0) 70%, rgb(227 18 107 / 0.32) 100%)",
        }}
      />
      <svg viewBox="0 0 400 400" className="relative h-full w-full">
        {RINGS.map((ring) => (
          <g key={ring.radius}>
            <circle
              cx={CENTER}
              cy={CENTER}
              r={ring.radius}
              fill="none"
              className="stroke-ink"
              strokeOpacity="0.28"
              strokeWidth="1.5"
            />
            <text
              x={CENTER + 6}
              y={CENTER - ring.radius + 16}
              className="fill-ink-soft font-sans"
              fontSize="12"
              fontWeight="600"
            >
              {ring.label}
            </text>
          </g>
        ))}
        <line x1="20" y1={CENTER} x2="380" y2={CENTER} className="stroke-ink" strokeOpacity="0.14" />
        <line x1={CENTER} y1="20" x2={CENTER} y2="380" className="stroke-ink" strokeOpacity="0.14" />
        {SHOWS.map((show) => {
          const radians = (show.angle * Math.PI) / 180;
          const x = CENTER + Math.sin(radians) * show.distance;
          const y = CENTER - Math.cos(radians) * show.distance;
          return (
            <circle
              key={show.angle}
              cx={x}
              cy={y}
              r={show.followed ? 9 : 6}
              className={`radar-ping ${
                show.followed ? "fill-highlighter stroke-ink" : "fill-pink"
              }`}
              strokeWidth={show.followed ? 2 : 0}
              // Each show lights up when the sweep reaches its bearing.
              style={{ animationDelay: `${((show.angle / 360) * SWEEP_SECONDS).toFixed(2)}s` }}
            />
          );
        })}
        <circle cx={CENTER} cy={CENTER} r="7" className="fill-ink" />
      </svg>
    </div>
  );
}
