import type { RefObject } from 'react';
import type { ConfidenceLevel, DetectResponse, SignalOutput, Verdict } from '../types/detection';
import { PER_RESULT_WARNING } from '../lib/copy';
import { VERDICT_STYLE, isInBand, resolveBand } from '../lib/verdict';
import { ProbabilityBar } from './ProbabilityBar';
import { BandIndicator } from './BandIndicator';
import { UncertaintyBanner } from './UncertaintyBanner';
import { WhatIfSlider } from './WhatIfSlider';

export interface ResultCardProps {
  verdict: Verdict;
  probability: number;
  confidence: ConfidenceLevel;
  signals: SignalOutput[];
  /** Everything else the card needs from the response. */
  result: DetectResponse;
  /** Focus target after a result arrives (§10). */
  headingRef?: RefObject<HTMLHeadingElement | null>;
}

/**
 * §1 + §8 — the verdict, the mandatory probability sentence, the confidence
 * badge, the band position, and every warning the API attached.
 *
 * `unable_to_assess` deliberately suppresses the probability block: reporting
 * a number the pipeline itself refused to stand behind would be the single
 * most misleading thing this UI could do.
 */
export function ResultCard({
  verdict,
  probability,
  confidence,
  signals,
  result,
  headingRef,
}: ResultCardProps) {
  const style = VERDICT_STYLE[verdict];
  const band = resolveBand(result.band);
  const inBand = isInBand(probability, band);
  const assessable = verdict !== 'unable_to_assess';
  const showUncertainty = verdict === 'uncertain' || result.uncertainty_score > 0.6 || !assessable;

  const applicableCount = signals.filter((s) => s.applicable !== false).length;

  return (
    <section aria-labelledby="verdict-heading" className="card overflow-hidden">
      <div className={`flex ${style.fill}`}>
        {/* 4px verdict stripe in the spec anchor hue. */}
        <div className={`w-1 shrink-0 ${style.stripe}`} aria-hidden="true" />

        <div className={`min-w-0 flex-1 border-l ${style.border} p-4`}>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2
              id="verdict-heading"
              ref={headingRef}
              tabIndex={-1}
              className={`flex items-center gap-2.5 text-[20px] font-semibold ${style.ink}`}
            >
              <span
                aria-hidden="true"
                className={`inline-flex h-7 w-7 items-center justify-center rounded-full border ${style.border} bg-surface font-mono text-[15px]`}
              >
                {style.glyph}
              </span>
              {style.label}
            </h2>

            <p className={`font-mono text-micro ${style.ink} opacity-90`}>
              <span className="sr-only">Request identifier </span>
              {result.request_id}
            </p>
          </div>

          {!assessable ? (
            <p className={`mt-2 text-note ${style.ink}`}>
              Capture quality was too low to run the detector. No manipulation probability is being
              reported for this image.
            </p>
          ) : (
            <p className={`mt-2 text-note ${style.ink} opacity-90`}>
              Capture type: {result.capture_type}. {applicableCount} signal
              {applicableCount === 1 ? ' was' : 's were'} evaluated for this capture.
            </p>
          )}
        </div>
      </div>

      <div className="space-y-4 p-4">
        {assessable ? (
          <>
            <ProbabilityBar value={probability} confidence={confidence} verdict={verdict} />
            <BandIndicator
              pFake={probability}
              band={band}
              isDefaultBand={!result.band}
            />
          </>
        ) : null}

        {showUncertainty ? (
          <UncertaintyBanner uncertainty_score={result.uncertainty_score} in_band={inBand} />
        ) : null}

        {result.warnings.length > 0 ? (
          <ul aria-label="Warnings for this result" className="space-y-2">
            {result.warnings.map((warning) => (
              <li
                key={warning}
                className="flex items-start gap-2 rounded-[8px] border border-ochre-500 bg-ochre-50 px-3 py-2 text-note text-ochre-700"
              >
                <span aria-hidden="true" className="mt-px font-mono">
                  ⚠
                </span>
                <span>{warning}</span>
              </li>
            ))}
          </ul>
        ) : null}

        {assessable ? (
          <WhatIfSlider pFake={probability} band={band} officialVerdict={verdict} />
        ) : null}

        {/* §7.2 — appended to every result, verbatim. */}
        <p className="limitation border-t border-line pt-3">{PER_RESULT_WARNING}</p>
      </div>
    </section>
  );
}
