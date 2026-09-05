import { useId, useMemo } from 'react';
import type { SignalOutput } from '../types/detection';
import { formatProbability } from '../lib/copy';
import { DIRECTION_STYLE, clamp01, isApplicable } from '../lib/verdict';

interface SignalRadarProps {
  signals: SignalOutput[];
}

const SIZE = 260;
const CENTRE = SIZE / 2;
const RADIUS = 88;
const RINGS = [0.25, 0.5, 0.75, 1];

interface Spoke {
  code: string;
  short: string;
  strength: number;
  direction: SignalOutput['direction'];
  x: number;
  y: number;
  labelX: number;
  labelY: number;
  anchor: 'start' | 'middle' | 'end';
}

/**
 * §11 — Signal Radar Chart.
 *
 * Shows every applicable signal's strength on one dial, so a reviewer can see
 * the *balance* of evidence at a glance rather than reading five bars in
 * sequence. A lopsided web means one signal is carrying the result; a small
 * even web means nothing is confident.
 *
 * The chart is decorative-plus: the same numbers are in the list below it, and
 * the whole figure is exposed to assistive tech as a table-like description,
 * so nothing here is available only to sighted users.
 */
export function SignalRadar({ signals }: SignalRadarProps) {
  const gradientId = useId();

  const spokes = useMemo<Spoke[]>(() => {
    const applicable = signals.filter((s) => isApplicable(s.applicable));
    const n = applicable.length;
    return applicable.map((signal, i) => {
      // Start at 12 o'clock and go clockwise.
      const angle = (i / n) * Math.PI * 2 - Math.PI / 2;
      const strength = clamp01(signal.strength);
      const r = strength * RADIUS;
      const labelR = RADIUS + 22;
      const lx = CENTRE + Math.cos(angle) * labelR;
      return {
        code: signal.code,
        short: shorten(signal.code),
        strength,
        direction: signal.direction,
        x: CENTRE + Math.cos(angle) * r,
        y: CENTRE + Math.sin(angle) * r,
        labelX: lx,
        labelY: CENTRE + Math.sin(angle) * labelR,
        anchor: lx < CENTRE - 6 ? 'end' : lx > CENTRE + 6 ? 'start' : 'middle',
      };
    });
  }, [signals]);

  if (spokes.length < 3) return null;

  const polygon = spokes.map((s) => `${s.x.toFixed(1)},${s.y.toFixed(1)}`).join(' ');
  const perimeter = estimatePerimeter(spokes);

  const description = `Radar chart of ${spokes.length} signal strengths. ${spokes
    .map((s) => `${s.code}: ${formatProbability(s.strength)}, ${DIRECTION_STYLE[s.direction].label}`)
    .join('. ')}.`;

  return (
    <div className="flex flex-col items-center">
      <svg
        viewBox={`0 0 ${SIZE} ${SIZE}`}
        width="100%"
        style={{ maxWidth: SIZE }}
        role="img"
        aria-label={description}
        className="overflow-visible"
      >
        <defs>
          <radialGradient id={gradientId}>
            <stop offset="0%" stopColor="var(--blue-300)" stopOpacity="0.42" />
            <stop offset="100%" stopColor="var(--sky-500)" stopOpacity="0.16" />
          </radialGradient>
        </defs>

        {/* Rings, labelled at the outer edge. */}
        {RINGS.map((ring) => (
          <circle
            key={ring}
            cx={CENTRE}
            cy={CENTRE}
            r={RADIUS * ring}
            fill="none"
            stroke="var(--border)"
            strokeWidth="1"
            strokeDasharray={ring === 1 ? undefined : '3 4'}
          />
        ))}

        {/* Spoke guides. */}
        {spokes.map((spoke, i) => {
          const angle = (i / spokes.length) * Math.PI * 2 - Math.PI / 2;
          return (
            <line
              key={spoke.code}
              x1={CENTRE}
              y1={CENTRE}
              x2={CENTRE + Math.cos(angle) * RADIUS}
              y2={CENTRE + Math.sin(angle) * RADIUS}
              stroke="var(--border)"
              strokeWidth="1"
            />
          );
        })}

        {/* The web. */}
        <polygon
          points={polygon}
          fill={`url(#${gradientId})`}
          stroke="var(--blue-500)"
          strokeWidth="2"
          strokeLinejoin="round"
          className="a-draw"
          style={{
            ['--dash' as string]: `${perimeter}`,
            strokeDasharray: perimeter,
          }}
        />

        {/* Vertices, coloured by the signal's direction. */}
        {spokes.map((spoke, i) => (
          <circle
            key={spoke.code}
            cx={spoke.x}
            cy={spoke.y}
            r="4"
            fill={vertexColour(spoke.direction)}
            stroke="var(--surface)"
            strokeWidth="1.5"
            className="a-pop"
            style={{ ['--delay' as string]: `${420 + i * 70}ms` }}
          />
        ))}

        {/* Labels. */}
        {spokes.map((spoke, i) => (
          <text
            key={spoke.code}
            x={spoke.labelX}
            y={spoke.labelY}
            textAnchor={spoke.anchor}
            dominantBaseline="middle"
            className="a-fade"
            style={{ ['--delay' as string]: `${520 + i * 70}ms` }}
            fontSize="9.5"
            fontFamily="var(--font-mono, monospace)"
            fill="var(--text-2)"
          >
            {spoke.short}
          </text>
        ))}
      </svg>

      <p className="limitation mt-2 text-center">
        Each axis is one signal&apos;s strength from 0 at the centre to 1 at the rim. A lopsided
        web means a single signal is driving the result; a small, even web means no signal is
        confident. Strength is a magnitude, not a probability.
      </p>
    </div>
  );
}

function vertexColour(direction: SignalOutput['direction']): string {
  switch (direction) {
    case 'toward_fake':
      return 'var(--terracotta-500)';
    case 'toward_real':
      return 'var(--blue-500)';
    case 'toward_uncertain':
      return 'var(--ochre-500)';
    default:
      return 'var(--text-3)';
  }
}

/** Keeps axis labels readable at 9.5px without truncating meaning. */
function shorten(code: string): string {
  const parts = code.split('_');
  if (code.length <= 14) return code;
  if (parts.length > 1) return parts.map((p) => p.slice(0, 5)).join('_');
  return `${code.slice(0, 13)}…`;
}

function estimatePerimeter(spokes: Spoke[]): number {
  let total = 0;
  for (let i = 0; i < spokes.length; i += 1) {
    const a = spokes[i];
    const b = spokes[(i + 1) % spokes.length];
    total += Math.hypot(b.x - a.x, b.y - a.y);
  }
  return Math.ceil(total) + 4;
}
