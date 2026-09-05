import type { ModelInfo } from '../types/detection';
import { Tooltip } from './ui/Tooltip';
import { InfoIcon } from './ui/Icon';

export interface VersionInfoProps {
  model: string;
  threshold?: string;
  calibration?: string;
  info?: ModelInfo;
}

const UNSET = 'not reported';

/**
 * §6 — the three artefact versions that make a result reproducible, plus the
 * model provenance tooltip. If the API omits a version we say so rather than
 * inventing one; an unversioned threshold is a governance problem, not a
 * cosmetic gap.
 */
export function VersionInfo({ model, threshold, calibration, info }: VersionInfoProps) {
  return (
    <section aria-labelledby="version-heading" className="card p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="version-heading" className="text-[15px] font-semibold text-ink">
          Model &amp; artefact versions
        </h2>

        <Tooltip
          triggerLabel="Show model details"
          align="right"
          content={
            <span className="block space-y-2">
              <span className="block">
                <span className="block text-micro font-semibold uppercase tracking-wide text-ink-3">
                  Architecture
                </span>
                <span className="block text-note text-ink-2">{info?.architecture ?? UNSET}</span>
              </span>
              <span className="block">
                <span className="block text-micro font-semibold uppercase tracking-wide text-ink-3">
                  Training data
                </span>
                <span className="block text-note text-ink-2">{info?.training_data ?? UNSET}</span>
              </span>
              <span className="block">
                <span className="block text-micro font-semibold uppercase tracking-wide text-ink-3">
                  Last updated
                </span>
                <span className="block font-mono text-note text-ink-2">
                  {info?.last_updated ?? UNSET}
                </span>
              </span>
              <span className="block">
                <span className="block text-micro font-semibold uppercase tracking-wide text-ink-3">
                  SHA256 of weights
                </span>
                <span className="block break-all font-mono text-micro text-ink-2">
                  {info?.weights_sha256 ?? UNSET}
                </span>
              </span>
            </span>
          }
        >
          <span className="flex items-center gap-1.5 text-note text-blue-600">
            <InfoIcon />
            Model details
          </span>
        </Tooltip>
      </div>

      <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5">
        <Row label="Model" value={model} />
        <Row label="Threshold" value={threshold} />
        <Row label="Calibration" value={calibration} />
      </dl>

      <p className="limitation mt-3">
        Quote all three versions when escalating a result. A probability is only meaningful
        alongside the calibration and thresholds that produced it.
      </p>
    </section>
  );
}

function Row({ label, value }: { label: string; value?: string }) {
  const missing = !value;
  return (
    <>
      <dt className="text-note text-ink-3">{label}</dt>
      <dd
        className={`font-mono text-note ${missing ? 'italic text-ink-3' : 'text-ink-2'}`}
        title={value ?? UNSET}
      >
        {value ?? UNSET}
      </dd>
    </>
  );
}
