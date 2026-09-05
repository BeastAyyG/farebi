import type { ConfidenceLevel, Verdict } from '../types/detection';
import { assertNoBannedPhrase, formatProbability, probabilitySentence } from '../lib/copy';
import { VERDICT_STYLE, clamp01 } from '../lib/verdict';
import { useGrow } from '../lib/motion';
import { ConfidenceBadge } from './ConfidenceBadge';

export interface ProbabilityBarProps {
  /** Calibrated `fake_probability` in [0, 1]. */
  value: number;
  confidence: ConfidenceLevel;
  verdict: Verdict;
}

/**
 * §1.2 — the mandatory probability sentence with a bar for scale.
 *
 * The number is always two decimals and never a percentage. The bar is
 * decoration: the sentence above it is the authoritative rendering, and the
 * bar carries `role="img"` with the same text so assistive tech is not asked
 * to interpret a gradient.
 */
export function ProbabilityBar({ value, confidence, verdict }: ProbabilityBarProps) {
  const p = clamp01(value);
  const grown = useGrow(p);
  const sentence = probabilitySentence(p, confidence);
  const style = VERDICT_STYLE[verdict];

  assertNoBannedPhrase(sentence, 'ProbabilityBar');

  return (
    <div>
      <p className="text-[15px] leading-[1.6] text-ink">
        Estimated manipulation probability:{' '}
        <strong className="font-mono text-[16px] font-semibold">{formatProbability(p)}</strong>.{' '}
        <span className="font-semibold">Confidence:</span> {confidence}. The image should be
        manually reviewed.
      </p>

      <div
        role="img"
        aria-label={sentence}
        className="mt-3 h-3 w-full overflow-hidden rounded-full border border-line bg-sunken"
      >
        <div
          className={`a-bar h-full rounded-full ${style.stripe}`}
          style={{ width: `${grown * 100}%` }}
        />
      </div>

      <div
        aria-hidden="true"
        className="mt-1 flex justify-between font-mono text-micro text-ink-3"
      >
        <span>0.00</span>
        <span>0.50</span>
        <span>1.00</span>
      </div>

      <ConfidenceBadge confidence={confidence} className="mt-3" />
    </div>
  );
}
