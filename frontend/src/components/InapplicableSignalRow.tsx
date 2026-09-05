import type { SignalOutput } from '../types/detection';
import { SIGNAL_NOT_APPLICABLE } from '../lib/copy';
import { STAGGER_MS } from '../lib/motion';

interface InapplicableSignalRowProps {
  signal: SignalOutput;
  /** Position in the list, used to stagger the entrance. */
  index?: number;
}

/**
 * §3.3 — a signal that could not run. Rendered greyed out but never hidden:
 * a reviewer needs to know which measurements are missing before weighing the
 * ones that survived.
 */
export function InapplicableSignalRow({ signal, index = 0 }: InapplicableSignalRowProps) {
  const reason = signal.not_applicable_reason ?? qualityReason(signal);

  return (
    <li
      className="a-fade rounded-[10px] border border-dashed border-line bg-sunken p-3 opacity-90"
      style={{ ['--delay' as string]: `${index * STAGGER_MS}ms` }}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="tag-mono text-ink-3">{signal.code}</span>
        <span className="text-micro font-medium uppercase tracking-wide text-ink-3">
          Not applicable
        </span>
      </div>

      <p className="mt-2 text-note text-ink-3">{SIGNAL_NOT_APPLICABLE}</p>

      {reason ? <p className="mt-1 font-mono text-micro text-ink-3">Reason: {reason}</p> : null}

      {signal.limitation ? <p className="limitation mt-1.5">{signal.limitation}</p> : null}
    </li>
  );
}

/** Falls back to naming whichever quality indicator blocked the signal. */
function qualityReason(signal: SignalOutput): string | null {
  const quality = signal.quality;
  if (!quality) return null;
  const parts: string[] = [];
  for (const [key, value] of Object.entries(quality)) {
    if (typeof value === 'number') parts.push(`${key} ${Number(value.toFixed(2))}`);
    else if (typeof value === 'boolean') parts.push(`${key} ${value}`);
  }
  return parts.length ? parts.join(', ') : null;
}
