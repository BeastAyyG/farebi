import { formatProbability, UNCERTAINTY_INTERPRETATION } from '../lib/copy';
import { clamp01, uncertaintyBucket } from '../lib/verdict';
import { useGrow } from '../lib/motion';

export interface UncertaintyBannerProps {
  uncertainty_score: number;
  /** True when `fake_probability` sits strictly inside the conformal band. */
  in_band: boolean;
}

/**
 * §8.2 — numeric uncertainty with its interpretation, plus the reason the
 * pipeline declined to decide when the probability landed inside the band.
 */
export function UncertaintyBanner({ uncertainty_score, in_band }: UncertaintyBannerProps) {
  const score = clamp01(uncertainty_score);
  const bucket = uncertaintyBucket(score);
  const grown = useGrow(score);

  return (
    <aside
      aria-labelledby="uncertainty-heading"
      className="rounded-card border border-ochre-500 bg-ochre-50 p-3.5"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3
          id="uncertainty-heading"
          className="flex items-center gap-2 text-[14px] font-semibold text-ochre-700"
        >
          <span aria-hidden="true" className="font-mono">
            ⚠
          </span>
          Uncertainty
        </h3>
        <p className="font-mono text-note text-ochre-700">
          <span className="sr-only">Uncertainty score </span>
          {formatProbability(score)}
          <span aria-hidden="true"> / 1.00</span>
        </p>
      </div>

      <div
        role="img"
        aria-label={`Uncertainty score ${formatProbability(score)} out of 1.00 — ${
          UNCERTAINTY_INTERPRETATION[bucket]
        }`}
        className="mt-2.5 h-2 w-full overflow-hidden rounded-full bg-ochre-100"
      >
        <div
          className="a-bar h-full rounded-full bg-ochre-500"
          style={{ width: `${grown * 100}%` }}
        />
      </div>

      <p className="mt-2 text-note text-ochre-700">
        {UNCERTAINTY_INTERPRETATION[bucket]}
        {in_band
          ? ' The calibrated probability falls inside the conformal decision band, so the detector declines to decide.'
          : ''}
      </p>

      <p className="mt-1.5 text-note text-ochre-700 opacity-90">
        Send this capture to a human reviewer before acting on it.
      </p>
    </aside>
  );
}
