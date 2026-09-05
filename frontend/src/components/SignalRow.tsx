import { useState } from 'react';
import type { SignalOutput } from '../types/detection';
import { formatProbability } from '../lib/copy';
import { DIRECTION_STYLE, clamp01 } from '../lib/verdict';
import { reasonCodeDoc, signalDocsUrl } from '../lib/signalDocs';

interface SignalRowProps {
  signal: SignalOutput;
}

/**
 * §3.2 — one applicable signal: code tag, direction, strength bar, message and
 * the mandatory limitation. Clicking the code opens the Reason Code Explorer
 * inline (§11) rather than navigating away mid-review.
 */
export function SignalRow({ signal }: SignalRowProps) {
  const [expanded, setExpanded] = useState(false);
  const direction = DIRECTION_STYLE[signal.direction] ?? DIRECTION_STYLE.neutral;
  const strength = clamp01(signal.strength);
  const doc = reasonCodeDoc(signal.code);
  const panelId = `signal-${signal.code}-detail`;

  return (
    <li className="rounded-[10px] border border-line bg-surface p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <button
          type="button"
          onClick={() => setExpanded((prev) => !prev)}
          aria-expanded={expanded}
          aria-controls={panelId}
          className="anim tag-mono hover:border-line-strong hover:bg-blue-50 hover:text-blue-700"
          title={`${doc.title} — open forensic explanation`}
        >
          {signal.code}
          <span aria-hidden="true" className="ml-1.5 text-ink-3">
            {expanded ? '−' : '+'}
          </span>
        </button>

        <span className={`flex items-center gap-1.5 text-note font-medium ${direction.ink}`}>
          <span aria-hidden="true" className="font-mono text-[15px] leading-none">
            {direction.arrow}
          </span>
          {direction.label}
        </span>
      </div>

      <div className="mt-2.5 flex items-center gap-3">
        <div
          role="img"
          aria-label={`Strength ${formatProbability(strength)} out of 1.00, ${direction.label}`}
          className="h-2 flex-1 overflow-hidden rounded-full bg-sunken"
        >
          <div
            className={`anim h-full rounded-full transition-[width] ${direction.fill}`}
            style={{ width: `${strength * 100}%` }}
          />
        </div>
        <span className="w-10 shrink-0 text-right font-mono text-micro text-ink-2">
          {formatProbability(strength)}
        </span>
      </div>

      <p className="mt-2 text-note text-ink-2" title={signal.message}>
        {signal.message}
      </p>
      <p className="limitation mt-1.5">{signal.limitation}</p>

      {expanded ? (
        <div
          id={panelId}
          className="mt-3 rounded-[8px] border border-line bg-sunken p-3"
        >
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h3 className="text-[14px] font-semibold text-ink">{doc.title}</h3>
            <span className="text-micro text-ink-3">{doc.family}</span>
          </div>

          <p className="mt-2 text-note text-ink-2">{signal.message}</p>

          <h4 className="mt-3 text-micro font-semibold uppercase tracking-wide text-ink-3">
            What could cause a false positive
          </h4>
          <ul className="mt-1.5 space-y-1">
            {doc.falsePositives.map((cause) => (
              <li key={cause} className="flex gap-2 text-note text-ink-2">
                <span aria-hidden="true" className="text-ink-3">
                  •
                </span>
                <span>{cause}</span>
              </li>
            ))}
          </ul>

          <p className="limitation mt-3">{signal.limitation}</p>

          <a
            href={signalDocsUrl(signal.code)}
            target="_blank"
            rel="noreferrer noopener"
            className="anim mt-3 inline-flex items-center gap-1 text-note font-medium text-blue-600 underline underline-offset-2 hover:text-blue-700"
          >
            Open signal documentation
            <span aria-hidden="true">↗</span>
            <span className="sr-only">(opens in a new tab)</span>
          </a>
        </div>
      ) : (
        <div id={panelId} hidden />
      )}
    </li>
  );
}
