import type { DecisionBand } from '../types/detection';
import { formatProbability } from '../lib/copy';
import { VERDICT_STYLE, clamp01, verdictFromBand } from '../lib/verdict';

export interface BandIndicatorProps {
  /** Calibrated probability being placed on the scale. */
  pFake: number;
  band: DecisionBand;
  /** Set when the band came from the UI default rather than the API. */
  isDefaultBand?: boolean;
  /** Slider mode renders a lighter variant without the caption. */
  compact?: boolean;
}

/**
 * §8.1 — where this probability sits relative to the conformal decision band.
 *
 *   [ q_lo ──────── p_fake ──────── q_hi ]
 *
 * Zones are labelled in text as well as tinted, and the marker carries a mono
 * numeric readout, so nothing here depends on colour perception.
 */
export function BandIndicator({
  pFake,
  band,
  isDefaultBand = false,
  compact = false,
}: BandIndicatorProps) {
  const p = clamp01(pFake);
  const lo = clamp01(band.q_lo);
  const hi = clamp01(band.q_hi);
  const zoneVerdict = verdictFromBand(p, band);
  const style = VERDICT_STYLE[zoneVerdict];

  const pct = (v: number) => `${v * 100}%`;

  return (
    <div>
      {!compact ? (
        <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
          <h3 className="text-[14px] font-semibold text-ink">Decision band</h3>
          <p className="font-mono text-micro text-ink-3">
            q_lo {formatProbability(lo)} · q_hi {formatProbability(hi)}
          </p>
        </div>
      ) : null}

      <div
        role="img"
        aria-label={`Probability ${formatProbability(
          p,
        )} falls in the ${style.label} zone. The uncertain band runs from ${formatProbability(
          lo,
        )} to ${formatProbability(hi)}.`}
        className="relative h-10 w-full overflow-hidden rounded-[8px] border border-line"
      >
        {/* Zones: real / uncertain / fake. */}
        <div className="absolute inset-0 flex">
          <div className="h-full bg-sage-100" style={{ width: pct(lo) }} />
          <div className="h-full bg-ochre-100" style={{ width: pct(Math.max(0, hi - lo)) }} />
          <div className="h-full bg-terracotta-100" style={{ width: pct(Math.max(0, 1 - hi)) }} />
        </div>

        {/* q_lo / q_hi ticks. */}
        {[lo, hi].map((tick, index) => (
          <div
            key={index}
            aria-hidden="true"
            className="absolute top-0 h-full w-px"
            style={{ left: pct(tick), backgroundColor: 'var(--text-2)' }}
          />
        ))}

        {/* p_fake marker. */}
        <div
          aria-hidden="true"
          className="absolute top-0 h-full w-0.5"
          style={{ left: pct(p), backgroundColor: 'var(--text)' }}
        />
        <div
          aria-hidden="true"
          className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 rounded-full border-2 border-surface"
          style={{
            left: pct(p),
            width: 12,
            height: 12,
            backgroundColor: 'var(--text)',
          }}
        />
      </div>

      {/* Textual zone key — the colours above are never the only channel. */}
      <div className="mt-2 grid grid-cols-3 gap-2 text-micro">
        <ZoneKey
          swatch="bg-verdict-real-anchor"
          label="Likely Real"
          range={`p ≤ ${formatProbability(lo)}`}
          active={zoneVerdict === 'likely_real'}
        />
        <ZoneKey
          swatch="bg-verdict-unc-anchor"
          label="Uncertain"
          range={`${formatProbability(lo)} – ${formatProbability(hi)}`}
          active={zoneVerdict === 'uncertain'}
        />
        <ZoneKey
          swatch="bg-verdict-fake-anchor"
          label="Likely Fake"
          range={`p ≥ ${formatProbability(hi)}`}
          active={zoneVerdict === 'likely_fake'}
        />
      </div>

      <p className="mt-2 font-mono text-micro text-ink-2">
        p_fake {formatProbability(p)} → {style.label}
      </p>

      {!compact ? (
        <p className="limitation mt-2">
          {isDefaultBand
            ? 'Band thresholds were not supplied by the API, so an illustrative default band is shown. Calibrated thresholds come from a held-out split.'
            : 'Thresholds are conformal quantiles fitted on a held-out calibration split. A probability inside the band means the model declines to decide.'}
        </p>
      ) : null}
    </div>
  );
}

function ZoneKey({
  swatch,
  label,
  range,
  active,
}: {
  swatch: string;
  label: string;
  range: string;
  active: boolean;
}) {
  return (
    <div
      className={[
        'anim rounded-[6px] border px-2 py-1',
        active ? 'border-line-strong bg-surface font-semibold text-ink' : 'border-transparent text-ink-3',
      ].join(' ')}
    >
      <span className="flex items-center gap-1.5">
        <span aria-hidden="true" className={`inline-block h-2 w-2 rounded-full ${swatch}`} />
        <span>{label}</span>
        {active ? <span className="sr-only">(current zone)</span> : null}
      </span>
      <span className="mt-0.5 block font-mono text-ink-3">{range}</span>
    </div>
  );
}
