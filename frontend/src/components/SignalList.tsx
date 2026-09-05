import type { SignalOutput } from '../types/detection';
import { isApplicable } from '../lib/verdict';
import { SignalRow } from './SignalRow';
import { InapplicableSignalRow } from './InapplicableSignalRow';
import { SignalRadar } from './SignalRadar';

export interface SignalListProps {
  signals: SignalOutput[];
}

/**
 * §3 — applicable signals first, sorted by strength so the loudest evidence is
 * read first; skipped signals follow, greyed out but present.
 */
export function SignalList({ signals }: SignalListProps) {
  const applicable = signals
    .filter((signal) => isApplicable(signal.applicable))
    .slice()
    .sort((a, b) => (b.strength ?? 0) - (a.strength ?? 0));

  const inapplicable = signals.filter((signal) => !isApplicable(signal.applicable));

  return (
    <section aria-labelledby="signals-heading" className="card p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="signals-heading" className="text-[15px] font-semibold text-ink">
          Signal explanations
        </h2>
        <p className="text-micro text-ink-3">
          {applicable.length} applicable
          {inapplicable.length > 0 ? ` · ${inapplicable.length} skipped` : ''}
        </p>
      </div>

      <p className="limitation mt-1">
        Each signal is one measurement, not a decision. Strength is a magnitude in 0 to 1, not a
        probability that the image is manipulated.
      </p>

      {applicable.length === 0 && inapplicable.length === 0 ? (
        <p className="mt-3 text-note text-ink-2">No signals were reported for this capture.</p>
      ) : null}

      {/* §11 Signal Radar — the balance of evidence at a glance, above the
          detail rows that back it up. Renders only when there are enough
          axes for a polygon to mean anything. */}
      {applicable.length >= 3 ? (
        <div className="mt-4 rounded-[10px] border border-line bg-sunken px-3 py-4">
          <SignalRadar signals={applicable} />
        </div>
      ) : null}

      {applicable.length > 0 ? (
        <ul className="mt-3 space-y-2.5">
          {applicable.map((signal, i) => (
            <SignalRow key={signal.code} signal={signal} index={i} />
          ))}
        </ul>
      ) : null}

      {inapplicable.length > 0 ? (
        <>
          <h3 className="mt-4 text-micro font-semibold uppercase tracking-wide text-ink-3">
            Skipped signals
          </h3>
          <ul className="mt-2 space-y-2.5">
            {inapplicable.map((signal, i) => (
              <InapplicableSignalRow key={signal.code} signal={signal} index={i} />
            ))}
          </ul>
        </>
      ) : null}
    </section>
  );
}
