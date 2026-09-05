import { useMemo, useState } from 'react';
import type { DecisionBand, Verdict } from '../types/detection';
import { formatProbability } from '../lib/copy';
import { VERDICT_STYLE, clamp01, verdictFromBand } from '../lib/verdict';
import { Disclosure } from './ui/Disclosure';

interface WhatIfSliderProps {
  pFake: number;
  band: DecisionBand;
  officialVerdict: Verdict;
}

/**
 * §11 — "What-if" slider.
 *
 * Moves the band width client-side and shows how the verdict would flip. This
 * is a sensitivity demonstration for the reviewer's intuition; it never touches
 * the official result, and the copy says so twice.
 */
export function WhatIfSlider({ pFake, band, officialVerdict }: WhatIfSliderProps) {
  const p = clamp01(pFake);
  const [threshold, setThreshold] = useState(() => Number(((band.q_lo + band.q_hi) / 2).toFixed(2)));
  const [halfWidth, setHalfWidth] = useState(() =>
    Number(Math.max(0, (band.q_hi - band.q_lo) / 2).toFixed(2)),
  );

  const simulated = useMemo<{ band: DecisionBand; verdict: Verdict }>(() => {
    const lo = clamp01(threshold - halfWidth);
    const hi = clamp01(threshold + halfWidth);
    const next: DecisionBand = { q_lo: Math.min(lo, hi), q_hi: Math.max(lo, hi) };
    return { band: next, verdict: verdictFromBand(p, next) };
  }, [halfWidth, p, threshold]);

  const changed = simulated.verdict !== officialVerdict;
  const style = VERDICT_STYLE[simulated.verdict];

  return (
    <Disclosure summary="What-if: move the decision threshold" hint="illustrative only">
      <p className="text-note text-ink-2">
        Drag the controls to see how this capture would be classified under a different decision
        band. The calibrated probability{' '}
        <span className="font-mono text-ink">{formatProbability(p)}</span> does not change — only
        the policy applied to it does.
      </p>

      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <SliderField
          id="whatif-threshold"
          label="Band centre"
          value={threshold}
          onChange={setThreshold}
          min={0}
          max={1}
        />
        <SliderField
          id="whatif-width"
          label="Band half-width"
          value={halfWidth}
          onChange={setHalfWidth}
          min={0}
          max={0.5}
        />
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-3 rounded-[8px] border border-line bg-sunken p-3">
        <span
          className={`inline-flex items-center gap-2 rounded-[6px] border px-2.5 py-1 text-note font-semibold ${style.fill} ${style.ink} ${style.border}`}
        >
          <span aria-hidden="true" className="font-mono">
            {style.glyph}
          </span>
          {style.label}
        </span>
        <p className="font-mono text-micro text-ink-2">
          q_lo {formatProbability(simulated.band.q_lo)} · q_hi{' '}
          {formatProbability(simulated.band.q_hi)}
        </p>
        <p aria-live="polite" className="text-note text-ink-2">
          {changed
            ? `Under this band the verdict would read ${style.label} instead of ${VERDICT_STYLE[officialVerdict].label}.`
            : `Under this band the verdict would stay ${style.label}.`}
        </p>
      </div>

      <p className="limitation mt-3">
        This simulation is illustrative. It does not change the official result, is not calibrated,
        and must not be used to justify a decision. Production thresholds are fitted on a held-out
        calibration split and versioned.
      </p>
    </Disclosure>
  );
}

function SliderField({
  id,
  label,
  value,
  onChange,
  min,
  max,
}: {
  id: string;
  label: string;
  value: number;
  onChange: (next: number) => void;
  min: number;
  max: number;
}) {
  return (
    <div>
      <label htmlFor={id} className="flex items-baseline justify-between text-note text-ink-2">
        <span>{label}</span>
        <span className="font-mono text-ink">{formatProbability(value)}</span>
      </label>
      <input
        id={id}
        type="range"
        min={min}
        max={max}
        step={0.01}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        aria-valuetext={formatProbability(value)}
        className="mt-1.5 w-full accent-[var(--blue-500)]"
      />
    </div>
  );
}
