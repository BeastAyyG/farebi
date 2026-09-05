import type { Quality, Verdict } from '../types/detection';
import { QUALITY_SUMMARY } from '../lib/copy';
import { deriveQualityWarnings, qualitySeverity, type QualitySeverity } from '../lib/quality';

interface QualityWarningsProps {
  /** The `quality` dict straight from the response. */
  quality: Quality | undefined;
  /** Lets `unable_to_assess` force the critical state. */
  verdict?: Verdict;
}

const SEVERITY_STYLE: Record<
  QualitySeverity,
  { bar: string; chipBg: string; chipInk: string; glyph: string; label: string }
> = {
  pass: {
    bar: 'bg-sage-500',
    chipBg: 'bg-sage-50 border-sage-500',
    chipInk: 'text-sage-700',
    glyph: '✓',
    label: QUALITY_SUMMARY.pass,
  },
  warn: {
    bar: 'bg-ochre-500',
    chipBg: 'bg-ochre-50 border-ochre-500',
    chipInk: 'text-ochre-700',
    glyph: '!',
    label: QUALITY_SUMMARY.warn,
  },
  fail: {
    bar: 'bg-terracotta-500',
    chipBg: 'bg-terracotta-50 border-terracotta-500',
    chipInk: 'text-terracotta-700',
    glyph: '✕',
    label: QUALITY_SUMMARY.fail,
  },
};

/**
 * §5 — the quality summary bar plus every individual indicator warning.
 * Severity is carried by the bar colour, a glyph, and the written label, so
 * the state survives greyscale printing and colour-blind viewing.
 */
export function QualityWarnings({ quality, verdict }: QualityWarningsProps) {
  const warnings = deriveQualityWarnings(quality);
  const severity = qualitySeverity(warnings, verdict);
  const style = SEVERITY_STYLE[severity];

  return (
    <section aria-labelledby="quality-heading" className="card overflow-hidden">
      {/* Summary bar (§5.2). */}
      <div className={`h-1.5 w-full ${style.bar}`} aria-hidden="true" />

      <div className="p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 id="quality-heading" className="text-[15px] font-semibold text-ink">
            Capture quality
          </h2>
          <span
            className={`inline-flex items-center gap-1.5 rounded-[6px] border px-2 py-0.5 text-micro font-medium ${style.chipBg} ${style.chipInk}`}
          >
            <span aria-hidden="true" className="font-mono">
              {style.glyph}
            </span>
            {style.label}
          </span>
        </div>

        {warnings.length === 0 ? (
          <p className="mt-2 text-note text-ink-2">
            All capture quality checks passed for this image.
          </p>
        ) : (
          <ul className="mt-3 space-y-2">
            {warnings.map((warning) => {
              const rowStyle = SEVERITY_STYLE[warning.severity];
              return (
                <li
                  key={warning.id}
                  className={`flex items-start gap-2 rounded-[8px] border px-2.5 py-2 ${rowStyle.chipBg}`}
                >
                  <span aria-hidden="true" className={`mt-px ${rowStyle.chipInk}`}>
                    ⚠
                  </span>
                  <span className="min-w-0">
                    <span className={`block text-note ${rowStyle.chipInk}`}>
                      <span className="sr-only">
                        {warning.severity === 'fail' ? 'Critical: ' : 'Warning: '}
                      </span>
                      {warning.text}
                    </span>
                    {warning.detail ? (
                      <span className="mt-0.5 block font-mono text-micro text-ink-3">
                        {warning.detail}
                      </span>
                    ) : null}
                  </span>
                </li>
              );
            })}
          </ul>
        )}

        <p className="limitation mt-3">
          Quality indicators describe the capture, not the person. Poor quality reduces how much
          weight any signal deserves.
        </p>
      </div>
    </section>
  );
}
